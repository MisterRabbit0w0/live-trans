//! System tray icon and menu, driven by the core's cached state.
use serde_json::Value;
use tauri::menu::{MenuBuilder, MenuItem, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Wry};

use crate::core::{show_main_window, Core};
use crate::AppState;

/// Menu items whose labels/enabled state follow the core snapshot.
pub struct TrayParts {
    pub tray: TrayIcon<Wry>,
    pub pause: MenuItem<Wry>,
    pub stop: MenuItem<Wry>,
    pub subtitles: MenuItem<Wry>,
}

fn call_core(core: &std::sync::Arc<Core>, method: &'static str) {
    let core = core.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(error) = core.call(method, None).await {
            log::warn!("托盘操作 {method} 失败: {error}");
        }
    });
}

pub fn build(app: &AppHandle) -> tauri::Result<TrayParts> {
    let open = MenuItemBuilder::with_id("open", "打开控制中心").build(app)?;
    let pause = MenuItemBuilder::with_id("pause", "开始翻译").build(app)?;
    let stop = MenuItemBuilder::with_id("stop", "停止翻译")
        .enabled(false)
        .build(app)?;
    let subtitles = MenuItemBuilder::with_id("subtitles", "显示字幕").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "退出 LiveTrans").build(app)?;
    let menu = MenuBuilder::new(app)
        .item(&open)
        .separator()
        .item(&pause)
        .item(&stop)
        .item(&subtitles)
        .separator()
        .item(&quit)
        .build()?;

    let mut builder = TrayIconBuilder::with_id("livetrans-tray")
        .tooltip("LiveTrans")
        .menu(&menu)
        // Windows/Linux: left click shows the window; macOS opens the menu.
        .show_menu_on_left_click(cfg!(target_os = "macos"))
        .on_menu_event(|app, event| {
            let core = app.state::<AppState>().core.clone();
            match event.id().as_ref() {
                "open" => show_main_window(app),
                "pause" => call_core(&core, "app.togglePause"),
                "stop" => call_core(&core, "app.stop"),
                "subtitles" => call_core(&core, "app.toggleSubtitles"),
                "quit" => call_core(&core, "app.requestQuit"),
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    let tray = builder.build(app)?;
    Ok(TrayParts {
        tray,
        pause,
        stop,
        subtitles,
    })
}

/// Reflect the latest core state into tray tooltip and item enablement.
pub fn sync(app: &AppHandle, params: &Value) {
    let Some(state) = app.try_state::<AppState>() else {
        return;
    };
    let app_state = &params["app"];
    let status = app_state["state"].as_str().unwrap_or("idle");
    let busy = app_state["busy"].as_bool().unwrap_or(false);
    let title = app_state["statusTitle"].as_str().unwrap_or("LiveTrans");
    let _ = state
        .tray
        .tray
        .set_tooltip(Some(format!("LiveTrans · {title}")));
    let pause_text = match status {
        "running" => "暂停翻译",
        "paused" => "继续翻译",
        _ => "开始翻译",
    };
    let _ = state.tray.pause.set_text(pause_text);
    let _ = state.tray.pause.set_enabled(!busy);
    let _ = state.tray.stop.set_enabled(matches!(
        status,
        "starting" | "running" | "paused" | "error"
    ));
    let subtitle_visible = app_state["subtitleVisible"].as_bool().unwrap_or(false);
    let _ = state.tray.subtitles.set_text(if subtitle_visible {
        "隐藏字幕"
    } else {
        "显示字幕"
    });
}
