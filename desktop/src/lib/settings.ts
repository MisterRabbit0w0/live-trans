/** Draft settings helpers: nested path access + validation navigation. */
import { call } from "./core";
import { core } from "./store.svelte";

export function readPath(path: string): unknown {
  let node: unknown = core.state?.settings.draft;
  for (const key of path.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

export function readString(path: string): string {
  const value = readPath(path);
  return value === undefined || value === null ? "" : String(value);
}

export function readBool(path: string, fallback = false): boolean {
  const value = readPath(path);
  return value === undefined || value === null ? fallback : Boolean(value);
}

export function readNumber(path: string): number {
  return Number(readPath(path)) || 0;
}

export function errorFor(path: string): string {
  return core.state?.settings.errors[path] ?? "";
}

/** Optimistically update the draft, then let the core push the truth. */
export function setValue(path: string, value: unknown): void {
  const draft = core.state?.settings.draft;
  if (draft) {
    const keys = path.split(".");
    let node = draft as Record<string, unknown>;
    for (const key of keys.slice(0, -1)) {
      const next = node[key];
      if (next === null || typeof next !== "object") return;
      node = next as Record<string, unknown>;
    }
    node[keys[keys.length - 1]] = value;
  }
  void call("settings.set", { path, value });
}

/** Maps a validation-failed path to the owning page index (Main.qml). */
export function pageForPath(path: string): number {
  if (path.startsWith("audio_") && !path.startsWith("audio_gain_")) return 1;
  if (path.startsWith("asr.") || path.startsWith("vad_") || path.startsWith("audio_gain_")) return 2;
  if (path.startsWith("translate.")) return 3;
  if (path.startsWith("subtitle.")) return 4;
  if (path.startsWith("record.")) return 5;
  return 6;
}

/** Whether the failing field lives inside the ASR advanced section. */
export function needsAdvanced(path: string): boolean {
  return (
    path.startsWith("vad_") ||
    path.startsWith("audio_gain_") ||
    path === "asr.device" ||
    path === "asr.runtime"
  );
}
