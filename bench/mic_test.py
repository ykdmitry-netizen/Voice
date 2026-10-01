"""Проверка реального захвата с микрофона (без распознавания)."""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pylibs"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("PANTELA_HOME", os.path.join(ROOT, "testhome"))

from app.audio import Recorder, trim_silence  # noqa: E402


def main() -> int:
    recorder = Recorder()
    devices = Recorder.list_input_devices()
    print("устройства ввода:", len(devices))
    if not devices:
        print("ИТОГ: пропущено — в системе нет ни одного устройства ввода")
        return 0
    try:
        recorder.start("", 16000)
    except Exception as exc:  # noqa: BLE001
        print(f"ИТОГ: пропущено — микрофон не открылся: {exc}")
        return 0
    print("запись 2 секунды…")
    time.sleep(2.0)
    levels = []
    for _ in range(10):
        levels.append(round(recorder.level, 3))
        time.sleep(0.05)
    samples = recorder.stop()
    duration = len(samples) / 16000
    peak = float(abs(samples).max()) if samples.size else 0.0
    rms = float((samples ** 2).mean() ** 0.5) if samples.size else 0.0
    trimmed = trim_silence(samples)
    print(f"получено {duration:.2f} с, отсчётов {samples.size}")
    print(f"пик {peak:.4f}, RMS {rms:.5f}, после обрезки тишины {len(trimmed) / 16000:.2f} с")
    print("уровни в процессе:", levels)
    ok = duration > 1.5 and samples.size > 0
    print("ИТОГ:", "захват с микрофона работает" if ok else "ПРОБЛЕМА: данных нет")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
