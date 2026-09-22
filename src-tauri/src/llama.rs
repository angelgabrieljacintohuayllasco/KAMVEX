//! llama-server lifecycle: resolve which binary to download for a backend,
//! download + extract it, spawn the server, monitor readiness, kill on exit.
//!
//! Binaries live under `<binaries_dir>/<backend>/` (a per-user app-data folder
//! in release builds, `<repo>/binarios/` in dev). Nothing is compiled: the
//! official llama.cpp release assets are downloaded on demand.

use serde::Serialize;
use std::fs;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Pinned llama.cpp release tag.
pub const LLAMA_TAG: &str = "b9827";
const LLAMA_REPO: &str = "ggml-org/llama.cpp";
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(600);

#[derive(Clone, Debug, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Backend {
    Cpu,
    Vulkan,
    Cuda,
    Bitnet,
    Rwkv,
}

impl Backend {
    pub fn parse(s: &str) -> Backend {
        match s {
            "vulkan" => Backend::Vulkan,
            "cuda" => Backend::Cuda,
            "bitnet" => Backend::Bitnet,
            "rwkv" => Backend::Rwkv,
            _ => Backend::Cpu,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Backend::Cpu => "cpu",
            Backend::Vulkan => "vulkan",
            Backend::Cuda => "cuda",
            Backend::Bitnet => "bitnet",
            Backend::Rwkv => "rwkv",
        }
    }

    /// Release assets to download and extract, in order. Empty = not downloadable (v2 backends).
    fn assets(&self) -> Vec<String> {
        match self {
            Backend::Cpu => vec![format!("llama-{LLAMA_TAG}-bin-win-cpu-x64.zip")],
            Backend::Vulkan => vec![format!("llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip")],
            // The CUDA build dynamically links the CUDA runtime, shipped as a separate asset.
            Backend::Cuda => vec![
                format!("llama-{LLAMA_TAG}-bin-win-cuda-12.4-x64.zip"),
                "cudart-llama-bin-win-cuda-12.4-x64.zip".to_string(),
            ],
            Backend::Bitnet | Backend::Rwkv => vec![],
        }
    }

    fn binary_name(&self) -> &'static str {
        if cfg!(target_os = "windows") {
            match self {
                Backend::Cpu | Backend::Vulkan | Backend::Cuda => "llama-server.exe",
                Backend::Bitnet => "bitnet-server.exe",
                Backend::Rwkv => "rwkv-server.exe",
            }
        } else {
            match self {
                Backend::Cpu | Backend::Vulkan | Backend::Cuda => "llama-server",
                Backend::Bitnet => "bitnet-server",
                Backend::Rwkv => "rwkv-server",
            }
        }
    }
}

/// Managed Tauri state for the inference engine.
pub struct LlamaState {
    pub port: u16,
    pub child: Mutex<Option<Child>>,
    pub backend: Mutex<Backend>,
    pub model: Mutex<Option<String>>,
    pub binaries_dir: PathBuf,
    pub log_path: Option<PathBuf>,
}

#[derive(Serialize, Clone, Debug)]
pub struct LlamaStatus {
    pub running: bool,
    pub port: u16,
    pub backend: String,
    pub model: Option<String>,
    pub pid: Option<u32>,
    pub log_path: Option<String>,
}

/// Resolve which backend to use based on hardware.
#[allow(dead_code)]
pub fn resolve_backend(has_vulkan: bool, has_cuda: bool) -> Backend {
    if has_cuda {
        Backend::Cuda
    } else if has_vulkan {
        Backend::Vulkan
    } else {
        Backend::Cpu
    }
}

/// Path to the server binary for a backend.
pub fn binary_path(binaries_dir: &Path, backend: &Backend) -> PathBuf {
    binaries_dir.join(backend.as_str()).join(backend.binary_name())
}

/// Download URL for a release asset.
fn download_url(asset: &str) -> String {
    format!("https://github.com/{LLAMA_REPO}/releases/download/{LLAMA_TAG}/{asset}")
}

pub fn is_binary_present(binaries_dir: &Path, backend: &Backend) -> bool {
    binary_path(binaries_dir, backend).exists()
}

/// Download and extract every asset of the backend. Idempotent.
pub fn ensure_binary(binaries_dir: &Path, backend: &Backend) -> Result<PathBuf, String> {
    let path = binary_path(binaries_dir, backend);
    if path.exists() {
        return Ok(path);
    }
    let assets = backend.assets();
    if assets.is_empty() {
        return Err(format!("el backend {} aún no tiene binarios oficiales (roadmap v2)", backend.as_str()));
    }
    if !cfg!(target_os = "windows") {
        return Err("la descarga automática de llama-server solo está disponible en Windows".into());
    }

    let dir = path.parent().ok_or("ruta de binario inválida")?;
    fs::create_dir_all(dir).map_err(|e| format!("mkdir {}: {e}", dir.display()))?;

    for asset in assets {
        let zip_path = dir.join(format!("{asset}.download"));
        download_to_file(&download_url(&asset), &zip_path)?;
        let extracted = extract_zip(&zip_path, dir);
        fs::remove_file(&zip_path).ok();
        extracted?;
    }

    if !path.exists() {
        return Err(format!(
            "extracción completa pero no se encontró {} en {}",
            backend.binary_name(),
            dir.display()
        ));
    }
    Ok(path)
}

/// Stream a URL to disk (no full in-memory buffering: the Vulkan zip is ~100 MB).
fn download_to_file(url: &str, dest: &Path) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(DOWNLOAD_TIMEOUT)
        .user_agent(concat!("KAMVEX/", env!("CARGO_PKG_VERSION")))
        .build()
        .map_err(|e| format!("cliente http: {e}"))?;
    let mut resp = client.get(url).send().map_err(|e| format!("descarga {url}: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("descarga {url} devolvió {}", resp.status()));
    }
    let mut file = fs::File::create(dest).map_err(|e| format!("crear {}: {e}", dest.display()))?;
    resp.copy_to(&mut file).map_err(|e| format!("escribir {}: {e}", dest.display()))?;
    Ok(())
}

/// Extract a zip into `dest`, refusing entries that escape it (zip-slip).
fn extract_zip(zip_path: &Path, dest: &Path) -> Result<(), String> {
    let file = fs::File::open(zip_path).map_err(|e| format!("abrir zip: {e}"))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("leer zip: {e}"))?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| format!("entrada zip {i}: {e}"))?;
        let Some(rel) = entry.enclosed_name() else {
            return Err(format!("entrada zip insegura: {}", entry.name()));
        };
        if entry.is_dir() {
            continue;
        }
        let out_path = dest.join(rel);
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
        }
        let mut out = fs::File::create(&out_path).map_err(|e| format!("crear {}: {e}", out_path.display()))?;
        std::io::copy(&mut entry, &mut out).map_err(|e| format!("escribir {}: {e}", out_path.display()))?;
    }
    Ok(())
}

/// Ask the OS for an unused TCP port.
pub fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8766)
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
    if cfg!(debug_assertions) {
        (Stdio::inherit(), Stdio::inherit())
    } else {
        (Stdio::null(), Stdio::null())
    }
}

/// Spawn llama-server with the given model and flags (must already be downloaded).
pub fn spawn(exe: &Path, port: u16, model: &str, flags: &[String], log: Option<&Path>) -> Result<Child, String> {
    if !exe.exists() {
        return Err(format!("binario no encontrado: {} (descárgalo primero)", exe.display()));
    }
    if !Path::new(model).is_file() {
        return Err(format!("modelo no encontrado: {model}"));
    }
    let mut cmd = Command::new(exe);
    cmd.arg("--port").arg(port.to_string())
        .arg("--host").arg("127.0.0.1")
        .arg("-m").arg(model)
        .arg("--no-webui");
    for f in flags {
        cmd.arg(f);
    }
    // ggml looks for its DLLs next to the executable.
    if let Some(dir) = exe.parent() {
        cmd.current_dir(dir);
    }
    let (out, err) = log_stdio(log);
    cmd.stdout(out).stderr(err).stdin(Stdio::null());
    hide_console(&mut cmd);
    cmd.spawn().map_err(|e| format!("spawn llama-server: {e}"))
}

/// True once llama-server is responding on the port.
pub fn port_open(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}").parse().expect("valid addr");
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

/// Block until the port is open, the child exits, or `timeout` elapses.
pub fn wait_ready(state: &LlamaState, timeout: Duration) -> Result<bool, String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if port_open(state.port) {
            return Ok(true);
        }
        if let Ok(mut guard) = state.child.lock() {
            if let Some(child) = guard.as_mut() {
                if let Ok(Some(status)) = child.try_wait() {
                    *guard = None;
                    return Err(format!(
                        "llama-server terminó antes de estar listo ({status}); revisa {}",
                        state.log_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "el log".into())
                    ));
                }
            } else {
                return Err("llama-server no está en ejecución".into());
            }
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    Ok(false)
}

/// Kill the running server (if any).
pub fn stop(state: &LlamaState) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    if let Ok(mut m) = state.model.lock() {
        *m = None;
    }
}

pub fn status(state: &LlamaState) -> LlamaStatus {
    let mut running = false;
    let mut pid = None;
    if let Ok(mut guard) = state.child.lock() {
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
    LlamaStatus {
        running,
        port: state.port,
        backend: state.backend.lock().map(|b| b.as_str().to_string()).unwrap_or_default(),
        model: state.model.lock().ok().and_then(|m| m.clone()),
        pid,
        log_path: state.log_path.as_ref().map(|p| p.display().to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_backend_prefers_cuda_then_vulkan() {
        assert!(matches!(resolve_backend(true, true), Backend::Cuda));
        assert!(matches!(resolve_backend(true, false), Backend::Vulkan));
        assert!(matches!(resolve_backend(false, false), Backend::Cpu));
    }

    #[test]
    fn download_url_contains_tag_and_backend() {
        let assets = Backend::Vulkan.assets();
        assert_eq!(assets.len(), 1);
        let url = download_url(&assets[0]);
        assert!(url.contains("vulkan"));
        assert!(url.contains(LLAMA_TAG));
        assert!(url.starts_with("https://github.com/ggml-org/llama.cpp/releases/download/"));
    }

    #[test]
    fn cuda_needs_runtime_asset_too() {
        let assets = Backend::Cuda.assets();
        assert_eq!(assets.len(), 2);
        assert!(assets[1].starts_with("cudart-"));
        assert!(Backend::Bitnet.assets().is_empty());
    }

    #[test]
    fn backend_parse_roundtrip() {
        for b in ["cpu", "vulkan", "cuda", "bitnet", "rwkv"] {
            assert_eq!(Backend::parse(b).as_str(), b);
        }
        assert_eq!(Backend::parse("nonsense"), Backend::Cpu);
        assert_eq!(serde_json::to_string(&Backend::Vulkan).unwrap(), "\"vulkan\"");
    }

    #[test]
    fn binary_path_layout() {
        let p = binary_path(Path::new("/tmp/bin"), &Backend::Vulkan);
        assert!(p.starts_with("/tmp/bin/vulkan"));
        assert!(p.file_name().unwrap().to_string_lossy().starts_with("llama-server"));
    }

    #[test]
    fn free_port_returns_valid_port() {
        let p = free_port();
        assert!(p > 1024);
    }

    #[test]
    fn extract_zip_rejects_zip_slip() {
        use std::io::Write;
        let dir = std::env::temp_dir().join(format!("kamvex-zipslip-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let zip_path = dir.join("evil.zip");
        {
            let f = fs::File::create(&zip_path).unwrap();
            let mut w = zip::ZipWriter::new(f);
            let opts = zip::write::SimpleFileOptions::default();
            w.start_file("../../evil.txt", opts).unwrap();
            w.write_all(b"pwned").unwrap();
            w.finish().unwrap();
        }
        let out = dir.join("out");
        fs::create_dir_all(&out).unwrap();
        let err = extract_zip(&zip_path, &out).unwrap_err();
        assert!(err.contains("insegura"), "{err}");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn spawn_refuses_missing_binary_or_model() {
        let err = spawn(Path::new("/nonexistent/llama-server"), 1, "/nonexistent.gguf", &[], None).unwrap_err();
        assert!(err.contains("binario no encontrado"));
    }
}
