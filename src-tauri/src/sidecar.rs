//! Python sidecar lifecycle: pick a free port, spawn the FastAPI server,
//! check readiness, and kill it on app exit.

use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Managed Tauri state: the sidecar port and its child process handle.
pub struct Sidecar {
    pub port: u16,
    pub child: Mutex<Option<Child>>,
}

/// Ask the OS for an unused TCP port by binding to :0 and reading it back.
pub fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

/// Path to sidecar/server.py. In dev it sits next to src-tauri/.
/// In production, the PyInstaller-built binary is in the app's resource dir.
fn server_script() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("sidecar")
        .join("server.py")
}

/// In production, the sidecar is bundled as a PyInstaller exe.
/// Tauri resolves it via the externalBin mechanism with target-triple suffix.
fn sidecar_binary() -> Option<PathBuf> {
    let target = if cfg!(target_os = "windows") {
        "kamvex-sidecar-x86_64-pc-windows-msvc.exe"
    } else if cfg!(target_os = "macos") {
        "kamvex-sidecar-aarch64-apple-darwin"
    } else {
        "kamvex-sidecar-x86_64-unknown-linux-gnu"
    };

    // Check resource dir (production)
    if let Ok(res) = std::env::var("TAURI_RESOURCE_DIR") {
        let p = PathBuf::from(res).join(target);
        if p.exists() {
            return Some(p);
        }
    }

    // Check dev binaries dir
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("binaries")
        .join(target);
    if dev.exists() {
        return Some(dev);
    }

    None
}

fn python_exe() -> String {
    std::env::var("DASA_UI_PYTHON").unwrap_or_else(|_| "python".to_string())
}

/// Launch the sidecar. In production, uses the PyInstaller binary.
/// In dev, uses `python sidecar/server.py`.
pub fn spawn(port: u16) -> std::io::Result<Child> {
    if let Some(bin) = sidecar_binary() {
        return Command::new(&bin)
            .arg("--port")
            .arg(port.to_string())
            .spawn();
    }
    Command::new(python_exe())
        .arg(server_script())
        .arg("--port")
        .arg(port.to_string())
        .spawn()
}

/// True once something is listening on the sidecar port (uvicorn is up).
pub fn port_open(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}").parse().expect("valid loopback addr");
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

/// Block until the port is open or `timeout` elapses.
#[allow(dead_code)]
pub fn wait_ready(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if port_open(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spawn_ready_kill() {
        let port = free_port();
        let mut child = spawn(port).expect("failed to spawn sidecar");
        // First import (uvicorn + dasa/shard) can take a while; allow generously.
        let ready = wait_ready(port, Duration::from_secs(60));
        let _ = child.kill();
        let _ = child.wait();
        assert!(ready, "sidecar never opened port {port}");
    }
}
