mod hardware;
mod llama;
mod sidecar;

use std::sync::Mutex;
use sidecar::Sidecar;
use llama::{LlamaState, Backend};
use tauri::Manager;

/// Frontend reads this to know where the sidecar listens.
#[tauri::command]
fn sidecar_port(state: tauri::State<Sidecar>) -> u16 {
    state.port
}

/// Frontend polls this until the sidecar is up.
#[tauri::command]
fn sidecar_ready(state: tauri::State<Sidecar>) -> bool {
    sidecar::port_open(state.port)
}

/// Inference engine port (0 if not started).
#[tauri::command]
fn llama_port(state: tauri::State<LlamaState>) -> u16 {
    state.port
}

/// Is the inference engine running?
#[tauri::command]
fn llama_ready(state: tauri::State<LlamaState>) -> bool {
    llama::port_open(state.port)
}

/// Start the inference engine with a model + flags.
#[tauri::command]
fn llama_start(
    state: tauri::State<LlamaState>,
    model: String,
    flags: Vec<String>,
) -> Result<String, String> {
    let backend = state.backend.lock().unwrap().clone();
    let port = state.port;
    let child = llama::spawn(&backend, port, &model, &flags)?;
    *state.child.lock().unwrap() = Some(child);
    Ok(port.to_string())
}

/// Stop the inference engine.
#[tauri::command]
fn llama_stop(state: tauri::State<LlamaState>) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Ensure the binary for the given backend is downloaded.
#[tauri::command]
fn llama_ensure_binary(backend_str: String) -> Result<String, String> {
    let backend = match backend_str.as_str() {
        "vulkan" => Backend::Vulkan,
        "cuda" => Backend::Cuda,
        _ => Backend::Cpu,
    };
    let path = llama::ensure_binary(&backend)?;
    Ok(path.to_string_lossy().to_string())
}

/// Check if binary is already present.
#[tauri::command]
fn llama_binary_present(backend_str: String) -> bool {
    let backend = match backend_str.as_str() {
        "vulkan" => Backend::Vulkan,
        "cuda" => Backend::Cuda,
        _ => Backend::Cpu,
    };
    llama::is_binary_present(&backend)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let sc_port = sidecar::free_port();
    let sc_child = sidecar::spawn(sc_port).ok();
    let sidecar_state = Sidecar { port: sc_port, child: Mutex::new(sc_child) };

    let ll_port = llama::free_port();
    let llama_state = LlamaState {
        port: ll_port,
        child: Mutex::new(None),
        backend: Mutex::new(Backend::Cpu),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(sidecar_state)
        .manage(llama_state)
        .invoke_handler(tauri::generate_handler![
            sidecar_port,
            sidecar_ready,
            hardware::detect_hardware,
            llama_port,
            llama_ready,
            llama_start,
            llama_stop,
            llama_ensure_binary,
            llama_binary_present
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(sc) = window.try_state::<Sidecar>() {
                    if let Ok(mut guard) = sc.child.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
                if let Some(ls) = window.try_state::<LlamaState>() {
                    if let Ok(mut guard) = ls.child.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
