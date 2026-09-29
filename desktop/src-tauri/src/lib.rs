//! LiveTrans desktop shell: two chromeless windows, a tray icon and the
//! Python core sidecar bridge.
mod appearance;
mod core;
mod tray;

use std::sync::Arc;

use serde_json::Value;
use tauri::{AppHandle, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

use crate::core::Core;

pub struct AppState {
    pub core: Arc<Core>,
    pub tray: tray::TrayParts,
}

#[tauri::command]
async fn core_call(
    state: State<'_, AppState>,
    method: String,
    params: Option<Value>,
) -> Result<Value, String> {
    state.core.call(&method, params).await
}

#[tauri::command]
async fn core_restart(state: State<'_, AppState>) -> Result<(), String> {
    state.core.spawn()
}

/// Work area of the primary monitor in physical pixels, defaulting to the
/// monitor size minus nothing when the platform cannot report it.
#[cfg(windows)]
fn work_area(app: &AppHandle) -> (i32, i32, u32, u32, f64) {
    use windows::Win32::Foundation::RECT;
    use windows::Win32::UI::WindowsAndMessaging::{
        SystemParametersInfoW, SPI_GETWORKAREA, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS,
    };
    let scale = app
        .primary_monitor()
        .ok()
        .flatten()
        .map(|m| m.scale_factor())
        .unwrap_or(1.0);
    let mut rect = RECT::default();
    let ok = unsafe {
        SystemParametersInfoW(
            SPI_GETWORKAREA,
            0,
            Some(&mut rect as *mut RECT as *mut std::ffi::c_void),
            SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0),
        )
    };
    if ok.is_ok() {
        (
            rect.left,
            rect.top,
            (rect.right - rect.left) as u32,
            (rect.bottom - rect.top) as u32,
            scale,
        )
    } else if let Ok(Some(monitor)) = app.primary_monitor() {
        let size = monitor.size();
        let pos = monitor.position();
        (pos.x, pos.y, size.width, size.height, scale)
    } else {
        (0, 0, 1920, 1080, scale)
    }
}

#[cfg(windows)]
fn set_dwm_corner_preference(window: &tauri::WebviewWindow, round: bool) {
    use windows::Win32::Graphics::Dwm::{
        DwmSetWindowAttribute, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND, DWMWCP_ROUND,
    };
    if let Ok(hwnd) = window.hwnd() {
        let preference = if round {
            DWMWCP_ROUND
        } else {
            DWMWCP_DONOTROUND
        };
        unsafe {
            let _ = DwmSetWindowAttribute(
                windows::Win32::Foundation::HWND(hwnd.0),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                &preference as *const _ as *const _,
                std::mem::size_of_val(&preference) as u32,
            );
        }
    }
}
#[cfg(not(windows))]
fn work_area(app: &AppHandle) -> (i32, i32, u32, u32, f64) {
    match app.primary_monitor() {
        Ok(Some(monitor)) => {
            let size = monitor.size();
            let pos = monitor.position();
            (
                pos.x,
                pos.y,
                size.width,
                size.height,
                monitor.scale_factor(),
            )
        }
        _ => (0, 0, 1920, 1080, 1.0),
    }
}

fn create_windows(app: &AppHandle) -> tauri::Result<()> {
    let (wx, wy, ww, wh, scale) = work_area(app);
    let to_logical = |px: f64| px / scale.max(0.5);
    let width = (to_logical(ww as f64) * 0.92).min(1040.0);
    let height = (to_logical(wh as f64) * 0.92).min(720.0);

    let main = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title("LiveTrans")
        .inner_size(width, height)
        .min_inner_size(800.0, 540.0)
        .center()
        .decorations(false)
        .transparent(true)
        .shadow(true)
        .visible(false)
        .build()?;
    #[cfg(windows)]
    set_dwm_corner_preference(&main, true);
    // Closing the control center only hides it; quitting goes through the tray.
    let main_for_close = main.clone();
    main.on_window_event(move |event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = main_for_close.hide();
        }
    });

    // Bottom-center of the work area, 100 px above its lower edge.
    let sub_width = 900.0f64;
    let sub_height = 120.0f64;
    let sub_x = to_logical(wx as f64) + (to_logical(ww as f64) - sub_width) / 2.0;
    let sub_y = to_logical(wy as f64 + wh as f64) - sub_height - to_logical(100.0);
    let sub = WebviewWindowBuilder::new(app, "subtitle", WebviewUrl::App("subtitle.html".into()))
        .title("LiveTrans 字幕")
        .inner_size(sub_width, sub_height)
        .position(sub_x, sub_y)
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .visible_on_all_workspaces(true)
        .focused(false)
        .focusable(false)
        .visible(false)
        .build()?;
    #[cfg(windows)]
    set_dwm_corner_preference(&sub, false);
    Ok(())
}

pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch just raises the first instance's control center.
            core::show_main_window(app);
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            core_call,
            core_restart,
            appearance::set_material,
            appearance::system_appearance,
        ])
        .setup(|app| {
            create_windows(app.handle())?;
            let tray = tray::build(app.handle())?;
            let core = Core::new(app.handle().clone());
            app.manage(AppState { core, tray });
            let state = app.state::<AppState>();
            if let Err(error) = state.core.spawn() {
                log::error!("核心进程启动失败: {error}");
            }
            let core = state.core.clone();
            tauri::async_runtime::spawn(async move {
                let _ = core.call("app.startup", None).await;
            });
            appearance::watch(app.handle().clone());
            Ok(())
        });

    let app = builder
        .build(tauri::generate_context!())
        .expect("无法构建 LiveTrans 桌面应用");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            handle.state::<AppState>().core.shutdown_graceful();
        }
    });
}
