<script lang="ts">
  interface Props {
    title: string;
    subtitle?: string;
  }
  let { title, subtitle = "" }: Props = $props();
</script>

<header class="heading">
  <h1>{title}</h1>
  {#if subtitle}<p>{subtitle}</p>{/if}
</header>

<style>
  .heading h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .heading p {
    margin: 6px 0 0;
    color: var(--md-sys-color-on-surface-variant);
  }
</style>
