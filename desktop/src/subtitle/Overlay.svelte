<script lang="ts">
  import { onMount, tick } from "svelte";
  import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";

  import SubtitleEntry from "../lib/components/SubtitleEntry.svelte";
  import { call, showControlCenter } from "../lib/core";
  import { core } from "../lib/store.svelte";
  import {
    appearanceState,
    initAppearance,
  } from "../lib/theme/appearance.svelte";

  const inTauri =
    typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  const win = inTauri ? getCurrentWindow() : null;

  const committed = $derived(core.state?.app.committed);
  const subtitle = $derived(committed?.subtitle);
  const fontSize = $derived(subtitle?.font_size ?? 22);
  const opacity = $derived(subtitle?.opacity ?? 0.75);
  const showOriginal = $derived(subtitle?.show_original ?? true);
  const maxLines = $derived(Math.max(1, subtitle?.max_lines ?? 3));

  initAppearance("subtitle", {
    forceDark: true,
    materialEnabled: () => opacity > 0,
  });

  const width = $derived(
    Math.min(subtitle?.width ?? 900, screen.availWidth - 32),
  );
  const rows = $derived(core.subtitles.slice(-maxLines));
  const appState = $derived(core.state?.app.state ?? "idle");
  const statusTitle = $derived(core.state?.app.statusTitle ?? "");

  const showStatus = $derived(
    rows.length === 0 ||
      ["paused", "starting", "stopping", "error"].includes(appState),
  );
  const statusText = $derived(
    rows.length === 0
      ? appState === "running"
        ? "等待声音…"
        : statusTitle
      : statusTitle,
  );
  const statusSize = $derived(Math.max(12, fontSize * 0.7));

  // Native material already supplies translucency; without it, darken more.
  const alpha = $derived(
    opacity <= 0
      ? 0
      : appearanceState.material === "native"
        ? opacity * 0.55
        : opacity * 0.85,
  );

  let viewport: HTMLElement | undefined = $state();
  let lines: HTMLElement | undefined = $state();

  // Keep the newest row visible (Flickable contentY behavior).
  $effect(() => {
    void core.subtitles;
    void maxLines;
    void fontSize;
    tick().then(() => {
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    });
  });

  // Resize the native window to content: min(content + 32, 0.6 * availHeight).
  onMount(() => {
    if (!win || !lines) return;
    const observer = new ResizeObserver(() => {
      const height = Math.min(
        Math.ceil((lines?.scrollHeight ?? 0) + 32),
        Math.floor(screen.availHeight * 0.6),
      );
      void win.setSize(new LogicalSize(width, Math.max(56, height)));
    });
    observer.observe(lines);
    return () => observer.disconnect();
  });

  function onMouseDown(event: MouseEvent) {
    if (event.button !== 0) return;
    if ((event.target as HTMLElement).closest(".toolbar")) return;
    void win?.startDragging();
  }

  function onWheel(event: WheelEvent) {
    if (event.ctrlKey) {
      event.preventDefault();
      void call("app.adjustFont", { delta: event.deltaY > 0 ? -1 : 1 });
    }
    // Plain wheel scrolls natively inside the viewport.
  }
</script>

<div
  class="overlay"
  role="presentation"
  onmousedown={onMouseDown}
  onwheel={onWheel}
>
  <div
    class="box"
    class:clear={opacity <= 0}
    style:width="{width}px"
    style:background={alpha > 0 ? `rgba(6 8 12 / ${alpha})` : "transparent"}
  >
    <div class="viewport" bind:this={viewport}>
      <div class="lines" bind:this={lines}>
        {#each rows as row (row.id)}
          <SubtitleEntry
            original={row.original}
            translation={row.translation}
            {showOriginal}
            textSize={fontSize}
            onDark
          />
        {/each}
        {#if showStatus}
          <p class="status" style:font-size="{statusSize}px">{statusText}</p>
        {/if}
      </div>
    </div>
    <div class="toolbar">
      <button class="tool" onclick={() => void showControlCenter()}>
        控制中心
      </button>
      <button class="tool" onclick={() => void call("app.toggleSubtitles")}>
        隐藏
      </button>
    </div>
  </div>
</div>

<style>
  .overlay {
    display: flex;
    justify-content: center;
    padding: 0;
  }
  .box {
    position: relative;
    border-radius: var(--lt-radius-overlay, 12px);
    overflow: hidden;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: 0 8px 24px -4px rgb(0 0 0 / 0.4);
    border: 1px solid rgb(255 255 255 / 0.14);
    cursor: move;
    user-select: none;
    transition:
      border-color var(--lt-fast) var(--lt-ease),
      box-shadow var(--lt-fast) var(--lt-ease);
  }
  .box.clear {
    border-color: transparent;
    box-shadow: none;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
  :global(html[data-contrast="high"]) .box,
  :global(html[data-material="solid"]) .box {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
  :global(html[data-contrast="high"]) .box {
    background: #000 !important;
    border: 2px solid #fff;
    box-shadow: none;
  }
  .viewport {
    max-height: calc(100vh - 32px);
    overflow-y: auto;
    overflow-x: hidden;
    margin: 16px;
    scrollbar-width: none;
  }
  .viewport::-webkit-scrollbar {
    display: none;
  }
  .lines {
    display: flex;
    flex-direction: column;
    gap: 14px;
    text-align: center;
  }
  .status {
    margin: 0;
    color: #c4d1e4;
  }
  .toolbar {
    position: absolute;
    top: 4px;
    right: 8px;
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity var(--lt-fast) var(--lt-ease);
  }
  .box:hover .toolbar,
  .toolbar:focus-within {
    opacity: 1;
  }
  .tool {
    height: 28px;
    padding: 0 10px;
    border: 1px solid rgb(255 255 255 / 0.12);
    border-radius: var(--lt-radius-sm);
    background: rgb(20 25 35 / 0.85);
    color: #dce5f2;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    transition:
      background-color var(--lt-fast) var(--lt-ease),
      border-color var(--lt-fast) var(--lt-ease),
      color var(--lt-fast) var(--lt-ease);
  }
  .tool:hover {
    background: rgb(40 48 64 / 0.95);
    border-color: rgb(255 255 255 / 0.25);
    color: #fff;
  }
</style>
