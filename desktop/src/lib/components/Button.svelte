<script lang="ts">
  import type { Snippet } from "svelte";
  import type { MouseEventHandler } from "svelte/elements";

  import Icon from "./Icon.svelte";

  interface Props {
    variant?: "primary" | "raised" | "quiet";
    icon?: string;
    disabled?: boolean;
    label?: string;
    onclick?: MouseEventHandler<HTMLButtonElement>;
    children?: Snippet;
    [key: string]: unknown;
  }
  let {
    variant = "raised",
    icon = "",
    disabled = false,
    label = "",
    onclick,
    children,
    ...rest
  }: Props = $props();
</script>

<button
  {...rest}
  class="lt-btn"
  class:lt-primary={variant === "primary"}
  class:lt-raised={variant === "raised"}
  class:lt-quiet={variant === "quiet"}
  aria-label={label || undefined}
  {disabled}
  {onclick}
>
  {#if icon}<Icon name={icon} size={16} />{/if}
  <span class="btn-label">{@render children?.()}</span>
</button>

<style>
  .lt-btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    min-height: 36px;
    padding: 0 16px;
    border: none;
    border-radius: var(--lt-radius-control);
    font: inherit;
    font-weight: 500;
    color: var(--md-sys-color-on-surface);
    cursor: pointer;
    white-space: nowrap;
  }
  /* Variant colors live here — scoped selectors need the extra class weight
     to beat the unscoped variant rules in skeuo.css. */
  .lt-btn.lt-primary {
    color: var(--md-sys-color-on-primary);
  }
  .lt-quiet {
    color: var(--md-sys-color-on-surface-variant);
  }
  .lt-quiet:hover:not(:disabled) {
    color: var(--md-sys-color-on-surface);
  }
  /* Material disabled treatment — flat fill, faded content, no effects. */
  .lt-btn:disabled {
    cursor: default;
    color: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 38%,
      transparent
    );
  }
  .lt-btn.lt-raised:disabled,
  .lt-btn.lt-primary:disabled {
    background: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 12%,
      transparent
    );
    border-color: transparent;
    box-shadow: none;
  }
  .lt-btn.lt-quiet:disabled {
    background: transparent;
  }
  .btn-label {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }
  .lt-btn :global(.icon) {
    position: relative;
  }
</style>
