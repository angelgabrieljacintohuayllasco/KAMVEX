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
    filters: [{ name: "JSON", extensions: ["json"] }],
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

export async function chat(dataset: string, query: string): Promise<ChatResponse> {
  const r = await fetch(`${await base()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, query }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}: ${await r.text()}`);
  return r.json();
}
