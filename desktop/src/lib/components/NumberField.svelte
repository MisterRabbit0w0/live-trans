<script lang="ts" module>
  let numSeq = 0;

  /** Mirrors NumberSetting.qml's DoubleValidator rules (locale "C"). */
  export function parseNumberField(
    text: string,
    opts: { minimum: number; maximum: number; decimals?: number },
  ): number | null {
    const trimmed = text.trim();
    if (trimmed === "") return null;
    const value = Number(trimmed);
    if (!Number.isFinite(value)) return null;
    if (value < opts.minimum || value > opts.maximum) return null;
    const decimals = opts.decimals ?? 0;
    const scaled = value * 10 ** decimals;
    if (Math.abs(scaled - Math.round(scaled)) > 1e-9) return null;
    return value;
  }

  export function formatNumberField(
    stored: number,
    factor: number,
    decimals: number,
  ): string {
    const shown = stored * factor;
    return String(Math.round(shown * 100) / 100);
  }
</script>

<script lang="ts">
  import { errorFor } from "../settings";
  import SettingHint from "./SettingHint.svelte";

  interface Props {
    label?: string;
    path?: string;
    hint?: string;
    suffix?: string;
    value: number;
    minimum?: number;
    maximum?: number;
    step?: number;
    factor?: number;
    decimals?: number;
    disabled?: boolean;
    onchange?: (value: number) => void;
  }
  let {
    label = "",
    path = "",
    hint = "",
    suffix = "",
    value,
    minimum = 0,
    maximum = 100,
    step = 1,
    factor = 1,
    decimals = 0,
    disabled = false,
    onchange,
  }: Props = $props();

  const uid = `lt-num-${++numSeq}`;
  const hintId = `${uid}-hint`;

  let focused = $state(false);
  let local = $state("");

  const shown = $derived(formatNumberField(value, factor, decimals));
  const error = $derived(path ? errorFor(path) : "");

  $effect(() => {
    if (!focused) local = shown;
  });

  const fill = $derived(
    maximum > minimum
      ? ((Math.min(maximum, Math.max(minimum, value * factor)) - minimum) /
          (maximum - minimum)) *
          100
      : 0,
  );

  function commit(text: string): boolean {
    const parsed = parseNumberField(text, { minimum, maximum, decimals });
    if (parsed === null) return false;
    onchange?.(parsed / factor);
    return true;
  }
</script>

<div class="setting">
  {#if label}<span class="label" id="{uid}-label">{label}</span>{/if}
  <div class="row">
    <input
      class="slider"
      type="range"
      aria-labelledby={label ? `${uid}-label` : undefined}
      min={minimum}
      max={maximum}
      {step}
      {disabled}
      value={value * factor}
      style:--fill="{fill}%"
      oninput={(e) =>
        onchange?.(Number(e.currentTarget.value) / factor)}
    />
    <input
      id={uid}
      class="number lt-field"
      class:lt-error={!!error}
      data-path={path || undefined}
      inputmode="decimal"
      aria-labelledby={label ? `${uid}-label` : undefined}
      aria-invalid={!!error || undefined}
      aria-describedby={hint || error ? hintId : undefined}
      {disabled}
      value={focused ? local : shown}
      onfocus={() => {
        focused = true;
        local = shown;
      }}
      oninput={(e) => {
        local = e.currentTarget.value;
        commit(local);
      }}
      onblur={() => {
        if (!commit(local)) local = shown;
        focused = false;
      }}
      onkeydown={(e) => {
        if (e.key === "Enter") {
          if (!commit(local)) local = shown;
        }
      }}
    />
    {#if suffix}<span class="suffix">{suffix}</span>{/if}
  </div>
  <SettingHint {path} {hint} id={hintId} />
</div>

<style>
  .setting {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .label {
    font-weight: 500;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .slider {
    flex: 1;
    appearance: none;
    -webkit-appearance: none;
    height: 20px;
    background: transparent;
    cursor: pointer;
  }
  .slider::-webkit-slider-runnable-track {
    height: 4px;
    border-radius: var(--lt-radius-xs);
    background:
      linear-gradient(
        var(--md-sys-color-primary),
        var(--md-sys-color-primary)
      )
      0 / var(--fill, 0%) 100% no-repeat,
      var(--md-sys-color-surface-container-highest);
    box-shadow: none;
  }
  .slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    border-radius: var(--lt-radius-full);
    border: 2px solid var(--md-sys-color-primary);
    background: var(--md-sys-color-surface);
    box-shadow: none;
    transition: transform var(--lt-fast) var(--lt-ease);
  }
  .slider::-webkit-slider-thumb:hover {
    transform: scale(1.15);
  }
  .slider:focus-visible {
    outline: none;
  }
  .slider:focus-visible::-webkit-slider-thumb {
    outline: 2px solid var(--md-sys-color-primary);
    outline-offset: 2px;
  }
  .slider:disabled {
    cursor: default;
  }
  .slider:disabled::-webkit-slider-runnable-track {
    background: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 12%,
      transparent
    );
    box-shadow: none;
  }
  .slider:disabled::-webkit-slider-thumb {
    background: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 38%,
      transparent
    );
    box-shadow: none;
  }
  @media (forced-colors: active) {
    .slider::-webkit-slider-runnable-track {
      background: ButtonFace;
      border: 1px solid ButtonBorder;
      box-shadow: none;
    }
    .slider::-webkit-slider-thumb {
      background: ButtonText;
      border: 1px solid ButtonFace;
      box-shadow: none;
    }
    .slider:disabled::-webkit-slider-thumb {
      background: GrayText;
    }
  }
  .number {
    width: 72px;
    height: 38px;
    border-radius: var(--lt-radius-control);
    text-align: center;
    font-size: 13px;
    font-family: inherit;
    color: inherit;
  }
  .number:focus {
    outline: none;
  }
  .suffix {
    width: 24px;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
    flex: none;
  }
</style>
