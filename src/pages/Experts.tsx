import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookA, Check, Code, Download, HeartPulse, Landmark, MessageCircle, Scale, Sparkles,
} from "lucide-react";
import {
  downloadHubModel,
  installDataset,
  listExperts,
  subscribeHubDownload,
  type DownloadProgress,
  type Expert,
} from "../api/client";
import { Badge, Button, Card } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../api/errors";

const ICONS: Record<string, React.ReactNode> = {
  Code: <Code className="h-5 w-5" />,
  HeartPulse: <HeartPulse className="h-5 w-5" />,
  Scale: <Scale className="h-5 w-5" />,
  BookA: <BookA className="h-5 w-5" />,
  Landmark: <Landmark className="h-5 w-5" />,
  MessageCircle: <MessageCircle className="h-5 w-5" />,
};

type Step = { label: string; progress?: DownloadProgress };

function fmtMb(mb: number): string {
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${mb} MB`;
}

/**
 * Experts: pick a domain and KAMVEX installs the corpus and the model that make
 * it good at that domain, then answers with the right mode, prompt and decoding.
 */
/** El modelo que el sidecar recomienda para esta maquina, no el primero del catalogo.
 *  El catalogo va de mayor a menor; el sidecar elige el mas capaz que cabe en la RAM. */
function recommendedModel(e: Expert) {
  return e.models.find((m) => m.id === e.status.recommended_model) ?? e.models[0];
}

export default function Experts({
  onChanged,
  selectedExpert,
  onSelectExpert,
  goChat,
}: {
  onChanged: () => void;
  selectedExpert: string | null;
  onSelectExpert: (id: string | null) => void;
  goChat: (question?: string) => void;
}) {
  const { t } = useI18n();
  const [experts, setExperts] = useState<Expert[]>([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState<string | null>(null);
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const unsubs = useRef<Array<() => void>>([]);

  const reload = useCallback(() => {
    listExperts()
      .then((d) => setExperts(d.experts))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
    const u = unsubs.current;
    return () => u.forEach((f) => f());
  }, [reload]);

  function waitDownload(id: string, label: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const un = subscribeHubDownload(id, (p) => {
        setStep({ label, progress: p });
        if (p.status === "done") resolve();
        else if (p.status === "error") reject(new Error(p.error));
        else if (p.status === "cancelled") reject(new Error("cancelled"));
      });
      unsubs.current.push(un);
    });
  }

  /** Install everything the expert needs: its datasets, then its recommended model. */
  async function setup(e: Expert) {
    setInstalling(e.id);
    setError(null);
    try {
      for (const ds of e.status.missing_datasets) {
        setStep({ label: t("experts.installingDataset").replace("{name}", ds) });
        const res = await installDataset({ id: ds });
        await waitDownload(res.download_id, t("experts.installingDataset").replace("{name}", ds));
      }
      const model = recommendedModel(e);
      if (model && !e.status.model_present) {
        setStep({ label: t("experts.downloadingModel").replace("{name}", model.name) });
        const res = await downloadHubModel(model.repo, model.file);
        if (res.status !== "already" && res.download_id) {
          await waitDownload(res.download_id, t("experts.downloadingModel").replace("{name}", model.name));
        }
      }
      onChanged();
      reload();
      onSelectExpert(e.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setInstalling(null);
      setStep(null);
    }
  }

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1 tracking-tight">{t("experts.title")}</h1>
      <p className="text-sm text-white/40 mb-5">{t("experts.desc")}</p>

      {loading && experts.length === 0 && <p className="text-sm text-white/40">{t("catalogds.loading")}</p>}
      {error && <p className="mb-4 text-sm text-red-400 whitespace-pre-wrap">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {experts.map((e) => {
          const active = selectedExpert === e.id;
          const busy = installing === e.id;
          const model = recommendedModel(e);
          const needs = e.status.missing_datasets.length + (model && !e.status.model_present ? 1 : 0);
          return (
            <Card key={e.id} className={active ? "border-accent/50" : ""}>
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 shrink-0 ${active ? "text-accent" : "text-white/40"}`}>
                  {ICONS[e.icon] ?? <Sparkles className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="font-medium">{e.name}</h2>
                    {e.status.ready && <Badge tone="success">{t("experts.ready")}</Badge>}
                    {active && <Badge tone="accent">{t("experts.active")}</Badge>}
                    <Badge tone="neutral">{t(`mode.${e.default_mode}`)}</Badge>
                  </div>
                  <p className="text-sm text-white/50 mt-1">{e.description}</p>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                    {e.datasets.map((d) => (
                      <Badge key={d} tone={e.status.installed_datasets.includes(d) ? "success" : "neutral"}>
                        {e.status.installed_datasets.includes(d) && <Check className="h-2.5 w-2.5" />} {d}
                      </Badge>
                    ))}
                    {model && (
                      <Badge tone={e.status.model_present ? "success" : "neutral"}>
                        {e.status.model_present && <Check className="h-2.5 w-2.5" />} {model.name} · {fmtMb(model.size_mb)}
                      </Badge>
                    )}
                  </div>
                  {model?.reason && !e.status.model_present && (
                    <p className="text-[10px] text-white/30 mt-1">{model.reason}</p>
                  )}

                  {busy && step && (
                    <div className="mt-2">
                      <p className="text-[11px] text-amber-300">{step.label}</p>
                      {step.progress && (
                        <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden mt-1">
                          <div
                            className="h-full rounded-full bg-accent transition-all"
                            style={{ width: `${step.progress.status === "downloading" ? step.progress.pct : 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  )}

                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    {needs > 0 ? (
                      <Button onClick={() => setup(e)} loading={busy} variant="primary" size="sm" icon={<Download className="h-3.5 w-3.5" />}>
                        {t("experts.setup")}
                      </Button>
                    ) : (
                      <Button
                        onClick={() => { onSelectExpert(e.id); goChat(); }}
                        variant={active ? "secondary" : "primary"}
                        size="sm"
                      >
                        {active ? t("experts.goChat") : t("experts.use")}
                      </Button>
                    )}
                    {active && (
                      <Button onClick={() => onSelectExpert(null)} variant="ghost" size="sm">
                        {t("experts.deactivate")}
                      </Button>
                    )}
                  </div>

                  {e.examples.length > 0 && e.status.ready && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {e.examples.slice(0, 3).map((q) => (
                        <button
                          key={q}
                          onClick={() => { onSelectExpert(e.id); goChat(q); }}
                          className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] text-white/60 hover:bg-white/10 hover:text-white/90 transition-colors"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
