/**
 * Shared appearance driver for both webviews: watches the committed UI
 * settings, OS appearance and media queries, then generates the Material 3
 * theme, selects the material mode (native/css/solid) and keeps the native
 * window backdrop in sync.
 */
import { core } from "../store.svelte";
import {
  onSystemAppearance,
  setMaterial,
  systemAppearance,
  type SystemAppearance,
} from "../core";
import { buildTheme, DEFAULT_SEED } from "./material";

const QUERIES = {
  dark: "(prefers-color-scheme: dark)",
  contrast: "(prefers-contrast: more)",
  forced: "(forced-colors: active)",
  motion: "(prefers-reduced-motion: reduce)",
  transparency: "(prefers-reduced-transparency: reduce)",
} as const;

type WindowLabel = "main" | "subtitle";

/** Live OS appearance — shared so pages can render the system accent. */
export const sysAppearance = $state<SystemAppearance>({
  accent: null,
  transparency: true,
});

/** Current material mode of this window, resolved asynchronously. */
export const appearanceState = $state<{
  material: "native" | "css" | "solid";
  dark: boolean;
}>({ material: "css", dark: false });

/**
 * `materialEnabled` lets a window add its own condition on top of
 * `glassAllowed` (the subtitle window also requires opacity > 0).
 * `forceDark` makes the overlay resolve the dark scheme regardless of theme.
 */
export function initAppearance(
  windowLabel: WindowLabel,
  options: {
    materialEnabled?: () => boolean;
    forceDark?: boolean;
  } = {},
): void {
  $effect.root(() => {
    const flags = $state<Record<keyof typeof QUERIES, boolean>>({
      dark: false,
      contrast: false,
      forced: false,
      motion: false,
      transparency: false,
    });

    void systemAppearance().then((appearance) => {
      sysAppearance.accent = appearance.accent;
      sysAppearance.transparency = appearance.transparency;
    });
    void onSystemAppearance((appearance) => {
      sysAppearance.accent = appearance.accent;
      sysAppearance.transparency = appearance.transparency;
    });

    for (const key of Object.keys(QUERIES) as (keyof typeof QUERIES)[]) {
      const mq = matchMedia(QUERIES[key]);
      flags[key] = mq.matches;
      const update = () => {
        flags[key] = mq.matches;
      };
      mq.addEventListener("change", update);
    }

    const ui = $derived(core.state?.app.committed.ui);
    const dark = $derived(
      options.forceDark === true ||
        ui?.theme === "dark" ||
        (ui?.theme !== "light" && flags.dark),
    );
    const highContrast = $derived(flags.contrast || flags.forced);
    const contrast = $derived(highContrast ? 1.0 : 0);
    const seed = $derived(
      !ui?.accent || ui.accent === "system"
        ? (sysAppearance.accent ?? DEFAULT_SEED)
        : ui.accent,
    );
    const glassAllowed = $derived(
      !ui?.reduce_transparency &&
        !flags.transparency &&
        sysAppearance.transparency &&
        !highContrast,
    );
    const reduceMotion = $derived(!!ui?.reduce_motion || flags.motion);
    const materialEnabled = $derived(
      glassAllowed && (options.materialEnabled?.() ?? true),
    );

    // Regenerate and apply theme variables.
    $effect(() => {
      const vars = buildTheme({ seed, dark, contrast });
      const el = document.documentElement;
      for (const [name, value] of Object.entries(vars)) {
        el.style.setProperty(name, value);
      }
      el.style.colorScheme = dark ? "dark" : "light";
      el.dataset.theme = dark ? "dark" : "light";
      el.dataset.motion = reduceMotion ? "reduce" : "normal";
      el.dataset.contrast = highContrast ? "high" : "normal";
      appearanceState.dark = dark;
    });

    // Native material + mode bookkeeping. A sequence number keeps the latest
    // call authoritative even though setMaterial resolves asynchronously.
    let seq = 0;
    $effect(() => {
      const enabled = materialEnabled;
      const isDark = dark;
      const allowed = glassAllowed;
      const current = ++seq;
      void setMaterial(windowLabel, enabled, isDark).then((native) => {
        if (current !== seq) return;
        const material = native ? "native" : allowed ? "css" : "solid";
        document.documentElement.dataset.material = material;
        appearanceState.material = material;
      });
    });
  });
}
