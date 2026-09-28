//! Native window materials and system appearance (accent, transparency).
use serde::Serialize;
use tauri::{AppHandle, Manager, Theme, WebviewWindow};

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct SystemAppearance {
    /// System accent color as ``#rrggbb`` when the platform exposes one.
    pub accent: Option<String>,
    /// Whether the OS currently wants translucent surfaces.
    pub transparency: bool,
}

#[tauri::command]
pub fn system_appearance() -> SystemAppearance {
    query_system_appearance()
}

/// Set window theme and platform material; returns whether an effect applied.
#[tauri::command]
pub fn set_material(app: AppHandle, window: String, enabled: bool, dark: bool) -> bool {
    let Some(window) = app.get_webview_window(&window) else {
        return false;
    };
    let _ = window.set_theme(Some(if dark { Theme::Dark } else { Theme::Light }));
    if !enabled {
        let _ = window.set_effects(None::<tauri::utils::config::WindowEffectsConfig>);
        return false;
    }
    apply_effect(&window, window.label())
}

#[cfg(windows)]
fn apply_effect(window: &WebviewWindow, _label: &str) -> bool {
    use tauri::window::{Effect, EffectsBuilder};
    // Acrylic behind a transparent window requires Windows 11 (22621+).
    if windows_version::OsVersion::current().build < 22621 {
        return false;
    }
    let effects = EffectsBuilder::new().effect(Effect::Acrylic).build();
    window.set_effects(effects).is_ok()
}

#[cfg(target_os = "macos")]
fn apply_effect(window: &WebviewWindow, label: &str) -> bool {
    use tauri::window::{Effect, EffectState, EffectsBuilder};
    let (effect, state) = if label == "subtitle" {
        (Effect::HudWindow, EffectState::Active)
    } else {
        (
            Effect::UnderWindowBackground,
            EffectState::FollowsWindowActiveState,
        )
    };
    let effects = EffectsBuilder::new().effect(effect).state(state).build();
    window.set_effects(effects).is_ok()
}

#[cfg(not(any(windows, target_os = "macos")))]
fn apply_effect(_window: &WebviewWindow, _label: &str) -> bool {
    false
}

#[cfg(windows)]
fn query_system_appearance() -> SystemAppearance {
    use windows::UI::ViewManagement::{UIColorType, UISettings};
    let Ok(settings) = UISettings::new() else {
        return SystemAppearance {
            accent: None,
            transparency: true,
        };
    };
    let accent = settings
        .GetColorValue(UIColorType::Accent)
        .ok()
        .map(|c| format!("#{:02x}{:02x}{:02x}", c.R, c.G, c.B));
    let transparency = settings.AdvancedEffectsEnabled().unwrap_or(true);
    SystemAppearance {
        accent,
        transparency,
    }
}

#[cfg(target_os = "macos")]
fn query_system_appearance() -> SystemAppearance {
    use objc2_app_kit::{NSColor, NSColorSpace};
    let accent = NSColor::controlAccentColor()
        .colorUsingColorSpace(&NSColorSpace::sRGBColorSpace())
        .map(|color| {
            format!(
                "#{:02x}{:02x}{:02x}",
                (color.redComponent() * 255.0).round() as u8,
                (color.greenComponent() * 255.0).round() as u8,
                (color.blueComponent() * 255.0).round() as u8,
            )
        });
    SystemAppearance {
        accent,
        transparency: true,
    }
}

#[cfg(not(any(windows, target_os = "macos")))]
fn query_system_appearance() -> SystemAppearance {
    SystemAppearance {
        accent: None,
        transparency: true,
    }
}

/// Poll for system appearance changes and broadcast them to all webviews.
pub fn watch(app: AppHandle) {
    std::thread::Builder::new()
        .name("livetrans-appearance".into())
        .spawn(move || {
            let mut last = query_system_appearance();
            loop {
                std::thread::sleep(std::time::Duration::from_secs(2));
                let current = query_system_appearance();
                if current != last {
                    last = current.clone();
                    use tauri::Emitter;
                    let _ = app.emit("system://appearance", current);
                }
            }
        })
        .map(|_| ())
        .unwrap_or_else(|error| log::warn!("外观监听线程启动失败: {error}"));
}
