import { describe, expect, it } from "vitest";

import { needsAdvanced, pageForPath } from "./settings";

describe("pageForPath", () => {
  it("maps paths to their owning page", () => {
    expect(pageForPath("audio_source_mode")).toBe(1);
    expect(pageForPath("audio_device")).toBe(1);
    expect(pageForPath("asr.backend")).toBe(2);
    expect(pageForPath("asr.language")).toBe(2);
    expect(pageForPath("vad_silence_ms")).toBe(2);
    expect(pageForPath("translate.base_url")).toBe(3);
    expect(pageForPath("translate.model")).toBe(3);
    expect(pageForPath("subtitle.font_size")).toBe(4);
    expect(pageForPath("record.enabled")).toBe(5);
    expect(pageForPath("ui.theme")).toBe(6);
    expect(pageForPath("anything.else")).toBe(6);
  });
});

describe("needsAdvanced", () => {
  it("detects fields inside the ASR advanced section", () => {
    expect(needsAdvanced("vad_silence_ms")).toBe(true);
    expect(needsAdvanced("vad_max_segment_s")).toBe(true);
    expect(needsAdvanced("vad_min_speech_ms")).toBe(true);
    expect(needsAdvanced("asr.device")).toBe(true);
    expect(needsAdvanced("asr.runtime")).toBe(true);
    expect(needsAdvanced("asr.backend")).toBe(false);
    expect(needsAdvanced("asr.language")).toBe(false);
    expect(needsAdvanced("translate.model")).toBe(false);
  });
});
