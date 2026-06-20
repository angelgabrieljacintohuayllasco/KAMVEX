mod hardware;
mod sidecar;

use std::sync::Mutex;
use sidecar::Sidecar;
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = sidecar::free_port();
    let child = sidecar::spawn(port).ok();
    let state = Sidecar { port, child: Mutex::new(child) };

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            sidecar_port,
            sidecar_ready,
            hardware::detect_hardware
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
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
