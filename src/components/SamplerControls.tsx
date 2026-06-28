import { useI18n } from "../i18n";

export type Samplers = {
  temperature: number;
  top_p: number;
  top_k: number;
  repeat_penalty: number;
};

export default function SamplerControls({
  samplers,
  onChange,
}: {
  samplers: Samplers;
  onChange: (s: Samplers) => void;
}) {
  const { t } = useI18n();
  const Slider = ({ label, key_, min, max, step }: { label: string; key_: keyof Samplers; min: number; max: number; step: number }) => (
    <label className="flex flex-col gap-0.5">
      <span className="text-white/40">{label}: <b className="text-white/80">{samplers[key_]}</b></span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={samplers[key_]}
        onChange={(e) => onChange({ ...samplers, [key_]: parseFloat(e.target.value) })}
        className="accent-indigo-500"
      />
    </label>
  );

  return (
    <details className="rounded-lg border border-white/10 bg-black/20 p-2">
      <summary className="cursor-pointer text-xs text-white/40">{t("sampler.title")}</summary>
      <div className="mt-2 grid grid-cols-2 gap-3">
        <Slider label={t("sampler.temp")} key_="temperature" min={0} max={2} step={0.05} />
        <Slider label={t("sampler.topP")} key_="top_p" min={0} max={1} step={0.01} />
        <Slider label={t("sampler.topK")} key_="top_k" min={1} max={100} step={1} />
        <Slider label={t("sampler.repeat")} key_="repeat_penalty" min={0.8} max={2} step={0.05} />
      </div>
    </details>
  );
}
