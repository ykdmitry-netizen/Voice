"""Запуск без консольного окна (двойной клик или автозагрузка)."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (os.path.join(ROOT, "pylibs"), ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

if __name__ == "__main__":
    from app.main import main

    raise SystemExit(main())
