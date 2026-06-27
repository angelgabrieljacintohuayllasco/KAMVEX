//! Auto-tune: hardware + model size → optimal llama-server flags.

use serde::Serialize;
use crate::hardware::HwInfo;

#[derive(Serialize, Clone, Debug)]
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
}

#[derive(Clone, Debug)]
pub enum Preset {
    Eco,
    Balanced,
    Max,
}

/// Compute optimal flags for a model of `model_size_mb` on the given hardware.
pub fn autotune(hw: &HwInfo, model_size_mb: u64, preset: Preset) -> Prescription {
    let model_gb = model_size_mb as f64 / 1024.0;
    let threads = hw.physical_cores as u32;

    let (backend, vram_mb) = hw.gpus.iter()
        .find(|g| g.backend == "cuda")
        .or_else(|| hw.gpus.iter().find(|g| g.backend == "vulkan"))
        .map(|g| (g.backend.clone(), g.vram_mb))
        .unwrap_or(("cpu".to_string(), 0u64));

    let vram_gb = vram_mb as f64 / 1024.0;
    let ngl = if vram_gb >= model_gb && vram_gb > 0.0 {
        999
    } else if vram_gb > 0.0 {
        ((vram_gb / model_gb) * 100.0) as u32
    } else {
        0
    };

    let (ctx, ctk, ctv, flash_attn, mlock, batch) = match preset {
        Preset::Eco => (2048, "q4_0".to_string(), "q4_0".to_string(), true, false, 256),
        Preset::Balanced => (4096, "q8_0".to_string(), "q8_0".to_string(), true, false, 512),
        Preset::Max => (8192, "f16".to_string(), "f16".to_string(), true, true, 1024),
    };

    let is_apu = vram_gb == 0.0 && backend != "cpu";
    let ctx = if is_apu { ctx.min(2048) } else { ctx };

    Prescription {
        backend,
        ngl,
        threads,
        ctx,
        batch,
        ctk,
        ctv,
        flash_attn,
        mlock,
        draft_model: None,
    }
}

/// Convert a Prescription to llama-server CLI flags.
#[allow(dead_code)]
pub fn prescription_to_flags(p: &Prescription) -> Vec<String> {
    let mut flags = vec![
        "-ngl".to_string(), p.ngl.to_string(),
        "-t".to_string(), p.threads.to_string(),
        "-c".to_string(), p.ctx.to_string(),
        "-b".to_string(), p.batch.to_string(),
        "-ub".to_string(), p.batch.to_string(),
        "-ctk".to_string(), p.ctk.clone(),
        "-ctv".to_string(), p.ctv.clone(),
    ];
    if p.flash_attn {
        flags.push("-fa".to_string());
    }
    if p.mlock {
        flags.push("--mlock".to_string());
    }
    flags
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::GpuInfo;

    fn mock_hw(ram_gb: f64, cores: usize, gpus: Vec<GpuInfo>) -> HwInfo {
        HwInfo {
            cpu_brand: "Test CPU".to_string(),
            physical_cores: cores,
            logical_cores: cores * 2,
            total_ram_gb: ram_gb,
            available_ram_gb: ram_gb * 0.8,
            gpus,
            has_vulkan: false,
            has_cuda: false,
        }
    }

    #[test]
    fn cpu_only_full_offload_is_zero() {
        let hw = mock_hw(8.0, 4, vec![]);
        let p = autotune(&hw, 4000, Preset::Balanced);
        assert_eq!(p.ngl, 0);
        assert_eq!(p.backend, "cpu");
    }

    #[test]
    fn vram_larger_than_model_full_offload() {
        let gpu = GpuInfo { vendor: "NVIDIA".to_string(), name: "RTX 3060".to_string(), vram_mb: 12288, backend: "cuda".to_string() };
        let hw = mock_hw(16.0, 8, vec![gpu]);
        let p = autotune(&hw, 4000, Preset::Balanced);
        assert_eq!(p.ngl, 999);
        assert_eq!(p.backend, "cuda");
    }

    #[test]
    fn eco_preset_uses_q4_kv_quant() {
        let hw = mock_hw(8.0, 4, vec![]);
        let p = autotune(&hw, 2000, Preset::Eco);
        assert_eq!(p.ctk, "q4_0");
        assert_eq!(p.ctx, 2048);
    }

    #[test]
    fn max_preset_uses_f16_kv_quant() {
        let gpu = GpuInfo { vendor: "AMD".to_string(), name: "RX 6700".to_string(), vram_mb: 10240, backend: "vulkan".to_string() };
        let hw = mock_hw(32.0, 8, vec![gpu]);
        let p = autotune(&hw, 8000, Preset::Max);
        assert_eq!(p.ctk, "f16");
        assert_eq!(p.ctx, 8192);
    }

    #[test]
    fn prescription_to_flags_includes_key_flags() {
        let p = Prescription {
            backend: "vulkan".into(), ngl: 20, threads: 6, ctx: 4096, batch: 512,
            ctk: "q8_0".into(), ctv: "q8_0".into(), flash_attn: true, mlock: false,
            draft_model: None,
        };
        let flags = prescription_to_flags(&p);
        assert!(flags.contains(&"-ngl".to_string()));
        assert!(flags.contains(&"20".to_string()));
        assert!(flags.contains(&"-fa".to_string()));
        assert!(!flags.contains(&"--mlock".to_string()));
    }
}
