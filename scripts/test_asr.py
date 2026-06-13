"""验证 ASR：转写一个 wav 文件。用法: python scripts/test_asr.py [capture_test.wav]"""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from livetrans.asr.whisper_local import LocalWhisper, detect_free_vram_mb, pick_model

wav_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "capture_test.wav")
with wave.open(wav_path, "rb") as w:
    assert w.getframerate() == 16000 and w.getnchannels() == 1, "需要 16k 单声道 wav"
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

vram = detect_free_vram_mb()
print(f"空闲显存: {vram} MB → 选档: {pick_model(vram)}")
engine = LocalWhisper()
result = engine.transcribe(audio)
print(f"语言: {result.language}")
print(f"文本: {result.text}")
