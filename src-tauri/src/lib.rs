mod autotune;
mod gguf;
mod hardware;
mod llama;
mod sidecar;

use autotune::{ModelHints, Prescription, Preset};
use llama::{Backend, LlamaState};
use sidecar::{Sidecar, SidecarEnv};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent};

/// Where KAMVEX keeps its data. Dev builds use the repo layout so the existing
/// `sidecar/appdata`, `sidecar/models` and `binarios` folders keep working;
/// release builds use the per-user app-data folder. `KAMVEX_HOME` overrides both.
#[derive(Clone, Debug, serde::Serialize)]
pub struct AppDirs {
    pub data: PathBuf,
    pub models: PathBuf,
    pub binaries: PathBuf,
    pub logs: PathBuf,
}

fn resolve_dirs(app: &AppHandle) -> AppDirs {
    if let Ok(home) = std::env::var("KAMVEX_HOME") {
        let home = PathBuf::from(home);
        return AppDirs {
            data: home.join("datasets"),
            models: home.join("models"),
            binaries: home.join("binarios"),
            logs: home.join("logs"),
        };
    }
    if cfg!(debug_assertions) {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
        return AppDirs {
            data: repo.join("sidecar").join("appdata").join("datasets"),
            models: repo.join("sidecar").join("models"),
            binaries: repo.join("binarios"),
            logs: repo.join("logs"),
        };
    }
    let base = app
        .path()
        .app_local_data_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("kamvex"));
    AppDirs {
        data: base.join("datasets"),
        models: base.join("models"),
        binaries: base.join("binarios"),
        logs: base.join("logs"),
    }
}

// ── Sidecar commands ────────────────────────────────────────────────────────

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

#[tauri::command]
fn sidecar_status(state: tauri::State<Sidecar>) -> sidecar::SidecarStatus {
    sidecar::status(&state)
}

#[tauri::command]
fn app_dirs(state: tauri::State<AppDirs>) -> AppDirs {
    state.inner().clone()
}

// ── Model metadata ──────────────────────────────────────────────────────────

/// Read GGUF metadata (architecture, layers, context, quantization, size).
#[tauri::command]
async fn model_info(path: String) -> Result<gguf::GgufInfo, String> {
    tauri::async_runtime::spawn_blocking(move || gguf::read_file(Path::new(&path)))
        .await
        .map_err(|e| e.to_string())?
}

// ── Inference engine commands ───────────────────────────────────────────────

/// Inference engine port (fixed per app run).
#[tauri::command]
fn llama_port(state: tauri::State<LlamaState>) -> u16 {
    state.port
}

/// Is the inference engine responding?
#[tauri::command]
fn llama_ready(state: tauri::State<LlamaState>) -> bool {
    llama::port_open(state.port)
}

#[tauri::command]
fn llama_status(state: tauri::State<LlamaState>) -> llama::LlamaStatus {
    llama::status(&state)
}

/// Start the inference engine with a model and a prescription (backend + flags).
/// Any previous instance is stopped first. Returns the port.
#[tauri::command]
async fn llama_start(
    app: AppHandle,
    model: String,
    prescription: Prescription,
    extra_flags: Option<Vec<String>>,
) -> Result<u16, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<LlamaState>();
        let backend = Backend::parse(&prescription.backend);
        let exe = llama::binary_path(&state.binaries_dir, &backend);
        if !exe.exists() {
            return Err(format!(
                "el motor {} no está descargado todavía (pulsa «Descargar llama-server»)",
                backend.as_str()
            ));
        }
        llama::stop(&state);
        let mut flags = autotune::prescription_to_flags(&prescription);
        flags.extend(extra_flags.unwrap_or_default());
        let child = llama::spawn(&exe, state.port, &model, &flags, state.log_path.as_deref())?;
        *state.child.lock().map_err(|e| e.to_string())? = Some(child);
        *state.backend.lock().map_err(|e| e.to_string())? = backend;
        *state.model.lock().map_err(|e| e.to_string())? = Some(model);
        Ok(state.port)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Wait until llama-server answers (model loaded) or fails. Ok(false) = timeout.
#[tauri::command]
async fn llama_wait_ready(app: AppHandle, timeout_ms: Option<u64>) -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<LlamaState>();
        llama::wait_ready(&state, Duration::from_millis(timeout_ms.unwrap_or(180_000)))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Stop the inference engine.
#[tauri::command]
fn llama_stop(state: tauri::State<LlamaState>) {
    llama::stop(&state);
}

/// Ensure the binaries for the given backend are downloaded (blocking download off the UI thread).
#[tauri::command]
async fn llama_ensure_binary(app: AppHandle, backend_str: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<LlamaState>();
        let path = llama::ensure_binary(&state.binaries_dir, &Backend::parse(&backend_str))?;
        Ok(path.to_string_lossy().to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Check if the binary for a backend is already present.
#[tauri::command]
fn llama_binary_present(state: tauri::State<LlamaState>, backend_str: String) -> bool {
    llama::is_binary_present(&state.binaries_dir, &Backend::parse(&backend_str))
}

/// Compute optimal flags for a model. Reads GGUF metadata when a path is given.
#[tauri::command]
async fn autotune_flags(
    model_path: Option<String>,
    model_size_mb: Option<u64>,
    preset: String,
) -> Result<Prescription, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let hw = hardware::detect_hardware();
        let mut hints = ModelHints { size_mb: model_size_mb.unwrap_or(0), ..Default::default() };
        if let Some(p) = model_path.as_deref().filter(|p| !p.trim().is_empty()) {
            match gguf::read_file(Path::new(p)) {
                Ok(info) => {
                    if info.size_mb > 0 {
                        hints.size_mb = info.size_mb;
                    }
                    hints.block_count = info.block_count;
                    hints.context_length = info.context_length;
                    hints.is_moe = info.is_moe();
                }
                Err(_) => {
                    if let Ok(meta) = std::fs::metadata(p) {
                        hints.size_mb = meta.len() / (1024 * 1024);
                    }
                }
            }
        }
        if hints.size_mb == 0 {
            hints.size_mb = 4000;
        }
        Ok(autotune::autotune(&hw, &hints, Preset::parse(&preset)))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Check for updates via the Tauri updater plugin.
#[tauri::command]
async fn check_updates(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_updater::UpdaterExt;
    let updater = app.updater().map_err(|e| e.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => Ok(Some(format!(
            "v{} — {}",
            update.version,
            update.date.map(|d| d.to_string()).unwrap_or_default()
        ))),
        Ok(None) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

// ── App lifecycle ───────────────────────────────────────────────────────────

fn kill_children(app: &AppHandle) {
    if let Some(ls) = app.try_state::<LlamaState>() {
        llama::stop(&ls);
    }
    if let Some(sc) = app.try_state::<Sidecar>() {
        sidecar::stop(&sc);
    }
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let show_i = MenuItem::with_id(app, "show", "Mostrar KAMVEX", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

    let mut tray = TrayIconBuilder::new()
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
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
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
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();
            let dirs = resolve_dirs(&handle);
            for d in [&dirs.data, &dirs.models, &dirs.binaries, &dirs.logs] {
                let _ = std::fs::create_dir_all(d);
            }

            // The sidecar gets its directories through env vars and, when the CPU
            // engine is present, the llama-server path for GGUF embeddings.
            let cpu_bin = llama::binary_path(&dirs.binaries, &Backend::Cpu);
            let env = SidecarEnv {
                data_dir: dirs.data.clone(),
                models_dir: dirs.models.clone(),
                binaries_dir: dirs.binaries.clone(),
                llama_server: cpu_bin.exists().then_some(cpu_bin),
            };
            let sc_port = sidecar::free_port();
            let sc_log = dirs.logs.join("sidecar.log");
            let (sc_child, launch) = match sidecar::spawn(sc_port, &env, Some(&sc_log)) {
                Ok((child, how)) => (Some(child), how),
                Err(e) => {
                    eprintln!("[kamvex] {e}");
                    (None, format!("error:{e}"))
                }
            };
            app.manage(Sidecar { port: sc_port, child: Mutex::new(sc_child), launch, log_path: Some(sc_log) });

            app.manage(LlamaState {
                port: llama::free_port(),
                child: Mutex::new(None),
                backend: Mutex::new(Backend::Cpu),
                model: Mutex::new(None),
                binaries_dir: dirs.binaries.clone(),
                log_path: Some(dirs.logs.join("llama-server.log")),
            });
            app.manage(dirs);

            build_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_port,
            sidecar_ready,
            sidecar_status,
            app_dirs,
            hardware::detect_hardware,
            model_info,
            llama_port,
            llama_ready,
            llama_status,
            llama_start,
            llama_wait_ready,
            llama_stop,
            llama_ensure_binary,
            llama_binary_present,
            autotune_flags,
            check_updates
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Closing the window hides to the tray; "Salir" in the tray quits.
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            kill_children(app);
        }
    });
}
