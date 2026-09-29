<script lang="ts" module>
  let fieldSeq = 0;
</script>

<script lang="ts">
  import { errorFor } from "../settings";
  import IconButton from "./IconButton.svelte";
  import SettingHint from "./SettingHint.svelte";

  interface Props {
    label?: string;
    path?: string;
    hint?: string;
    value: string;
    secret?: boolean;
    disabled?: boolean;
    onchange?: (value: string) => void;
  }
  let {
    label = "",
    path = "",
    hint = "",
    value,
    secret = false,
    disabled = false,
    onchange,
  }: Props = $props();

  const uid = `lt-field-${++fieldSeq}`;
  const hintId = `${uid}-hint`;

  let focused = $state(false);
  let revealed = $state(false);
  let local = $state("");

  // Keep the user's text while focused; resync otherwise (apply/discard).
  $effect(() => {
    if (!focused) local = value;
  });

  const error = $derived(path ? errorFor(path) : "");
</script>

<div class="setting">
  {#if label}<label class="label" for={uid}>{label}</label>{/if}
  <div class="field lt-field" class:lt-error={!!error}>
    <input
      id={uid}
      data-path={path || undefined}
      type={secret && !revealed ? "password" : "text"}
      {disabled}
      value={local}
      aria-invalid={!!error || undefined}
      aria-describedby={hint || error ? hintId : undefined}
      onfocus={() => (focused = true)}
      onblur={() => (focused = false)}
      oninput={(e) => {
        local = e.currentTarget.value;
        onchange?.(local);
      }}
    />
    {#if secret}
      <IconButton
        icon={revealed ? "eye-off" : "eye"}
        label={revealed ? "隐藏密钥" : "显示密钥"}
        size={30}
        iconSize={15}
        aria-pressed={revealed}
        onclick={() => (revealed = !revealed)}
      />
    {/if}
  </div>
  <SettingHint {path} {hint} id={hintId} />
</div>

<style>
  .setting {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .label {
    font-weight: 500;
  }
  .field {
    display: flex;
    align-items: center;
    border-radius: var(--lt-radius-control);
    padding: 0 6px 0 12px;
    min-height: 40px;
  }
  input {
    flex: 1;
    min-width: 0;
    border: none;
    background: transparent;
    font: inherit;
    color: inherit;
    height: 38px;
    outline: none;
  }
</style>
