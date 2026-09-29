<script lang="ts">
  interface Props {
    checked: boolean;
    label?: string;
    disabled?: boolean;
    onchange?: (checked: boolean) => void;
    [key: string]: unknown;
  }
  let { checked, label = "", disabled = false, onchange, ...rest }: Props =
    $props();
</script>

<button
  {...rest}
  type="button"
  role="switch"
  class="toggle"
  class:on={checked}
  aria-checked={checked}
  aria-label={label || undefined}
  {disabled}
  onclick={() => onchange?.(!checked)}
>
  <span class="track">
    <span class="knob"></span>
  </span>
</button>

<style>
  .toggle {
    border: none;
    background: transparent;
    padding: 3px 1px;
    cursor: pointer;
    flex: none;
  }
  .toggle:disabled {
    cursor: default;
  }
  .toggle:disabled .track {
    background: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 12%,
      transparent
    );
    border-color: transparent;
    box-shadow: none;
  }
  .toggle:disabled .knob {
    background: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 38%,
      transparent
    );
    box-shadow: none;
  }
  .track {
    display: block;
    position: relative;
    width: 44px;
    height: 24px;
    border-radius: var(--lt-radius-full);
    background: var(--md-sys-color-surface-container-highest);
    border: 1px solid var(--md-sys-color-outline-variant);
    box-shadow: none;
    transition:
      background-color var(--lt-fast) var(--lt-ease),
      border-color var(--lt-fast) var(--lt-ease);
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 18px;
    height: 18px;
    border-radius: var(--lt-radius-full);
    background: var(--md-sys-color-outline);
    box-shadow: none;
    transition:
      transform var(--lt-fast) var(--lt-ease),
      background-color var(--lt-fast) var(--lt-ease);
  }
  .toggle.on .track {
    background: var(--md-sys-color-primary);
    border-color: var(--md-sys-color-primary);
    box-shadow: none;
  }
  .toggle.on .knob {
    background: var(--md-sys-color-on-primary);
    transform: translateX(20px);
    box-shadow: none;
  }
  :global(html[data-contrast="high"]) .track {
    border-color: var(--md-sys-color-outline);
    box-shadow: none;
  }
  :global(html[data-contrast="high"]) .toggle.on .track {
    background: var(--md-sys-color-primary);
  }
  @media (forced-colors: active) {
    .track {
      background: ButtonFace;
      border-color: ButtonText;
      box-shadow: none;
    }
    .knob {
      background: ButtonText;
      box-shadow: none;
    }
    .toggle.on .track {
      background: Highlight;
      border-color: Highlight;
    }
    .toggle.on .knob {
      background: HighlightText;
    }
    .toggle:disabled .track {
      border-color: GrayText;
    }
    .toggle:disabled .knob {
      background: GrayText;
    }
  }
</style>
