<script lang="ts">
  import { onMount } from "svelte";

  import Button from "../../lib/components/Button.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import Icon from "../../lib/components/Icon.svelte";
  import ProgressBar from "../../lib/components/ProgressBar.svelte";
  import { call } from "../../lib/core";
  import { readString } from "../../lib/settings";
  import { core } from "../../lib/store.svelte";

  const models = $derived(core.state?.models);

  const runtime = $derived(readString("asr.runtime").trim());
  const selected = $derived(readString("asr.model").trim());
  // "auto" resolves to the best installed model, so offer the recommended one.
  const wanted = $derived(
    selected === "auto" ? (models?.recommended ?? "") : selected,
  );
  const ready = $derived(
    selected === "auto"
      ? (models?.autoModel ?? "") !== ""
      : isInstalled(selected),
  );

  function isInstalled(name: string): boolean {
    return models?.installedNames.includes(name) ?? false;
  }

  function refresh() {
    void call("models.refresh", { runtime });
  }

  onMount(refresh);

  // Debounce refreshes when the runtime draft changes (ModelPanel.qml 600 ms).
  let first = true;
  $effect(() => {
    void runtime;
    if (first) {
      first = false;
      return;
    }
    const timer = setTimeout(refresh, 600);
    return () => clearTimeout(timer);
  });

  const statusText = $derived(
    models?.error
      ? models.error
      : models && !models.writable
        ? "该目录不可写，请改用可写的运行环境。"
        : ready
          ? selected === "auto"
            ? `自动模式将使用 ${models?.autoModel}。`
            : "所选模型已就绪。"
          : wanted
            ? `所选模型 ${wanted} 尚未下载，开始翻译前需要先下载。`
            : "",
  );
  const statusError = $derived(
    !!models?.error ||
      (!ready && !!models?.directory && !models?.busy),
  );
</script>

<GlassPanel gap={14}>
  <div class="head">
    <div class="head-text">
      <span class="title">已下载的模型</span>
      <span class="dir" title={models?.directory ?? ""}>
        {models?.directory
          ? `保存在 ${models.directory}`
          : "正在读取运行环境…"}
      </span>
    </div>
    <Button
      variant="quiet"
      icon="folder"
      disabled={!models?.directory}
      onclick={() => void call("models.openDirectory")}
    >
      打开文件夹
    </Button>
    <Button
      variant="quiet"
      icon="refresh"
      disabled={models?.busy}
      onclick={refresh}
    >
      刷新
    </Button>
  </div>

  {#each models?.installed ?? [] as model (model.name)}
    <div class="installed">
      <Icon name="check" size={16} />
      <span class="name" title={model.name}>{model.name}</span>
      <span class="size">{model.size}</span>
      <Button
        variant="quiet"
        icon="close"
        disabled={models?.busy}
        label="删除模型 {model.name}"
        onclick={() =>
          void call("models.remove", { runtime, name: model.name })}
      >
        删除
      </Button>
    </div>
  {/each}
  {#if models?.directory && models.installed.length === 0}
    <p class="empty">此运行环境中还没有模型。</p>
  {/if}

  {#if models?.state === "downloading"}
    <div class="download">
      <p class="download-text">
        正在下载 {models.target}{"  "}{models.progressText}
      </p>
      <ProgressBar
        value={Math.max(0, models.progress)}
        indeterminate={models.progress < 0}
      />
    </div>
  {/if}

  <div class="status-row">
    <p class="status" class:error={statusError}>{statusText}</p>
    {#if models?.state === "downloading"}
      <Button
        variant="raised"
        icon="stop"
        onclick={() => void call("models.cancel")}
      >
        取消下载
      </Button>
    {:else}
      <Button
        variant={ready ? "raised" : "primary"}
        icon="arrow"
        disabled={!models ||
          models.busy ||
          wanted === "" ||
          !models.writable ||
          isInstalled(wanted)}
        onclick={() => void call("models.download", { runtime, name: wanted })}
      >
        下载 {wanted}
      </Button>
    {/if}
  </div>
</GlassPanel>

<style>
  .head {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .head-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .title {
    font-weight: 500;
  }
  .dir {
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .installed {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .installed :global(.icon) {
    color: var(--lt-success);
  }
  .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .size {
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .empty {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .download-text {
    margin: 0 0 6px;
    font-size: 12px;
  }
  .status-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .status {
    flex: 1;
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    overflow-wrap: break-word;
  }
  .status.error {
    color: var(--md-sys-color-error);
  }
</style>
