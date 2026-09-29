import { describe, expect, it } from "vitest";

import {
  buildTheme,
  SUCCESS_TOKENS,
  THEME_ROLES,
} from "./material";

function srgbToLin(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * srgbToLin((n >> 16) & 0xff) +
    0.7152 * srgbToLin((n >> 8) & 0xff) +
    0.0722 * srgbToLin(n & 0xff)
  );
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("buildTheme", () => {
  it("emits every role plus derived tokens for light and dark", () => {
    for (const dark of [false, true]) {
      const vars = buildTheme({ seed: "#1767db", dark, contrast: 0 });
      for (const role of THEME_ROLES) {
        expect(
          vars[`--md-sys-color-${role}`],
          `--md-sys-color-${role}`,
        ).toMatch(/^#[0-9a-f]{6}$/i);
      }
      for (const token of [
        "--lt-primary-hi",
        "--lt-primary-lo",
        ...SUCCESS_TOKENS,
      ]) {
        expect(vars[token], token).toMatch(/^#[0-9a-f]{6}$/i);
      }
      expect(vars["--lt-shadow-rgb"]).toBe("0 0 0");
      expect(vars["--lt-rim-rgb"]).toBe("255 255 255");
    }
  });

  it("produces different colors for light and dark", () => {
    const light = buildTheme({ seed: "#1767db", dark: false, contrast: 0 });
    const dark = buildTheme({ seed: "#1767db", dark: true, contrast: 0 });
    expect(light["--md-sys-color-surface"]).not.toBe(
      dark["--md-sys-color-surface"],
    );
    expect(light["--md-sys-color-primary"]).not.toBe(
      dark["--md-sys-color-primary"],
    );
  });

  it("meets WCAG AAA-ish contrast at contrast level 1.0", () => {
    for (const dark of [false, true]) {
      const vars = buildTheme({ seed: "#1767db", dark, contrast: 1.0 });
      expect(
        ratio(
          vars["--md-sys-color-on-surface"],
          vars["--md-sys-color-surface"],
        ),
      ).toBeGreaterThanOrEqual(7);
      expect(
        ratio(
          vars["--md-sys-color-on-primary"],
          vars["--md-sys-color-primary"],
        ),
      ).toBeGreaterThanOrEqual(7);
    }
  });

  it("harmonizes the success color toward a far-hue seed", () => {
    const vars = buildTheme({ seed: "#c0265e", dark: false, contrast: 0 });
    expect(vars["--lt-success"].toLowerCase()).not.toBe("#2e9d6e");
  });
});
