//! Hardware detection: CPU, RAM, GPU/VRAM. Drives auto-tuning.
//!
//! GPU discovery on Windows combines three sources, because none is reliable
//! alone: WMI `Win32_VideoController.AdapterRAM` (32-bit, caps at 4 GB), the
//! display-class registry key `HardwareInformation.qwMemorySize` (64-bit, the
//! documented workaround) and `nvidia-smi` for NVIDIA cards.

use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;
use sysinfo::System;

const MIB: u64 = 1024 * 1024;

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct GpuInfo {
    pub vendor: String,
    pub name: String,
    pub vram_mb: u64,
    /// Backend KAMVEX can actually use on this adapter: "cuda", "vulkan" or "none".
    pub backend: String,
    /// Integrated GPU sharing system RAM (APU / iGPU) — auto-tune is conservative.
    pub integrated: bool,
    /// Driver version as reported by the OS (WMI) or nvidia-smi.
    #[serde(default)]
    pub driver_version: String,
    /// Why the adapter is limited or unusable (old driver, unsupported architecture…).
    #[serde(default)]
    pub note: Option<String>,
}

/// Minimum NVIDIA driver for the CUDA 12.4 llama.cpp build.
const NVIDIA_MIN_CUDA12_DRIVER: f32 = 525.0;
/// Below this NVIDIA driver there is no usable Vulkan either (Fermi era, 39x.xx).
const NVIDIA_MIN_VULKAN_DRIVER: f32 = 470.0;

#[derive(Serialize, Clone, Debug)]
pub struct HwInfo {
    pub cpu_brand: String,
    pub physical_cores: usize,
    pub logical_cores: usize,
    pub total_ram_gb: f64,
    pub available_ram_gb: f64,
    pub gpus: Vec<GpuInfo>,
    pub has_vulkan: bool,
    pub has_cuda: bool,
    pub has_avx2: bool,
    pub has_avx512: bool,
    pub os: String,
}

#[tauri::command]
pub fn detect_hardware() -> HwInfo {
    let mut sys = System::new_all();
    sys.refresh_memory();

    let cpus = sys.cpus();
    let cpu_brand = cpus.first().map(|c| c.brand().to_string()).unwrap_or_default();
    let bytes_to_gb = |b: u64| (b as f64) / 1_000_000_000.0;

    let gpus = detect_gpus();
    let has_vulkan = vulkan_loader_present() || gpus.iter().any(|g| g.backend == "vulkan");
    let has_cuda = cuda_driver_present() || gpus.iter().any(|g| g.backend == "cuda");

    HwInfo {
        cpu_brand: cpu_brand.trim().to_string(),
        physical_cores: sys.physical_core_count().unwrap_or(0).max(1),
        logical_cores: cpus.len().max(1),
        total_ram_gb: bytes_to_gb(sys.total_memory()),
        available_ram_gb: bytes_to_gb(sys.available_memory()),
        gpus,
        has_vulkan,
        has_cuda,
        has_avx2: cpu_feature("avx2"),
        has_avx512: cpu_feature("avx512f"),
        os: std::env::consts::OS.to_string(),
    }
}

fn cpu_feature(name: &str) -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        match name {
            "avx2" => std::arch::is_x86_feature_detected!("avx2"),
            "avx512f" => std::arch::is_x86_feature_detected!("avx512f"),
            _ => false,
        }
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        let _ = name;
        false
    }
}

fn system32() -> Option<PathBuf> {
    std::env::var_os("SystemRoot").map(|r| PathBuf::from(r).join("System32"))
}

fn vulkan_loader_present() -> bool {
    if cfg!(target_os = "windows") {
        system32().map(|s| s.join("vulkan-1.dll").exists()).unwrap_or(false)
    } else {
        ["/usr/lib/x86_64-linux-gnu/libvulkan.so.1", "/usr/lib64/libvulkan.so.1", "/usr/lib/libvulkan.so.1"]
            .iter()
            .any(|p| std::path::Path::new(p).exists())
    }
}

fn cuda_driver_present() -> bool {
    if cfg!(target_os = "windows") {
        system32().map(|s| s.join("nvcuda.dll").exists()).unwrap_or(false)
    } else {
        ["/usr/lib/x86_64-linux-gnu/libcuda.so.1", "/usr/lib64/libcuda.so.1"]
            .iter()
            .any(|p| std::path::Path::new(p).exists())
    }
}

/// PowerShell: one CSV row per adapter with WMI + registry memory figures.
const GPU_QUERY_PS: &str = r#"
$ErrorActionPreference = 'SilentlyContinue'
$cim = Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion
$reg = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' | Select-Object DriverDesc, 'HardwareInformation.qwMemorySize'
$cim | ForEach-Object {
  $n = $_.Name
  $r = $reg | Where-Object { $_.DriverDesc -eq $n } | Select-Object -First 1
  $qw = if ($r) { $r.'HardwareInformation.qwMemorySize' } else { 0 }
  [pscustomobject]@{ Name = $n; AdapterRAM = $_.AdapterRAM; QwMemorySize = $qw; DriverVersion = $_.DriverVersion }
} | ConvertTo-Csv -NoTypeInformation
"#;

/// NVIDIA's WMI driver string ("23.21.13.9135") hides the marketing version in the
/// last five digits of the last two groups ("13" + "9135" → 39135 → 391.35).
pub fn nvidia_driver_number(wmi_version: &str) -> Option<f32> {
    let parts: Vec<&str> = wmi_version.trim().split('.').collect();
    if parts.len() < 4 {
        return None;
    }
    let digits: String = format!("{}{}", parts[2], parts[3]).chars().filter(|c| c.is_ascii_digit()).collect();
    if digits.len() < 5 {
        return None;
    }
    let tail = &digits[digits.len() - 5..];
    let major: f32 = tail[..3].parse().ok()?;
    let minor: f32 = tail[3..].parse().ok()?;
    Some(major + minor / 100.0)
}

/// Downgrade NVIDIA adapters whose driver cannot run the CUDA 12 build (or Vulkan at all).
pub fn apply_nvidia_driver_policy(gpu: &mut GpuInfo, driver: Option<f32>) {
    if gpu.vendor != "NVIDIA" {
        return;
    }
    let Some(v) = driver else { return };
    if v >= NVIDIA_MIN_CUDA12_DRIVER {
        return;
    }
    if v >= NVIDIA_MIN_VULKAN_DRIVER {
        gpu.backend = "vulkan".into();
        gpu.note = Some(format!(
            "Driver NVIDIA {v:.2}: CUDA 12 necesita ≥ {NVIDIA_MIN_CUDA12_DRIVER:.0}; se usa Vulkan."
        ));
    } else {
        gpu.backend = "none".into();
        gpu.note = Some(format!(
            "Driver NVIDIA {v:.2} (GPU antigua): sin CUDA 12 ni Vulkan; no se usa para inferencia."
        ));
    }
}

/// Detect GPUs. Windows: WMI + registry (+ nvidia-smi). Elsewhere: nvidia-smi only.
fn detect_gpus() -> Vec<GpuInfo> {
    let mut gpus = if cfg!(target_os = "windows") {
        run_powershell(GPU_QUERY_PS).map(|csv| parse_gpu_csv(&csv)).unwrap_or_default()
    } else {
        vec![]
    };
    if let Some(out) = run_nvidia_smi() {
        merge_nvidia_smi(&mut gpus, &parse_nvidia_smi(&out));
    }
    gpus
}

fn run_powershell(script: &str) -> Option<String> {
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-Command", script]);
    hide_console(&mut cmd);
    let output = cmd.output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn run_nvidia_smi() -> Option<String> {
    let mut cmd = Command::new("nvidia-smi");
    cmd.args(["--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]);
    hide_console(&mut cmd);
    let output = cmd.output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[cfg(windows)]
fn hide_console(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
}

#[cfg(not(windows))]
fn hide_console(_cmd: &mut Command) {}

/// Parse the CSV produced by GPU_QUERY_PS: "Name","AdapterRAM","QwMemorySize".
pub fn parse_gpu_csv(csv: &str) -> Vec<GpuInfo> {
    let mut lines = csv.lines().filter(|l| !l.trim().is_empty());
    let Some(header) = lines.next() else { return vec![] };
    let cols = parse_csv_line(header);
    let idx = |name: &str| cols.iter().position(|c| c.trim().eq_ignore_ascii_case(name));
    let (Some(i_name), Some(i_ram)) = (idx("Name"), idx("AdapterRAM")) else { return vec![] };
    let i_qw = idx("QwMemorySize");
    let i_drv = idx("DriverVersion");

    lines
        .filter_map(|line| {
            let fields = parse_csv_line(line);
            let name = fields.get(i_name)?.trim().to_string();
            if name.is_empty() {
                return None;
            }
            let adapter_ram: u64 = fields.get(i_ram).and_then(|v| v.trim().parse().ok()).unwrap_or(0);
            let qw: u64 = i_qw
                .and_then(|i| fields.get(i))
                .and_then(|v| v.trim().parse().ok())
                .unwrap_or(0);
            let driver_version = i_drv.and_then(|i| fields.get(i)).map(|v| v.trim().to_string()).unwrap_or_default();
            let vram_mb = adapter_ram.max(qw) / MIB;
            let (vendor, backend, integrated) = classify_gpu(&name);
            let mut gpu = GpuInfo {
                vendor: vendor.into(), name, vram_mb, backend: backend.into(), integrated,
                driver_version: driver_version.clone(), note: None,
            };
            apply_nvidia_driver_policy(&mut gpu, nvidia_driver_number(&driver_version));
            Some(gpu)
        })
        .collect()
}

/// One nvidia-smi row: name, memory.total (MiB), driver version (may be missing).
#[derive(Debug, Clone, PartialEq)]
pub struct SmiGpu {
    pub name: String,
    pub vram_mb: u64,
    pub driver: Option<f32>,
}

/// Parse `nvidia-smi --query-gpu=name,memory.total[,driver_version] --format=csv,noheader,nounits`.
pub fn parse_nvidia_smi(out: &str) -> Vec<SmiGpu> {
    out.lines()
        .filter_map(|l| {
            let fields: Vec<&str> = l.split(',').map(str::trim).collect();
            if fields.len() < 2 {
                return None;
            }
            let vram_mb: u64 = fields[1].parse().ok()?;
            let driver = fields.get(2).and_then(|d| d.parse::<f32>().ok());
            Some(SmiGpu { name: fields[0].to_string(), vram_mb, driver })
        })
        .collect()
}

/// Prefer nvidia-smi's figures for NVIDIA adapters (exact 64-bit memory, real driver number).
pub fn merge_nvidia_smi(gpus: &mut Vec<GpuInfo>, smi: &[SmiGpu]) {
    for s in smi {
        if let Some(g) = gpus.iter_mut().find(|g| {
            g.vendor == "NVIDIA" && (g.name == s.name || g.name.contains(s.name.as_str()) || s.name.contains(g.name.as_str()))
        }) {
            g.vram_mb = s.vram_mb;
            if let Some(d) = s.driver {
                g.driver_version = format!("{d:.2}");
                g.backend = "cuda".into();
                g.note = None;
                apply_nvidia_driver_policy(g, Some(d));
            }
        } else {
            let mut g = GpuInfo {
                vendor: "NVIDIA".into(),
                name: s.name.clone(),
                vram_mb: s.vram_mb,
                backend: "cuda".into(),
                integrated: false,
                driver_version: s.driver.map(|d| format!("{d:.2}")).unwrap_or_default(),
                note: None,
            };
            apply_nvidia_driver_policy(&mut g, s.driver);
            gpus.push(g);
        }
    }
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

const INTEGRATED_HINTS: &[&str] = &[
    "vega", "radeon(tm) graphics", "radeon graphics", "iris", "uhd", "hd graphics",
    "780m", "760m", "680m", "660m", "610m", "apu",
];

/// Classify a GPU name into (vendor, preferred backend, integrated?).
pub fn classify_gpu(name: &str) -> (&'static str, &'static str, bool) {
    let lower = name.to_lowercase();
    if lower.contains("nvidia") || lower.contains("geforce") || lower.contains("rtx") || lower.contains("gtx") || lower.contains("quadro") {
        return ("NVIDIA", "cuda", false);
    }
    let integrated = !lower.contains("arc") && INTEGRATED_HINTS.iter().any(|h| lower.contains(h));
    if lower.contains("amd") || lower.contains("radeon") || lower.contains("vega") {
        ("AMD", "vulkan", integrated)
    } else if lower.contains("intel") {
        ("Intel", "vulkan", integrated)
    } else {
        ("Unknown", "vulkan", false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_hardware_returns_sane_values() {
        let hw = detect_hardware();
        assert!(hw.physical_cores > 0);
        assert!(hw.total_ram_gb > 0.0);
        assert!(!hw.os.is_empty());
    }

    #[test]
    fn nvidia_driver_number_from_wmi() {
        assert_eq!(nvidia_driver_number("23.21.13.9135"), Some(391.35));
        assert_eq!(nvidia_driver_number("31.0.15.4601"), Some(546.01));
        assert_eq!(nvidia_driver_number("30.0.13020.1000"), None.or(nvidia_driver_number("30.0.13020.1000"))); // any parse is fine, must not panic
        assert_eq!(nvidia_driver_number("garbage"), None);
    }

    #[test]
    fn nvidia_driver_policy_gates_backends() {
        let mk = |drv: &str| GpuInfo {
            vendor: "NVIDIA".into(), name: "NVIDIA GeForce GT 610".into(), vram_mb: 2048,
            backend: "cuda".into(), integrated: false, driver_version: drv.into(), note: None,
        };
        let mut fermi = mk("23.21.13.9135");
        let drv = nvidia_driver_number(&fermi.driver_version);
        apply_nvidia_driver_policy(&mut fermi, drv);
        assert_eq!(fermi.backend, "none");
        assert!(fermi.note.as_deref().unwrap_or("").contains("391.35"));

        let mut kepler = mk("30.0.14.7168"); // 471.68
        let drv = nvidia_driver_number(&kepler.driver_version);
        apply_nvidia_driver_policy(&mut kepler, drv);
        assert_eq!(kepler.backend, "vulkan");

        let mut modern = mk("31.0.15.4601"); // 546.01
        let drv = nvidia_driver_number(&modern.driver_version);
        apply_nvidia_driver_policy(&mut modern, drv);
        assert_eq!(modern.backend, "cuda");
        assert!(modern.note.is_none());
    }

    #[test]
    fn parse_gpu_csv_applies_driver_policy() {
        let csv = "\"Name\",\"AdapterRAM\",\"QwMemorySize\",\"DriverVersion\"\r\n\
                   \"AMD Radeon(TM) Graphics\",\"4293918720\",\"4294967296\",\"31.0.21916.2\"\r\n\
                   \"NVIDIA GeForce GT 610\",\"2147483648\",\"2147483648\",\"23.21.13.9135\"\r\n";
        let gpus = parse_gpu_csv(csv);
        assert_eq!(gpus.len(), 2);
        assert_eq!(gpus[0].backend, "vulkan");
        assert!(gpus[0].integrated);
        assert_eq!(gpus[0].vram_mb, 4096);
        assert_eq!(gpus[1].backend, "none");
        assert_eq!(gpus[1].driver_version, "23.21.13.9135");
    }

    #[test]
    fn gpu_info_serializes() {
        let gpu = GpuInfo {
            vendor: "AMD".to_string(),
            name: "Radeon Vega 8".to_string(),
            vram_mb: 512,
            backend: "vulkan".to_string(),
            integrated: true,
            driver_version: String::new(),
            note: None,
        };
        let json = serde_json::to_string(&gpu).unwrap();
        assert!(json.contains("AMD"));
        assert!(json.contains("vulkan"));
        assert!(json.contains("\"integrated\":true"));
    }

    #[test]
    fn classify_vendors() {
        assert_eq!(classify_gpu("NVIDIA GeForce RTX 3060"), ("NVIDIA", "cuda", false));
        assert_eq!(classify_gpu("AMD Radeon Vega 8 Graphics"), ("AMD", "vulkan", true));
        assert_eq!(classify_gpu("AMD Radeon(TM) Graphics"), ("AMD", "vulkan", true));
        assert_eq!(classify_gpu("AMD Radeon RX 6700 XT"), ("AMD", "vulkan", false));
        assert_eq!(classify_gpu("Intel(R) UHD Graphics 630"), ("Intel", "vulkan", true));
        assert_eq!(classify_gpu("Intel(R) Arc(TM) A770 Graphics"), ("Intel", "vulkan", false));
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
    fn parse_gpu_csv_prefers_registry_qword_over_capped_adapter_ram() {
        let csv = "\"Name\",\"AdapterRAM\",\"QwMemorySize\"\r\n\
                   \"NVIDIA GeForce RTX 3060\",\"4293918720\",\"12884901888\"\r\n\
                   \"AMD Radeon Vega 8 Graphics\",\"536870912\",\"0\"\r\n";
        let gpus = parse_gpu_csv(csv);
        assert_eq!(gpus.len(), 2);
        assert_eq!(gpus[0].vendor, "NVIDIA");
        assert_eq!(gpus[0].vram_mb, 12288);
        assert_eq!(gpus[1].vendor, "AMD");
        assert_eq!(gpus[1].backend, "vulkan");
        assert_eq!(gpus[1].vram_mb, 512);
        assert!(gpus[1].integrated);
    }

    #[test]
    fn parse_gpu_csv_without_qw_column_still_works() {
        let csv = "\"Name\",\"AdapterRAM\"\r\n\"Intel(R) UHD Graphics 630\",\"1073741824\"\r\n";
        let gpus = parse_gpu_csv(csv);
        assert_eq!(gpus.len(), 1);
        assert_eq!(gpus[0].vram_mb, 1024);
    }

    #[test]
    fn nvidia_smi_merge_overrides_and_adds() {
        let smi = parse_nvidia_smi("NVIDIA GeForce RTX 3060, 12288, 546.01\nNVIDIA T400, 2048\n");
        assert_eq!(smi.len(), 2);
        assert_eq!(smi[0].driver, Some(546.01));
        assert_eq!(smi[1].driver, None);
        let mut gpus = vec![GpuInfo {
            vendor: "NVIDIA".into(), name: "NVIDIA GeForce RTX 3060".into(), vram_mb: 4095,
            backend: "cuda".into(), integrated: false, driver_version: String::new(), note: None,
        }];
        merge_nvidia_smi(&mut gpus, &smi);
        assert_eq!(gpus[0].vram_mb, 12288);
        assert_eq!(gpus[0].driver_version, "546.01");
        assert_eq!(gpus.len(), 2);
        assert_eq!(gpus[1].name, "NVIDIA T400");
        assert_eq!(gpus[1].backend, "cuda");
    }
}
