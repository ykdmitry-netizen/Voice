"""Build REPORT.md from the benchmark JSON files."""

import json
import os

import numpy as np

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "bench")

MODEL_LABELS = {
    "tiny": "Whisper tiny (int8)",
    "base": "Whisper base (int8)",
    "small": "Whisper small (int8)",
    "medium": "Whisper medium (int8)",
    "large-v3-turbo": "Whisper large-v3-turbo (int8)",
    "gigaam": "GigaAM v2 CTC ru (int8, ONNX)",
    "parakeet": "Parakeet TDT 0.6B v3 (int8, ONNX)",
}

LANG_LABELS = {"ru": "RU", "en": "EN", "de": "DE"}


def load(name: str) -> list[dict]:
    path = os.path.join(BENCH, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in json.load(fh) if "error" not in r]


def fit_latency(rows: list[dict]) -> tuple[float, float] | None:
    pts = [(r["audio_s"], r["time_s"]) for r in rows if r["audio_s"] > 0]
    if len(pts) < 2:
        return None
    x = np.array([p[0] for p in pts], dtype=float)
    y = np.array([p[1] for p in pts], dtype=float)
    b, a = np.polyfit(x, y, 1)
    return float(a), float(b)


def main() -> None:
    rows = load("whisper_results.json") + load("whisper_heavy.json") + load("sherpa_results.json")
    if not rows:
        raise SystemExit("no benchmark results found")

    order = ["tiny", "base", "small", "medium", "large-v3-turbo", "gigaam", "parakeet"]
    models = [m for m in order if any(r["model"] == m for r in rows)]

    out: list[str] = []
    out.append("# Бенчмарк локального распознавания речи\n")
    out.append("Машина: **Intel Core i5-4460 @ 3.20 ГГц, 4 ядра, 4 потока, AVX2, 8 ГБ RAM; GPU для инференса нет**  ")
    out.append("Видеокарта: NVIDIA GeForce GT 730 (Kepler, 2014, драйвер 388.13) — CUDA-рантайм не "
               "установлен, архитектура sm_35 не поддерживается актуальными сборками CUDA 12, "
               "для инференса непригодна. Вывод: считаем только на CPU.\n")
    out.append("ОС: Windows, ветка сборки 26100  ")
    out.append("Движки: faster-whisper 1.2.1 / CTranslate2 4.8.2 (int8, 4 потока, beam_size=1), "
               "sherpa-onnx 1.13.8 (int8, 4 потока, onnxruntime CPU)\n")
    out.append("Аудио: реальная человеческая речь — русская 11.3 с и 71.3 с, английская 3.9 с и 11.0 с, "
               "немецкая 2.8 с. Загруженные модели замерялись после прогрева, время загрузки модели "
               "в замер не входит.\n")

    out.append("## Скорость\n")
    out.append("| Модель | Язык | Аудио, с | Время, с | RTF |")
    out.append("|---|---|---|---|---|")
    for m in models:
        for r in sorted((r for r in rows if r["model"] == m), key=lambda r: (r["lang"], r["audio_s"])):
            out.append(
                f"| {MODEL_LABELS.get(m, m)} | {LANG_LABELS.get(r['lang'], r['lang'])} | "
                f"{r['audio_s']:.2f} | {r['time_s']:.2f} | **{r['rtf']:.2f}x** |"
            )
    out.append("")

    out.append("## Ориентировочная задержка ответа\n")
    out.append("| Модель | Фраза 3 с | Фраза 5 с | Фраза 10 с | Речь 1 мин |")
    out.append("|---|---|---|---|---|")
    for m in models:
        fit = fit_latency([r for r in rows if r["model"] == m])
        if not fit:
            continue
        a, b = fit
        out.append(
            f"| {MODEL_LABELS.get(m, m)} | {a + 3 * b:.1f} с | {a + 5 * b:.1f} с | "
            f"{a + 10 * b:.1f} с | {a + 60 * b:.0f} с |"
        )
    out.append("\nЛинейная аппроксимация `a + b*t` (a — постоянные накладные расходы, "
               "b — стоимость секунды речи) по измеренным точкам. Для Whisper задержка почти "
               "не зависит от длины фразы: аудио дополняется до 30-секундного окна, поэтому даже "
               "короткая фраза стоит как одно окно. Для ONNX-моделей зависимость заметно "
               "нелинейна (стоимость растёт с числом распознанных токенов), так что колонку "
               "«Фраза 3 с» для них следует читать как нижнюю оценку — ориентируйтесь на "
               "измеренные значения в таблице скорости.\n")

    out.append("## Вывод\n")
    out.append(
        "**Parakeet TDT 0.6B v3 (int8, ONNX через sherpa-onnx) — рабочая модель для этой машины.** "
        "Она одновременно быстрее и точнее всех вариантов Whisper, которые влезают в 4 ядра без GPU: "
        "5.4x реального времени на русском (2.1 с на 11.3 с речи) и 7.5x на английском, "
        "с пунктуацией и заглавными буквами, ~670 МБ на диске, ~5 с на загрузку.\n"
    )
    out.append(
        "Whisper large-v3-turbo — модель, на которую рассчитано оригинальное macOS-приложение — "
        "на этом процессоре даёт **0.5x**, то есть 21 секунду на 11 секунд речи. Использовать её "
        "нельзя. Whisper small (1.8x, 6.3 с на фразу) — на грани, medium (0.7x) — нет.\n"
    )
    out.append(
        "GigaAM v2 CTC (русская модель) даёт сопоставимое качество, но медленнее Parakeet "
        "(3.4x против 5.4x на русском) и выдаёт текст без пунктуации и заглавных букв; "
        "годится как второй движок для русского, но не как основной.\n"
    )
    out.append(
        "Если качество русского важнее скорости — Whisper small даёт близкий текст за 6.3 с "
        "на 11 с речи; для диктовки короткими фразами это ощутимая пауза после каждой фразы.\n"
    )

    out.append("## Качество: что реально распознано (русский)\n")
    for m in models:
        sample = next(
            (r for r in rows if r["model"] == m and r["file"].startswith("ru_real")), None
        )
        if sample:
            out.append(f"**{MODEL_LABELS.get(m, m)}** — {sample['time_s']:.2f} с на 11.3 с речи:")
            out.append(f"> {sample['text']}\n")

    out.append("## Качество: что реально распознано (английский)\n")
    for m in models:
        sample = next((r for r in rows if r["model"] == m and r["file"] == "jfk.wav"), None)
        if sample:
            out.append(f"**{MODEL_LABELS.get(m, m)}** — {sample['time_s']:.2f} с на 11.0 с речи:")
            out.append(f"> {sample['text']}\n")

    path = os.path.join(BENCH, "REPORT.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("saved:", path)


if __name__ == "__main__":
    main()
