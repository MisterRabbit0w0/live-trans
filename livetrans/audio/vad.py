"""Silero VAD (ONNX) 流式切句。

输入 16kHz float32 流（任意大小的块），按语音停顿切出整句，
通过 on_segment 回调输出每句的音频。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import onnxruntime as ort

SAMPLE_RATE = 16000
FRAME_SIZE = 512  # silero v5 在 16k 下每帧 512 采样 (32ms)
CONTEXT_SIZE = 64  # v5 要求每帧前拼接上一帧末尾 64 采样作为上下文
MODEL_PATH = Path(__file__).resolve().parent.parent / "assets" / "silero_vad.onnx"


class _SileroOnnx:
    def __init__(self):
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(
            str(MODEL_PATH), opts, providers=["CPUExecutionProvider"]
        )
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT_SIZE, dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        """frame: float32 [512]"""
        x = np.concatenate([self._context, frame])
        out, self._state = self._sess.run(
            None,
            {
                "input": x[np.newaxis, :],
                "state": self._state,
                "sr": np.array(SAMPLE_RATE, dtype=np.int64),
            },
        )
        self._context = frame[-CONTEXT_SIZE:]
        return float(out[0, 0])


class VadSegmenter:
    """流式 VAD 切句状态机。

    - 语音概率 > start_threshold 进入说话状态（附带 pre_roll 前导音频）
    - 静音持续 silence_ms 毫秒后切出一句；句长超过 long_segment_s 后
      所需静音缩短为 60%，长句在下一个小停顿尽早切出
    - 句长到达 max_segment_s 时软强切：回看最近 lookback 窗口内语音
      概率最低的帧（最接近词间隙）作为切点，剩余音频留在缓冲继续
    - 短于 min_speech_ms 的句子丢弃
    """

    def __init__(
        self,
        on_segment: Callable[[np.ndarray], None],
        silence_ms: int = 500,
        max_segment_s: float = 8.0,
        min_speech_ms: int = 250,
        start_threshold: float = 0.35,
        end_threshold: float | None = None,
        pre_roll_ms: int = 200,
        long_segment_s: float = 5.0,
        lookback_s: float = 1.5,
    ):
        self._on_segment = on_segment
        self._model = _SileroOnnx()
        self._silence_frames = max(1, int(silence_ms * SAMPLE_RATE / 1000 / FRAME_SIZE))
        self._max_frames = max(1, int(max_segment_s * SAMPLE_RATE / FRAME_SIZE))
        self._min_speech_frames = max(1, int(min_speech_ms * SAMPLE_RATE / 1000 / FRAME_SIZE))
        self._start_th = float(start_threshold)
        self._end_th = (
            float(end_threshold)
            if end_threshold is not None
            else max(0.12, self._start_th * 0.65)
        )
        self._pre_roll_frames = max(1, int(pre_roll_ms * SAMPLE_RATE / 1000 / FRAME_SIZE))
        self._long_frames = max(1, int(long_segment_s * SAMPLE_RATE / FRAME_SIZE))
        self._lookback_frames = max(2, int(lookback_s * SAMPLE_RATE / FRAME_SIZE))

        self._residual = np.empty(0, dtype=np.float32)
        self._pre_roll: list[np.ndarray] = []
        self._segment: list[np.ndarray] = []
        self._probs: list[float] = []
        self._speech_frames = 0
        self._silence_run = 0
        self._in_speech = False

    def reset(self) -> None:
        self._model.reset()
        self._residual = np.empty(0, dtype=np.float32)
        self._pre_roll.clear()
        self._segment.clear()
        self._probs.clear()
        self._speech_frames = 0
        self._silence_run = 0
        self._in_speech = False

    def feed(self, chunk: np.ndarray) -> None:
        data = np.concatenate([self._residual, chunk]) if len(self._residual) else chunk
        n_frames = len(data) // FRAME_SIZE
        for i in range(n_frames):
            self._process_frame(data[i * FRAME_SIZE : (i + 1) * FRAME_SIZE])
        self._residual = data[n_frames * FRAME_SIZE :]

    def _process_frame(self, frame: np.ndarray) -> None:
        p = self._model.prob(frame)
        if not self._in_speech:
            self._pre_roll.append(frame)
            if len(self._pre_roll) > self._pre_roll_frames:
                self._pre_roll.pop(0)
            if p >= self._start_th:
                self._in_speech = True
                self._segment = list(self._pre_roll)
                self._pre_roll = []
                self._speech_frames = 1
                self._silence_run = 0
            return

        self._segment.append(frame)
        self._probs.append(p)
        if p >= self._end_th:
            self._speech_frames += 1
            self._silence_run = 0
        else:
            self._silence_run += 1

        # 长句降低停顿要求，尽早在小停顿处切出
        required = self._silence_frames
        if len(self._segment) >= self._long_frames:
            required = max(2, int(self._silence_frames * 0.6))

        if self._silence_run >= required:
            self._emit(trim_tail=True)
        elif len(self._segment) >= self._max_frames:
            self._soft_split()

    def _emit(self, trim_tail: bool) -> None:
        seg = self._segment
        if trim_tail and self._silence_run:
            # 去掉尾部静音，只留一点收尾
            keep = max(len(seg) - self._silence_run + 2, 1)
            seg = seg[:keep]
        self._segment = []
        self._probs = []
        self._in_speech = False
        self._silence_run = 0
        if self._speech_frames >= self._min_speech_frames and seg:
            self._on_segment(np.concatenate(seg))
        self._speech_frames = 0

    def _soft_split(self) -> None:
        """到达最大句长：在回看窗口内语音概率最低处切开，剩余继续累积。"""
        lookback = min(self._lookback_frames, len(self._segment) // 2)
        window = self._probs[-lookback:]
        cut = len(self._segment) - lookback + int(np.argmin(window))
        cut = max(cut, 1)
        head = self._segment[:cut]
        self._segment = self._segment[cut:]
        self._probs = self._probs[cut:]
        self._speech_frames = sum(1 for q in self._probs if q >= self._end_th)
        self._silence_run = 0
        for q in reversed(self._probs):
            if q < self._end_th:
                self._silence_run += 1
            else:
                break
        if head:
            self._on_segment(np.concatenate(head))
class ConservativeAGC:
    """保守型流式自适应音频增益控制器。

    设计原则（四大安全防线）：
    1. 底噪门限冻结：低于 noise_gate_rms (-60 dBFS) 时增益不放大并缓慢归一，绝不放大底噪。
    2. 快降慢升（Fast attack, smooth decay）：大音量极速压低（Attack = 0.8），
       小音量平缓抬升（Decay = 0.05）。
    4. 软限幅硬顶保护：最终信号软限制，保证采样在 [-0.98, +0.98] 之内，杜绝溢出爆音。
    """

    def __init__(
        self,
        target_peak: float = 0.35,
        max_gain: float = 6.0,
        noise_gate_rms: float = 0.001,
        attack_rate: float = 0.8,
        decay_rate: float = 0.05,
    ):
        self.target_peak = target_peak
        self.max_gain = max_gain
        self.noise_gate_rms = noise_gate_rms
        self.attack_rate = attack_rate
        self.decay_rate = decay_rate
        self.current_gain = 1.0

    def reset(self) -> None:
        self.current_gain = 1.0

    def process(self, chunk: np.ndarray) -> np.ndarray:
        if len(chunk) == 0:
            return chunk
        peak = float(np.max(np.abs(chunk)))
        rms = float(np.sqrt(np.mean(chunk**2)))

        # 纯静音或微弱底噪：不盲目放大，增益平缓回落至 1.0
        if rms < self.noise_gate_rms or peak < 1e-4:
            self.current_gain += (1.0 - self.current_gain) * self.decay_rate
            return chunk * self.current_gain

        # 计算当前目标增益，受限在 [1.0, max_gain]
        desired_gain = self.target_peak / peak
        desired_gain = max(1.0, min(self.max_gain, desired_gain))

        # 快降慢升平滑过渡
        if desired_gain < self.current_gain:
            self.current_gain += (desired_gain - self.current_gain) * self.attack_rate
        else:
            self.current_gain += (desired_gain - self.current_gain) * self.decay_rate

        out = chunk * self.current_gain
        max_val = np.max(np.abs(out))
        if max_val > 0.95:
            out = np.clip(out, -0.98, 0.98)
        return out
