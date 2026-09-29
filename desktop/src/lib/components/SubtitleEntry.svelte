<script lang="ts">
  interface Props {
    original: string;
    translation: string;
    showOriginal?: boolean;
    textSize?: number;
    onDark?: boolean;
  }
  let {
    original,
    translation,
    showOriginal = true,
    textSize = 22,
    onDark = false,
  }: Props = $props();

  const hasTranslation = $derived(
    translation !== "" && translation !== original,
  );
  const showSource = $derived(showOriginal && original !== "" && hasTranslation);
  const mainText = $derived(translation || original || "…");
</script>

<div class="entry" class:on-dark={onDark}>
  {#if showSource}
    <p class="original" style:font-size="{Math.max(11, textSize * 0.72)}px">
      {original}
    </p>
  {/if}
  <p class="translation" style:font-size="{textSize}px">
    {mainText}
  </p>
</div>

<style>
  .entry {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .entry p {
    margin: 0;
    overflow-wrap: break-word;
  }
  .original {
    color: var(--md-sys-color-on-surface-variant);
  }
  .translation {
    font-weight: 600;
    color: var(--md-sys-color-on-surface);
  }
  .entry.on-dark .original {
    color: #c5cedb;
  }
  .entry.on-dark .translation {
    color: #ffffff;
    text-shadow: 0 1px 2px rgb(0 0 0 / 0.6);
  }
</style>
