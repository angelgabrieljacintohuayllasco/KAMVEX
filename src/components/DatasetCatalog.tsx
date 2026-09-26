import { useCallback, useEffect, useRef, useState } from "react";
import { Download, ExternalLink, FolderOpen, RefreshCw } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  datasetsCatalog,
  importDataset,
  installDataset,
  listDownloads,
  pickFile,
  subscribeHubDownload,
  type CatalogDataset,
  type DownloadProgress,
} from "../api/client";
import { Badge, Button, Card } from "./ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../api/errors";

type Progress = Record<string, DownloadProgress & { downloadId: string }>;

function fmtBytes(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${Math.round(b / 1e3)} KB`;
}

/**
 * Pre-built datasets (shards + IVF-PQ index) published as `.kamvex` bundles:
 * one click downloads, verifies (sha256) and unpacks — no embedding step on
 * the user's machine. Also imports local `.kamvex` files.
 */
export default function DatasetCatalog({ onChanged, embedReady }: { onChanged: () => void; embedReady: boolean }) {
  const { t } = useI18n();
  const [items, setItems] = useState<CatalogDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<Progress>({});
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const unsubs = useRef<Record<string, () => void>>({});

  const reload = useCallback(() => {
    setLoading(true);
    datasetsCatalog()
      .then((c) => setItems(c.datasets))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  function track(id: string, downloadId: string, initial?: DownloadProgress) {
    setProgress((p) => ({
      ...p,
      [id]: { downloadId, ...(initial ?? { status: "downloading", downloaded: 0, total: 0, pct: 0, speed_mbps: 0, error: "" }) },
    }));
    unsubs.current[id]?.();
    unsubs.current[id] = subscribeHubDownload(downloadId, (pr) => {
      setProgress((p) => ({ ...p, [id]: { ...pr, downloadId } }));
      if (pr.status === "done") {
        delete unsubs.current[id];
        onChanged();
        reload();
      }
      if (pr.status === "error") setError(pr.error);
    });
  }

  useEffect(() => {
    reload();
    listDownloads()
      .then((entries) => {
        for (const e of entries) {
          if (e.kind !== "dataset" || !(e.status === "downloading" || e.status === "paused" || e.status === "verifying" || e.status === "installing")) continue;
          const id = (e.file ?? "").replace(/\.kamvex$/, "");
          track(id, e.download_id, e);
        }
      })
      .catch(() => {});
    const u = unsubs.current;
    return () => Object.values(u).forEach((f) => f());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  async function install(d: CatalogDataset) {
    setError(null);
    try {
      const res = await installDataset({ id: d.id });
      track(d.id, res.download_id);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function importLocal() {
    setError(null);
    const path = await pickFile("KAMVEX dataset", ["kamvex", "zip"]);
    if (!path) return;
    setImporting(true);
    try {
      await importDataset(path);
      onChanged();
      reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <Card className="mb-6">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
        <div>
          <h2 className="font-medium">{t("catalogds.title")}</h2>
          <p className="text-xs text-white/40 mt-0.5">{t("catalogds.desc")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={importLocal} loading={importing} variant="secondary" size="sm" icon={<FolderOpen className="h-3.5 w-3.5" />}>
            {t("catalogds.import")}
          </Button>
          <Button onClick={reload} variant="ghost" size="sm" title={t("catalogds.refresh")} icon={<RefreshCw className="h-3.5 w-3.5" />} />
        </div>
      </div>

      {loading && items.length === 0 && <p className="text-sm text-white/40">{t("catalogds.loading")}</p>}
      {!loading && items.length === 0 && <p className="text-sm text-white/40">{t("catalogds.empty")}</p>}

      <div className="flex flex-col gap-2">
        {items.map((d) => {
          const pr = progress[d.id];
          const active = pr && (pr.status === "downloading" || pr.status === "paused" || pr.status === "verifying" || pr.status === "installing");
          return (
            <div key={d.id} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{d.name}</span>
                    <Badge>{d.records.toLocaleString()} {t("knowledge.records")}</Badge>
                    <Badge>{fmtBytes(d.size_bytes)}</Badge>
                    {d.language && <Badge tone="neutral">{d.language}</Badge>}
                    {d.installed && <Badge tone="success">{t("catalogds.installed")}</Badge>}
                  </div>
                  <p className="text-xs text-white/50 mt-1">{d.description}</p>
                  <p className="text-[10px] text-white/30 mt-1 flex items-center gap-2 flex-wrap">
                    {d.license && <span>{d.license}</span>}
                    {d.source_url && (
                      <a href={d.source_url} onClick={(e) => { e.preventDefault(); openUrl(d.source_url).catch(() => {}); }} className="hover:text-accent flex items-center gap-1">
                        <ExternalLink className="h-2.5 w-2.5" /> {t("catalogds.source")}
                      </a>
                    )}
                  </p>
                  {active && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between text-[10px] text-white/50 mb-1">
                        <span>{t(`catalogds.status.${pr.status}`)}{pr.status === "downloading" ? ` ${pr.pct}%` : ""}</span>
                        <span>
                          {pr.total > 0 && `${fmtBytes(pr.downloaded)} / ${fmtBytes(pr.total)}`}
                          {pr.status === "downloading" && pr.speed_mbps > 0 && ` · ${pr.speed_mbps.toFixed(1)} MB/s`}
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${pr.status === "installing" || pr.status === "verifying" ? "bg-emerald-400 animate-pulse" : "bg-accent"}`}
                          style={{ width: `${pr.status === "downloading" ? pr.pct : 100}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
                <div className="shrink-0">
                  {!active && (
                    <Button
                      onClick={() => install(d)}
                      variant={d.installed ? "ghost" : "primary"}
                      size="sm"
                      disabled={!d.url}
                      icon={<Download className="h-3.5 w-3.5" />}
                      title={embedReady ? undefined : t("catalogds.embedHint")}
                    >
                      {d.installed ? t("catalogds.reinstall") : t("catalogds.install")}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {error && <p className="mt-3 text-sm text-red-400 whitespace-pre-wrap">{error}</p>}
    </Card>
  );
}
