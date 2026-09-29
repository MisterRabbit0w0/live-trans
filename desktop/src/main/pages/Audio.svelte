<script lang="ts">
  import Button from "../../lib/components/Button.svelte";
  import GlassPanel from "../../lib/components/GlassPanel.svelte";
  import PageHeading from "../../lib/components/PageHeading.svelte";
  import Select from "../../lib/components/Select.svelte";
  import { call } from "../../lib/core";
  import { readString, setValue } from "../../lib/settings";
  import { core } from "../../lib/store.svelte";

  const app = $derived(core.state?.app);
  const mode = $derived(readString("audio_source_mode"));

  const SOURCE_OPTIONS = [
    { label: "整个系统", value: "system" },
    { label: "指定软件", value: "process" },
  ];
</script>

<div class="page-col">
  <PageHeading title="声音来源" subtitle="捕获系统声音，或指定一个应用。" />

  <GlassPanel>
    <Select
      label="捕获范围"
      path="audio_source_mode"
      value={mode}
      options={SOURCE_OPTIONS}
      onchange={(v) => setValue("audio_source_mode", v)}
    />
    {#if mode === "system"}
      <Select
        label="输出设备"
        path="audio_device"
        value={readString("audio_device")}
        options={app?.devices ?? []}
        hint={app?.audioHints.system ?? ""}
        onchange={(v) => setValue("audio_device", v)}
      />
    {:else if mode === "process"}
      <Select
        label="目标软件"
        path="audio_process_name"
        editable
        value={readString("audio_process_name")}
        options={app?.processes ?? []}
        hint={app?.audioHints.app ?? ""}
        onchange={(v) => setValue("audio_process_name", v)}
      />
    {/if}
    <div class="discovery">
      <p class="discovery-text" class:error={!!app?.discoveryError}>
        {app?.discoveryError || "设备变更后，刷新列表并重新选择。"}
      </p>
      <Button
        variant="raised"
        icon="refresh"
        disabled={app?.refreshing}
        onclick={() => void call("app.refreshDevices")}
      >
        {app?.refreshing ? "正在刷新…" : "刷新列表"}
      </Button>
    </div>
  </GlassPanel>

  <p class="footnote">声音来源的修改将在应用设置后生效。</p>
</div>

<style>
  .page-col {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }
  .discovery {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .discovery-text {
    flex: 1;
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .discovery-text.error {
    color: var(--md-sys-color-error);
  }
  .footnote {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-outline);
  }
</style>
