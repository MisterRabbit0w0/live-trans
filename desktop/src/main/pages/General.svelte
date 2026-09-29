<script lang="ts">
  import Button from "../../lib/components/Button.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import Icon from "../../lib/components/Icon.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import Select from "../../lib/components/Select.svelte";
  import ToggleField from "../../lib/components/ToggleField.svelte";
  import { call } from "../../lib/core";
  import { readString, setValue } from "../../lib/settings";
  import { sysAppearance } from "../../lib/theme/appearance.svelte";
  import { DEFAULT_SEED } from "../../lib/theme/material";

  const THEME_OPTIONS = [
    { label: "跟随系统", value: "system" },
    { label: "浅色", value: "light" },
    { label: "深色", value: "dark" },
  ];

  const ACCENTS = [
    { label: "蓝", value: "#1767db" },
    { label: "青", value: "#0b8a7a" },
    { label: "绿", value: "#3a8f3e" },
    { label: "琥珀", value: "#b7791f" },
    { label: "橙", value: "#c2410c" },
    { label: "玫红", value: "#c0265e" },
    { label: "紫", value: "#7c4dff" },
  ];

  const accent = $derived(readString("ui.accent") || "system");
  const systemAccent = $derived(sysAppearance.accent ?? DEFAULT_SEED);

  function accentKeys(event: KeyboardEvent) {
    const group = event.currentTarget as HTMLElement;
    const items = Array.from(
      group.querySelectorAll<HTMLElement>('[role="radio"]'),
    );
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    let next = -1;
    if (event.key === "ArrowRight" || event.key === "ArrowDown")
      next = (index + 1) % items.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (index - 1 + items.length) % items.length;
    if (next >= 0) {
      event.preventDefault();
      items[next].focus();
      items[next].click();
    }
  }
</script>

<div class="page-col">
  <PageHeading
    title="通用"
    subtitle="设置启动方式、主题和辅助显示选项。"
  />

  <GlassPanel>
    <h2 class="section">启动与后台</h2>
    <ToggleField
      path="ui.silent_start"
      label="静默启动"
      hint="启动时隐藏控制中心，保留系统托盘。翻译时仍显示字幕。"
    />
    <ToggleField
      path="ui.auto_translate"
      label="启动后自动开始翻译"
      hint="使用已保存的声音来源和模型配置。"
    />
    <p class="note">
      关闭控制中心后仍在后台运行。可从系统托盘重新打开或退出。
    </p>
  </GlassPanel>

  <GlassPanel>
    <h2 class="section">翻译记录</h2>
    <ToggleField
      path="record.enabled"
      label="保存翻译记录"
      hint="逐句保存原文、译文和时间，便于回看和整理纪要。只保存在本机，不保存音频。"
    />
    <div class="row">
      <p class="note flex">
        每次开始翻译生成一个记录文件，修改识别设置后继续写入同一文件。
      </p>
      <Button
        variant="quiet"
        icon="folder"
        onclick={() => void call("app.openRecordDirectory")}
      >
        打开记录文件夹
      </Button>
    </div>
  </GlassPanel>

  <GlassPanel>
    <h2 class="section">外观与辅助显示</h2>
    <Select
      label="主题"
      path="ui.theme"
      value={readString("ui.theme")}
      options={THEME_OPTIONS}
      onchange={(v) => setValue("ui.theme", v)}
    />
    <div class="accent-setting">
      <span class="label">强调色</span>
      <div
        class="swatches"
        role="radiogroup"
        aria-label="强调色"
        tabindex="-1"
        onkeydown={accentKeys}
      >
        <button
          type="button"
          role="radio"
          class="swatch"
          class:selected={accent === "system"}
          aria-checked={accent === "system"}
          aria-label="跟随系统"
          title="跟随系统"
          style:background={systemAccent}
          onclick={() => setValue("ui.accent", "system")}
        >
          <span class="auto-glyph"><Icon name="auto" size={14} /></span>
        </button>
        {#each ACCENTS as item (item.value)}
          <button
            type="button"
            role="radio"
            class="swatch"
            class:selected={accent === item.value}
            aria-checked={accent === item.value}
            aria-label={item.label}
            title={item.label}
            style:background={item.value}
            onclick={() => setValue("ui.accent", item.value)}
          ></button>
        {/each}
      </div>
    </div>
    <ToggleField
      path="ui.reduce_motion"
      label="减少动态效果"
      hint="关闭页面切换和控件过渡动画。"
    />
    <ToggleField
      path="ui.reduce_transparency"
      label="减少透明效果"
      hint="使用实色面板，提高内容对比度。"
    />
    <p class="note">同时遵循系统的动画、透明度和高对比设置。</p>
  </GlassPanel>

  <GlassPanel>
    <div class="row">
      <div class="about">
        <span class="app-name">LiveTrans</span>
        <span class="tagline">实时语音识别与翻译</span>
      </div>
      <Button
        variant="raised"
        icon="folder"
        onclick={() => void call("app.openLogDirectory")}
      >
        打开日志目录
      </Button>
    </div>
  </GlassPanel>
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
  .section {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .note.flex {
    flex: 1;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .accent-setting {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .label {
    font-weight: 500;
  }
  .swatches {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .swatch {
    position: relative;
    width: 28px;
    height: 28px;
    border-radius: var(--lt-radius-full);
    border: 1px solid var(--md-sys-color-outline-variant);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    box-shadow: none;
    transition:
      transform var(--lt-fast) var(--lt-ease),
      outline var(--lt-fast) var(--lt-ease);
  }
  .swatch:hover {
    transform: scale(1.1);
  }
  .swatch.selected {
    outline: 2px solid var(--md-sys-color-primary);
    outline-offset: 2px;
    border-color: transparent;
    box-shadow: none;
  }
  .auto-glyph {
    display: inline-flex;
    filter: none;
  }
  .about {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .app-name {
    font-size: 16px;
    font-weight: 600;
  }
  .tagline {
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
</style>
