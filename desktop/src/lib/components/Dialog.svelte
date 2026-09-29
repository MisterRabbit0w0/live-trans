<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    open: boolean;
    title: string;
    onclose?: () => void;
    children?: Snippet;
    actions?: Snippet;
  }
  let { open, title, onclose, children, actions }: Props = $props();

  let box: HTMLElement | undefined = $state();
  let restoreTo: HTMLElement | null = null;

  $effect(() => {
    if (open) {
      restoreTo = document.activeElement as HTMLElement | null;
      requestAnimationFrame(() => {
        const target =
          box?.querySelector<HTMLElement>("button:not([disabled])") ?? box;
        target?.focus();
      });
    } else if (restoreTo) {
      restoreTo.focus();
      restoreTo = null;
    }
  });

  function onKeydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onclose?.();
      return;
    }
    if (event.key !== "Tab" || !box) return;
    const focusable = Array.from(
      box.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute("disabled"));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <div class="scrim">
    <div
      bind:this={box}
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabindex={-1}
    >
      <h2>{title}</h2>
      <div class="body">{@render children?.()}</div>
      {#if actions}<div class="actions">{@render actions()}</div>{/if}
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(
      in oklab,
      var(--md-sys-color-scrim) 40%,
      transparent
    );
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }
  :global(html[data-material="solid"]) .scrim,
  :global(html[data-contrast="high"]) .scrim {
    backdrop-filter: none;
  }
  .dialog {
    width: 360px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    border-radius: var(--lt-radius-card);
    background: var(--md-sys-color-surface-container-high);
    border: 1px solid var(--md-sys-color-outline-variant);
    box-shadow: 0 12px 32px -4px rgb(0 0 0 / 0.28);
  }
  :global(html[data-contrast="high"]) .dialog {
    border: 2px solid var(--md-sys-color-outline);
    box-shadow: none;
  }
  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }
  .body {
    color: var(--md-sys-color-on-surface-variant);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
