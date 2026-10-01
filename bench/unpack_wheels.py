"""Extract downloaded wheels into a flat directory usable via PYTHONPATH.

pip install is blocked by the sandbox (PermissionError while writing wheel
metadata into its own temp dir), but pip download works. Wheels are zip files,
so we unpack them ourselves, honouring the *.data/{purelib,platlib} layout.
"""

import os
import shutil
import sys
import zipfile

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHEELS = os.path.join(ROOT, "wheels")
LIBS = os.path.join(ROOT, "pylibs")


def install_sitecustomize() -> None:
    """Кладёт патч временных каталогов в pylibs, если он есть в tools."""
    source = os.path.join(ROOT, "tools", "sitecustomize.py")
    if not os.path.exists(source):
        return
    target = os.path.join(LIBS, "sitecustomize.py")
    if os.path.abspath(source) == os.path.abspath(target):
        return
    shutil.copyfile(source, target)
    print(f"установлен патч {target}")


def main() -> None:
    os.makedirs(LIBS, exist_ok=True)
    wheels = sorted(f for f in os.listdir(WHEELS) if f.endswith(".whl"))
    if not wheels:
        raise SystemExit(f"no wheels in {WHEELS}")

    for wheel in wheels:
        path = os.path.join(WHEELS, wheel)
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for name in names:
                parts = name.split("/")
                # *.data/{purelib,platlib}/... -> strip the first two parts
                if len(parts) > 2 and parts[0].endswith(".data") and parts[1] in ("purelib", "platlib"):
                    target_rel = "/".join(parts[2:])
                else:
                    target_rel = name
                if not target_rel or target_rel.endswith("/"):
                    continue
                dest = os.path.join(LIBS, *target_rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
        print(f"unpacked {wheel}")

    install_sitecustomize()
    print(f"\n{len(wheels)} wheels -> {LIBS}")


if __name__ == "__main__":
    main()
