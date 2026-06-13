"""验证 VAD：对已知语音 wav（TTS 合成）计算逐帧概率与切句。"""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from livetrans.audio.vad import FRAME_SIZE, VadSegmenter, _SileroOnnx

wav_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "tts_test.wav")
with wave.open(wav_path, "rb") as w:
    assert w.getframerate() == 16000 and w.getnchannels() == 1
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

probe = _SileroOnnx()
probs = np.array([
    probe.prob(audio[i * FRAME_SIZE:(i + 1) * FRAME_SIZE])
    for i in range(len(audio) // FRAME_SIZE)
])
print(f"帧数={len(probs)} prob_max={probs.max():.3f} prob_mean={probs.mean():.3f} "
      f">0.5占比={(probs > 0.5).mean():.1%}")

segs = []
seg = VadSegmenter(on_segment=segs.append)
seg.feed(audio)
durations = ", ".join(f"{len(s)/16000:.1f}s" for s in segs)
print(f"切句数={len(segs)} 时长: [{durations}]")
print("VAD 正常" if probs.max() > 0.8 and segs else "VAD 异常！")
