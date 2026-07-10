import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Section, Button, SegmentedControl } from "../../components/ui";
import { useI18n } from "../../i18n";

export default function GeneralPanel() {
  const { lang, setLang, t } = useI18n();
  const [updateMsg, setUpdateMsg] = useState<string | null>(null);
  const [updateBusy, setUpdateBusy] = useState(false);

  return (
    <>
      <Section title={t("settings.language")}>
        <SegmentedControl
          size="md"
          value={lang}
          options={[
            { value: "es", label: "Español" },
            { value: "en", label: "English" },
          ]}
          onChange={setLang}
        />
      </Section>

      <Section title={t("settings.updates")}>
        <Button
          onClick={async () => {
            setUpdateBusy(true);
            setUpdateMsg(null);
            try {
              const result = await invoke<string | null>("check_updates");
              setUpdateMsg(result ? `${t("settings.updateAvailable")} ${result}` : t("settings.upToDate"));
            } catch (e) {
              setUpdateMsg(String(e));
            } finally {
              setUpdateBusy(false);
            }
          }}
          loading={updateBusy}
        >
          {updateBusy ? t("settings.checking") : t("settings.checkUpdates")}
        </Button>
        {updateMsg && <p className="mt-2 text-xs text-white/50">{updateMsg}</p>}
      </Section>
    </>
  );
}
