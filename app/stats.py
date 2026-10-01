"""Статистика по истории диктовок: слова, минуты, категории, активность."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .history import Entry

#: скорость набора на клавиатуре, слов в минуту (для оценки сэкономленного времени)
TYPING_WPM = 40

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Задачи": (
        "нужно", "надо", "сделать", "сделай", "задача", "задачи", "проверь",
        "проверить", "добавь", "добавить", "исправь", "напомни", "позвони",
        "отправь", "закажи", "купи", "встреча", "дедлайн",
    ),
    "Документы": (
        "документ", "документы", "отчёт", "отчет", "договор", "письмо",
        "заявление", "сертификат", "счёт", "счет", "акт", "запрос", "смета",
        "инструкция", "проект", "правки", "файл",
    ),
    "Заметки": (
        "заметка", "заметки", "идея", "идеи", "запомни", "план", "мысль",
        "черновик", "список", "набросок",
    ),
}

CATEGORY_COLORS = {
    "Задачи": "#e5aa3d",
    "Документы": "#7cc47f",
    "Заметки": "#d9b45b",
    "Другое": "#6d6d76",
}

STOPWORDS = {
    "это", "что", "чтобы", "как", "так", "вот", "все", "всё", "ещё", "еще",
    "уже", "или", "если", "для", "при", "над", "под", "про", "без", "через",
    "тоже", "также", "только", "можно", "надо", "нужно", "быть", "есть",
    "был", "была", "было", "будут", "меня", "тебя", "него", "неё", "нее",
    "них", "нам", "вам", "там", "тут", "здесь", "когда", "потом", "сейчас",
    "который", "которая", "которые", "этот", "эта", "эти", "того", "этого",
    "the", "and", "you", "that", "with", "for", "this", "have", "not",
}


@dataclass
class Summary:
    words: int = 0
    seconds: float = 0.0
    days: int = 0
    saved_minutes: float = 0.0
    week_words: int = 0
    categories: list[tuple[str, int, float]] = field(default_factory=list)
    frequent: list[tuple[str, int]] = field(default_factory=list)
    activity: list[tuple[dt.date, int]] = field(default_factory=list)
    entries: int = 0


def classify(text: str) -> str:
    """Простое отнесение записи к категории по ключевым словам."""
    low = text.lower()
    best, best_score = "Другое", 0
    for name, keywords in CATEGORY_KEYWORDS.items():
        score = sum(low.count(word) for word in keywords)
        if score > best_score:
            best, best_score = name, score
    return best


def word_counts(entries: list[Entry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        for raw in entry.text.split():
            word = "".join(c for c in raw.lower() if c.isalnum() or c in "-ё")
            if len(word) < 4 or word in STOPWORDS or word.isdigit():
                continue
            counts[word] = counts.get(word, 0) + 1
    return counts


def summarize(entries: list[Entry], days: int = 28,
              now: dt.datetime | None = None) -> Summary:
    now = now or dt.datetime.now()
    result = Summary(entries=len(entries))
    if not entries:
        result.activity = [(now.date() - dt.timedelta(days=days - 1 - i), 0)
                           for i in range(days)]
        return result

    result.words = sum(e.words for e in entries)
    result.seconds = sum(e.seconds for e in entries)
    dates = {dt.datetime.fromtimestamp(e.ts).date() for e in entries}
    result.days = len(dates)

    typing_minutes = result.words / TYPING_WPM if TYPING_WPM else 0.0
    result.saved_minutes = max(0.0, typing_minutes - result.seconds / 60.0)

    week_start = (now - dt.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result.week_words = sum(
        e.words for e in entries if dt.datetime.fromtimestamp(e.ts) >= week_start
    )

    counters: dict[str, int] = {}
    for entry in entries:
        name = classify(entry.text)
        counters[name] = counters.get(name, 0) + entry.words
    total = sum(counters.values()) or 1
    result.categories = sorted(
        ((name, count, 100.0 * count / total) for name, count in counters.items()),
        key=lambda item: item[1],
        reverse=True,
    )

    counts = word_counts(entries)
    result.frequent = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:14]

    by_day: dict[dt.date, int] = {}
    for entry in entries:
        day = dt.datetime.fromtimestamp(entry.ts).date()
        by_day[day] = by_day.get(day, 0) + entry.words
    result.activity = [
        (now.date() - dt.timedelta(days=days - 1 - i),
         by_day.get(now.date() - dt.timedelta(days=days - 1 - i), 0))
        for i in range(days)
    ]
    return result


def human_minutes(minutes: float) -> str:
    if minutes < 60:
        return f"{minutes:.0f} мин"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} ч"
    return f"{hours / 24:.1f} сут"
