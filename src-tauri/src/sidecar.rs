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
fn server_script() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("sidecar")
        .join("server.py")
}

fn python_exe() -> String {
    std::env::var("DASA_UI_PYTHON").unwrap_or_else(|_| "python".to_string())
}

/// Launch `python sidecar/server.py --port <port>`.
pub fn spawn(port: u16) -> std::io::Result<Child> {
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
