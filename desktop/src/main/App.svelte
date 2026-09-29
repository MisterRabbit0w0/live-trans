<script lang="ts">
  import { onMount, tick } from "svelte";
  import { getCurrentWindow } from "@tauri-apps/api/window";

  // @tauri-apps/api declares ResizeDirection as a local type; mirror it here.
  type ResizeDirection =
    | "East"
    | "North"
    | "NorthEast"
    | "NorthWest"
    | "South"
    | "SouthEast"
    | "SouthWest"
    | "West";

  import logo from "../assets/livetrans.svg";
  import Button from "../lib/components/Button.svelte";
  import Dialog from "../lib/components/Dialog.svelte";
  import Icon from "../lib/components/Icon.svelte";
  import IconButton from "../lib/components/IconButton.svelte";
  import Notice from "../lib/components/Notice.svelte";
  import { call, onEvent, restartCore } from "../lib/core";
  import { needsAdvanced, pageForPath } from "../lib/settings";
  import { core, resync } from "../lib/store.svelte";
  import { initAppearance } from "../lib/theme/appearance.svelte";
  import Audio from "./pages/Audio.svelte";
  import Asr from "./pages/Asr.svelte";
  import General from "./pages/General.svelte";
  import Overview from "./pages/Overview.svelte";
  import Subtitle from "./pages/Subtitle.svelte";
  import Translation from "./pages/Translation.svelte";
  import Records from "./pages/Records.svelte";
  initAppearance("main");

  const inTauri =
    typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  const win = inTauri ? getCurrentWindow() : null;

  const PAGES = [
    { title: "概览", symbol: "overview", component: Overview },
    { title: "声音来源", symbol: "audio", component: Audio },
    { title: "语音识别", symbol: "mic", component: Asr },
    { title: "翻译", symbol: "translate", component: Translation },
    { title: "字幕外观", symbol: "subtitles", component: Subtitle },
    { title: "记录与纪要", symbol: "document", component: Records },
    { title: "通用", symbol: "settings", component: General },
  ];

  const STATE_LABEL: Record<string, string> = {
    running: "正在翻译",
    paused: "已暂停",
    starting: "准备中",
    stopping: "停止中",
    idle: "尚未开始",
    error: "需要检查",
  };

  let currentPage = $state(
    Math.min(
      6,
      Math.max(0, Number(new URLSearchParams(location.search).get("page")) || 0),
    ),
  );
  let asrAdvanced = $state(
    new URLSearchParams(location.search).get("adv") === "1",
  );
  let quitOpen = $state(false);
  let scrollEl: HTMLElement | undefined = $state();
  let fadeTop = $state(0);
  let fadeBottom = $state(0);

  function updateFades() {
    if (!scrollEl) return;
    fadeTop = scrollEl.scrollTop > 1 ? 24 : 0;
    fadeBottom =
      scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight > 1
        ? 24
        : 0;
  }

  $effect(() => {
    void currentPage;
    const el = scrollEl;
    if (!el) return;
    const observer = new ResizeObserver(updateFades);
    observer.observe(el);
    for (const child of el.children) observer.observe(child);
    updateFades();
    return () => observer.disconnect();
  });

  const app = $derived(core.state?.app);
  const settings = $derived(core.state?.settings);
  const dirty = $derived(settings?.dirty ?? false);
  const busy = $derived(app?.busy ?? false);

  function navigate(index: number) {
    if (index === currentPage) return;
    currentPage = index;
    if (index === 1) void call("app.refreshDevices");
    if (scrollEl) scrollEl.scrollTop = 0;
  }

  onMount(() => {
    let unlisten: (() => void) | undefined;
    void onEvent(async (event) => {
      if (event.name === "quitConfirmationRequested") {
        quitOpen = true;
      } else if (event.name === "validationFailed") {
        const path = String(event.payload.path ?? "");
        const index = pageForPath(path);
        if (index === 2 && needsAdvanced(path)) asrAdvanced = true;
        navigate(index);
        await tick();
        document
          .querySelector<HTMLElement>(`[data-path="${CSS.escape(path)}"]`)
          ?.focus();
      }
    }).then((off) => (unlisten = off));
    return () => unlisten?.();
  });

  function onKeydown(event: KeyboardEvent) {
    if (!event.ctrlKey) return;
    if (event.key === ",") {
      event.preventDefault();
      navigate(5);
    } else if (event.key === "Enter") {
      event.preventDefault();
      void call("app.applySettings");
    } else if (event.key.toLowerCase() === "q") {
      event.preventDefault();
      void call("app.requestQuit");
    }
  }

  async function toggleMaximize() {
    if (!win) return;
    (await win.isMaximized()) ? await win.unmaximize() : await win.maximize();
  }

  function startResize(direction: ResizeDirection) {
    return async () => {
      if (win && !(await win.isMaximized()))
        await win.startResizeDragging(direction);
    };
  }

  const EDGES: Array<{ dir: ResizeDirection; class: string; cursor: string }> = [
    { dir: "West", class: "edge-w", cursor: "ew-resize" },
    { dir: "East", class: "edge-e", cursor: "ew-resize" },
    { dir: "North", class: "edge-n", cursor: "ns-resize" },
    { dir: "South", class: "edge-s", cursor: "ns-resize" },
    { dir: "NorthWest", class: "edge-nw", cursor: "nwse-resize" },
    { dir: "NorthEast", class: "edge-ne", cursor: "nesw-resize" },
    { dir: "SouthWest", class: "edge-sw", cursor: "nesw-resize" },
    { dir: "SouthEast", class: "edge-se", cursor: "nwse-resize" },
  ];
</script>

<svelte:window onkeydown={onKeydown} />

<div class="window">
  <header class="titlebar" data-tauri-drag-region>
    <div class="brand" data-tauri-drag-region>
      <img src={logo} alt="" width="28" height="28" data-tauri-drag-region />
      <span class="app-name" data-tauri-drag-region>LiveTrans</span>
      <span class="page-title" data-tauri-drag-region>
        {PAGES[currentPage].title}
      </span>
    </div>
    <!-- svelte-ignore a11y_no_static_element_interactions a11y_interactive_supports_focus -->
    <div
      class="drag-fill"
      data-tauri-drag-region
      ondblclick={toggleMaximize}
    ></div>
    <div class="window-buttons">
      <IconButton
        icon="minus"
        label="最小化"
        onclick={() => void win?.minimize()}
      />
      <IconButton
        icon="maximize"
        label="最大化或还原"
        onclick={() => void toggleMaximize()}
      />
      <IconButton
        icon="close"
        label="隐藏到托盘"
        onclick={() => void win?.hide()}
      />
    </div>
  </header>

  <div class="body">
    <nav class="sidebar lt-panel" aria-label="主导航">
      {#each PAGES as page, index (index)}
        <button
          class="lt-nav-item nav"
          aria-current={index === currentPage ? "page" : undefined}
          onclick={() => navigate(index)}
        >
          <Icon name={page.symbol} size={18} />
          <span>{page.title}</span>
        </button>
      {/each}
      <div class="spacer"></div>
      <div class="separator"></div>
      <div class="status">
        <span class="lt-led" data-state={app?.state ?? "idle"}></span>
        <span class="status-label">
          {STATE_LABEL[app?.state ?? "idle"]}
        </span>
      </div>
    </nav>

    <div class="content">
      {#if core.exited !== null}
        <div class="exited-row">
          <Notice error message="核心进程已退出" />
          <Button
            variant="raised"
            icon="refresh"
            onclick={() =>
              void restartCore().then(async () => {
                core.exited = null;
                await resync();
              })}>重启</Button
          >
        </div>
      {:else if app?.notice}
        <Notice
          message={app.notice}
          error={app.noticeIsError}
          ondismiss={() => void call("app.dismissNotice")}
        />
      {/if}

      <div
        class="scroll"
        bind:this={scrollEl}
        onscroll={updateFades}
        style:--lt-fade-top="{fadeTop}px"
        style:--lt-fade-bottom="{fadeBottom}px"
      >
        {#key currentPage}
          <div class="page">
            {#if currentPage === 0}
              <Overview onnavigate={navigate} />
            {:else if currentPage === 1}
              <Audio />
            {:else if currentPage === 2}
              <Asr bind:advanced={asrAdvanced} />
            {:else if currentPage === 3}
              <Translation />
            {:else if currentPage === 4}
              <Subtitle />
            {:else if currentPage === 5}
              <Records />
            {:else}
              <General />
            {/if}
          </div>
        {/key}
      </div>

      <footer class="footer lt-panel">
        <Icon
          name={dirty ? "settings" : "check"}
          size={16}
        />
        <span class="footer-label">
          {dirty ? "有未应用的修改" : "设置已同步"}
        </span>
        <div class="spacer"></div>
        <Button
          variant="quiet"
          disabled={!dirty || busy}
          onclick={() => void call("app.discardSettings")}>还原修改</Button
        >
        <Button
          variant="primary"
          disabled={!dirty || busy}
          onclick={() => void call("app.applySettings")}>应用设置</Button
        >
      </footer>
    </div>
  </div>

  {#if win}
    {#each EDGES as edge (edge.dir)}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="edge {edge.class}"
        style:cursor={edge.cursor}
        onpointerdown={startResize(edge.dir)}
      ></div>
    {/each}
  {/if}
</div>

<Dialog
  open={quitOpen}
  title="还有未应用的修改"
  onclose={() => (quitOpen = false)}
>
  退出将丢弃设置草稿。已应用的配置会保留。
  {#snippet actions()}
    <Button variant="raised" onclick={() => (quitOpen = false)}>返回设置</Button>
    <Button
      variant="primary"
      onclick={() => {
        quitOpen = false;
        void call("app.confirmQuit");
      }}>丢弃并退出</Button
    >
  {/snippet}
</Dialog>

<style>
  .window {
    position: fixed;
    inset: 0;
    display: flex;
    flex-direction: column;
    border-radius: 0;
    border: none;
    overflow: hidden;
  }
  :global(html[data-contrast="high"]) .window {
    border: 1px solid var(--md-sys-color-on-surface);
  }

  .titlebar {
    display: flex;
    align-items: center;
    height: 48px;
    flex: none;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
    padding-left: 22px;
    width: 226px;
    flex: none;
  }
  .app-name {
    font-size: 15px;
    font-weight: 600;
  }
  .page-title {
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    margin-left: 18px;
    white-space: nowrap;
  }
  .drag-fill {
    flex: 1;
    height: 100%;
  }
  .window-buttons {
    display: flex;
    gap: 2px;
    padding: 8px;
  }

  .body {
    flex: 1;
    display: flex;
    min-height: 0;
    padding: 0 0 12px;
  }
  .sidebar {
    width: 200px;
    margin-left: 12px;
    flex: none;
    display: flex;
    flex-direction: column;
    padding: 10px;
    gap: 4px;
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container);
    border: 1px solid var(--md-sys-color-outline-variant);
  }
  .nav {
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: none;
    background: transparent;
    font: inherit;
    font-size: 13px;
    color: var(--md-sys-color-on-surface);
    cursor: pointer;
    text-align: left;
  }
  .nav :global(.icon) {
    color: var(--md-sys-color-on-surface-variant);
  }
  .nav[aria-current="page"] :global(.icon) {
    color: var(--md-sys-color-on-secondary-container);
  }
  .spacer {
    flex: 1;
  }
  .separator {
    height: 1px;
    margin: 0 10px;
    background: var(--md-sys-color-outline-variant);
  }
  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 10px;
  }
  .status-label {
    font-size: 11px;
    color: var(--md-sys-color-on-surface-variant);
  }

  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    margin: 1px 28px 12px 28px;
    gap: 12px;
  }
  .exited-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .exited-row :global(.notice) {
    flex: 1;
  }
  .scroll {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    /* Soft fade at whichever edges still have hidden content. */
    mask-image: linear-gradient(
      180deg,
      transparent,
      #000 var(--lt-fade-top, 0px),
      #000 calc(100% - var(--lt-fade-bottom, 0px)),
      transparent
    );
  }
  @media (forced-colors: active) {
    .scroll {
      mask-image: none;
    }
  }
  .page {
    padding: 0 4px 8px 0;
    animation: page-in var(--lt-duration) var(--lt-ease);
  }
  @keyframes page-in {
    from {
      opacity: 0.35;
    }
    to {
      opacity: 1;
    }
  }

  .footer {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    height: 52px;
    padding: 8px 12px;
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container);
    border: 1px solid var(--md-sys-color-outline-variant);
  }
  .footer :global(.icon) {
    color: var(--md-sys-color-on-surface-variant);
    margin-left: 4px;
  }
  .footer-label {
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }

  .edge {
    position: fixed;
    z-index: 50;
  }
  .edge-w {
    left: 0;
    top: 7px;
    bottom: 7px;
    width: 7px;
  }
  .edge-e {
    right: 0;
    top: 7px;
    bottom: 7px;
    width: 7px;
  }
  .edge-n {
    top: 0;
    left: 7px;
    right: 7px;
    height: 7px;
  }
  .edge-s {
    bottom: 0;
    left: 7px;
    right: 7px;
    height: 7px;
  }
  .edge-nw {
    left: 0;
    top: 0;
    width: 14px;
    height: 14px;
  }
  .edge-ne {
    right: 0;
    top: 0;
    width: 14px;
    height: 14px;
  }
  .edge-sw {
    left: 0;
    bottom: 0;
    width: 14px;
    height: 14px;
  }
  .edge-se {
    right: 0;
    bottom: 0;
    width: 14px;
    height: 14px;
  }
</style>
