/** Typed bridge to the Python core over the Rust shell's stdio JSON-RPC. */
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";

/** Outside Tauri (plain browser / visual QA) the mock core answers instead. */
const inTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
type Mock = typeof import("./mock");
let mockModule: Promise<Mock> | null = null;
function mock(): Promise<Mock> {
  return (mockModule ??= import("./mock"));
}

export type AppRuntimeState =
  | "idle"
  | "starting"
  | "running"
  | "paused"
  | "stopping"
  | "error";

export interface Choice {
  label: string;
  value: string;
}

/** Mirrors AppController.snapshot() — camelCase keys, secrets stripped. */
export interface CommittedConfig {
  audio_source_mode: string;
  audio_device: string;
  audio_process_name: string;
  asr: Record<string, unknown>;
  translate: Record<string, unknown>;
  subtitle: {
    font_size: number;
    show_original: boolean;
    max_lines: number;
    opacity: number;
    width: number;
  };
  ui: Record<string, unknown> & { theme: string; accent: string };
  record: { enabled: boolean };
  vad_silence_ms: number;
  vad_max_segment_s: number;
  vad_min_speech_ms: number;
}

export interface AppState {
  state: AppRuntimeState;
  statusTitle: string;
  statusDetail: string;
  busy: boolean;
  recording: boolean;
  translating?: boolean;
  translateEnabled?: boolean;
  recordEnabled?: boolean;
  subtitleVisible: boolean;
  notice: string;
  noticeIsError: boolean;
  committed: CommittedConfig;
  sourceLabel: string;
  modelLabel: string;
  sourceLanguageLabel: string;
  translationModelLabel: string;
  targetLanguageLabel: string;
  devices: Choice[];
  processes: Choice[];
  refreshing: boolean;
  discoveryError: string;
  audioHints: { system: string; app: string };
}

export interface SettingsState {
  draft: Record<string, unknown>;
  errors: Record<string, string>;
  dirty: boolean;
  targetLanguages: Choice[];
}

export interface ModelsState {
  state: "idle" | "loading" | "downloading" | "deleting";
  busy: boolean;
  error: string;
  directory: string;
  writable: boolean;
  recommended: string;
  autoModel: string;
  installed: { name: string; size: string }[];
  installedNames: string[];
  target: string;
  progress: number;
  progressText: string;
}

export interface CoreState {
  app: AppState;
  settings: SettingsState;
  models: ModelsState;
}

export interface SubtitleRow {
  id: number;
  original: string;
  translation: string;
  language: string;
}

export interface CoreEvent {
  name: string;
  payload: Record<string, unknown>;
}

export interface Snapshot {
  state: CoreState;
  subtitles: SubtitleRow[];
}

export interface SystemAppearance {
  accent: string | null;
  transparency: boolean;
}

export function call<T = null>(
  method: string,
  params?: Record<string, unknown>,
): Promise<T> {
  if (inTauri)
    return invoke<T>("core_call", { method, params: params ?? null });
  return mock().then((m) => m.call<T>(method, params));
}

export function snapshot(): Promise<Snapshot> {
  return call<Snapshot>("app.snapshot");
}

export function restartCore(): Promise<void> {
  if (inTauri) return invoke("core_restart");
  return mock().then((m) => m.restartCore());
}

/** Show/focus the control center (tray "打开控制中心" equivalent). */
export async function showControlCenter(): Promise<void> {
  if (inTauri) {
    const win = await WebviewWindow.getByLabel("main");
    if (win) {
      await win.show();
      await win.unminimize();
      await win.setFocus();
    }
    return;
  }
  await mock().then((m) => m.call("app.showControlCenter"));
}

export function setMaterial(
  window: string,
  enabled: boolean,
  dark: boolean,
): Promise<boolean> {
  if (inTauri) return invoke<boolean>("set_material", { window, enabled, dark });
  return mock().then((m) => m.setMaterial(window, enabled, dark));
}

export function systemAppearance(): Promise<SystemAppearance> {
  if (inTauri) return invoke<SystemAppearance>("system_appearance");
  return mock().then((m) => m.systemAppearance());
}

export function onState(cb: (state: CoreState) => void): Promise<UnlistenFn> {
  if (inTauri)
    return listen<CoreState>("core://state", (e) => cb(e.payload));
  return mock().then((m) => m.onState(cb));
}

export function onSubtitles(
  cb: (entries: SubtitleRow[]) => void,
): Promise<UnlistenFn> {
  if (inTauri)
    return listen<{ entries: SubtitleRow[] }>("core://subtitles", (e) =>
      cb(e.payload.entries),
    );
  return mock().then((m) => m.onSubtitles(cb));
}

export function onEvent(cb: (event: CoreEvent) => void): Promise<UnlistenFn> {
  if (inTauri)
    return listen<CoreEvent>("core://event", (e) => cb(e.payload));
  return mock().then((m) => m.onEvent(cb));
}

export function onExited(cb: (code: number | null) => void): Promise<UnlistenFn> {
  if (inTauri)
    return listen<{ code: number | null }>("core://exited", (e) =>
      cb(e.payload.code),
    );
  return mock().then((m) => m.onExited(cb));
}

export function onSystemAppearance(
  cb: (appearance: SystemAppearance) => void,
): Promise<UnlistenFn> {
  if (inTauri)
    return listen<SystemAppearance>("system://appearance", (e) =>
      cb(e.payload),
    );
  return mock().then((m) => m.onSystemAppearance(cb));
}
