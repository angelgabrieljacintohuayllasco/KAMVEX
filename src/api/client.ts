import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

export type Dataset = {
  name: string;
  n_records: number;
  profile: string;
  path: string;
  dim?: number;
};

export type Fragment = { text: string; score: number; source_id: string | null };
export type ChatResponse = { answer: string; fragments: Fragment[] };
export type BuildEvent = { stage: string; pct: number; msg: string };
export type HwInfo = {
  cpu_brand: string;
  physical_cores: number;
  logical_cores: number;
  total_ram_gb: number;
  available_ram_gb: number;
  gpus: GpuInfo[];
  has_vulkan: boolean;
  has_cuda: boolean;
};

export type GpuInfo = {
  vendor: string;
  name: string;
  vram_mb: number;
  backend: string;
};

export type Prescription = {
  backend: string;
  ngl: number;
  threads: number;
  ctx: number;
  batch: number;
  ctk: string;
  ctv: string;
  flash_attn: boolean;
  mlock: boolean;
  draft_model: string | null;
};

let _base: string | null = null;

async function base(): Promise<string> {
  if (_base) return _base;
  const port = await invoke<number>("sidecar_port");
  _base = `http://127.0.0.1:${port}`;
  return _base;
}

/** Poll the Rust side until the sidecar's port is open. */
export async function waitForSidecar(timeoutMs = 90_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await invoke<boolean>("sidecar_ready")) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

export async function detectHardware(): Promise<HwInfo> {
  return invoke<HwInfo>("detect_hardware");
}

export async function listDatasets(): Promise<Dataset[]> {
  const r = await fetch(`${await base()}/datasets`);
  if (!r.ok) throw new Error(`listDatasets ${r.status}`);
  return r.json();
}

export async function pickJsonFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    filters: [{ name: "Data files", extensions: ["json", "jsonl", "csv"] }],
  });
  return typeof selected === "string" ? selected : null;
}

export async function startBuild(
  name: string,
  json_path: string,
  profile: string,
): Promise<string> {
  const r = await fetch(`${await base()}/datasets/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, json_path, profile }),
  });
  if (!r.ok) throw new Error(`startBuild ${r.status}: ${await r.text()}`);
  return (await r.json()).job_id as string;
}

/** Subscribe to build progress via SSE. Resolves when done, rejects on error. */
export async function streamBuild(
  jobId: string,
  onEvent: (e: BuildEvent) => void,
): Promise<void> {
  const url = `${await base()}/datasets/build/${jobId}/events`;
  return new Promise((resolve, reject) => {
    const es = new EventSource(url);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as BuildEvent;
      onEvent(ev);
      if (ev.stage === "done") {
        es.close();
        resolve();
      } else if (ev.stage === "error") {
        es.close();
        reject(new Error(ev.msg));
      }
    };
    es.onerror = () => {
      es.close();
      reject(new Error("conexión SSE perdida"));
    };
  });
}

export async function chat(
  dataset: string,
  query: string,
  agentBMode: string = "statistical",
  samplers?: { temperature?: number; top_p?: number; top_k?: number; repeat_penalty?: number },
): Promise<ChatResponse> {
  const body: Record<string, unknown> = { dataset, query, agent_b_mode: agentBMode };
  if (samplers) Object.assign(body, samplers);
  const r = await fetch(`${await base()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`chat ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Inference engine (llama-server) ─────────────────────────────────────────

export async function llamaPort(): Promise<number> {
  return invoke<number>("llama_port");
}

export async function llamaReady(): Promise<boolean> {
  return invoke<boolean>("llama_ready");
}

export async function llamaStart(model: string, flags: string[]): Promise<string> {
  return invoke<string>("llama_start", { model, flags });
}

export async function llamaStop(): Promise<void> {
  return invoke<void>("llama_stop");
}

export async function llamaEnsureBinary(backend: string): Promise<string> {
  return invoke<string>("llama_ensure_binary", { backendStr: backend });
}

export async function llamaBinaryPresent(backend: string): Promise<boolean> {
  return invoke<boolean>("llama_binary_present", { backendStr: backend });
}

export async function autotuneFlags(modelSizeMb: number, preset: string): Promise<Prescription> {
  return invoke<Prescription>("autotune_flags", { modelSizeMb, preset });
}

export async function inferenceConnect(port: number): Promise<{ status: string; alive: boolean }> {
  const r = await fetch(`${await base()}/inference/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port }),
  });
  if (!r.ok) throw new Error(`inferenceConnect ${r.status}`);
  return r.json();
}

export async function inferenceDisconnect(): Promise<void> {
  await fetch(`${await base()}/inference/disconnect`, { method: "POST" });
}

export async function inferenceStatus(): Promise<{ connected: boolean; alive?: boolean }> {
  const r = await fetch(`${await base()}/inference/status`);
  if (!r.ok) return { connected: false };
  return r.json();
}

export type InferenceMetrics = {
  connected: boolean;
  active_slots: number;
  total_decoded: number;
  slots: Array<{ id: number; is_processing: boolean; n_ctx: number; next_token?: { n_decoded: number } }>;
};

export async function inferenceMetrics(): Promise<InferenceMetrics> {
  const r = await fetch(`${await base()}/inference/metrics`);
  if (!r.ok) return { connected: false, active_slots: 0, total_decoded: 0, slots: [] };
  return r.json();
}

// ── Oregano Test (anti-hallucination quality audit) ─────────────────────────

export type OreganoDetail = {
  query: string;
  forbidden: string[];
  forbidden_found: string[];
  passed: boolean;
  answer_preview: string;
};

export type OreganoResult = {
  dataset: string;
  score: number;
  total: number;
  passed: number;
  hallucinations: number;
  details: OreganoDetail[];
};

export async function runOreganoTest(dataset: string): Promise<OreganoResult> {
  const r = await fetch(`${await base()}/oregano/${encodeURIComponent(dataset)}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`oregano ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── HuggingFace Hub (curated GGUF) ──────────────────────────────────────────

export type HubModel = {
  repo: string;
  file: string;
  name: string;
  size_mb: number;
  desc: string;
};

export async function listHubModels(): Promise<HubModel[]> {
  const r = await fetch(`${await base()}/models/hub`);
  if (!r.ok) throw new Error(`listHubModels ${r.status}`);
  return r.json();
}

export async function downloadHubModel(repo: string, file: string): Promise<{ status: string; path?: string; error?: string }> {
  const r = await fetch(`${await base()}/models/hub/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo, file }),
  });
  if (!r.ok) throw new Error(`downloadHubModel ${r.status}`);
  return r.json();
}

// ── Federated query (MoE semantic router) ───────────────────────────────────

export type FederatedResponse = ChatResponse & {
  dataset: string | null;
  score: number;
};

export async function federatedChat(
  query: string,
  agentBMode: string = "statistical",
  samplers?: { temperature?: number; top_p?: number; top_k?: number; repeat_penalty?: number },
): Promise<FederatedResponse> {
  const body: Record<string, unknown> = { query, agent_b_mode: agentBMode };
  if (samplers) Object.assign(body, samplers);
  const r = await fetch(`${await base()}/federated`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`federated ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Dataset export (.kamvex) ────────────────────────────────────────────────

export async function exportDatasetUrl(dataset: string): Promise<string> {
  const b = await base();
  return `${b}/datasets/${encodeURIComponent(dataset)}/export`;
}

// ── Model A/B comparison ────────────────────────────────────────────────────

export type CompareResult = {
  a: { answer: string; mode: string; fragments: Fragment[] };
  b: { answer: string; mode: string; fragments: Fragment[] };
};

export async function compareModels(
  dataset: string,
  query: string,
  modeA: string = "statistical",
  modeB: string = "grounded",
): Promise<CompareResult> {
  const r = await fetch(`${await base()}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, query, mode_a: modeA, mode_b: modeB }),
  });
  if (!r.ok) throw new Error(`compare ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Build dataset from raw text ─────────────────────────────────────────────

export async function startBuildText(name: string, text: string, profile: string = "low-ram", pdfPath?: string): Promise<{ job_id: string; n_chunks: number }> {
  const r = await fetch(`${await base()}/datasets/build-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, text, profile, pdf_path: pdfPath ?? "" }),
  });
  if (!r.ok) throw new Error(`startBuildText ${r.status}: ${await r.text()}`);
  return r.json();
}
