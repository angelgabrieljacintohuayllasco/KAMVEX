import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

// ── Types ───────────────────────────────────────────────────────────────────

export type Dataset = {
  name: string;
  n_records: number;
  profile: string;
  path: string;
  dim?: number;
  source_doc?: string;
  n_pages?: number;
  built_at?: number;
  embedding_backend?: string;
  embedding_model?: string;
  has_records?: boolean;
  display_name?: string;
  description?: string;
  license?: string;
};

export type Fragment = { text: string; score: number; source_id: string | null };
export type ChatResponse = { answer: string; fragments: Fragment[]; mode?: string; dataset?: string | null };
export type BuildEvent = { stage: string; pct: number; msg: string };

export type GpuInfo = {
  vendor: string;
  name: string;
  vram_mb: number;
  backend: string;
  integrated: boolean;
  driver_version?: string;
  note?: string | null;
};

export type HwInfo = {
  cpu_brand: string;
  physical_cores: number;
  logical_cores: number;
  total_ram_gb: number;
  available_ram_gb: number;
  gpus: GpuInfo[];
  has_vulkan: boolean;
  has_cuda: boolean;
  has_avx2: boolean;
  has_avx512: boolean;
  os: string;
};

/** Single source of truth for llama-server flags — produced by Rust, applied by Rust. */
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
  warnings: string[];
  offloaded_layers: number | null;
  total_layers: number | null;
};

export type GgufInfo = {
  architecture: string;
  name: string;
  file_type: number | null;
  quant: string;
  block_count: number | null;
  context_length: number | null;
  embedding_length: number | null;
  expert_count: number | null;
  vocab_size: number | null;
  size_mb: number;
  version: number;
};

export type SidecarStatus = {
  port: number;
  running: boolean;
  ready: boolean;
  launch: string;
  pid: number | null;
  log_path: string | null;
};

export type LlamaStatus = {
  running: boolean;
  port: number;
  backend: string;
  model: string | null;
  pid: number | null;
  log_path: string | null;
};

export type AppDirs = { data: string; models: string; binaries: string; logs: string };

export type HealthInfo = {
  status: string;
  version: string;
  dasa: boolean;
  embeddings: "sentence-transformers" | "llama-gguf" | "none";
  data_dir: string;
  models_dir: string;
};

export type EmbeddingsStatus = {
  backend: "sentence-transformers" | "llama-gguf" | "none";
  ready: boolean;
  st_installed: boolean;
  server_bin: string | null;
  model_path: string;
  model_present: boolean;
  model_repo: string;
  model_file: string;
  running: boolean;
  port: number | null;
  dim?: number | null;
};

export type SamplerOpts = {
  temperature?: number;
  top_p?: number;
  top_k?: number;
  repeat_penalty?: number;
  max_tokens?: number;
};

export type ChatTurn = { role: "user" | "assistant"; content: string };

// ── Transport helpers ───────────────────────────────────────────────────────

let _base: string | null = null;

async function base(): Promise<string> {
  if (_base) return _base;
  const port = await invoke<number>("sidecar_port");
  _base = `http://127.0.0.1:${port}`;
  return _base;
}

async function getJson<T>(path: string, fallback?: T): Promise<T> {
  const r = await fetch(`${await base()}${path}`);
  if (!r.ok) {
    if (fallback !== undefined) return fallback;
    throw new Error(`${path} ${r.status}: ${await errorText(r)}`);
  }
  return r.json();
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${await base()}${path}`, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} ${r.status}: ${await errorText(r)}`);
  return r.json();
}

async function del<T>(path: string): Promise<T> {
  const r = await fetch(`${await base()}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${path} ${r.status}: ${await errorText(r)}`);
  return r.json();
}

/** FastAPI puts the human message in `detail`; surface it instead of raw JSON. */
async function errorText(r: Response): Promise<string> {
  const text = await r.text();
  try {
    const j = JSON.parse(text);
    if (typeof j?.detail === "string") return j.detail;
  } catch {
    /* not JSON */
  }
  return text;
}

/** Read an SSE stream of JSON events until `isFinal` says so or the stream ends. */
function subscribeSse<T>(path: string, onEvent: (e: T) => void, isFinal: (e: T) => boolean): () => void {
  let stopped = false;
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  (async () => {
    try {
      const resp = await fetch(`${await base()}${path}`);
      reader = resp.body?.getReader() ?? null;
      if (!reader) return;
      const decoder = new TextDecoder();
      let buf = "";
      while (!stopped) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6)) as T;
            onEvent(ev);
            if (isFinal(ev)) {
              stopped = true;
              break;
            }
          } catch {
            /* malformed line */
          }
        }
      }
    } catch {
      /* connection lost — caller sees no further events */
    } finally {
      reader?.cancel().catch(() => {});
    }
  })();
  return () => {
    stopped = true;
  };
}

// ── Shell (Rust) ────────────────────────────────────────────────────────────

/** Poll the Rust side until the sidecar's port is open. */
export async function waitForSidecar(timeoutMs = 90_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await invoke<boolean>("sidecar_ready")) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

export const sidecarStatus = () => invoke<SidecarStatus>("sidecar_status");
export const appDirs = () => invoke<AppDirs>("app_dirs");
export const detectHardware = () => invoke<HwInfo>("detect_hardware");
export const modelInfo = (path: string) => invoke<GgufInfo>("model_info", { path });

export const llamaPort = () => invoke<number>("llama_port");
export const llamaReady = () => invoke<boolean>("llama_ready");
export const llamaStatus = () => invoke<LlamaStatus>("llama_status");
export const llamaStop = () => invoke<void>("llama_stop");
export const llamaEnsureBinary = (backend: string) => invoke<string>("llama_ensure_binary", { backendStr: backend });
export const llamaBinaryPresent = (backend: string) => invoke<boolean>("llama_binary_present", { backendStr: backend });

export function llamaStart(model: string, prescription: Prescription, extraFlags?: string[]): Promise<number> {
  return invoke<number>("llama_start", { model, prescription, extraFlags: extraFlags ?? null });
}

/** Resolves true when llama-server answers, false on timeout; rejects if the process died. */
export function llamaWaitReady(timeoutMs = 180_000): Promise<boolean> {
  return invoke<boolean>("llama_wait_ready", { timeoutMs });
}

export function autotuneFlags(opts: { modelPath?: string; modelSizeMb?: number; preset: string }): Promise<Prescription> {
  return invoke<Prescription>("autotune_flags", {
    modelPath: opts.modelPath ?? null,
    modelSizeMb: opts.modelSizeMb ?? null,
    preset: opts.preset,
  });
}

/**
 * Full engine start: auto-tune → make sure the backend binary exists → spawn →
 * wait for the model to load → hook the sidecar. Used by the Models page and by
 * the chat auto-start so both follow exactly the same path.
 */
export async function startEngine(
  modelPath: string,
  preset: string,
  options: { prescription?: Prescription; draftModel?: string | null; onStage?: (stage: string) => void } = {},
): Promise<{ port: number; prescription: Prescription }> {
  const stage = options.onStage ?? (() => {});
  stage("autotune");
  const prescription = options.prescription ?? (await autotuneFlags({ modelPath, preset }));
  if (options.draftModel !== undefined) prescription.draft_model = options.draftModel;
  stage("binary");
  await llamaEnsureBinary(prescription.backend);
  stage("spawn");
  const port = await llamaStart(modelPath, prescription);
  stage("loading");
  const ready = await llamaWaitReady();
  if (!ready) throw new Error("llama-server no respondió a tiempo (modelo demasiado grande o lento)");
  stage("connect");
  await inferenceConnect(port);
  return { port, prescription };
}

// ── Sidecar: health / embeddings ────────────────────────────────────────────

export const health = () => getJson<HealthInfo>("/health");
export const embeddingsStatus = () => getJson<EmbeddingsStatus>("/embeddings/status");
export const embeddingsSetup = () =>
  postJson<{ status: "already" | "started"; download_id?: string; path?: string }>("/embeddings/setup");

// ── Datasets ────────────────────────────────────────────────────────────────

export const listDatasets = () => getJson<Dataset[]>("/datasets");

export async function pickJsonFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    filters: [{ name: "Data files", extensions: ["json", "jsonl", "csv"] }],
  });
  return typeof selected === "string" ? selected : null;
}

export async function pickFile(name: string, extensions: string[]): Promise<string | null> {
  const selected = await open({ multiple: false, filters: [{ name, extensions }] });
  return typeof selected === "string" ? selected : null;
}

export async function startBuild(name: string, json_path: string, profile: string): Promise<string> {
  return (await postJson<{ job_id: string }>("/datasets/build", { name, json_path, profile })).job_id;
}

export function startBuildText(name: string, text: string, profile = "low-ram", pdfPath?: string) {
  return postJson<{ job_id: string; n_chunks: number }>("/datasets/build-text", {
    name,
    text,
    profile,
    pdf_path: pdfPath ?? "",
  });
}

/** Subscribe to build progress via SSE. Resolves when done, rejects on error. */
export function streamBuild(jobId: string, onEvent: (e: BuildEvent) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    let finished = false;
    subscribeSse<BuildEvent>(
      `/datasets/build/${jobId}/events`,
      (ev) => {
        onEvent(ev);
        if (ev.stage === "done") {
          finished = true;
          resolve();
        } else if (ev.stage === "error") {
          finished = true;
          reject(new Error(ev.msg));
        }
      },
      (ev) => ev.stage === "done" || ev.stage === "error",
    );
    // A dropped connection without a final event must not hang the UI forever.
    setTimeout(() => {
      if (!finished) reject(new Error("conexión SSE perdida"));
    }, 6 * 60 * 60 * 1000);
  });
}

export const deleteDataset = (name: string) => del<{ status: string }>(`/datasets/${encodeURIComponent(name)}`);

// ── Experts (domain profiles: corpus + model + mode + prompt + samplers) ────

export type ExpertModel = {
  id: string;
  name: string;
  repo: string;
  file: string;
  size_mb: number;
  reason: string;
};

export type ExpertStatus = {
  ready: boolean;
  missing_datasets: string[];
  installed_datasets: string[];
  model_present: string | null;
  recommended_model: string | null;
};

export type Expert = {
  id: string;
  name: string;
  description: string;
  icon: string;
  datasets: string[];
  models: ExpertModel[];
  default_mode: "statistical" | "grounded" | "free";
  system_prompt: string;
  samplers: Record<string, number>;
  top_k: number;
  min_score: number | null;
  examples: string[];
  language: string;
  status: ExpertStatus;
};

export const listExperts = () => getJson<{ version: number; experts: Expert[] }>("/experts");
export const getExpert = (id: string) => getJson<Expert>(`/experts/${encodeURIComponent(id)}`);

export type ExpertChatResponse = ChatResponse & {
  expert: string;
  meta: Record<string, unknown>;
};

export function expertChat(
  expert: string,
  query: string,
  opts: { history?: ChatTurn[]; mode?: string; dataset?: string; samplers?: SamplerOpts; overrideSamplers?: boolean } = {},
) {
  return postJson<ExpertChatResponse>(`/experts/${encodeURIComponent(expert)}/chat`, {
    expert,
    query,
    history: opts.history ?? [],
    mode: opts.mode ?? "",
    dataset: opts.dataset ?? "",
    override_samplers: opts.overrideSamplers ?? false,
    ...(opts.samplers ?? {}),
  });
}

// ── Dataset catalog (pre-built .kamvex bundles) ─────────────────────────────

export type CatalogDataset = {
  id: string;
  name: string;
  description: string;
  language: string;
  license: string;
  source_url: string;
  records: number;
  profile?: string;
  dim?: number;
  embedding_model?: string | null;
  file: string;
  url?: string;
  size_bytes: number;
  sha256?: string;
  source_file?: string;
  source_url_file?: string;
  source_size_bytes?: number;
  built_at?: number;
  installed: boolean;
};

export const datasetsCatalog = () =>
  getJson<{ version: number; release_base: string; datasets: CatalogDataset[] }>("/datasets/catalog");

export function installDataset(opts: { id?: string; url?: string; name?: string; sha256?: string }) {
  return postJson<{ status: "started" | "in_progress"; download_id: string; name: string }>("/datasets/install", opts);
}

export const importDataset = (path: string, name?: string) =>
  postJson<{ status: string; name: string; n_records: number; dim: number }>("/datasets/import", { path, name: name ?? "" });

export const rebuildDataset = (name: string, profile = "low-ram") =>
  postJson<{ job_id: string }>(`/datasets/${encodeURIComponent(name)}/rebuild`, { profile });

export async function exportDatasetUrl(dataset: string): Promise<string> {
  return `${await base()}/datasets/${encodeURIComponent(dataset)}/export`;
}

export async function datasetSummary(name: string): Promise<string> {
  return (await postJson<{ summary: string }>(`/datasets/${encodeURIComponent(name)}/summary`)).summary;
}

// ── Chat ────────────────────────────────────────────────────────────────────

export function chat(dataset: string, query: string, agentBMode = "statistical", samplers?: SamplerOpts) {
  return postJson<ChatResponse>("/chat", { dataset, query, agent_b_mode: agentBMode, ...(samplers ?? {}) });
}

export function freeChat(query: string, samplers?: SamplerOpts, history: ChatTurn[] = [], systemPrompt = "") {
  return postJson<ChatResponse>("/chat/free", { query, history, system_prompt: systemPrompt, ...(samplers ?? {}) });
}

export type FederatedResponse = ChatResponse & { dataset: string | null; score: number };

export function federatedChat(query: string, agentBMode = "statistical", samplers?: SamplerOpts) {
  return postJson<FederatedResponse>("/federated", { query, agent_b_mode: agentBMode, ...(samplers ?? {}) });
}

export type CompareResult = {
  a: { answer: string; mode: string; fragments: Fragment[] };
  b: { answer: string; mode: string; fragments: Fragment[] };
};

export function compareModels(dataset: string, query: string, modeA = "statistical", modeB = "grounded") {
  return postJson<CompareResult>("/compare", { dataset, query, mode_a: modeA, mode_b: modeB });
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

export const runOreganoTest = (dataset: string) => postJson<OreganoResult>(`/oregano/${encodeURIComponent(dataset)}`);

// ── Local models + downloads ────────────────────────────────────────────────

export type LocalModel = { name: string; file: string; path: string; size_mb: number; mtime?: number };

export const listLocalModels = () => getJson<LocalModel[]>("/models/local", []);
export const deleteLocalModel = (file: string) => del<{ status: string }>(`/models/local/${encodeURIComponent(file)}`);

export type DownloadProgress = {
  status: "downloading" | "paused" | "verifying" | "installing" | "done" | "error" | "cancelled";
  downloaded: number;
  total: number;
  pct: number;
  speed_mbps: number;
  error: string;
  file?: string;
  kind?: "model" | "dataset";
  result?: Record<string, unknown> | null;
};

export type DownloadEntry = DownloadProgress & { download_id: string };

export function downloadHubModel(repo: string, file: string) {
  return postJson<{ status: "already" | "in_progress" | "started"; download_id?: string; path?: string }>(
    "/models/hub/download",
    { repo, file },
  );
}

export const listDownloads = () => getJson<DownloadEntry[]>("/downloads", []);

const isFinalDownload = (p: DownloadProgress) => p.status === "done" || p.status === "error" || p.status === "cancelled";

/** Subscribe to any download (model GGUF or dataset bundle). */
export function subscribeHubDownload(downloadId: string, onProgress: (p: DownloadProgress) => void): () => void {
  return subscribeSse<DownloadProgress>(`/downloads/${downloadId}/events`, onProgress, isFinalDownload);
}

/** Promise form: resolves on "done", rejects on error/cancel. */
export function waitDownload(downloadId: string, onProgress?: (p: DownloadProgress) => void): Promise<DownloadProgress> {
  return new Promise((resolve, reject) => {
    subscribeHubDownload(downloadId, (p) => {
      onProgress?.(p);
      if (p.status === "done") resolve(p);
      else if (p.status === "error") reject(new Error(p.error || "download error"));
      else if (p.status === "cancelled") reject(new Error("cancelled"));
    });
  });
}

export const cancelHubDownload = (id: string) => postJson(`/downloads/${id}/cancel`).then(() => {});
export const pauseHubDownload = (id: string) => postJson(`/downloads/${id}/pause`).then(() => {});
export const resumeHubDownload = (id: string) => postJson(`/downloads/${id}/resume`).then(() => {});

// ── Inference hook (sidecar ↔ llama-server) ─────────────────────────────────

export const inferenceConnect = (port: number) =>
  postJson<{ status: string; alive: boolean }>("/inference/connect", { port });
export const inferenceDisconnect = () => postJson("/inference/disconnect").then(() => {});
export const inferenceStatus = () => getJson<{ connected: boolean; alive?: boolean }>("/inference/status", { connected: false });

export type InferenceMetrics = {
  connected: boolean;
  active_slots: number;
  total_decoded: number;
  tokens_per_second: number;
  ttft_ms: number;
  context_used: number;
  context_total: number;
  context_pct: number;
  ram_used_gb?: number;
  ram_total_gb?: number;
  vram_used_mb?: number;
  vram_total_mb?: number;
  slots: Array<{ id: number; is_processing: boolean; n_ctx: number; next_token?: { n_decoded: number } }>;
};

const EMPTY_METRICS: InferenceMetrics = {
  connected: false, active_slots: 0, total_decoded: 0, tokens_per_second: 0, ttft_ms: 0,
  context_used: 0, context_total: 0, context_pct: 0, slots: [],
};

export const inferenceMetrics = () => getJson<InferenceMetrics>("/inference/metrics", EMPTY_METRICS);

// ── Citations ───────────────────────────────────────────────────────────────
// PDF page citations are encoded into Fragment.source_id as "{document}.pdf · p.{N}"
// (see sidecar/textsource.py). Parse it back out for display instead of threading
// new fields through DASA's Fragment dataclass, which KAMVEX does not modify.

export type ParsedCitation = { doc: string | null; page: number | null; label: string };

export function parseCitation(sourceId: string | null): ParsedCitation {
  if (!sourceId) return { doc: null, page: null, label: "" };
  const match = sourceId.match(/^(.*) · p\.(\d+)(?:#\d+)?$/);
  if (match) {
    return { doc: match[1], page: Number(match[2]), label: `${match[1]} · p.${match[2]}` };
  }
  return { doc: null, page: null, label: sourceId };
}
