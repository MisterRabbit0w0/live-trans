"""验证按进程捕获：启动一个播放 wav 的子进程，只捕获它的声音。"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from livetrans.audio.process_capture import ProcessLoopbackCapture, list_audio_processes

wav = Path(__file__).parent / "capture_test.wav"
assert wav.exists(), "先运行 test_capture.py 生成 capture_test.wav"

# 子进程循环播放 wav（产生独立音频会话）
player = subprocess.Popen(
    [sys.executable, "-c",
     f"import winsound\n"
     f"for _ in range(5): winsound.PlaySound(r'{wav}', winsound.SND_FILENAME)"],
)
print(f"播放子进程 PID={player.pid}，等待声音出现…")
time.sleep(2)

print("当前发声进程:", list_audio_processes())

chunks = []
cap = ProcessLoopbackCapture(chunks.append, pid=player.pid, process_name="python.exe")
cap.start()
print(f"捕获 [{cap.device_name}] 4 秒…")
time.sleep(4)
cap.stop()
player.kill()

audio = np.concatenate(chunks) if chunks else np.empty(0)
peak = float(np.abs(audio).max()) if len(audio) else 0.0
print(f"捕获 {len(audio)/16000:.1f} 秒，峰值 {peak:.3f}")
print("OK: 按进程捕获正常" if peak > 0.01 else "FAIL: 没有捕获到目标进程的声音")
