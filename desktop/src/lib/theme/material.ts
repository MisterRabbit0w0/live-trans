/**
 * Material 3 HCT theming: seed color → CSS custom properties.
 * Uses the TonalSpot dynamic scheme (2021 spec).
 */
import {
  argbFromHex,
  Blend,
  DynamicScheme,
  Hct,
  hexFromArgb,
  MaterialDynamicColors,
  SchemeTonalSpot,
  TonalPalette,
  type DynamicColor,
} from "@material/material-color-utilities";

export const DEFAULT_SEED = "#1767db";
const SUCCESS_HEX = "#2e9d6e";

const ROLES: Array<[string, DynamicColor]> = [
  ["primary", MaterialDynamicColors.primary],
  ["on-primary", MaterialDynamicColors.onPrimary],
  ["primary-container", MaterialDynamicColors.primaryContainer],
  ["on-primary-container", MaterialDynamicColors.onPrimaryContainer],
  ["secondary", MaterialDynamicColors.secondary],
  ["on-secondary", MaterialDynamicColors.onSecondary],
  ["secondary-container", MaterialDynamicColors.secondaryContainer],
  ["on-secondary-container", MaterialDynamicColors.onSecondaryContainer],
  ["tertiary", MaterialDynamicColors.tertiary],
  ["on-tertiary", MaterialDynamicColors.onTertiary],
  ["tertiary-container", MaterialDynamicColors.tertiaryContainer],
  ["on-tertiary-container", MaterialDynamicColors.onTertiaryContainer],
  ["error", MaterialDynamicColors.error],
  ["on-error", MaterialDynamicColors.onError],
  ["error-container", MaterialDynamicColors.errorContainer],
  ["on-error-container", MaterialDynamicColors.onErrorContainer],
  ["surface", MaterialDynamicColors.surface],
  ["surface-dim", MaterialDynamicColors.surfaceDim],
  ["surface-bright", MaterialDynamicColors.surfaceBright],
  [
    "surface-container-lowest",
    MaterialDynamicColors.surfaceContainerLowest,
  ],
  ["surface-container-low", MaterialDynamicColors.surfaceContainerLow],
  ["surface-container", MaterialDynamicColors.surfaceContainer],
  ["surface-container-high", MaterialDynamicColors.surfaceContainerHigh],
  [
    "surface-container-highest",
    MaterialDynamicColors.surfaceContainerHighest,
  ],
  ["on-surface", MaterialDynamicColors.onSurface],
  ["on-surface-variant", MaterialDynamicColors.onSurfaceVariant],
  ["outline", MaterialDynamicColors.outline],
  ["outline-variant", MaterialDynamicColors.outlineVariant],
  ["shadow", MaterialDynamicColors.shadow],
  ["scrim", MaterialDynamicColors.scrim],
  ["inverse-surface", MaterialDynamicColors.inverseSurface],
  ["inverse-on-surface", MaterialDynamicColors.inverseOnSurface],
  ["inverse-primary", MaterialDynamicColors.inversePrimary],
];

export const THEME_ROLES = ROLES.map(([name]) => name);

export const SUCCESS_TOKENS = [
  "--lt-success",
  "--lt-on-success",
  "--lt-success-container",
  "--lt-on-success-container",
] as const;

function clampTone(tone: number): number {
  return Math.min(100, Math.max(0, tone));
}

export interface ThemeOptions {
  seed: string;
  dark: boolean;
  contrast: number;
}

export function buildTheme(options: ThemeOptions): Record<string, string> {
  const seedArgb = argbFromHex(options.seed);
  const scheme = new SchemeTonalSpot(
    Hct.fromInt(seedArgb),
    options.dark,
    options.contrast,
    DynamicScheme.DEFAULT_SPEC_VERSION,
    DynamicScheme.DEFAULT_PLATFORM,
  );

  const vars: Record<string, string> = {};
  for (const [name, color] of ROLES) {
    vars[`--md-sys-color-${name}`] = hexFromArgb(color.getArgb(scheme));
  }

  // Glossy gradient stops around the resolved primary tone.
  const primaryTone = Hct.fromInt(
    MaterialDynamicColors.primary.getArgb(scheme),
  ).tone;
  vars["--lt-primary-hi"] = hexFromArgb(
    scheme.primaryPalette.tone(clampTone(primaryTone + 8)),
  );
  vars["--lt-primary-lo"] = hexFromArgb(
    scheme.primaryPalette.tone(clampTone(primaryTone - 6)),
  );

  // Harmonized custom success color.
  const successArgb = Blend.harmonize(argbFromHex(SUCCESS_HEX), seedArgb);
  const successPalette = TonalPalette.fromInt(successArgb);
  const tones = options.dark ? [80, 20, 30, 90] : [40, 100, 90, 10];
  vars["--lt-success"] = hexFromArgb(successPalette.tone(tones[0]));
  vars["--lt-on-success"] = hexFromArgb(successPalette.tone(tones[1]));
  vars["--lt-success-container"] = hexFromArgb(successPalette.tone(tones[2]));
  vars["--lt-on-success-container"] = hexFromArgb(
    successPalette.tone(tones[3]),
  );

  vars["--lt-shadow-rgb"] = "0 0 0";
  vars["--lt-rim-rgb"] = "255 255 255";
  return vars;
}
