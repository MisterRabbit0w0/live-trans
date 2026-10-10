import { describe, expect, it, vi } from "vitest";

import type { CoreEvent } from "./core";
import { SummaryTracker, type SummaryBridge } from "./summary.svelte";

interface Call {
  method: string;
  params?: Record<string, unknown>;
}

function fakeBridge(handlers: Record<string, (p?: Record<string, unknown>) => unknown> = {}) {
  const calls: Call[] = [];
  let eventCb: ((event: CoreEvent) => void) | null = null;
  const bridge: SummaryBridge = {
    call: async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls.push({ method, params });
      const handler = handlers[method];
      if (!handler) throw new Error(`Unknown method ${method}`);
      return handler(params) as T;
    },
    onEvent: vi.fn(async (cb: (event: CoreEvent) => void) => {
      eventCb = cb;
      return () => {
        eventCb = null;
      };
    }),
  };
  return { bridge, calls, emit: (e: CoreEvent) => eventCb?.(e) };
}

const summary = {
  content: "# 纪要",
  mode: "minutes",
  model: "fake",
  created_at: 1760000100,
  utterance_count: 4,
};

describe("SummaryTracker", () => {
  it("submit returns immediately with queued, result arrives via event", async () => {
    const { bridge, calls, emit } = fakeBridge({
      "records.summarize": () => ({ status: "queued", mode: "minutes" }),
    });
    const done: Array<[string, unknown]> = [];
    const tracker = new SummaryTracker(bridge, (m, s) => done.push([m, s]));
    await tracker.listen();
    tracker.select("a.jsonl");

    await tracker.submit("minutes");
    expect(calls).toEqual([
      { method: "records.summarize", params: { name: "a.jsonl", mode: "minutes", force: false } },
    ]);
    expect(tracker.jobs["minutes"].status).toBe("running");
    expect(done).toHaveLength(0);

    emit({
      name: "record.summary",
      payload: { record_id: "a.jsonl", mode: "minutes", status: "done", summary },
    });
    expect(tracker.jobs["minutes"].status).toBe("done");
    expect(tracker.jobs["minutes"].summary).toEqual(summary);
    expect(done).toEqual([["minutes", summary]]);
  });

  it("blocks resubmit while the same record+mode is running", async () => {
    const { bridge, calls } = fakeBridge({
      "records.summarize": () => ({ status: "queued", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");

    expect(await tracker.submit("minutes")).toBe(true);
    expect(await tracker.submit("minutes")).toBe(false);
    expect(calls).toHaveLength(1);
    // 不同模式可以并行提交
    expect(await tracker.submit("concise")).toBe(true);
    expect(calls).toHaveLength(2);
    expect(tracker.anyRunning).toBe(true);
  });

  it("surfaces error events with actionable text", async () => {
    const { bridge, emit } = fakeBridge({
      "records.summarize": () => ({ status: "queued", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");
    await tracker.submit("minutes");

    emit({
      name: "record.summary",
      payload: {
        record_id: "a.jsonl",
        mode: "minutes",
        status: "error",
        error: "转录超出纪要输入预算",
      },
    });
    expect(tracker.jobs["minutes"].status).toBe("error");
    expect(tracker.jobs["minutes"].error).toBe("转录超出纪要输入预算");
  });

  it("surfaces submit rejection as an error job", async () => {
    const { bridge } = fakeBridge({
      "records.summarize": () => {
        throw new Error("纪要服务不可用");
      },
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");
    await tracker.submit("minutes");
    expect(tracker.jobs["minutes"].status).toBe("error");
    expect(tracker.jobs["minutes"].error).toBe("纪要服务不可用");
  });

  it("restores an in-flight job via records.summary GET", async () => {
    const { bridge, calls } = fakeBridge({
      "records.summary": () => ({ status: "running", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    tracker.select("a.jsonl");
    await tracker.refresh("minutes");
    expect(calls).toEqual([
      { method: "records.summary", params: { record_id: "a.jsonl", mode: "minutes" } },
    ]);
    expect(tracker.jobs["minutes"].status).toBe("running");
  });

  it("treats unknown records.summary as idle and ignores idle", async () => {
    const { bridge } = fakeBridge({
      "records.summary": () => ({ status: "idle", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    tracker.select("a.jsonl");
    await tracker.refresh("minutes");
    expect(tracker.jobs["minutes"]).toBeUndefined();
  });

  it("ignores events for other records and drops state on select/delete", async () => {
    const { bridge, emit } = fakeBridge({
      "records.summarize": () => ({ status: "queued", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");
    await tracker.submit("minutes");

    // 别的记录的事件不污染当前视图
    emit({
      name: "record.summary",
      payload: { record_id: "b.jsonl", mode: "minutes", status: "done", summary },
    });
    expect(tracker.jobs["minutes"].status).toBe("running");

    // 删除/切换后，晚到的 a.jsonl 结果不落到新视图
    tracker.select(null);
    emit({
      name: "record.summary",
      payload: { record_id: "a.jsonl", mode: "minutes", status: "done", summary },
    });
    expect(tracker.jobs["minutes"]).toBeUndefined();

    tracker.select("b.jsonl");
    emit({
      name: "record.summary",
      payload: { record_id: "a.jsonl", mode: "minutes", status: "done", summary },
    });
    expect(tracker.jobs["minutes"]).toBeUndefined();
  });

  it("accepts a synchronous done result for older cores", async () => {
    const { bridge } = fakeBridge({
      "records.summarize": () => ({ status: "done", mode: "minutes", summary }),
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");
    await tracker.submit("minutes");
    expect(tracker.jobs["minutes"].status).toBe("done");
    expect(tracker.jobs["minutes"].summary).toEqual(summary);
  });

  it("infers the mode of an event when exactly one job is running", async () => {
    const { bridge, emit } = fakeBridge({
      "records.summarize": () => ({ status: "queued", mode: "minutes" }),
    });
    const tracker = new SummaryTracker(bridge);
    await tracker.listen();
    tracker.select("a.jsonl");
    await tracker.submit("minutes");

    emit({
      name: "record.summary",
      payload: { record_id: "a.jsonl", status: "error", error: "纪要被截断" },
    });
    expect(tracker.jobs["minutes"].status).toBe("error");
  });
});
