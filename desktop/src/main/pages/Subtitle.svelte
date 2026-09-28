<script lang="ts">
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import NumberField from "../../lib/components/NumberField.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import SubtitleEntry from "../../lib/components/SubtitleEntry.svelte";
  import ToggleField from "../../lib/components/ToggleField.svelte";
  import {
    readBool,
    readNumber,
    setValue,
  } from "../../lib/settings";

  const opacity = $derived(readNumber("subtitle.opacity"));
  const fontSize = $derived(readNumber("subtitle.font_size"));
  const showOriginal = $derived(readBool("subtitle.show_original"));
</script>

<div class="page-col">
  <PageHeading
    title="字幕外观"
    subtitle="预览字幕样式，应用后更新悬浮窗。"
  />

  <GlassPanel gap={14}>
    <div class="preview-head">
      <span class="preview-title">即时预览</span>
      <span class="preview-note">应用后更新悬浮窗</span>
    </div>
    <div class="preview">
      <div
        class="sample-bg"
        style:background="rgba(6 8 12 / {opacity})"
      >
        <SubtitleEntry
          original="The next session starts in five minutes."
          translation="下一场将在五分钟后开始。"
          {showOriginal}
          textSize={fontSize}
          onDark
        />
      </div>
    </div>
  </GlassPanel>

  <GlassPanel>
    <ToggleField
      path="subtitle.show_original"
      label="显示原文"
      hint="同时显示原文和译文。"
    />
    <NumberField
      label="字幕字号"
      path="subtitle.font_size"
      value={fontSize}
      minimum={10}
      maximum={48}
      suffix="px"
      onchange={(v) => setValue("subtitle.font_size", v)}
    />
    <NumberField
      label="同屏条数"
      path="subtitle.max_lines"
      value={readNumber("subtitle.max_lines")}
      minimum={1}
      maximum={10}
      suffix="条"
      onchange={(v) => setValue("subtitle.max_lines", v)}
    />
    <NumberField
      label="背景不透明度"
      path="subtitle.opacity"
      value={opacity}
      minimum={0}
      maximum={100}
      step={5}
      factor={100}
      decimals={2}
      suffix="%"
      onchange={(v) => setValue("subtitle.opacity", v)}
    />
    <NumberField
      label="悬浮窗宽度"
      path="subtitle.width"
      value={readNumber("subtitle.width")}
      minimum={300}
      maximum={2400}
      step={10}
      suffix="px"
      onchange={(v) => setValue("subtitle.width", v)}
    />
  </GlassPanel>

  <p class="footnote">拖动悬浮窗可调整位置，Ctrl + 滚轮可直接调整字号。</p>
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
  .preview-head {
    display: flex;
    align-items: baseline;
  }
  .preview-title {
    flex: 1;
    font-weight: 500;
  }
  .preview-note {
    font-size: 11px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .preview {
    border-radius: var(--lt-radius-card);
    padding: 20px 12px;
    background: #181d26;
    border: 1px solid var(--md-sys-color-outline-variant);
  }
  .sample-bg {
    border-radius: var(--lt-radius-control);
    border: 1px solid rgb(255 255 255 / 0.15);
    padding: 14px 16px;
    text-align: center;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
  }
  .footnote {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-outline);
  }
</style>
