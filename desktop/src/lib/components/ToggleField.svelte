<script lang="ts">
  import { readBool, setValue } from "../settings";
  import Toggle from "./Toggle.svelte";

  interface Props {
    path: string;
    label: string;
    hint?: string;
    fallback?: boolean;
  }
  let { path, label, hint = "", fallback = false }: Props = $props();
</script>

<div class="row">
  <div class="text">
    <span class="label">{label}</span>
    {#if hint}<p class="hint">{hint}</p>{/if}
  </div>
  <Toggle
    checked={readBool(path, fallback)}
    {label}
    onchange={(v) => setValue(path, v)}
  />
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
  }
  .label {
    font-weight: 500;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
</style>
