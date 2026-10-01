"""Проверка глифов Segoe MDL2 Assets: какие коды рисуются, а какие пустые."""

import os
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pylibs"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import ImageGrab  # noqa: E402

SHOTS = os.path.join(ROOT, "bench", "shots")

CANDIDATES = [
    ("E80F", "home"), ("E713", "settings"), ("E115", "settings2"), ("E897", "help"),
    ("E9CE", "unknown"), ("E946", "info"), ("E720", "mic"), ("E767", "volume"),
    ("E8C8", "copy"), ("E74D", "delete"), ("E72C", "refresh"), ("E823", "clock"),
    ("E787", "calendar"), ("E945", "bolt"), ("E8FD", "list"), ("E70B", "note"),
    ("E8A5", "doc"), ("E9D5", "chart?"), ("E9D9", "chart2?"), ("E9D2", "chart3?"),
    ("E8D2", "words?"), ("E721", "search"), ("E7E8", "power"), ("E76C", "chevron"),
    ("E73E", "check"), ("E8B7", "folder"), ("E765", "keyboard"), ("E768", "play"),
    ("E71E", "zoom"), ("E8E9", "text?"), ("E8BD", "target"), ("E9A9", "spark?"),
    ("E734", "star"), ("E735", "star2"), ("E7C3", "page"), ("E896", "download"),
    ("E898", "upload"), ("E8BB", "close"), ("E70F", "edit"), ("E71C", "filter"),
]


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    root = tk.Tk()
    root.title("Глифы")
    root.configure(bg="#101014")
    icon_font = tkfont.Font(family="Segoe MDL2 Assets", size=18)
    small = tkfont.Font(family="Segoe UI", size=8)

    cols = 8
    for index, (code, name) in enumerate(CANDIDATES):
        row, col = divmod(index, cols)
        cell = tk.Frame(root, bg="#1a1a1f", padx=6, pady=6)
        cell.grid(row=row, column=col, padx=3, pady=3)
        tk.Label(cell, text=chr(int(code, 16)), font=icon_font,
                 bg="#1a1a1f", fg="#e5aa3d").pack()
        tk.Label(cell, text=f"{code} {name}", font=small,
                 bg="#1a1a1f", fg="#9b9ba4").pack()

    root.update()
    for _ in range(25):
        root.update()
        time.sleep(0.03)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    image = ImageGrab.grab((x - 4, y - 30, x + root.winfo_width() + 8,
                            y + root.winfo_height() + 8))
    image.save(os.path.join(SHOTS, "icons_preview.png"))
    print("снимок:", image.size)
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
