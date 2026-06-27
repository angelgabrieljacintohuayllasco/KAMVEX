//! Hardware detection: CPU, RAM, GPU/Vulkan. Drives auto-tuning.

use serde::Serialize;
use std::path::Path;
use std::process::Command;
use sysinfo::System;

#[derive(Serialize, Clone, Debug)]
pub struct GpuInfo {
    pub vendor: String,
    pub name: String,
    pub vram_mb: u64,
    pub backend: String,
}

#[derive(Serialize)]
pub struct HwInfo {
    pub cpu_brand: String,
    pub physical_cores: usize,
    pub logical_cores: usize,
    pub total_ram_gb: f64,
    pub available_ram_gb: f64,
    pub gpus: Vec<GpuInfo>,
    pub has_vulkan: bool,
    pub has_cuda: bool,
}

#[tauri::command]
pub fn detect_hardware() -> HwInfo {
    let mut sys = System::new_all();
    sys.refresh_memory();

    let cpus = sys.cpus();
    let cpu_brand = cpus.first().map(|c| c.brand().to_string()).unwrap_or_default();
    let bytes_to_gb = |b: u64| (b as f64) / 1_000_000_000.0;

    let gpus = detect_gpus();
    let has_vulkan = Path::new("C:\\Windows\\System32\\vulkan-1.dll").exists()
        || gpus.iter().any(|g| g.backend == "vulkan");
    let has_cuda = Path::new("C:\\Windows\\System32\\nvcuda.dll").exists()
        || gpus.iter().any(|g| g.backend == "cuda");

    HwInfo {
        cpu_brand: cpu_brand.trim().to_string(),
        physical_cores: sys.physical_core_count().unwrap_or(0),
        logical_cores: cpus.len(),
        total_ram_gb: bytes_to_gb(sys.total_memory()),
        available_ram_gb: bytes_to_gb(sys.available_memory()),
        gpus,
        has_vulkan,
        has_cuda,
    }
}

/// Detect GPUs via PowerShell CIM (Win32_VideoController).
/// Returns one GpuInfo per detected GPU. Falls back to empty vec on error.
fn detect_gpus() -> Vec<GpuInfo> {
    let output = Command::new("powershell")
        .args([
            "-NoProfile", "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Csv -NoTypeInformation",
        ])
        .output();

    let Ok(output) = output else { return vec![] };
    if !output.status.success() {
        return vec![];
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    parse_cim_output(&stdout)
}

/// Parse CSV output from PowerShell CIM query.
fn parse_cim_output(csv: &str) -> Vec<GpuInfo> {
    let lines: Vec<&str> = csv.lines().collect();
    if lines.len() < 2 {
        return vec![];
    }

    // First line is header: "Name","AdapterRAM","DriverVersion"
    // Subsequent lines are data rows
    lines[1..]
        .iter()
        .filter_map(|line| {
            let fields: Vec<String> = parse_csv_line(line);
            if fields.len() < 3 {
                return None;
            }
            let name = fields[0].trim().to_string();
            if name.is_empty() {
                return None;
            }
            let vram_bytes: u64 = fields[1].trim().parse().unwrap_or(0);
            let vram_mb = vram_bytes / 1_000_000;

            let (vendor, backend) = classify_gpu(&name);
            Some(GpuInfo {
                vendor: vendor.to_string(),
                name,
                vram_mb,
                backend: backend.to_string(),
            })
        })
        .collect()
}

/// Parse a single CSV line (handles quoted fields with commas).
fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = vec![];
    let mut current = String::new();
    let mut in_quotes = false;

    for ch in line.chars() {
        match ch {
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => {
                fields.push(current.clone());
                current.clear();
            }
            _ => current.push(ch),
        }
    }
    fields.push(current);
    fields
}

/// Classify a GPU name into vendor + preferred backend.
fn classify_gpu(name: &str) -> (&'static str, &'static str) {
    let lower = name.to_lowercase();
    if lower.contains("nvidia") || lower.contains("geforce") || lower.contains("rtx") || lower.contains("gtx") {
        ("NVIDIA", "cuda")
    } else if lower.contains("amd") || lower.contains("radeon") || lower.contains("vega") {
        ("AMD", "vulkan")
    } else if lower.contains("intel") {
        ("Intel", "vulkan")
    } else {
        ("Unknown", "vulkan")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_hardware_returns_gpu_info() {
        let hw = detect_hardware();
        assert!(hw.physical_cores > 0);
        assert!(!hw.gpus.is_empty() || !hw.gpus.is_empty()); // field exists
    }

    #[test]
    fn gpu_info_serializes() {
        let gpu = GpuInfo {
            vendor: "AMD".to_string(),
            name: "Radeon Vega 8".to_string(),
            vram_mb: 512,
            backend: "vulkan".to_string(),
        };
        let json = serde_json::to_string(&gpu).unwrap();
        assert!(json.contains("AMD"));
        assert!(json.contains("vulkan"));
    }

    #[test]
    fn classify_nvidia() {
        assert_eq!(classify_gpu("NVIDIA GeForce RTX 3060"), ("NVIDIA", "cuda"));
    }

    #[test]
    fn classify_amd_vega() {
        assert_eq!(classify_gpu("AMD Radeon Vega 8 Graphics"), ("AMD", "vulkan"));
    }

    #[test]
    fn classify_intel() {
        assert_eq!(classify_gpu("Intel UHD Graphics 630"), ("Intel", "vulkan"));
    }

    #[test]
    fn parse_csv_simple() {
        let line = r#""AMD Radeon Vega 8 Graphics","536870912","30.0.13020.1000""#;
        let fields = parse_csv_line(line);
        assert_eq!(fields.len(), 3);
        assert_eq!(fields[0], "AMD Radeon Vega 8 Graphics");
        assert_eq!(fields[1], "536870912");
    }

    #[test]
    fn parse_cim_output_extracts_gpu() {
        let csv = "\"Name\",\"AdapterRAM\",\"DriverVersion\"\r\n\"AMD Radeon Vega 8 Graphics\",\"536870912\",\"30.0.13020.1000\"\r\n";
        let gpus = parse_cim_output(csv);
        assert_eq!(gpus.len(), 1);
        assert_eq!(gpus[0].vendor, "AMD");
        assert_eq!(gpus[0].backend, "vulkan");
        assert_eq!(gpus[0].vram_mb, 536);
    }
}
