<script lang="ts">
  import Button from "../../lib/components/Button.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import NumberField from "../../lib/components/NumberField.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import Select from "../../lib/components/Select.svelte";
  import TextField from "../../lib/components/TextField.svelte";
  import ToggleField from "../../lib/components/ToggleField.svelte";
  import {
    readBool,
    readNumber,
    readString,
    setValue,
  } from "../../lib/settings";
  import ModelPanel from "./ModelPanel.svelte";

  interface Props {
    advanced?: boolean;
  }
  let { advanced = $bindable(false) }: Props = $props();

  const backend = $derived(readString("asr.backend"));
  const local = $derived(backend === "local");

  const BACKEND_OPTIONS = [
    { label: "本地识别", value: "local" },
    { label: "云端识别 · OpenAI 兼容", value: "cloud" },
  ];
  const LANGUAGE_OPTIONS = [
    { label: "自动检测", value: "auto" },
    { label: "英语", value: "en" },
    { label: "日语", value: "ja" },
    { label: "韩语", value: "ko" },
    { label: "中文", value: "zh" },
    { label: "俄语", value: "ru" },
    { label: "西班牙语", value: "es" },
    { label: "法语", value: "fr" },
    { label: "德语", value: "de" },
  ];
  const MODEL_OPTIONS = [
    { label: "自动选择", value: "auto" },
    { label: "large-v3-turbo", value: "large-v3-turbo" },
    { label: "large-v3", value: "large-v3" },
    { label: "medium", value: "medium" },
    { label: "small", value: "small" },
    { label: "base", value: "base" },
  ];
  const DEVICE_OPTIONS = [
    { label: "自动", value: "auto" },
    { label: "NVIDIA GPU · CUDA", value: "cuda" },
    { label: "CPU", value: "cpu" },
  ];
</script>

<div class="page-col">
  <PageHeading
    title="语音识别"
    subtitle="选择本地模型或云端服务，将声音转换为文字。"
  />

  <GlassPanel>
    <Select
      label="识别方式"
      path="asr.backend"
      value={backend}
      options={BACKEND_OPTIONS}
      onchange={(v) => setValue("asr.backend", v)}
    />
    <Select
      label="源语言"
      path="asr.language"
      value={readString("asr.language")}
      options={LANGUAGE_OPTIONS}
      onchange={(v) => setValue("asr.language", v)}
    />
    {#if local}
      <Select
        label="本地模型"
        path="asr.model"
        editable
        value={readString("asr.model")}
        options={MODEL_OPTIONS}
        hint="自动模式根据可用显存，在已下载的模型中选择。模型只在点击下载时获取。"
        onchange={(v) => setValue("asr.model", v)}
      />
    {:else}
      <TextField
        label="服务地址"
        path="asr.cloud_base_url"
        value={readString("asr.cloud_base_url")}
        hint="支持 OpenAI 兼容的语音转写服务。"
        onchange={(v) => setValue("asr.cloud_base_url", v)}
      />
      <TextField
        label="API 密钥"
        path="asr.cloud_api_key"
        secret
        value={readString("asr.cloud_api_key")}
        onchange={(v) => setValue("asr.cloud_api_key", v)}
      />
      <TextField
        label="云端模型"
        path="asr.cloud_model"
        value={readString("asr.cloud_model")}
        onchange={(v) => setValue("asr.cloud_model", v)}
      />
    {/if}
  </GlassPanel>

  {#if local}<ModelPanel />{/if}

  <div>
    <Button
      variant="quiet"
      icon="settings"
      onclick={() => (advanced = !advanced)}
    >
      {advanced ? "收起高级选项" : "高级选项"}
    </Button>
  </div>

  {#if advanced}
    <GlassPanel>
      {#if local}
        <Select
          label="计算设备"
          path="asr.device"
          value={readString("asr.device")}
          options={DEVICE_OPTIONS}
          onchange={(v) => setValue("asr.device", v)}
        />
        <TextField
          label="模型运行环境"
          path="asr.runtime"
          value={readString("asr.runtime")}
          hint="本地模型在独立进程中运行。留空使用内置环境；也可填写另一个装有 faster-whisper 的 Python 环境目录或解释器路径（例如带 CUDA 的 venv）。模型下载到该环境内。"
          onchange={(v) => setValue("asr.runtime", v)}
        />
      {/if}
      <NumberField
        label="切句停顿"
        path="vad_silence_ms"
        value={readNumber("vad_silence_ms")}
        minimum={250}
        maximum={1000}
        step={50}
        suffix="ms"
        hint="数值越小，字幕出现越快，句子也可能更碎。"
        onchange={(v) => setValue("vad_silence_ms", v)}
      />
      <NumberField
        label="最长句子"
        path="vad_max_segment_s"
        value={readNumber("vad_max_segment_s")}
        minimum={1}
        maximum={30}
        step={0.5}
        decimals={2}
        suffix="秒"
        onchange={(v) => setValue("vad_max_segment_s", v)}
      />
      <NumberField
        label="最短语音"
        path="vad_min_speech_ms"
        value={readNumber("vad_min_speech_ms")}
        minimum={50}
        maximum={1000}
        step={50}
        suffix="ms"
        hint="短于此长度的语音片段将被忽略。"
        onchange={(v) => setValue("vad_min_speech_ms", v)}
      />
      <NumberField
        label="触发灵敏度 (VAD 阈值)"
        path="vad_threshold"
        value={readNumber("vad_threshold") || 0.35}
        minimum={0.1}
        maximum={0.9}
        step={0.05}
        decimals={2}
        hint="默认 0.35。数值越小越灵敏；适中或较小音量建议 0.25–0.35；环境嘈杂可适当调高。"
        onchange={(v) => setValue("vad_threshold", v)}
      />
      <ToggleField
        label="自适应音频增益 (AGC)"
        path="audio_gain_enabled"
        fallback={true}
        hint="自动将适中或微弱的声音平滑增益至标准电平，防止漏切；内置底噪门限与防爆音保护。"
      />
    </GlassPanel>
  {/if}
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
</style>
