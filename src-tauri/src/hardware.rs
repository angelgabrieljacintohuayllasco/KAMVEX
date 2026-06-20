//! Hardware detection (informational in the MVP; drives auto-tuning in slice 3).

use serde::Serialize;
use sysinfo::System;

#[derive(Serialize)]
pub struct HwInfo {
    cpu_brand: String,
    physical_cores: usize,
    logical_cores: usize,
    total_ram_gb: f64,
    available_ram_gb: f64,
}

#[tauri::command]
pub fn detect_hardware() -> HwInfo {
    let mut sys = System::new_all();
    sys.refresh_memory();

    let cpus = sys.cpus();
    let cpu_brand = cpus.first().map(|c| c.brand().to_string()).unwrap_or_default();
    let bytes_to_gb = |b: u64| (b as f64) / 1_000_000_000.0;

    HwInfo {
        cpu_brand: cpu_brand.trim().to_string(),
        physical_cores: sys.physical_core_count().unwrap_or(0),
        logical_cores: cpus.len(),
        total_ram_gb: bytes_to_gb(sys.total_memory()),
        available_ram_gb: bytes_to_gb(sys.available_memory()),
    }
}
