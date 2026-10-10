import { describe, expect, it } from "vitest";

import { entryOrigin, formatRelTime, sessionOrigin } from "./time";

describe("formatRelTime", () => {
  it("formats seconds under one hour as [MM:SS]", () => {
    expect(formatRelTime(0, 0)).toBe("[00:00]");
    expect(formatRelTime(65, 0)).toBe("[01:05]");
    expect(formatRelTime(3599.9, 0)).toBe("[59:59]");
  });

  it("formats real Unix timestamps relative to the session origin", () => {
    const t0 = 1760000000;
    expect(formatRelTime(t0 + 2.5, t0)).toBe("[00:02]");
    expect(formatRelTime(t0 + 600, t0)).toBe("[10:00]");
  });

  it("switches to [H:MM:SS] past one hour and across hours", () => {
    const t0 = 1760000000;
    expect(formatRelTime(t0 + 3600, t0)).toBe("[1:00:00]");
    expect(formatRelTime(t0 + 3661, t0)).toBe("[1:01:01]");
    expect(formatRelTime(t0 + 7322, t0)).toBe("[2:02:02]");
  });

  it("clamps negative offsets instead of rendering garbage", () => {
    expect(formatRelTime(1759999990, 1760000000)).toBe("[00:00]");
  });
});

describe("sessionOrigin", () => {
  it("reads the meta t field as the session origin", () => {
    expect(sessionOrigin({ t: 1760000000, source: "system" })).toBe(1760000000);
  });

  it("returns null when meta or t is missing or non-numeric", () => {
    expect(sessionOrigin({})).toBeNull();
    expect(sessionOrigin(null)).toBeNull();
    expect(sessionOrigin(undefined)).toBeNull();
    expect(sessionOrigin({ t: "1760000000" })).toBeNull();
  });
});

describe("entryOrigin", () => {
  it("prefers meta t when present", () => {
    const entries = [{ start: 1760000002 }, { start: 1760000010 }];
    expect(entryOrigin({ t: 1760000000 }, entries)).toBe(1760000000);
  });

  it("falls back to the earliest entry start for old files without meta", () => {
    const entries = [{ start: 1760000010 }, { start: 1760000002.5 }];
    expect(entryOrigin({}, entries)).toBe(1760000002.5);
    expect(entryOrigin(null, entries)).toBe(1760000002.5);
  });

  it("falls back formatting to the first utterance, not raw Unix seconds", () => {
    const entries = [{ start: 1760000002.5 }, { start: 1760000008 }];
    const origin = entryOrigin({}, entries);
    expect(formatRelTime(entries[0].start, origin)).toBe("[00:00]");
    expect(formatRelTime(entries[1].start, origin)).toBe("[00:05]"); // 8 − 2.5 = 5.5 → floor
    expect(formatRelTime(entries[1].start, origin)).not.toContain("29333334");
  });

  it("returns 0 for an empty record", () => {
    expect(entryOrigin({}, [])).toBe(0);
  });
});
