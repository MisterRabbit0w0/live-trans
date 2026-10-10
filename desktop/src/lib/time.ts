/**
 * Session-relative timestamps for saved records.
 *
 * Utterance ``start`` values in transcript files are absolute Unix seconds;
 * the visible badge/copy text must show seconds elapsed since the session
 * origin (the ``t`` field of the leading ``session`` meta line). Older files
 * without meta fall back to the earliest utterance start.
 */

type Meta = ({ t?: unknown } & Record<string, unknown>) | null | undefined;

/** Session origin in absolute Unix seconds, or null when meta has no ``t``. */
export function sessionOrigin(meta: Meta): number | null {
  const t = meta?.t;
  return typeof t === "number" && Number.isFinite(t) ? t : null;
}

/** ``[MM:SS]`` under one hour, ``[H:MM:SS]`` above. Negative offsets clamp to 0. */
export function formatRelTime(start: number, origin: number): string {
  const rel = Math.max(0, Math.floor(start - origin));
  const s = rel % 60;
  const m = Math.floor(rel / 60) % 60;
  const h = Math.floor(rel / 3600);
  const ss = String(s).padStart(2, "0");
  const mm = String(m).padStart(2, "0");
  return h > 0 ? `[${h}:${mm}:${ss}]` : `[${mm}:${ss}]`;
}

/** Origin for entry rows: meta ``t`` or the earliest utterance start. */
export function entryOrigin(meta: Meta, entries: Array<{ start: number }>): number {
  const fromMeta = sessionOrigin(meta);
  if (fromMeta !== null) return fromMeta;
  if (entries.length === 0) return 0;
  return Math.min(...entries.map((e) => e.start));
}
