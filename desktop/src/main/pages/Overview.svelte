<script lang="ts">
  import Button from "../../lib/components/Button.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import Icon from "../../lib/components/Icon.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import SubtitleEntry from "../../lib/components/SubtitleEntry.svelte";
  import { call } from "../../lib/core";
  import { readBool } from "../../lib/settings";
  import { core } from "../../lib/store.svelte";
  interface Props {
    onnavigate?: (index: number) => void;
  }
  let { onnavigate }: Props = $props();

  const app = $derived(core.state?.app);
  const committed = $derived(app?.committed);

  const isRunning = $derived(app?.state === "running");
  const isPaused = $derived(app?.state === "paused");
  const isError = $derived(app?.state === "error");
  const translateOn = $derived(
    core.state?.settings.draft.translate
      ? readBool("translate.enabled", true)
      : (app?.translating ?? true),
  );
  const recordOn = $derived(
    core.state?.settings.draft.record
      ? readBool("record.enabled", false)
      : (app?.recording ?? false),
  );

  const actionStem = $derived(
    translateOn && recordOn
      ? "翻译与记录"
      : translateOn
        ? "实时翻译"
        : recordOn
          ? "识别与记录"
          : "语音识别",
  );

  const primaryLabel = $derived(
    isRunning
      ? `暂停${actionStem}`
      : isPaused
        ? `继续${actionStem}`
        : isError
          ? "重试"
          : `开始${actionStem}`,
  );
  const primaryIcon = $derived(isRunning ? "pause" : "play");
  const canStop = $derived(
    ["starting", "running", "paused", "stopping"].includes(
      app?.state ?? "idle",
    ),
  );
</script>
<div class="page-col">
  <PageHeading
    title="实时处理"
    subtitle="管理语音识别、实时翻译与会议记录状态，可独立开关或协同工作。"
  />

  <GlassPanel padding={22}>
    <div class="status-panel">
      <div class="status-text">
        <h2>{app?.statusTitle ?? "…"}</h2>
        <p class="detail">{app?.statusDetail ?? ""}</p>
        <div class="mode-chips">
          <button
            class="chip"
            class:active={translateOn}
            onclick={() => void call("app.toggleTranslation")}
            title="点击快速切换实时翻译"
          >
            <Icon name="translate" size={13} />
            <span>实时翻译：{translateOn ? "开启" : "关闭"}</span>
          </button>

          <button
            class="chip"
            class:active={recordOn}
            onclick={() => void call("app.toggleRecord")}
            title="点击快速切换会话记录"
          >
            <Icon name="document" size={13} />
            <span>保存记录：{recordOn ? "开启" : "关闭"}</span>
          </button>
        </div>

        <div class="actions">
          <Button
            variant="primary"
            icon={primaryIcon}
            disabled={app?.busy}
            onclick={() => void call("app.togglePause")}
          >
            {primaryLabel}
          </Button>
          {#if canStop}
            <Button
              variant="quiet"
              icon="stop"
              disabled={app?.state === "stopping"}
              onclick={() => void call("app.stop")}
            >
              停止
            </Button>
          {/if}
        </div>
      </div>
    </div>
  </GlassPanel>

  <div class="cards">
    <GlassPanel padding={16} gap={6} class="card">
      <div class="card-head">
        <Icon name="audio" size={16} />
        <span class="card-title">声音来源</span>
      </div>
      <p class="card-value">{app?.sourceLabel ?? ""}</p>
      <Button variant="quiet" icon="arrow" onclick={() => onnavigate?.(1)}>
        更改来源
      </Button>
    </GlassPanel>
    <GlassPanel padding={16} gap={6} class="card">
      <div class="card-head">
        <Icon name="mic" size={16} />
        <span class="card-title">语音识别</span>
      </div>
      <p class="card-value">{app?.modelLabel ?? ""}</p>
      <p class="card-sub">源语言 · {app?.sourceLanguageLabel ?? ""}</p>
      <Button variant="quiet" icon="arrow" onclick={() => onnavigate?.(2)}>
        调整识别
      </Button>
    </GlassPanel>
    <GlassPanel padding={16} gap={6} class="card">
      <div class="card-head">
        <Icon name="translate" size={16} />
        <span class="card-title">实时翻译</span>
        <span class="status-tag" class:active={translateOn}>
          {translateOn ? "开启" : "关闭"}
        </span>
      </div>
      <p class="card-value">
        {translateOn ? (app?.translationModelLabel ?? "") : "已关闭翻译"}
      </p>
      <p class="card-sub">目标语言 · {app?.targetLanguageLabel ?? ""}</p>
      <Button variant="quiet" icon="arrow" onclick={() => onnavigate?.(3)}>
        配置翻译
      </Button>
    </GlassPanel>
    <GlassPanel padding={16} gap={6} class="card">
      <div class="card-head">
        <Icon name="document" size={16} />
        <span class="card-title">记录与纪要</span>
        <span class="status-tag" class:active={recordOn}>
          {recordOn ? "录制中" : "未开启"}
        </span>
      </div>
      <p class="card-value">{recordOn ? "自动保存会话" : "未开启保存"}</p>
      <p class="card-sub">AI 会议纪要与速记</p>
      <Button variant="quiet" icon="arrow" onclick={() => onnavigate?.(5)}>
        查看纪要
      </Button>
    </GlassPanel>
  </div>

  <GlassPanel padding={20} gap={12}>
    <div class="recent-head">
      <h3>最近字幕</h3>
      <Button
        variant="quiet"
        icon="subtitles"
        onclick={() => void call("app.toggleSubtitles")}
      >
        {app?.subtitleVisible ? "隐藏悬浮字幕" : "显示悬浮字幕"}
      </Button>
    </div>
    {#if core.subtitles.length === 0}
      <div class="empty">
        <p class="empty-title">暂无字幕</p>
        <p class="empty-hint">开始翻译后，原文和译文会出现在这里。</p>
      </div>
    {:else}
      {#each core.subtitles as row (row.id)}
        <SubtitleEntry
          original={row.original}
          translation={row.translation}
          showOriginal={committed?.subtitle.show_original ?? true}
          textSize={17}
        />
      {/each}
    {/if}
  </GlassPanel>
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .status-text h2 {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
  }
  .detail {
    margin: 10px 0 0;
    color: var(--md-sys-color-on-surface-variant);
  }
  .mode-chips {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    flex-wrap: wrap;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: var(--lt-radius-full);
    border: 1px solid var(--md-sys-color-outline-variant);
    background: var(--md-sys-color-surface-container);
    font: inherit;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    cursor: pointer;
    transition:
      background-color var(--lt-fast) var(--lt-ease),
      border-color var(--lt-fast) var(--lt-ease),
      color var(--lt-fast) var(--lt-ease);
  }
  .chip:hover {
    background: var(--md-sys-color-surface-container-high);
  }
  .chip.active {
    background: color-mix(in oklab, var(--md-sys-color-primary) 14%, transparent);
    border-color: color-mix(in oklab, var(--md-sys-color-primary) 50%, transparent);
    color: var(--md-sys-color-primary);
    font-weight: 500;
  }
  .status-tag {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: var(--lt-radius-full);
    background: var(--md-sys-color-surface-container);
    color: var(--md-sys-color-on-surface-variant);
    margin-left: auto;
  }
  .status-tag.active {
    background: color-mix(in oklab, var(--lt-success) 20%, transparent);
    color: var(--lt-success);
    font-weight: 500;
  }
  .actions {
    display: flex;
    gap: 10px;
    margin-top: 14px;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
  }
  .cards :global(.card) {
    min-width: 0;
    align-items: flex-start;
  }
  .card-head {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    color: var(--md-sys-color-on-surface-variant);
  }
  .card-title {
    font-size: 14px;
    font-weight: 500;
  }
  .card-value {
    margin: 0;
    font-weight: 600;
    font-size: 14px;
    line-height: 1.4;
    word-break: break-all;
    overflow-wrap: anywhere;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .card-sub {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .recent-head {
    display: flex;
    align-items: center;
  }
  .recent-head h3 {
    flex: 1;
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .empty-title {
    margin: 0 0 6px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .empty-hint {
    margin: 0 0 4px;
    font-size: 12px;
    color: var(--md-sys-color-outline);
  }
</style>
