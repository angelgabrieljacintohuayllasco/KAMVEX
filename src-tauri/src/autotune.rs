//! Auto-tune: hardware + model metadata → llama-server flags ("prescription").
//!
//! The prescription is the single source of truth for the flags KAMVEX passes
//! to llama-server: the frontend shows it, the user can override it, and
//! `prescription_to_flags` turns it into the real command line.

use crate::hardware::HwInfo;
use serde::{Deserialize, Serialize};

/// VRAM kept free for KV cache, compute buffers and the driver (MiB).
const VRAM_RESERVE_DISCRETE_MB: u64 = 768;
const VRAM_RESERVE_INTEGRATED_MB: u64 = 256;
/// Layer count assumed when the GGUF metadata is unavailable.
const FALLBACK_LAYERS: u32 = 32;
/// Full offload sentinel understood by llama.cpp (`-ngl 999`).
pub const FULL_OFFLOAD: u32 = 999;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Prescription {
    pub backend: String,
    pub ngl: u32,
    pub threads: u32,
    pub ctx: u32,
    pub batch: u32,
    pub ctk: String,
    pub ctv: String,
    pub flash_attn: bool,
    pub mlock: bool,
    pub draft_model: Option<String>,
    /// Human-readable caveats (model too big for RAM, integrated GPU, CPU only…).
    #[serde(default)]
    pub warnings: Vec<String>,
    /// Layers offloaded / total layers (as far as known), for the UI.
    #[serde(default)]
    pub offloaded_layers: Option<u32>,
    #[serde(default)]
    pub total_layers: Option<u32>,
}

#[derive(Clone, Debug, Default)]
pub struct ModelHints {
    pub size_mb: u64,
    pub block_count: Option<u32>,
    pub context_length: Option<u32>,
    pub is_moe: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Preset {
    Eco,
    Balanced,
    Max,
}

impl Preset {
    pub fn parse(s: &str) -> Preset {
        match s {
            "eco" => Preset::Eco,
            "max" => Preset::Max,
            _ => Preset::Balanced,
        }
    }
}

/// Compute optimal flags for a model on the given hardware.
pub fn autotune(hw: &HwInfo, model: &ModelHints, preset: Preset) -> Prescription {
    let model_mb = model.size_mb.max(1);
    let model_gb = model_mb as f64 / 1024.0;
    let threads = (hw.physical_cores as u32).max(1);
    let mut warnings = Vec::new();

    // Usable adapters only ("none" = old driver / unsupported). CUDA first, then the
    // Vulkan adapter with the most memory (a 4 GB APU beats a 2 GB unusable card).
    let gpu = hw
        .gpus
        .iter()
        .filter(|g| g.backend == "cuda")
        .max_by_key(|g| g.vram_mb)
        .or_else(|| hw.gpus.iter().filter(|g| g.backend == "vulkan").max_by_key(|g| g.vram_mb));
    for g in hw.gpus.iter().filter(|g| g.backend == "none") {
        if let Some(n) = &g.note {
            warnings.push(format!("{}: {n}", g.name));
        }
    }
    let (backend, vram_mb, integrated) = match gpu {
        Some(g) => (g.backend.clone(), g.vram_mb, g.integrated),
        None => ("cpu".to_string(), 0u64, false),
    };
    // A backend the machine cannot run falls back to CPU (e.g. NVIDIA name but no driver).
    let backend = match backend.as_str() {
        "cuda" if !hw.has_cuda => {
            warnings.push("Driver CUDA no detectado: se usa CPU (instala el driver NVIDIA para acelerar).".into());
            "cpu".to_string()
        }
        "vulkan" if !hw.has_vulkan => {
            warnings.push("Vulkan no disponible en el sistema: se usa CPU.".into());
            "cpu".to_string()
        }
        b => b.to_string(),
    };

    let total_layers = model.block_count.map(|b| b + 1); // + output layer
    let (ngl, offloaded) = if backend == "cpu" || vram_mb == 0 {
        (0, Some(0))
    } else {
        let reserve = if integrated { VRAM_RESERVE_INTEGRATED_MB } else { VRAM_RESERVE_DISCRETE_MB };
        let usable = vram_mb.saturating_sub(reserve);
        if usable >= model_mb {
            (FULL_OFFLOAD, total_layers)
        } else {
            let layers = total_layers.unwrap_or(FALLBACK_LAYERS + 1);
            let per_layer = (model_mb as f64 / layers as f64).max(1.0);
            let fits = ((usable as f64) / per_layer).floor() as u32;
            let n = fits.min(layers.saturating_sub(1));
            (n, Some(n))
        }
    };

    let (mut ctx, ctk, ctv, flash_attn, mlock, batch) = match preset {
        Preset::Eco => (2048, "q4_0", "q4_0", true, false, 256),
        Preset::Balanced => (4096, "q8_0", "q8_0", true, false, 512),
        Preset::Max => (8192, "f16", "f16", true, true, 1024),
    };
    if integrated {
        ctx = ctx.min(2048);
        warnings.push("GPU integrada (memoria compartida): offload parcial y contexto reducido.".into());
    }
    if let Some(train_ctx) = model.context_length {
        if train_ctx > 0 {
            ctx = ctx.min(train_ctx);
        }
    }
    // mlock pins the whole model in RAM; only sensible when it clearly fits.
    let mlock = mlock && hw.total_ram_gb > model_gb + 2.0;

    if backend == "cpu" && hw.gpus.is_empty() {
        warnings.push("Sin GPU compatible: inferencia solo en CPU.".into());
    }
    if hw.total_ram_gb > 0.0 && model_gb > hw.total_ram_gb * 0.6 && ngl != FULL_OFFLOAD {
        warnings.push(format!(
            "El modelo ({model_gb:.1} GB) supera el 60% de la RAM ({:.1} GB): puede ir muy lento o fallar.",
            hw.total_ram_gb
        ));
    }
    if model.is_moe {
        warnings.push("Modelo MoE: pocos parámetros activos por token, pero todos los expertos ocupan memoria.".into());
    }

    Prescription {
        backend,
        ngl,
        threads,
        ctx,
        batch,
        ctk: ctk.to_string(),
        ctv: ctv.to_string(),
        flash_attn,
        mlock,
        draft_model: None,
        warnings,
        offloaded_layers: offloaded,
        total_layers,
    }
}

/// Convert a Prescription to llama-server CLI flags (everything except -m/--port/--host).
pub fn prescription_to_flags(p: &Prescription) -> Vec<String> {
    let mut flags = vec![
        "-ngl".to_string(), p.ngl.to_string(),
        "-t".to_string(), p.threads.max(1).to_string(),
        "-c".to_string(), p.ctx.max(256).to_string(),
        "-b".to_string(), p.batch.max(32).to_string(),
        "-ub".to_string(), p.batch.max(32).to_string(),
        "-ctk".to_string(), p.ctk.clone(),
        "-ctv".to_string(), p.ctv.clone(),
        "--flash-attn".to_string(), if p.flash_attn { "on".to_string() } else { "off".to_string() },
    ];
    if p.mlock {
        flags.push("--mlock".to_string());
    }
    if let Some(draft) = p.draft_model.as_deref().filter(|d| !d.trim().is_empty()) {
        flags.push("-md".to_string());
        flags.push(draft.to_string());
    }
    flags
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::GpuInfo;

    fn gpu(vendor: &str, name: &str, vram_mb: u64, backend: &str, integrated: bool) -> GpuInfo {
        GpuInfo {
            vendor: vendor.into(), name: name.into(), vram_mb, backend: backend.into(), integrated,
            driver_version: String::new(), note: None,
        }
    }

    #[test]
    fn unusable_nvidia_is_skipped_in_favor_of_the_apu() {
        // Ryzen 5600GT box: Radeon APU (Vulkan, 4 GB UMA) + GT 610 (driver 391, backend none).
        let mut old = gpu("NVIDIA", "NVIDIA GeForce GT 610", 2048, "none", false);
        old.note = Some("Driver NVIDIA 391.35 (GPU antigua): sin CUDA 12 ni Vulkan".into());
        let mut hw = mock_hw(28.0, 6, vec![gpu("AMD", "AMD Radeon(TM) Graphics", 4096, "vulkan", true), old]);
        hw.has_cuda = true; // nvcuda.dll exists, but the adapter is unusable
        let p = autotune(&hw, &hints(1100, Some(28)), Preset::Balanced);
        assert_eq!(p.backend, "vulkan");
        assert!(p.ngl > 0);
        assert!(p.warnings.iter().any(|w| w.contains("GT 610")));
    }

    #[test]
    fn biggest_vulkan_adapter_wins() {
        let hw = mock_hw(32.0, 8, vec![
            gpu("Intel", "Intel(R) UHD Graphics 630", 1024, "vulkan", true),
            gpu("AMD", "AMD Radeon RX 6700 XT", 12288, "vulkan", false),
        ]);
        let p = autotune(&hw, &hints(4000, Some(32)), Preset::Balanced);
        assert_eq!(p.backend, "vulkan");
        assert_eq!(p.ngl, FULL_OFFLOAD);
        assert_eq!(p.ctx, 4096, "the discrete card must not inherit the iGPU ctx cap");
    }

    fn mock_hw(ram_gb: f64, cores: usize, gpus: Vec<GpuInfo>) -> HwInfo {
        let has_cuda = gpus.iter().any(|g| g.backend == "cuda");
        let has_vulkan = gpus.iter().any(|g| g.backend == "vulkan");
        HwInfo {
            cpu_brand: "Test CPU".to_string(),
            physical_cores: cores,
            logical_cores: cores * 2,
            total_ram_gb: ram_gb,
            available_ram_gb: ram_gb * 0.8,
            gpus,
            has_vulkan,
            has_cuda,
            has_avx2: true,
            has_avx512: false,
            os: "test".into(),
        }
    }

    fn hints(size_mb: u64, layers: Option<u32>) -> ModelHints {
        ModelHints { size_mb, block_count: layers, context_length: None, is_moe: false }
    }

    #[test]
    fn cpu_only_full_offload_is_zero() {
        let hw = mock_hw(8.0, 4, vec![]);
        let p = autotune(&hw, &hints(4000, Some(32)), Preset::Balanced);
        assert_eq!(p.ngl, 0);
        assert_eq!(p.backend, "cpu");
        assert_eq!(p.threads, 4);
        assert!(p.warnings.iter().any(|w| w.contains("Sin GPU")));
    }

    #[test]
    fn vram_larger_than_model_full_offload() {
        let hw = mock_hw(16.0, 8, vec![gpu("NVIDIA", "RTX 3060", 12288, "cuda", false)]);
        let p = autotune(&hw, &hints(4000, Some(32)), Preset::Balanced);
        assert_eq!(p.ngl, FULL_OFFLOAD);
        assert_eq!(p.backend, "cuda");
        assert_eq!(p.offloaded_layers, Some(33));
        assert_eq!(p.total_layers, Some(33));
    }

    #[test]
    fn partial_offload_uses_real_layer_count() {
        // 8 GB model, 33 layers (~248 MB each); 6 GB card minus 768 MB reserve = ~5.3 GB → 21 layers
        let hw = mock_hw(32.0, 8, vec![gpu("NVIDIA", "RTX 2060", 6144, "cuda", false)]);
        let p = autotune(&hw, &hints(8192, Some(32)), Preset::Balanced);
        assert!(p.ngl > 0 && p.ngl < FULL_OFFLOAD, "ngl={}", p.ngl);
        assert_eq!(p.ngl, 21);
        assert_eq!(p.offloaded_layers, Some(21));
    }

    #[test]
    fn partial_offload_without_metadata_falls_back_to_32_layers() {
        let hw = mock_hw(32.0, 8, vec![gpu("AMD", "RX 6600", 8192, "vulkan", false)]);
        let p = autotune(&hw, &hints(16000, None), Preset::Balanced);
        assert!(p.ngl > 0 && p.ngl <= 32);
        assert_eq!(p.total_layers, None);
    }

    #[test]
    fn integrated_gpu_is_conservative() {
        let hw = mock_hw(16.0, 6, vec![gpu("AMD", "AMD Radeon Vega 8 Graphics", 512, "vulkan", true)]);
        let p = autotune(&hw, &hints(2000, Some(24)), Preset::Max);
        assert_eq!(p.backend, "vulkan");
        assert_eq!(p.ctx, 2048);
        assert!(p.ngl < 25);
        assert!(p.warnings.iter().any(|w| w.contains("integrada")));
    }

    #[test]
    fn eco_preset_uses_q4_kv_quant() {
        let hw = mock_hw(8.0, 4, vec![]);
        let p = autotune(&hw, &hints(2000, None), Preset::Eco);
        assert_eq!(p.ctk, "q4_0");
        assert_eq!(p.ctx, 2048);
        assert_eq!(p.batch, 256);
    }

    #[test]
    fn max_preset_uses_f16_and_caps_ctx_to_model() {
        let hw = mock_hw(32.0, 8, vec![gpu("AMD", "RX 6700", 10240, "vulkan", false)]);
        let mut h = hints(8000, Some(32));
        h.context_length = Some(4096);
        let p = autotune(&hw, &h, Preset::Max);
        assert_eq!(p.ctk, "f16");
        assert_eq!(p.ctx, 4096);
        assert!(p.mlock);
    }

    #[test]
    fn warns_when_model_exceeds_ram_budget() {
        let hw = mock_hw(8.0, 4, vec![]);
        let p = autotune(&hw, &hints(6000, Some(32)), Preset::Balanced);
        assert!(p.warnings.iter().any(|w| w.contains("60%")));
        assert!(!p.mlock);
    }

    #[test]
    fn cuda_gpu_without_driver_falls_back_to_cpu() {
        let mut hw = mock_hw(16.0, 8, vec![gpu("NVIDIA", "RTX 3060", 12288, "cuda", false)]);
        hw.has_cuda = false;
        let p = autotune(&hw, &hints(4000, Some(32)), Preset::Balanced);
        assert_eq!(p.backend, "cpu");
        assert_eq!(p.ngl, 0);
    }

    #[test]
    fn prescription_to_flags_includes_key_flags() {
        let p = Prescription {
            backend: "vulkan".into(), ngl: 20, threads: 6, ctx: 4096, batch: 512,
            ctk: "q8_0".into(), ctv: "q8_0".into(), flash_attn: true, mlock: false,
            draft_model: Some("C:/models/draft.gguf".into()), warnings: vec![],
            offloaded_layers: None, total_layers: None,
        };
        let flags = prescription_to_flags(&p);
        assert_eq!(flags[0..2], ["-ngl", "20"]);
        assert!(flags.windows(2).any(|w| w == ["--flash-attn", "on"]));
        assert!(flags.windows(2).any(|w| w == ["-md", "C:/models/draft.gguf"]));
        assert!(!flags.contains(&"--mlock".to_string()));
        assert!(!flags.contains(&"-fa".to_string()), "bare -fa is rejected by llama.cpp b9827");
    }

    #[test]
    fn prescription_roundtrips_through_json_without_new_fields() {
        // The frontend may send back a prescription it received earlier (or an older one).
        let old = r#"{"backend":"cpu","ngl":0,"threads":4,"ctx":4096,"batch":512,"ctk":"q8_0","ctv":"q8_0","flash_attn":true,"mlock":false,"draft_model":null}"#;
        let p: Prescription = serde_json::from_str(old).unwrap();
        assert!(p.warnings.is_empty());
        assert_eq!(prescription_to_flags(&p).len(), 16);
    }
}
