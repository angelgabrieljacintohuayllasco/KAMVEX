//! llama-server lifecycle: resolve which binary to download based on hardware,
//! download + extract it, spawn the server, monitor readiness, kill on exit.

use std::fs;
use std::io::Read;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use serde::Serialize;

/// Pinned llama.cpp release tag.
const LLAMA_TAG: &str = "b9827";
const LLAMA_REPO: &str = "ggml-org/llama.cpp";

#[derive(Clone, Debug, Serialize)]
pub enum Backend {
    Cpu,
    Vulkan,
    Cuda,
}

impl Backend {
    fn asset_suffix(&self) -> &'static str {
        match self {
            Backend::Cpu => "bin-win-cpu-x64.zip",
            Backend::Vulkan => "bin-win-vulkan-x64.zip",
            Backend::Cuda => "bin-win-cuda-12.4-x64.zip",
        }
    }

    fn binary_name(&self) -> &'static str {
        "llama-server.exe"
    }

    fn subdir(&self) -> &'static str {
        match self {
            Backend::Cpu => "cpu",
            Backend::Vulkan => "vulkan",
            Backend::Cuda => "cuda",
        }
    }
}

/// Managed Tauri state for the inference engine.
pub struct LlamaState {
    pub port: u16,
    pub child: Mutex<Option<Child>>,
    pub backend: Mutex<Backend>,
}

/// Resolve which backend to use based on hardware.
pub fn resolve_backend(has_vulkan: bool, has_cuda: bool) -> Backend {
    if has_cuda {
        Backend::Cuda
    } else if has_vulkan {
        Backend::Vulkan
    } else {
        Backend::Cpu
    }
}

/// Directory where binaries are stored: <app_root>/binarios/<backend>/
fn binarios_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("binarios")
}

/// Path to the extracted llama-server binary.
pub fn binary_path(backend: &Backend) -> PathBuf {
    binarios_dir().join(backend.subdir()).join(backend.binary_name())
}

/// Download URL for the given backend.
fn download_url(backend: &Backend) -> String {
    format!(
        "https://github.com/{}/releases/download/{}/llama-{}-{}",
        LLAMA_REPO, LLAMA_TAG, LLAMA_TAG, backend.asset_suffix()
    )
}

/// Check if the binary is already downloaded.
pub fn is_binary_present(backend: &Backend) -> bool {
    binary_path(backend).exists()
}

/// Download and extract the llama-server binary for the given backend.
pub fn ensure_binary(backend: &Backend) -> Result<PathBuf, String> {
    let path = binary_path(backend);
    if path.exists() {
        return Ok(path);
    }

    let dir = path.parent().unwrap();
    fs::create_dir_all(dir).map_err(|e| format!("mkdir {}: {e}", dir.display()))?;

    let url = download_url(backend);
    let zip_path = dir.join("download.zip");

    let resp = reqwest::blocking::get(&url)
        .map_err(|e| format!("download {url}: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("download {} returned {}", url, resp.status()));
    }
    let bytes = resp.bytes().map_err(|e| format!("read body: {e}"))?;
    fs::write(&zip_path, &bytes).map_err(|e| format!("write zip: {e}"))?;

    extract_zip(&zip_path, dir)?;
    fs::remove_file(&zip_path).ok();

    if !path.exists() {
        return Err(format!(
            "extraction complete but {} not found in {}",
            backend.binary_name(),
            dir.display()
        ));
    }
    Ok(path)
}

/// Extract a zip file to a directory.
fn extract_zip(zip_path: &Path, dest: &Path) -> Result<(), String> {
    let file = fs::File::open(zip_path).map_err(|e| format!("open zip: {e}"))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("read zip: {e}"))?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| format!("zip entry {i}: {e}"))?;
        let name = entry.name().to_string();

        if name.ends_with('/') || name.ends_with('\\') {
            continue;
        }

        let out_path = dest.join(&name);
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
        }

        let mut buf = Vec::new();
        entry.read_to_end(&mut buf).map_err(|e| format!("read entry: {e}"))?;
        fs::write(&out_path, &buf).map_err(|e| format!("write {}: {e}", out_path.display()))?;
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

/// Spawn llama-server with the given model and flags.
pub fn spawn(backend: &Backend, port: u16, model: &str, flags: &[String]) -> Result<Child, String> {
    let exe = ensure_binary(backend)?;
    let mut cmd = Command::new(&exe);
    cmd.arg("--port").arg(port.to_string())
       .arg("--host").arg("127.0.0.1")
       .arg("-m").arg(model);
    for f in flags {
        cmd.arg(f);
    }
    cmd.spawn().map_err(|e| format!("spawn llama-server: {e}"))
}

/// True once llama-server is responding on the port.
pub fn port_open(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}").parse().expect("valid addr");
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

/// Block until the port is open or timeout.
pub fn wait_ready(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if port_open(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    false
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
        let url = download_url(&Backend::Vulkan);
        assert!(url.contains("vulkan"));
        assert!(url.contains(LLAMA_TAG));
    }

    #[test]
    fn free_port_returns_valid_port() {
        let p = free_port();
        assert!(p > 1024);
    }
}
