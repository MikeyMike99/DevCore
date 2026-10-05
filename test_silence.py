import wave
import struct
with wave.open("sandbox/static/sounds/incoming.wav", "r") as f:
    frames = f.readframes(f.getnframes())
    # Unpack as short (16-bit signed integers)
    samples = struct.unpack(f"<{len(frames)//2}h", frames)
    print("Max amplitude:", max(samples))
    print("Min amplitude:", min(samples))
