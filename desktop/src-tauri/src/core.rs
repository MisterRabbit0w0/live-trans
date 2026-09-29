//! Sidecar bridge: spawns the Python core and routes newline-delimited
//! JSON-RPC between its stdin/stdout and the webviews.
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::oneshot;
use tokio::time::timeout;

const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
const QUIT_WAIT: Duration = Duration::from_secs(5);
const SHUTDOWN_WAIT: Duration = Duration::from_secs(3);

/// What one line of core stdout means for the bridge.
#[derive(Debug)]
pub enum Routed {
    Response {
        id: u64,
        result: Result<Value, String>,
    },
    Notification {
        method: String,
        params: Value,
    },
    Empty,
    Garbage,
}

/// Parse one NDJSON line: a response resolves a pending id, an object with a
/// `method` is a notification, anything else is ignored garbage.
pub fn route_line(line: &str) -> Routed {
    let line = line.trim();
    if line.is_empty() {
        return Routed::Empty;
    }
    let Ok(value) = serde_json::from_str::<Value>(line) else {
        return Routed::Garbage;
    };
    let Some(object) = value.as_object() else {
        return Routed::Garbage;
    };
    if let Some(method) = object.get("method").and_then(Value::as_str) {
        return Routed::Notification {
            method: method.to_string(),
            params: object.get("params").cloned().unwrap_or(Value::Null),
        };
    }
    if let Some(id) = object.get("id").and_then(Value::as_u64) {
        let result = if let Some(error) = object.get("error") {
            Err(error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("core error")
                .to_string())
        } else {
            Ok(object.get("result").cloned().unwrap_or(Value::Null))
        };
        return Routed::Response { id, result };
    }
    Routed::Garbage
}

/// Pending request ids waiting for their response.
#[derive(Default)]
pub struct PendingRequests {
    inner: Mutex<HashMap<u64, oneshot::Sender<Result<Value, String>>>>,
}

impl PendingRequests {
    pub fn register(&self, id: u64) -> oneshot::Receiver<Result<Value, String>> {
        let (tx, rx) = oneshot::channel();
        self.inner.lock().unwrap().insert(id, tx);
        rx
    }

    /// Complete a pending request; false when the id is unknown.
    pub fn resolve(&self, id: u64, result: Result<Value, String>) -> bool {
        match self.inner.lock().unwrap().remove(&id) {
            Some(tx) => {
                let _ = tx.send(result);
                true
            }
            None => false,
        }
    }

    pub fn cancel(&self, id: u64) {
        self.inner.lock().unwrap().remove(&id);
    }

    pub fn fail_all(&self, message: &str) {
        for (_, tx) in self.inner.lock().unwrap().drain() {
            let _ = tx.send(Err(message.to_string()));
        }
    }
}

#[derive(Default)]
struct CoreInner {
    child: Option<Child>,
    stdin: Option<std::process::ChildStdin>,
}

/// The running Python core process and the requests in flight.
pub struct Core {
    app: AppHandle,
    inner: Mutex<CoreInner>,
    pending: PendingRequests,
    next_id: AtomicU64,
    generation: AtomicU64,
    quitting: AtomicBool,
    last_state: Mutex<Value>,
}

#[cfg(not(debug_assertions))]
fn quote_log_dir(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_log_dir().ok()
}

fn core_command(app: &AppHandle) -> Result<Command, String> {
    #[cfg(debug_assertions)]
    let _ = app;
    let mut command = if let Ok(python) = std::env::var("LIVETRANS_CORE_PYTHON") {
        let mut command = Command::new(python);
        command.arg("-m").arg("livetrans.app");
        command.current_dir(repo_root());
        command
    } else {
        #[cfg(debug_assertions)]
        {
            let root = repo_root();
            #[cfg(windows)]
            let python = root.join(".venv").join("Scripts").join("python.exe");
            #[cfg(not(windows))]
            let python = root.join(".venv").join("bin").join("python");
            let mut command = Command::new(python);
            command.arg("-m").arg("livetrans.app");
            command.current_dir(&root);
            command
        }
        #[cfg(not(debug_assertions))]
        {
            let mut binary = app
                .path()
                .resource_dir()
                .map_err(|e| e.to_string())?
                .join("livetrans-core")
                .join("livetrans-core");
            if cfg!(windows) {
                binary.set_extension("exe");
            }
            if binary.is_file() {
                Command::new(binary)
            } else {
                let root = repo_root();
                #[cfg(windows)]
                let python = root.join(".venv").join("Scripts").join("python.exe");
                #[cfg(not(windows))]
                let python = root.join(".venv").join("bin").join("python");
                if python.is_file() {
                    let mut command = Command::new(python);
                    command.arg("-m").arg("livetrans.app");
                    command.current_dir(&root);
                    command
                } else {
                    return Err(format!("核心进程不存在: {}", binary.display()));
                }
            }
        }
    };
    if std::env::var("LIVETRANS_PREVIEW").as_deref() == Ok("1") {
        command.arg("--preview");
    }
    if let Ok(config) = std::env::var("LIVETRANS_CONFIG") {
        command.arg("--config").arg(config);
    }
    command
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped());
    #[cfg(debug_assertions)]
    command.stderr(Stdio::inherit());
    #[cfg(not(debug_assertions))]
    {
        let log_dir = quote_log_dir(app).ok_or("日志目录不可用")?;
        std::fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
        let file =
            std::fs::File::create(log_dir.join("core-stderr.log")).map_err(|e| e.to_string())?;
        command.stderr(Stdio::from(file));
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    Ok(command)
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

impl Core {
    pub fn new(app: AppHandle) -> Arc<Self> {
        Arc::new(Self {
            app,
            inner: Mutex::new(CoreInner::default()),
            pending: PendingRequests::default(),
            next_id: AtomicU64::new(1),
            generation: AtomicU64::new(0),
            quitting: AtomicBool::new(false),
            last_state: Mutex::new(Value::Null),
        })
    }

    /// Spawn (or respawn) the Python core; idempotent while alive.
    pub fn spawn(self: &Arc<Self>) -> Result<(), String> {
        let mut inner = self.inner.lock().unwrap();
        if let Some(child) = inner.child.as_mut() {
            if child.try_wait().map(|s| s.is_none()).unwrap_or(false) {
                return Ok(());
            }
            let _ = child.kill();
        }
        // Requests made against the previous process can never resolve.
        self.pending.fail_all("核心进程已重启");
        self.quitting.store(false, Ordering::SeqCst);
        let mut child = core_command(&self.app)
            .and_then(|mut c| c.spawn().map_err(|e| format!("核心进程启动失败: {e}")))?;
        let stdout = child.stdout.take().ok_or("无法读取核心输出")?;
        inner.stdin = child.stdin.take();
        inner.child = Some(child);
        let generation = self.generation.fetch_add(1, Ordering::SeqCst) + 1;
        drop(inner);
        let core = Arc::clone(self);
        thread::Builder::new()
            .name("livetrans-core-reader".into())
            .spawn(move || core.read_lines(generation, stdout))
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    fn write_line(&self, line: &str) -> Result<(), String> {
        let mut inner = self.inner.lock().unwrap();
        let stdin = inner.stdin.as_mut().ok_or("核心进程未运行")?;
        stdin
            .write_all(line.as_bytes())
            .and_then(|()| stdin.write_all(b"\n"))
            .and_then(|()| stdin.flush())
            .map_err(|e| format!("写入核心失败: {e}"))
    }

    pub async fn call(&self, method: &str, params: Option<Value>) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let rx = self.pending.register(id);
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params.unwrap_or(Value::Null),
        });
        self.write_line(&request.to_string())?;
        match timeout(REQUEST_TIMEOUT, rx).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => Err("核心响应通道已断开".into()),
            Err(_) => {
                self.pending.cancel(id);
                Err("核心请求超时".into())
            }
        }
    }

    fn read_lines(&self, generation: u64, stdout: ChildStdout) {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => self.handle_line(&line),
                Err(error) => {
                    log::warn!("读取核心输出失败: {error}");
                    break;
                }
            }
        }
        self.on_exit(generation);
    }

    fn handle_line(&self, line: &str) {
        match route_line(line) {
            Routed::Empty => {}
            Routed::Garbage => log::warn!("忽略无法解析的核心输出"),
            Routed::Response { id, result } => {
                if !self.pending.resolve(id, result) {
                    log::warn!("忽略未知请求 id {id} 的响应");
                }
            }
            Routed::Notification { method, params } => self.on_notification(&method, params),
        }
    }

    fn on_notification(&self, method: &str, params: Value) {
        if let Err(error) = self.app.emit(&format!("core://{method}"), params.clone()) {
            log::warn!("转发核心通知 {method} 失败: {error}");
        }
        match method {
            "state" => {
                *self.last_state.lock().unwrap() = params.clone();
                crate::tray::sync(&self.app, &params);
                let visible = params
                    .pointer("/app/subtitleVisible")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                if let Some(window) = self.app.get_webview_window("subtitle") {
                    // show() 不主动聚焦；窗口以 focusable(false) 创建。
                    if visible {
                        let _ = window.show();
                    } else {
                        let _ = window.hide();
                    }
                }
            }
            "event" => match params.get("name").and_then(Value::as_str) {
                Some("showRequested") => show_main_window(&self.app),
                Some("notification") => {
                    let message = params
                        .pointer("/payload/message")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string();
                    use tauri_plugin_notification::NotificationExt;
                    if let Err(error) = self
                        .app
                        .notification()
                        .builder()
                        .title("LiveTrans")
                        .body(message)
                        .show()
                    {
                        log::warn!("系统通知失败: {error}");
                    }
                }
                Some("quitReady") => {
                    self.quitting.store(true, Ordering::SeqCst);
                    self.wait_then_exit();
                }
                _ => {}
            },
            _ => {}
        }
    }

    /// After `quitReady` the core closes itself; give it a moment, then exit.
    fn wait_then_exit(&self) {
        let app = self.app.clone();
        let deadline = Instant::now() + QUIT_WAIT;
        loop {
            let exited = {
                let mut inner = self.inner.lock().unwrap();
                match inner.child.as_mut() {
                    Some(child) => child.try_wait().map(|s| s.is_some()).unwrap_or(true),
                    None => true,
                }
            };
            if exited || Instant::now() >= deadline {
                break;
            }
            thread::sleep(Duration::from_millis(50));
        }
        app.exit(0);
    }

    fn on_exit(&self, generation: u64) {
        if generation != self.generation.load(Ordering::SeqCst) {
            return; // a restart already replaced this process
        }
        let code = {
            let mut inner = self.inner.lock().unwrap();
            inner.stdin = None;
            inner
                .child
                .as_mut()
                .and_then(|child| child.wait().ok().and_then(|s| s.code()))
        };
        self.pending.fail_all("核心进程已退出");
        if self.quitting.load(Ordering::SeqCst) {
            return;
        }
        let _ = self.app.emit("core://exited", json!({ "code": code }));
    }

    /// Ask the core to close, wait briefly, then kill it. Idempotent.
    pub fn shutdown_graceful(&self) {
        self.quitting.store(true, Ordering::SeqCst);
        let running = {
            let mut inner = self.inner.lock().unwrap();
            inner
                .child
                .as_mut()
                .map(|child| child.try_wait().ok().flatten().is_none())
                .unwrap_or(false)
        };
        if !running {
            return;
        }
        let request = json!({"jsonrpc": "2.0", "id": self.next_id.fetch_add(1, Ordering::SeqCst),
            "method": "app.shutdown", "params": {}});
        let _ = self.write_line(&request.to_string());
        let deadline = Instant::now() + SHUTDOWN_WAIT;
        loop {
            let exited = {
                let mut inner = self.inner.lock().unwrap();
                match inner.child.as_mut() {
                    Some(child) => child.try_wait().map(|s| s.is_some()).unwrap_or(true),
                    None => true,
                }
            };
            if exited || Instant::now() >= deadline {
                break;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let mut inner = self.inner.lock().unwrap();
        if let Some(child) = inner.child.as_mut() {
            if child.try_wait().ok().flatten().is_none() {
                let _ = child.kill();
            }
        }
    }

    pub fn last_state(&self) -> Value {
        self.last_state.lock().unwrap().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn response_resolves_pending_id() {
        let pending = PendingRequests::default();
        let mut rx = pending.register(7);
        match route_line(r#"{"jsonrpc":"2.0","id":7,"result":{"ok":true}}"#) {
            Routed::Response { id, result } => assert!(pending.resolve(id, result)),
            _ => panic!("expected response"),
        }
        assert_eq!(rx.try_recv().unwrap().unwrap()["ok"], true);
    }

    #[test]
    fn error_response_becomes_err() {
        let pending = PendingRequests::default();
        let mut rx = pending.register(3);
        match route_line(
            r#"{"jsonrpc":"2.0","id":3,"error":{"code":-32601,"message":"Method not found"}}"#,
        ) {
            Routed::Response { id, result } => assert!(pending.resolve(id, result)),
            _ => panic!("expected response"),
        }
        assert_eq!(rx.try_recv().unwrap().unwrap_err(), "Method not found");
    }

    #[test]
    fn notifications_are_routed() {
        match route_line(r#"{"jsonrpc":"2.0","method":"subtitles","params":{"entries":[]}}"#) {
            Routed::Notification { method, params } => {
                assert_eq!(method, "subtitles");
                assert_eq!(params["entries"], json!([]));
            }
            _ => panic!("expected notification"),
        }
    }

    #[test]
    fn garbage_and_blank_lines_are_ignored() {
        assert!(matches!(route_line("not json {"), Routed::Garbage));
        assert!(matches!(route_line("   "), Routed::Empty));
        assert!(matches!(route_line(r#"["a","b"]"#), Routed::Garbage));
        assert!(matches!(
            route_line(r#"{"jsonrpc":"2.0"}"#),
            Routed::Garbage
        ));
    }

    #[test]
    fn response_for_unknown_id_is_ignored() {
        let pending = PendingRequests::default();
        match route_line(r#"{"jsonrpc":"2.0","id":99,"result":null}"#) {
            Routed::Response { id, result } => assert!(!pending.resolve(id, result)),
            _ => panic!("expected response"),
        }
    }

    #[test]
    fn null_id_response_is_ignored() {
        // Parse errors come back with id null and can never match a request.
        assert!(matches!(
            route_line(
                r#"{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error"}}"#
            ),
            Routed::Garbage
        ));
    }
}
