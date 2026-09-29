import { describe, expect, it } from "vitest";

import { formatNumberField, parseNumberField } from "./NumberField.svelte";

describe("parseNumberField", () => {
  const range = { minimum: 10, maximum: 48 };

  it("accepts integers inside the range", () => {
    expect(parseNumberField("22", range)).toBe(22);
    expect(parseNumberField("10", range)).toBe(10);
    expect(parseNumberField(" 48 ", range)).toBe(48);
  });

  it("rejects out-of-range, non-numeric and empty input", () => {
    expect(parseNumberField("9", range)).toBeNull();
    expect(parseNumberField("49", range)).toBeNull();
    expect(parseNumberField("abc", range)).toBeNull();
    expect(parseNumberField("", range)).toBeNull();
    expect(parseNumberField("  ", range)).toBeNull();
  });

  it("rejects fractions on integer paths (decimals 0)", () => {
    expect(parseNumberField("22.5", range)).toBeNull();
  });

  it("accepts decimals within the allowed precision", () => {
    const opts = { minimum: 1, maximum: 30, decimals: 2 };
    expect(parseNumberField("8", opts)).toBe(8);
    expect(parseNumberField("8.5", opts)).toBe(8.5);
    expect(parseNumberField("8.25", opts)).toBe(8.25);
    expect(parseNumberField("8.255", opts)).toBeNull();
  });
});

describe("formatNumberField", () => {
  it("scales by the display factor and rounds to 2 decimals", () => {
    expect(formatNumberField(0.75, 100, 2)).toBe("75");
    expect(formatNumberField(8, 1, 2)).toBe("8");
    expect(formatNumberField(22.456, 1, 2)).toBe("22.46");
  });
});
