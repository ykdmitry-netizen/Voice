import sounddevice as sd

print("PortAudio:", sd.get_portaudio_version()[1])
for i, d in enumerate(sd.query_devices()):
    kind = []
    if d["max_input_channels"] > 0:
        kind.append("IN")
    if d["max_output_channels"] > 0:
        kind.append("OUT")
    print(f"  [{i}] {'/'.join(kind):8s} {d['name']}  ({d['default_samplerate']:.0f} Hz)")
try:
    print("default input:", sd.query_devices(kind="input")["name"])
except Exception as exc:  # noqa: BLE001
    print("default input: FAILED", exc)
print("hostapis:", [h["name"] for h in sd.query_hostapis()])
