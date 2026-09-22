//! Python sidecar lifecycle: pick a free port, spawn the FastAPI server,
//! check readiness, and kill it on app exit.
//!
//! Resolution order (first hit wins):
//!   1. `KAMVEX_SIDECAR_BIN`         explicit executable
//!   2. dev builds: `sidecar/server.py` with the interpreter from `KAMVEX_PYTHON`
//!      (or `python`), unless `KAMVEX_USE_SIDECAR_BIN=1`
//!   3. the bundled PyInstaller exe next to the app (`kamvex-sidecar[.exe]`,
//!      Tauri strips the target-triple suffix when it copies `externalBin`)
//!   4. `sidecar/server.py` next to the executable (running a release build from the repo)

use std::fs;
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

const SIDECAR_NAME: &str = "kamvex-sidecar";

/// Managed Tauri state: the sidecar port and its child process handle.
pub struct Sidecar {
    pub port: u16,
    pub child: Mutex<Option<Child>>,
    /// How the sidecar was launched ("python:…", "binary:…") or the launch error.
    pub launch: String,
    pub log_path: Option<PathBuf>,
}

/// Directories and binaries the sidecar must know about (passed as env vars).
#[derive(Clone, Debug, Default)]
pub struct SidecarEnv {
    pub data_dir: PathBuf,
    pub models_dir: PathBuf,
    pub binaries_dir: PathBuf,
    pub llama_server: Option<PathBuf>,
}

#[derive(serde::Serialize, Clone, Debug)]
pub struct SidecarStatus {
    pub port: u16,
    pub running: bool,
    pub ready: bool,
    pub launch: String,
    pub pid: Option<u32>,
    pub log_path: Option<String>,
}

/// Ask the OS for an unused TCP port by binding to :0 and reading it back.
pub fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn exe_name(base: &str) -> String {
    if cfg!(target_os = "windows") { format!("{base}.exe") } else { base.to_string() }
}

fn current_exe_dir() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf))
}

/// `sidecar/server.py` in the dev checkout (compile-time path: debug builds only).
fn dev_server_script() -> Option<PathBuf> {
    if !cfg!(debug_assertions) {
        return None;
    }
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("sidecar").join("server.py");
    p.exists().then_some(p)
}

/// The bundled PyInstaller sidecar next to the running executable.
fn bundled_binary() -> Option<PathBuf> {
    let dir = current_exe_dir()?;
    let candidates = [
        dir.join(exe_name(SIDECAR_NAME)),
        dir.join(exe_name(&format!("{SIDECAR_NAME}-{}", std::env::consts::ARCH))),
    ];
    candidates
        .into_iter()
        .find(|p| p.is_file() && fs::metadata(p).map(|m| m.len() > 100_000).unwrap_or(false))
}

/// `sidecar/server.py` located relative to the executable (release run from the repo).
fn script_near_exe() -> Option<PathBuf> {
    let dir = current_exe_dir()?;
    for up in [dir.clone(), dir.join(".."), dir.join("..").join(".."), dir.join("..").join("..").join("..")] {
        let p = up.join("sidecar").join("server.py");
        if p.exists() {
            return Some(p);
        }
    }
    None
}

fn python_exe() -> String {
    std::env::var("KAMVEX_PYTHON")
        .or_else(|_| std::env::var("DASA_UI_PYTHON"))
        .unwrap_or_else(|_| "python".to_string())
}

#[derive(Debug, Clone, PartialEq)]
pub enum Launch {
    Binary(PathBuf),
    Script(PathBuf),
}

/// Decide how to launch the sidecar (see module docs).
pub fn resolve_launch() -> Result<Launch, String> {
    if let Ok(bin) = std::env::var("KAMVEX_SIDECAR_BIN") {
        let p = PathBuf::from(bin);
        return if p.is_file() {
            Ok(Launch::Binary(p))
        } else {
            Err(format!("KAMVEX_SIDECAR_BIN no existe: {}", p.display()))
        };
    }
    let force_bin = std::env::var("KAMVEX_USE_SIDECAR_BIN").map(|v| v == "1").unwrap_or(false);
    if !force_bin {
        if let Some(script) = dev_server_script() {
            return Ok(Launch::Script(script));
        }
    }
    if let Some(bin) = bundled_binary() {
        return Ok(Launch::Binary(bin));
    }
    if let Some(script) = script_near_exe() {
        return Ok(Launch::Script(script));
    }
    Err("no se encontró el sidecar: ni kamvex-sidecar junto al ejecutable ni sidecar/server.py".into())
}

#[cfg(windows)]
fn hide_console(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
}

#[cfg(not(windows))]
fn hide_console(_cmd: &mut Command) {}

fn log_stdio(log: Option<&Path>) -> (Stdio, Stdio) {
    if let Some(p) = log {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(f) = fs::OpenOptions::new().create(true).append(true).open(p) {
            let f2 = f.try_clone().ok();
            return (Stdio::from(f), f2.map(Stdio::from).unwrap_or_else(Stdio::null));
        }
    }
    (Stdio::inherit(), Stdio::inherit())
}

fn apply_env(cmd: &mut Command, env: &SidecarEnv) {
    cmd.env("KAMVEX_DATA_DIR", &env.data_dir)
        .env("KAMVEX_MODELS_DIR", &env.models_dir)
        .env("KAMVEX_BINARIES_DIR", &env.binaries_dir)
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1");
    if let Some(ls) = &env.llama_server {
        cmd.env("KAMVEX_LLAMA_SERVER", ls);
    }
}

/// Launch the sidecar. Returns the child and a description of how it was launched.
pub fn spawn(port: u16, env: &SidecarEnv, log: Option<&Path>) -> Result<(Child, String), String> {
    let launch = resolve_launch()?;
    let (mut cmd, how) = match &launch {
        Launch::Binary(bin) => (Command::new(bin), format!("binary:{}", bin.display())),
        Launch::Script(script) => {
            let mut c = Command::new(python_exe());
            c.arg(script);
            (c, format!("python:{}", script.display()))
        }
    };
    cmd.arg("--port").arg(port.to_string());
    apply_env(&mut cmd, env);
    let (out, err) = log_stdio(log);
    cmd.stdout(out).stderr(err).stdin(Stdio::null());
    hide_console(&mut cmd);
    let child = cmd.spawn().map_err(|e| format!("no se pudo lanzar el sidecar ({how}): {e}"))?;
    Ok((child, how))
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

pub fn status(sc: &Sidecar) -> SidecarStatus {
    let mut running = false;
    let mut pid = None;
    if let Ok(mut guard) = sc.child.lock() {
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(None) => {
                    running = true;
                    pid = Some(child.id());
                }
                _ => *guard = None,
            }
        }
    }
    SidecarStatus {
        port: sc.port,
        running,
        ready: port_open(sc.port),
        launch: sc.launch.clone(),
        pid,
        log_path: sc.log_path.as_ref().map(|p| p.display().to_string()),
    }
}

pub fn stop(sc: &Sidecar) {
    if let Ok(mut guard) = sc.child.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_port_is_usable() {
        assert!(free_port() > 1024);
    }

    #[test]
    fn exe_name_matches_platform() {
        let n = exe_name("kamvex-sidecar");
        if cfg!(target_os = "windows") {
            assert_eq!(n, "kamvex-sidecar.exe");
        } else {
            assert_eq!(n, "kamvex-sidecar");
        }
    }

    #[test]
    fn explicit_env_binary_must_exist() {
        std::env::set_var("KAMVEX_SIDECAR_BIN", "/definitely/not/here");
        let r = resolve_launch();
        std::env::remove_var("KAMVEX_SIDECAR_BIN");
        assert!(r.is_err());
    }

    /// Full integration: needs Python + FastAPI + DASA/SHARD next to the repo.
    #[test]
    #[ignore = "needs a Python environment with the sidecar deps"]
    fn spawn_ready_kill() {
        let port = free_port();
        let env = SidecarEnv {
            data_dir: std::env::temp_dir().join("kamvex-test-data"),
            models_dir: std::env::temp_dir().join("kamvex-test-models"),
            binaries_dir: std::env::temp_dir().join("kamvex-test-bin"),
            llama_server: None,
        };
        let (mut child, _how) = spawn(port, &env, None).expect("failed to spawn sidecar");
        let ready = wait_ready(port, Duration::from_secs(60));
        let _ = child.kill();
        let _ = child.wait();
        assert!(ready, "sidecar never opened port {port}");
    }
}
