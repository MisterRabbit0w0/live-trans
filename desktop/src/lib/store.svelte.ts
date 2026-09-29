/** Shared reactive core state for one webview (Svelte 5 runes). */
import {
  onExited,
  onState,
  onSubtitles,
  snapshot,
  type CoreState,
  type SubtitleRow,
} from "./core";

export const core = $state<{
  state: CoreState | null;
  subtitles: SubtitleRow[];
  exited: number | null;
}>({ state: null, subtitles: [], exited: null });

let started = false;

/**
 * Subscribe first, then take the snapshot: an event that arrives between
 * subscribe and snapshot resolution is newer and must not be overwritten.
 */
export async function initStore(): Promise<void> {
  if (started) return;
  started = true;
  let eventsApplied = 0;
  await onState((state) => {
    eventsApplied += 1;
    core.state = state;
  });
  await onSubtitles((entries) => {
    eventsApplied += 1;
    core.subtitles = entries;
  });
  await onExited((code) => {
    eventsApplied += 1;
    core.exited = code;
  });
  try {
    const result = await snapshot();
    if (eventsApplied === 0) {
      core.state = result.state;
      core.subtitles = result.subtitles;
    }
  } catch {
    // The core is not (re)started yet; the exited event will surface it.
  }
}

/** Re-pull the snapshot after a core restart. */
export async function resync(): Promise<void> {
  const result = await snapshot();
  core.state = result.state;
  core.subtitles = result.subtitles;
}
