<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    padding?: number;
    gap?: number;
    class?: string;
    children?: Snippet;
  }
  let { padding = 20, gap = 12, class: cls = "", children }: Props = $props();
</script>

<section
  class="lt-panel glass panel {cls}"
  style:padding="{padding}px"
  style:gap="{gap}px"
>
  {@render children?.()}
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
  }
</style>
