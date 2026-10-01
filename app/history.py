"""История диктовок: хранение и чтение.

Одна запись — одна строка JSON в `history.jsonl` рядом с настройками. Формат
нарочно простой: файл можно прочитать глазами и не жалко потерять.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

from .config import home_dir

MAX_ENTRIES = 5000


@dataclass
class Entry:
    ts: float
    text: str
    seconds: float = 0.0
    engine: str = "parakeet"

    @property
    def words(self) -> int:
        return len([w for w in self.text.split() if any(c.isalnum() for c in w)])

    @property
    def when(self) -> float:
        return self.ts

    def as_dict(self) -> dict:
        return asdict(self)


class History:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.path.join(home_dir(), "history.jsonl")
        self._entries: list[Entry] = []
        self.load()

    # --- чтение и запись --------------------------------------------------
    def load(self) -> None:
        self._entries = []
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # битая строка не должна ломать историю
                    text = str(raw.get("text", "")).strip()
                    if not text:
                        continue
                    self._entries.append(
                        Entry(
                            ts=float(raw.get("ts", 0.0)),
                            text=text,
                            seconds=float(raw.get("seconds", 0.0)),
                            engine=str(raw.get("engine", "parakeet")),
                        )
                    )
        except OSError:
            self._entries = []

    def add(self, text: str, seconds: float = 0.0, engine: str = "parakeet") -> Entry:
        entry = Entry(ts=time.time(), text=text, seconds=seconds, engine=engine)
        self._entries.append(entry)
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]
            self.rewrite()
        return entry

    def rewrite(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                for entry in self._entries:
                    fh.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def clear(self) -> None:
        self._entries = []
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError:
            pass

    def remove(self, entry: Entry) -> None:
        self._entries = [e for e in self._entries if e is not entry]
        self.rewrite()

    # --- выборки ----------------------------------------------------------
    def contains(self, entry: Entry) -> bool:
        """Есть ли эта самая запись в истории (сравнение по объекту)."""
        return any(existing is entry for existing in self._entries)

    def entries(self) -> list[Entry]:
        """Новые сверху."""
        return list(reversed(self._entries))

    @property
    def last(self) -> Entry | None:
        return self._entries[-1] if self._entries else None

    def total_words(self) -> int:
        return sum(e.words for e in self._entries)
