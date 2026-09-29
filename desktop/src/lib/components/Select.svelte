<script lang="ts" module>
  let selectSeq = 0;
</script>

<script lang="ts">
  import type { Choice } from "../core";
  import { errorFor } from "../settings";
  import Icon from "./Icon.svelte";
  import SettingHint from "./SettingHint.svelte";

  interface Props {
    label?: string;
    path?: string;
    hint?: string;
    value: string;
    options: Choice[];
    editable?: boolean;
    disabled?: boolean;
    onchange?: (value: string) => void;
  }
  let {
    label = "",
    path = "",
    hint = "",
    value,
    options,
    editable = false,
    disabled = false,
    onchange,
  }: Props = $props();

  const uid = `lt-select-${++selectSeq}`;
  const hintId = `${uid}-hint`;

  let open = $state(false);
  let highlighted = $state(-1);
  let typeAhead = "";
  let typeAheadAt = 0;
  let wrapper: HTMLDivElement;
  let trigger: HTMLDivElement | undefined = $state();
  let popup: HTMLUListElement | undefined = $state();
  let popupStyle = $state("");
  let inputEl: HTMLInputElement | undefined = $state();

  $effect(() => {
    if (inputEl && document.activeElement !== inputEl) {
      inputEl.value = value;
    }
  });
  const error = $derived(path ? errorFor(path) : "");

  /** Move the popup to <body> so backdrop-filter/stacking contexts of the
      glass panels can't trap or clip a position:fixed element. */
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }
  const selectedIndex = $derived(options.findIndex((o) => o.value === value));
  const displayText = $derived(
    editable ? value : (options[selectedIndex]?.label ?? value),
  );

  function positionPopup() {
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    popupStyle = `left:${rect.left}px;top:${rect.bottom + 4}px;width:${rect.width}px`;
  }

  function show() {
    if (disabled || open) return;
    open = true;
    highlighted = selectedIndex >= 0 ? selectedIndex : 0;
    positionPopup();
    scrollHighlighted();
  }

  function hide() {
    open = false;
    typeAhead = "";
  }

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    if (inputEl) {
      inputEl.value = option.value;
    }
    onchange?.(option.value);
    hide();
  }

  function move(delta: number) {
    if (options.length === 0) return;
    highlighted =
      (((highlighted < 0 ? 0 : highlighted) + delta) % options.length +
        options.length) %
      options.length;
    scrollHighlighted();
  }

  function scrollHighlighted() {
    requestAnimationFrame(() => {
      popup
        ?.querySelector(`[data-index="${highlighted}"]`)
        ?.scrollIntoView({ block: "nearest" });
    });
  }

  function jumpTo(char: string) {
    const now = Date.now();
    typeAhead = now - typeAheadAt < 600 ? typeAhead + char : char;
    typeAheadAt = now;
    const needle = typeAhead.toLowerCase();
    const found = options.findIndex((o) =>
      o.label.toLowerCase().startsWith(needle),
    );
    if (found >= 0) {
      highlighted = found;
      scrollHighlighted();
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (editable && event.target instanceof HTMLInputElement) {
      // Typing goes to the input; navigation still works.
      if (event.key === "ArrowDown") {
        event.preventDefault();
        show();
        move(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        show();
        move(-1);
      } else if (event.key === "Enter" && open) {
        event.preventDefault();
        choose(highlighted);
      } else if (event.key === "Escape" && open) {
        event.preventDefault();
        event.stopPropagation();
        hide();
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) show();
        else move(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (!open) show();
        else move(-1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (!open) show();
        else choose(highlighted);
        break;
      case "Escape":
        if (open) {
          event.preventDefault();
          event.stopPropagation();
          hide();
        }
        break;
      case "Home":
        if (open) {
          event.preventDefault();
          highlighted = 0;
          scrollHighlighted();
        }
        break;
      case "End":
        if (open) {
          event.preventDefault();
          highlighted = options.length - 1;
          scrollHighlighted();
        }
        break;
      default:
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
          if (!open) show();
          jumpTo(event.key);
        }
    }
  }

  function onPointerDown(event: PointerEvent) {
    const target = event.target as Node;
    if (open && !wrapper.contains(target) && !popup?.contains(target)) hide();
  }

  function onFocusOut(event: FocusEvent) {
    const next = event.relatedTarget as Node | null;
    if (open && next && !wrapper.contains(next) && !popup?.contains(next)) {
      hide();
    }
  }
</script>

<svelte:window
  onpointerdown={onPointerDown}
  onresize={() => open && positionPopup()}
  onscrollcapture={() => open && positionPopup()}
/>

<div class="setting" bind:this={wrapper} onfocusout={onFocusOut}>
  {#if label}<span class="label" id="{uid}-label">{label}</span>{/if}
  {#if editable}
    <div
      role="presentation"
      class="trigger lt-field"
      class:lt-error={!!error}
      bind:this={trigger}
      onclick={(e) => {
        if (e.target !== inputEl) inputEl?.focus();
      }}
    >
      <input
        bind:this={inputEl}
        class="editable-input"
        data-path={path || undefined}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls="{uid}-popup"
        aria-labelledby={label ? `${uid}-label` : undefined}
        aria-invalid={!!error || undefined}
        aria-describedby={hint || error ? hintId : undefined}
        {disabled}
        value={value}
        onkeydown={onKeydown}
        onfocus={show}
        oninput={(e) => onchange?.(e.currentTarget.value)}
      />
      {@render chevronBtn()}
    </div>
  {:else}
    <div
      class="trigger lt-field"
      class:lt-error={!!error}
      bind:this={trigger}
      data-path={path || undefined}
      role="combobox"
      aria-expanded={open}
      aria-haspopup="listbox"
      aria-controls="{uid}-popup"
      aria-labelledby={label ? `${uid}-label` : undefined}
      aria-disabled={disabled || undefined}
      tabindex={disabled ? -1 : 0}
      onkeydown={onKeydown}
      onclick={() => (open ? hide() : show())}
    >
      <span class="value">{displayText}</span>
      {@render chevronBtn()}
    </div>
  {/if}

  {#snippet chevronBtn()}
    <button
      class="chevron"
      type="button"
      tabindex={-1}
      aria-hidden="true"
      {disabled}
      onpointerdown={(e) => e.preventDefault()}
      onclick={(e) => {
        e.stopPropagation();
        if (open) {
          hide();
        } else {
          show();
          if (editable) inputEl?.focus();
        }
      }}
    >
      <Icon name="chevron" size={16} />
    </button>
  {/snippet}

  {#if open}
    <ul
      bind:this={popup}
      use:portal
      class="popup"
      id="{uid}-popup"
      role="listbox"
      aria-labelledby={label ? `${uid}-label` : undefined}
      style={popupStyle}
      onpointerdown={(e) => e.preventDefault()}
      onmousedown={(e) => e.preventDefault()}
    >
      {#each options as option, index (option.value + '-' + index)}
        <li
          role="option"
          data-index={index}
          aria-selected={option.value === value}
          class:highlighted={index === highlighted}
          onpointerenter={() => (highlighted = index)}
          onpointerdown={(e) => {
            e.preventDefault();
            choose(index);
          }}
          onclick={() => choose(index)}
          onkeydown={(e) => {
            if (e.key === "Enter") choose(index);
          }}
        >
          {option.label}
        </li>
      {:else}
        <li class="empty" aria-hidden="true">—</li>
      {/each}
    </ul>
  {/if}
  <SettingHint {path} {hint} id={hintId} />
</div>

<style>
  .setting {
    display: flex;
    flex-direction: column;
    gap: 8px;
    position: relative;
  }
  .label {
    font-weight: 500;
  }
  .trigger {
    display: flex;
    align-items: center;
    min-height: 40px;
    border-radius: var(--lt-radius-control);
    padding: 0 6px 0 12px;
    cursor: pointer;
    position: relative;
  }
  .trigger[aria-disabled] {
    color: color-mix(
      in oklab,
      var(--md-sys-color-on-surface) 38%,
      transparent
    );
    cursor: default;
  }
  .value {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    user-select: none;
  }
  .editable-input {
    flex: 1;
    min-width: 0;
    border: none;
    background: transparent;
    font: inherit;
    color: inherit;
    padding: 0;
    height: 40px;
    outline: none;
  }
  .chevron {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: none;
    background: transparent;
    color: var(--md-sys-color-on-surface-variant);
    cursor: pointer;
    border-radius: var(--lt-radius-sm);
  }
  .popup {
    /* fixed so the popup escapes the page scroll area's overflow clipping */
    position: fixed;
    z-index: 60;
    margin: 0;
    padding: 4px;
    list-style: none;
    max-height: 270px;
    overflow-y: auto;
    border-radius: var(--lt-radius-popup);
    background: color-mix(
      in oklab,
      var(--md-sys-color-surface-container-high) 92%,
      transparent
    );
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--md-sys-color-outline-variant);
    box-shadow: 0 4px 16px -4px rgb(0 0 0 / 0.2);
  }
  :global(html[data-material="solid"]) .popup,
  :global(html[data-contrast="high"]) .popup {
    background: var(--md-sys-color-surface-container-high);
    backdrop-filter: none;
  }
  .popup li {
    padding: 8px 12px;
    border-radius: var(--lt-radius-sm);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .popup li.highlighted {
    background: var(--md-sys-color-secondary-container);
    color: var(--md-sys-color-on-secondary-container);
  }
  .popup li.empty {
    cursor: default;
    color: var(--md-sys-color-on-surface-variant);
    text-align: center;
  }
  @media (forced-colors: active) {
    .popup li[aria-selected="true"] {
      background: Highlight;
      color: HighlightText;
    }
  }
</style>
