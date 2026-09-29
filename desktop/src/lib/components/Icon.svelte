<script lang="ts" module>
  // Exact path set ported from Icon.qml (stroke currentColor, width 1.65).
  export const ICON_PATHS: Record<string, string> = {
    overview:
      '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    audio: '<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>',
    mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 10v2a6 6 0 0 0 12 0v-2M12 18v3M9 21h6"/>',
    translate:
      '<path d="M3 5h12M9 3v2M6 5c0 7 6 10 6 10M13 5c0 7-9 11-9 11M14 21l4-11 4 11M16 17h4"/>',
    subtitles:
      '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h10M7 14h4M14 14h3"/>',
    settings:
      '<path d="M4 6h16M4 12h16M4 18h16"/><rect x="7" y="4" width="3" height="4" rx="1"/><rect x="14" y="10" width="3" height="4" rx="1"/><rect x="8" y="16" width="3" height="4" rx="1"/>',
    play: '<path d="m8 5 11 7-11 7Z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    refresh:
      '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
    check: '<path d="m5 12 4 4 10-10"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    minus: '<path d="M5 12h14"/>',
    maximize: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    chevron: '<path d="m8 10 4 4 4-4"/>',
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    folder: '<path d="M3 7V5h7l2 3h9v12H3Z"/>',
    // Glyphs added for the Svelte port, same stroke style.
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off":
      '<path d="m3 3 18 18"/><path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a17.5 17.5 0 0 1-2.7 3.6M6.6 6.6C4 8.5 2 12 2 12s3.5 7 10 7a9.9 9.9 0 0 0 4.4-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    auto: '<circle cx="12" cy="12" r="8.5"/><path d="m8.6 15.5 3.4-7 3.4 7M9.9 12.9h4.2"/>',
    document:
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    sparkles:
      '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    copy:
      '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    trash:
      '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    download:
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    history:
      '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  };
</script>

<script lang="ts">
  interface Props {
    name?: string;
    size?: number;
  }
  let { name = "overview", size = 20 }: Props = $props();
</script>

<svg
  class="icon"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.65"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {@html ICON_PATHS[name] ?? ICON_PATHS.overview}
</svg>

<style>
  .icon {
    display: block;
    flex: none;
  }
</style>
