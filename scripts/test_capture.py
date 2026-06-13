"""验证音频捕获：录制 5 秒系统声音存为 wav（播放任意视频后运行）。"""
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from livetrans.audio.capture import LoopbackCapture, TARGET_RATE

chunks = []
cap = LoopbackCapture(chunks.append)
cap.start()
print(f"正在从 [{cap.device_name}] 录制 5 秒…请确保有声音在播放")
time.sleep(5)
cap.stop()

audio = np.concatenate(chunks)
out = Path(__file__).parent / "capture_test.wav"
with wave.open(str(out), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(TARGET_RATE)
    w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
peak = float(np.abs(audio).max()) if len(audio) else 0.0
print(f"已保存 {out}（{len(audio)/TARGET_RATE:.1f} 秒，峰值幅度 {peak:.3f}）")
print("峰值接近 0 说明没抓到声音" if peak < 0.01 else "捕获正常 OK")
