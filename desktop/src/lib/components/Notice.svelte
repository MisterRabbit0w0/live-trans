<script lang="ts">
  import Button from "./Button.svelte";

  interface Props {
    message: string;
    error?: boolean;
    ondismiss?: () => void;
  }
  let { message, error = false, ondismiss }: Props = $props();
</script>

<div
  class="notice"
  class:error
  role={error ? "alert" : "status"}
>
  <span class="text">{message}</span>
  <Button variant="quiet" onclick={() => ondismiss?.()}>关闭</Button>
</div>

<style>
  .notice {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: var(--lt-radius-control);
    background: var(--md-sys-color-secondary-container);
    color: var(--md-sys-color-on-secondary-container);
    border: 1px solid color-mix(in oklab, var(--md-sys-color-secondary-container) 80%, black);
    font-size: 13px;
  }
  .notice.error {
    background: var(--md-sys-color-error-container);
    color: var(--md-sys-color-on-error-container);
    border-color: color-mix(in oklab, var(--md-sys-color-error) 40%, transparent);
  }
  .text {
    flex: 1;
  }
</style>
