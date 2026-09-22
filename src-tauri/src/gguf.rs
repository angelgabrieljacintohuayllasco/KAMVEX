//! Minimal GGUF metadata reader (header + key/value section only).
//!
//! Auto-tune needs the real layer count and training context of a model to
//! decide how many layers fit in VRAM; the UI needs the quantization and
//! architecture to show something better than a file name. Only the metadata
//! is read (a few KB..MB); tensor data is never touched.
//!
//! Spec: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md (v2 / v3).

use serde::Serialize;
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::Path;

const GGUF_MAGIC: &[u8; 4] = b"GGUF";
const MAX_STRING: u64 = 64 * 1024 * 1024; // sanity limit for a single string / array

#[derive(Serialize, Clone, Debug, Default, PartialEq)]
pub struct GgufInfo {
    pub architecture: String,
    pub name: String,
    pub file_type: Option<u32>,
    pub quant: String,
    pub block_count: Option<u32>,
    pub context_length: Option<u32>,
    pub embedding_length: Option<u32>,
    pub expert_count: Option<u32>,
    pub vocab_size: Option<u64>,
    pub size_mb: u64,
    pub version: u32,
}

impl GgufInfo {
    pub fn is_moe(&self) -> bool {
        self.expert_count.map(|n| n > 1).unwrap_or(false)
    }
}

/// llama.cpp `llama_ftype` → human label.
pub fn file_type_name(ft: u32) -> String {
    let s = match ft {
        0 => "F32",
        1 => "F16",
        2 => "Q4_0",
        3 => "Q4_1",
        7 => "Q8_0",
        8 => "Q5_0",
        9 => "Q5_1",
        10 => "Q2_K",
        11 => "Q3_K_S",
        12 => "Q3_K_M",
        13 => "Q3_K_L",
        14 => "Q4_K_S",
        15 => "Q4_K_M",
        16 => "Q5_K_S",
        17 => "Q5_K_M",
        18 => "Q6_K",
        19 => "IQ2_XXS",
        20 => "IQ2_XS",
        21 => "Q2_K_S",
        22 => "IQ3_XS",
        23 => "IQ3_XXS",
        24 => "IQ1_S",
        25 => "IQ4_NL",
        26 => "IQ3_S",
        27 => "IQ3_M",
        28 => "IQ2_S",
        29 => "IQ2_M",
        30 => "IQ4_XS",
        31 => "IQ1_M",
        32 => "BF16",
        36 => "TQ1_0",
        37 => "TQ2_0",
        38 => "MXFP4",
        _ => return format!("ftype {ft}"),
    };
    s.to_string()
}

#[derive(Debug)]
enum Value {
    U32(u32),
    U64(u64),
    Str(String),
    Other,
}

fn read_u8<R: Read>(r: &mut R) -> Result<u8, String> {
    let mut b = [0u8; 1];
    r.read_exact(&mut b).map_err(|e| format!("gguf: lectura u8: {e}"))?;
    Ok(b[0])
}

fn read_u32<R: Read>(r: &mut R) -> Result<u32, String> {
    let mut b = [0u8; 4];
    r.read_exact(&mut b).map_err(|e| format!("gguf: lectura u32: {e}"))?;
    Ok(u32::from_le_bytes(b))
}

fn read_u64<R: Read>(r: &mut R) -> Result<u64, String> {
    let mut b = [0u8; 8];
    r.read_exact(&mut b).map_err(|e| format!("gguf: lectura u64: {e}"))?;
    Ok(u64::from_le_bytes(b))
}

fn read_string<R: Read>(r: &mut R) -> Result<String, String> {
    let len = read_u64(r)?;
    if len > MAX_STRING {
        return Err(format!("gguf: string demasiado largo ({len} bytes)"));
    }
    let mut buf = vec![0u8; len as usize];
    r.read_exact(&mut buf).map_err(|e| format!("gguf: lectura string: {e}"))?;
    Ok(String::from_utf8_lossy(&buf).into_owned())
}

/// Fixed byte size of scalar value types (None for string / array).
fn scalar_size(vtype: u32) -> Option<u64> {
    match vtype {
        0 | 1 | 7 => Some(1),
        2 | 3 => Some(2),
        4 | 5 | 6 => Some(4),
        10 | 11 | 12 => Some(8),
        _ => None,
    }
}

fn skip<R: Read + Seek>(r: &mut R, n: u64) -> Result<(), String> {
    r.seek(SeekFrom::Current(n as i64)).map_err(|e| format!("gguf: seek: {e}"))?;
    Ok(())
}

/// Read one value. Scalars we care about are decoded; everything else is skipped.
fn read_value<R: Read + Seek>(r: &mut R, vtype: u32) -> Result<Value, String> {
    match vtype {
        4 => Ok(Value::U32(read_u32(r)?)),
        10 => Ok(Value::U64(read_u64(r)?)),
        8 => Ok(Value::Str(read_string(r)?)),
        9 => {
            let inner = read_u32(r)?;
            let count = read_u64(r)?;
            match scalar_size(inner) {
                Some(sz) => skip(r, sz.saturating_mul(count))?,
                None if inner == 8 => {
                    for _ in 0..count {
                        let len = read_u64(r)?;
                        if len > MAX_STRING {
                            return Err("gguf: string de array demasiado largo".into());
                        }
                        skip(r, len)?;
                    }
                }
                None => return Err(format!("gguf: array anidado no soportado (tipo {inner})")),
            }
            Ok(Value::Other)
        }
        _ => {
            let sz = scalar_size(vtype).ok_or_else(|| format!("gguf: tipo de valor desconocido {vtype}"))?;
            if vtype == 0 || vtype == 1 || vtype == 7 {
                read_u8(r)?;
            } else {
                skip(r, sz)?;
            }
            Ok(Value::Other)
        }
    }
}

/// Parse the metadata of a GGUF stream. `size_bytes` is only used to report size_mb.
pub fn parse<R: Read + Seek>(r: &mut R, size_bytes: u64) -> Result<GgufInfo, String> {
    let mut magic = [0u8; 4];
    r.read_exact(&mut magic).map_err(|e| format!("gguf: cabecera: {e}"))?;
    if &magic != GGUF_MAGIC {
        return Err("no es un archivo GGUF (magic inválido)".into());
    }
    let version = read_u32(r)?;
    if version != 2 && version != 3 {
        return Err(format!("gguf: versión {version} no soportada (se admiten 2 y 3)"));
    }
    let _tensor_count = read_u64(r)?;
    let kv_count = read_u64(r)?;
    if kv_count > 1_000_000 {
        return Err("gguf: número de metadatos inverosímil".into());
    }

    let mut info = GgufInfo { version, size_mb: size_bytes / (1024 * 1024), ..Default::default() };
    let mut pending: Vec<(String, Value)> = Vec::new();

    for _ in 0..kv_count {
        let key = read_string(r)?;
        let vtype = read_u32(r)?;
        let value = read_value(r, vtype)?;
        match key.as_str() {
            "general.architecture" => {
                if let Value::Str(s) = value { info.architecture = s; }
            }
            "general.name" => {
                if let Value::Str(s) = value { info.name = s; }
            }
            "general.file_type" => {
                if let Value::U32(v) = value { info.file_type = Some(v); }
            }
            _ => pending.push((key, value)),
        }
    }

    // Architecture-scoped keys (e.g. "llama.block_count") are only resolvable once
    // the architecture is known; it normally comes first but the spec doesn't promise it.
    let arch = info.architecture.clone();
    for (key, value) in pending {
        let Some(rest) = key.strip_prefix(&format!("{arch}.")) else { continue };
        let as_u32 = match value {
            Value::U32(v) => Some(v),
            Value::U64(v) => u32::try_from(v).ok(),
            _ => None,
        };
        match rest {
            "block_count" => info.block_count = as_u32,
            "context_length" => info.context_length = as_u32,
            "embedding_length" => info.embedding_length = as_u32,
            "expert_count" => info.expert_count = as_u32,
            "vocab_size" => info.vocab_size = as_u32.map(u64::from),
            _ => {}
        }
    }

    info.quant = match info.file_type {
        Some(ft) => file_type_name(ft),
        None => String::new(),
    };
    Ok(info)
}

/// Read metadata from a GGUF file on disk.
pub fn read_file(path: &Path) -> Result<GgufInfo, String> {
    let file = File::open(path).map_err(|e| format!("abrir {}: {e}", path.display()))?;
    let size = file.metadata().map(|m| m.len()).unwrap_or(0);
    let mut reader = BufReader::with_capacity(1 << 20, file);
    parse(&mut reader, size)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn put_str(buf: &mut Vec<u8>, s: &str) {
        buf.extend_from_slice(&(s.len() as u64).to_le_bytes());
        buf.extend_from_slice(s.as_bytes());
    }

    fn kv_str(buf: &mut Vec<u8>, key: &str, val: &str) {
        put_str(buf, key);
        buf.extend_from_slice(&8u32.to_le_bytes());
        put_str(buf, val);
    }

    fn kv_u32(buf: &mut Vec<u8>, key: &str, val: u32) {
        put_str(buf, key);
        buf.extend_from_slice(&4u32.to_le_bytes());
        buf.extend_from_slice(&val.to_le_bytes());
    }

    fn kv_f32(buf: &mut Vec<u8>, key: &str, val: f32) {
        put_str(buf, key);
        buf.extend_from_slice(&6u32.to_le_bytes());
        buf.extend_from_slice(&val.to_le_bytes());
    }

    fn kv_str_array(buf: &mut Vec<u8>, key: &str, vals: &[&str]) {
        put_str(buf, key);
        buf.extend_from_slice(&9u32.to_le_bytes());
        buf.extend_from_slice(&8u32.to_le_bytes());
        buf.extend_from_slice(&(vals.len() as u64).to_le_bytes());
        for v in vals {
            put_str(buf, v);
        }
    }

    fn kv_u32_array(buf: &mut Vec<u8>, key: &str, vals: &[u32]) {
        put_str(buf, key);
        buf.extend_from_slice(&9u32.to_le_bytes());
        buf.extend_from_slice(&4u32.to_le_bytes());
        buf.extend_from_slice(&(vals.len() as u64).to_le_bytes());
        for v in vals {
            buf.extend_from_slice(&v.to_le_bytes());
        }
    }

    fn sample(version: u32, arch_first: bool) -> Vec<u8> {
        let mut kvs: Vec<u8> = Vec::new();
        let mut count = 0u64;
        if arch_first {
            kv_str(&mut kvs, "general.architecture", "llama");
            count += 1;
        }
        kv_str(&mut kvs, "general.name", "Test Model 7B");
        kv_u32(&mut kvs, "general.file_type", 15);
        kv_u32(&mut kvs, "llama.block_count", 32);
        kv_u32(&mut kvs, "llama.context_length", 8192);
        kv_u32(&mut kvs, "llama.embedding_length", 4096);
        kv_f32(&mut kvs, "llama.attention.layer_norm_rms_epsilon", 1e-5);
        kv_str_array(&mut kvs, "tokenizer.ggml.tokens", &["<s>", "</s>", "hola"]);
        kv_u32_array(&mut kvs, "tokenizer.ggml.token_type", &[1, 2, 3]);
        count += 8;
        if !arch_first {
            kv_str(&mut kvs, "general.architecture", "llama");
            count += 1;
        }
        let mut buf = Vec::new();
        buf.extend_from_slice(b"GGUF");
        buf.extend_from_slice(&version.to_le_bytes());
        buf.extend_from_slice(&291u64.to_le_bytes()); // tensor count (ignored)
        buf.extend_from_slice(&count.to_le_bytes());
        buf.extend_from_slice(&kvs);
        buf.extend_from_slice(&[0u8; 64]); // pretend tensor info follows
        buf
    }

    #[test]
    fn parses_metadata_v3() {
        let data = sample(3, true);
        let info = parse(&mut Cursor::new(&data), 4_000 * 1024 * 1024).unwrap();
        assert_eq!(info.architecture, "llama");
        assert_eq!(info.name, "Test Model 7B");
        assert_eq!(info.file_type, Some(15));
        assert_eq!(info.quant, "Q4_K_M");
        assert_eq!(info.block_count, Some(32));
        assert_eq!(info.context_length, Some(8192));
        assert_eq!(info.embedding_length, Some(4096));
        assert_eq!(info.expert_count, None);
        assert!(!info.is_moe());
        assert_eq!(info.size_mb, 4000);
        assert_eq!(info.version, 3);
    }

    #[test]
    fn architecture_after_scoped_keys_still_resolves() {
        let data = sample(2, false);
        let info = parse(&mut Cursor::new(&data), 0).unwrap();
        assert_eq!(info.block_count, Some(32));
        assert_eq!(info.context_length, Some(8192));
    }

    #[test]
    fn rejects_non_gguf_and_v1() {
        let mut bad = sample(3, true);
        bad[0] = b'X';
        assert!(parse(&mut Cursor::new(&bad), 0).unwrap_err().contains("magic"));
        let v1 = sample(1, true);
        assert!(parse(&mut Cursor::new(&v1), 0).unwrap_err().contains("versión 1"));
    }

    #[test]
    fn file_type_labels() {
        assert_eq!(file_type_name(1), "F16");
        assert_eq!(file_type_name(7), "Q8_0");
        assert_eq!(file_type_name(18), "Q6_K");
        assert_eq!(file_type_name(999), "ftype 999");
    }

    #[test]
    fn moe_flag_from_expert_count() {
        let mut kvs = Vec::new();
        kv_str(&mut kvs, "general.architecture", "qwen3moe");
        kv_u32(&mut kvs, "qwen3moe.expert_count", 128);
        kv_u32(&mut kvs, "qwen3moe.block_count", 48);
        let mut buf = Vec::new();
        buf.extend_from_slice(b"GGUF");
        buf.extend_from_slice(&3u32.to_le_bytes());
        buf.extend_from_slice(&0u64.to_le_bytes());
        buf.extend_from_slice(&3u64.to_le_bytes());
        buf.extend_from_slice(&kvs);
        let info = parse(&mut Cursor::new(&buf), 0).unwrap();
        assert!(info.is_moe());
        assert_eq!(info.block_count, Some(48));
        assert_eq!(info.quant, "");
    }
}
