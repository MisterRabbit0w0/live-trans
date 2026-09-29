<script lang="ts">
  interface Props {
    value?: number;
    indeterminate?: boolean;
  }
  let { value = 0, indeterminate = false }: Props = $props();

  const pct = $derived(Math.min(100, Math.max(0, value * 100)));
</script>

<div
  class="bar"
  role="progressbar"
  aria-valuemin={0}
  aria-valuemax={100}
  aria-valuenow={indeterminate ? undefined : Math.round(pct)}
>
  {#if indeterminate}
    <div class="fill indeterminate"></div>
  {:else}
    <div class="fill" style:width="{pct}%"></div>
  {/if}
</div>

<style>
  .bar {
    height: 4px;
    border-radius: var(--lt-radius-xs);
    background: var(--md-sys-color-surface-container-highest);
    box-shadow: none;
    overflow: hidden;
    position: relative;
  }
  .fill {
    height: 100%;
    border-radius: var(--lt-radius-xs);
    background: var(--md-sys-color-primary);
    transition: width var(--lt-fast) var(--lt-ease);
  }
  .indeterminate {
    position: absolute;
    width: 40%;
    animation: slide 1.2s var(--lt-ease) infinite;
  }
  @keyframes slide {
    0% {
      left: -40%;
    }
    100% {
      left: 100%;
    }
  }
  :global(html[data-motion="reduce"]) .indeterminate {
    animation: none;
    left: 30%;
  }
  @media (forced-colors: active) {
    .bar {
      border: 1px solid ButtonBorder;
      box-shadow: none;
    }
    .fill {
      background: Highlight;
    }
  }
</style>
