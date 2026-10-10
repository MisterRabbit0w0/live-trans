/**
 * Async ``records.summarize`` job tracking, one tracker per viewed record.
 *
 * Contract (shared with the core):
 * - ``records.summarize`` returns ``{status: "queued" | "running", mode}``
 *   immediately; the result arrives later as a ``record.summary`` event with
 *   ``{record_id, mode, status: "done" | "error", summary?, error?}``.
 * - ``records.summary`` GET ``{record_id, mode}`` restores an in-flight or
 *   finished job after navigating back to the page.
 * - Submitting the same record+mode while running returns ``running`` and
 *   must not spawn a second task.
 *
 * The bridge is injected so the tracker is testable without Tauri.
 */
import type { CoreEvent } from "./core";

export type SummaryStatus = "idle" | "running" | "done" | "error";

export interface SummaryResult {
  content: string;
  mode: string;
  model: string;
  created_at: number;
  utterance_count: number;
}

export interface SummaryJob {
  mode: string;
  status: SummaryStatus;
  error: string;
  summary: SummaryResult | null;
}

export interface SummaryBridge {
  call<T>(method: string, params?: Record<string, unknown>): Promise<T>;
  onEvent(cb: (event: CoreEvent) => void): Promise<() => void>;
}

function errorText(payload: Record<string, unknown>): string {
  const error = payload.error;
  if (typeof error === "string" && error) return error;
  if (error && typeof error === "object") {
    const message = (error as Record<string, unknown>).message;
    if (typeof message === "string" && message) return message;
  }
  return "纪要生成失败";
}

export class SummaryTracker {
  /** Currently viewed record; the tracker only tracks this record's jobs. */
  recordName = $state<string | null>(null);
  /** mode -> job for the current record. */
  jobs = $state<Record<string, SummaryJob>>({});

  private readonly bridge: SummaryBridge;
  private readonly onDone?: (mode: string, summary: SummaryResult) => void;
  private unlisten: (() => void) | null = null;

  constructor(
    bridge: SummaryBridge,
    onDone?: (mode: string, summary: SummaryResult) => void,
  ) {
    this.bridge = bridge;
    this.onDone = onDone;
  }

  /** Subscribe to ``record.summary`` events. Must run before any GET/submit. */
  async listen(): Promise<void> {
    if (this.unlisten) return;
    this.unlisten = await this.bridge.onEvent((event) => {
      if (event.name !== "record.summary") return;
      this.handle(event.payload ?? {});
    });
  }

  dispose(): void {
    this.unlisten?.();
    this.unlisten = null;
  }

  /** Switch the tracked record; unrelated in-flight jobs are dropped. */
  select(name: string | null): void {
    if (name === this.recordName) return;
    this.recordName = name;
    this.jobs = {};
  }

  job(mode: string): SummaryJob | undefined {
    return this.jobs[mode];
  }

  get runningModes(): string[] {
    return Object.keys(this.jobs).filter((m) => this.jobs[m].status === "running");
  }

  get anyRunning(): boolean {
    return this.runningModes.length > 0;
  }

  /**
   * Submit ``records.summarize``; returns false when this record+mode is
   * already running (single-flight guard).
   */
  async submit(mode: string, force = false): Promise<boolean> {
    const name = this.recordName;
    if (!name) return false;
    if (this.jobs[mode]?.status === "running") return false;
    this.jobs = {
      ...this.jobs,
      [mode]: { mode, status: "running", error: "", summary: null },
    };
    try {
      const res = (await this.bridge.call<Record<string, unknown>>(
        "records.summarize",
        { name, mode, force },
      )) ?? {};
      if (this.recordName !== name) return true;
      if (res.status === "done" && res.summary) {
        // Defensive: a synchronous core may return the finished summary.
        this.settle(mode, "done", { summary: res.summary });
      } else if (res.status === "error") {
        this.settle(mode, "error", res);
      }
      // "queued"/"running": the record.summary event carries the result.
      return true;
    } catch (err) {
      if (this.recordName === name) {
        this.settle(mode, "error", {
          error: err instanceof Error ? err.message : String(err),
        });
      }
      return true;
    }
  }

  /** Restore in-flight/finished state for a mode after navigation. */
  async refresh(mode: string): Promise<void> {
    const name = this.recordName;
    if (!name) return;
    try {
      const res = (await this.bridge.call<Record<string, unknown>>(
        "records.summary",
        { record_id: name, mode },
      )) ?? {};
      if (this.recordName !== name) return;
      const status = res.status;
      if (status === "running" || status === "done" || status === "error") {
        // A newer event already won; don't overwrite it with a stale GET.
        const existing = this.jobs[mode];
        if (existing && existing.status !== "running" && status === "running")
          return;
        this.settle(mode, status, res);
      }
    } catch {
      // Core predates records.summary, or the record vanished: leave idle.
    }
  }

  /** Handle a ``record.summary`` event payload. */
  handle(payload: Record<string, unknown>): void {
    const id = payload.record_id ?? payload.name;
    if (id !== this.recordName) return;
    let mode = typeof payload.mode === "string" ? payload.mode : "";
    if (!mode) {
      const running = this.runningModes;
      if (running.length === 1) mode = running[0];
      else return;
    }
    const status = payload.status;
    if (status === "queued" || status === "running") {
      this.settle(mode, "running", payload);
    } else if (status === "done" || status === "error") {
      this.settle(mode, status, payload);
    }
  }

  private settle(
    mode: string,
    status: SummaryStatus,
    payload: Record<string, unknown>,
  ): void {
    const summary =
      status === "done" ? ((payload.summary ?? null) as SummaryResult | null) : null;
    const job: SummaryJob = {
      mode,
      status,
      error: status === "error" ? errorText(payload) : "",
      summary,
    };
    this.jobs = { ...this.jobs, [mode]: job };
    if (status === "done" && summary) this.onDone?.(mode, summary);
  }
}
