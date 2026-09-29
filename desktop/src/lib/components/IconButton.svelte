<script lang="ts">
  import type { MouseEventHandler } from "svelte/elements";

  import Icon from "./Icon.svelte";

  interface Props {
    icon: string;
    label: string;
    size?: number;
    iconSize?: number;
    disabled?: boolean;
    onclick?: MouseEventHandler<HTMLButtonElement>;
    [key: string]: unknown;
  }
  let {
    icon,
    label,
    size = 34,
    iconSize = 16,
    disabled = false,
    onclick,
    ...rest
  }: Props = $props();
</script>

<button
  {...rest}
  class="lt-icon-btn lt-quiet"
  style:width="{size}px"
  style:height="{size}px"
  aria-label={label}
  title={label}
  {disabled}
  {onclick}
>
  <Icon name={icon} size={iconSize} />
</button>

<style>
  .lt-icon-btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--lt-radius-sm);
    color: var(--md-sys-color-on-surface-variant);
    cursor: pointer;
    flex: none;
  }
  .lt-icon-btn:hover:not(:disabled) {
    color: var(--md-sys-color-on-surface);
  }
  .lt-icon-btn:disabled {
    color: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 38%,
      transparent
    );
    cursor: default;
  }
  .lt-icon-btn :global(.icon) {
    position: relative;
  }
</style>
