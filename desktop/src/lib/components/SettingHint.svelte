<script lang="ts">
  import { errorFor } from "../settings";

  interface Props {
    path?: string;
    hint?: string;
    id?: string;
  }
  let { path = "", hint = "", id }: Props = $props();

  const error = $derived(path ? errorFor(path) : "");
  const text = $derived(error || hint);
</script>

{#if text}
  <p class="hint" class:error={!!error} {id}>{text}</p>
{/if}

<style>
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--md-sys-color-on-surface-variant);
  }
  .hint.error {
    color: var(--md-sys-color-error);
  }
</style>
