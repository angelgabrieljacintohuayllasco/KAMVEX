import { Section, SegmentedControl } from "../../components/ui";
import { useI18n } from "../../i18n";

export default function AppearancePanel() {
  const { theme, setTheme, t } = useI18n();
  return (
    <Section title={t("settings.theme")}>
      <SegmentedControl
        size="md"
        value={theme}
        options={[
          { value: "dark", label: t("settings.themeDark") },
          { value: "light", label: t("settings.themeLight") },
        ]}
        onChange={setTheme}
      />
    </Section>
  );
}
