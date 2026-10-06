//! core-agent 桌面壳（change 0100 / 账本 C8 壳半；change 0139 程序化开窗）。
//!
//! 壳只做三件事（ADR-0015）：**开窗口 / 挂 SPA / 启 sidecar**。窗口指向 sidecar
//! 地址 ⇒ SPA 与 Web 同源、同一份 `frontend/dist` 产物，相对路径 fetch 无需任何改写。
//!
//! **端口单点**（change 0139 / 账本 E83）：端口一律取自 `CORE_PORT`（缺省 [`DEFAULT_PORT`]），
//! 由 `main` 解析一次后**同时**供 sidecar 启动与开窗使用 ⇒ 二者不可能漂移（此前 `tauri.conf.json`
//! 硬编码 `:8000`，内核换端口即白屏）。

use std::io;
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

/// 壳与 sidecar 的共同缺省端口（`CORE_PORT` 未设时）。唯一定义处。
const DEFAULT_PORT: u16 = 8000;

/// sidecar 子进程句柄：随壳退出回收，不留孤儿后端。
struct Sidecar(Mutex<Option<Child>>);

fn resolve_port() -> u16 {
    std::env::var("CORE_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(DEFAULT_PORT)
}

/// 程序化开窗：sidecar 就绪后按**同一端口**指向本地后端（change 0139）。
fn open_window(app: &tauri::AppHandle, port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let url: tauri::Url = format!("http://127.0.0.1:{port}").parse()?;
    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("core-agent")
        .inner_size(1100.0, 760.0)
        .build()?;
    Ok(())
}

fn spawn_sidecar(port: u16) -> io::Result<Child> {
    // 与 Python 侧 `DesktopBridge._default_start` **同 argv 口径**：列表形式、不经 shell。
    // 解释器可用 `CORE_PYTHON` 覆盖（打包场景指向随包分发的 Python）。
    let python = std::env::var("CORE_PYTHON").unwrap_or_else(|_| "python".to_string());
    Command::new(python)
        .args([
            "-m",
            "core.entry",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
        ])
        .spawn()
}

/// 等 sidecar 就绪：窗口早于后端上线会白屏 ⇒ 起窗前探测端口（超时即报错，不静默）。
fn wait_ready(port: u16, timeout: Duration) -> io::Result<()> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err(io::Error::new(
        io::ErrorKind::TimedOut,
        "sidecar 未在超时内就绪",
    ))
}

fn main() {
    let port = resolve_port();
    tauri::Builder::default()
        .setup(move |app| {
            let child = spawn_sidecar(port)?;
            app.manage(Sidecar(Mutex::new(Some(child))));
            wait_ready(port, Duration::from_secs(15))?;
            open_window(app.handle(), port)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Sidecar>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
