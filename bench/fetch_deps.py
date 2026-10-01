"""Resolve and download wheels from PyPI without pip.

pip cannot run in this sandbox: it writes thousands of `*.whl.metadata` files into
its own temp directory and every such write is denied. Plain file writes from
Python work fine, so we resolve dependencies ourselves through the PyPI JSON API
and download the wheels straight into ./wheels, to be unpacked by unpack_wheels.py.

Usage:  python fetch_deps.py faster-whisper sherpa-onnx
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHEELS = os.path.join(ROOT, "wheels")
LIBS = os.path.join(ROOT, "pylibs")
os.makedirs(WHEELS, exist_ok=True)
os.makedirs(LIBS, exist_ok=True)
if LIBS not in sys.path:
    sys.path.insert(0, LIBS)

UA = {"User-Agent": "pantela-bench/1.0 (personal use)"}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def download(url: str, dest: str) -> None:
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=900) as resp, open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh, 1 << 20)
    os.replace(tmp, dest)


def extract(wheel: str, target: str) -> None:
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            parts = name.split("/")
            if len(parts) > 2 and parts[0].endswith(".data") and parts[1] in ("purelib", "platlib"):
                rel = "/".join(parts[2:])
            else:
                rel = name
            if not rel or rel.endswith("/"):
                continue
            dest = os.path.join(target, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


def bootstrap_packaging() -> None:
    try:
        import packaging  # noqa: F401
        return
    except ImportError:
        pass
    print("bootstrapping 'packaging' ...")
    data = get_json("https://pypi.org/pypi/packaging/json")
    cand = [u for u in data["urls"] if u["filename"].endswith("py3-none-any.whl")]
    if not cand:
        raise SystemExit("cannot bootstrap packaging")
    dest = os.path.join(WHEELS, cand[0]["filename"])
    if not os.path.exists(dest):
        download(cand[0]["url"], dest)
    extract(dest, LIBS)


bootstrap_packaging()

from packaging.markers import Marker  # noqa: E402
from packaging.requirements import Requirement  # noqa: E402
from packaging.specifiers import SpecifierSet  # noqa: E402
from packaging.tags import Tag, sys_tags  # noqa: E402
from packaging.utils import canonicalize_name  # noqa: E402
from packaging.version import InvalidVersion, Version  # noqa: E402

TAG_RANK = {str(tag): i for i, tag in enumerate(sys_tags())}


def wheel_tags(filename: str) -> list[Tag]:
    """Wheel names are name-version(-build)-python-abi-platform; the last three
    dash-separated fields are the tags, each possibly dot-compressed."""
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return []
    py, abi, plat = parts[-3], parts[-2], parts[-1]
    return [
        Tag(p, a, pl)
        for p in py.split(".")
        for a in abi.split(".")
        for pl in plat.split(".")
    ]


def rank(filename: str) -> int:
    ranks = [TAG_RANK[str(t)] for t in wheel_tags(filename) if str(t) in TAG_RANK]
    return min(ranks) if ranks else -1


def pick_file(files: list[dict], spec: SpecifierSet) -> dict | None:
    best, best_rank = None, -1
    for f in files:
        if not f["filename"].endswith(".whl"):
            continue
        if f.get("yanked"):
            continue
        r = rank(f["filename"])
        if r < 0:
            continue
        if best is None or r < best_rank:
            best, best_rank = f, r
    return best


def resolve(roots: list[str]) -> list[dict]:
    resolved: dict[str, dict] = {}
    queue: list[tuple[Requirement, str]] = [(Requirement(r), "root") for r in roots]
    while queue:
        req, why = queue.pop(0)
        if req.marker is not None and not req.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(req.name)
        if name in resolved:
            continue
        info = get_json(f"https://pypi.org/pypi/{req.name}/json")
        versions = []
        for raw in info["releases"]:
            try:
                versions.append(Version(raw))
            except InvalidVersion:
                continue
        versions.sort(reverse=True)
        chosen = None
        for v in versions:
            if req.specifier and not req.specifier.contains(v, prereleases=False):
                continue
            vinfo = get_json(f"https://pypi.org/pypi/{req.name}/{v}/json")
            requires_python = vinfo["info"].get("requires_python") or ""
            files = info["releases"][str(v)]
            f = pick_file(files, req.specifier)
            if f is None:
                continue
            chosen = (v, f, vinfo["info"].get("requires_dist") or [])
            break
        if chosen is None:
            print(f"  !! no compatible wheel for {req} (from {why})")
            resolved[name] = {"error": str(req)}
            continue
        v, f, requires = chosen
        resolved[name] = {
            "name": req.name,
            "version": str(v),
            "filename": f["filename"],
            "url": f["url"],
            "size": f["size"],
            "requires": requires,
            "why": why,
        }
        print(f"  {req.name}=={v}  <- {why}")
        for r in requires:
            queue.append((Requirement(r), f"{req.name}=={v}"))

    return [v for v in resolved.values() if "error" not in v]


def main() -> None:
    roots = sys.argv[1:] or ["faster-whisper", "sherpa-onnx"]
    print("resolving:", ", ".join(roots))
    packages = resolve(roots)

    total = sum(p["size"] for p in packages)
    print(f"\n{len(packages)} wheels, {total / 1e6:.1f} MB")
    for p in packages:
        dest = os.path.join(WHEELS, p["filename"])
        if os.path.exists(dest) and os.path.getsize(dest) == p["size"]:
            print(f"  = {p['filename']}")
            continue
        print(f"  + {p['filename']} ({p['size'] / 1e6:.1f} MB)")
        download(p["url"], dest)
    print("\ndone")


if __name__ == "__main__":
    main()
