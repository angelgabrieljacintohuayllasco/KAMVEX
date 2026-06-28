mod autotune;
mod hardware;
mod llama;
mod sidecar;

use std::sync::Mutex;
use sidecar::Sidecar;
use llama::{LlamaState, Backend};
use tauri::Manager;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState};

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
        "bitnet" => Backend::Bitnet,
        "rwkv" => Backend::Rwkv,
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
        "bitnet" => Backend::Bitnet,
        "rwkv" => Backend::Rwkv,
        _ => Backend::Cpu,
    };
    llama::is_binary_present(&backend)
}

/// Compute optimal flags for a model given hardware + preset.
#[tauri::command]
fn autotune_flags(
    model_size_mb: u64,
    preset: String,
) -> Result<autotune::Prescription, String> {
    let hw = hardware::detect_hardware();
    let preset = match preset.as_str() {
        "eco" => autotune::Preset::Eco,
        "max" => autotune::Preset::Max,
        _ => autotune::Preset::Balanced,
    };
    Ok(autotune::autotune(&hw, model_size_mb, preset))
}

/// Check for updates via the Tauri updater plugin.
#[tauri::command]
async fn check_updates(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => Ok(Some(format!("v{} — {}", update.version, update.date.map(|d| d.to_string()).unwrap_or_default()))),
        Ok(None) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(sidecar_state)
        .manage(llama_state)
        .setup(|app| {
            let show_i = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("KAMVEX")
                .show_menu_on_left_click(false)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.unminimize();
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            if w.is_visible().unwrap_or(false) {
                                let _ = w.hide();
                            } else {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_port,
            sidecar_ready,
            hardware::detect_hardware,
            llama_port,
            llama_ready,
            llama_start,
            llama_stop,
            llama_ensure_binary,
            llama_binary_present,
            autotune_flags,
            check_updates
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
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
