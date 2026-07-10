import SegmentedControl, { type SegmentedOption } from "./ui/SegmentedControl";
import { useI18n } from "../i18n";

export type AgentBMode = "statistical" | "grounded" | "free";

const TONES: Record<AgentBMode, SegmentedOption["tone"]> = {
  statistical: "success",
  grounded: "warning",
  free: "neutral",
};

export default function ModeSelector({
  mode,
  onChange,
  inferenceRunning = true,
}: {
  mode: AgentBMode;
  onChange: (m: AgentBMode) => void;
  inferenceRunning?: boolean;
}) {
  const { t } = useI18n();

  const options: SegmentedOption<AgentBMode>[] = (["statistical", "grounded", "free"] as AgentBMode[]).map((m) => {
    const needsEngine = m !== "statistical";
    const unavailable = needsEngine && !inferenceRunning;
    return {
      value: m,
      label: t(`mode.${m}`),
      tone: TONES[m],
      dim: unavailable,
      title: unavailable ? t("mode.needsEngine") : t(`mode.${m}.desc`),
    };
  });

  return <SegmentedControl value={mode} options={options} onChange={onChange} />;
}
