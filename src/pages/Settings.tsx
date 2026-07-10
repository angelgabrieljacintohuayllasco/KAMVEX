import { useState, type ReactNode } from "react";
import { BookOpen, Cpu, Info, Palette, Server, SlidersHorizontal } from "lucide-react";
import { useI18n } from "../i18n";
import GeneralPanel from "./settings/GeneralPanel";
import AppearancePanel from "./settings/AppearancePanel";
import EnginePanel from "./settings/EnginePanel";
import HardwarePanel from "./settings/HardwarePanel";
import KnowledgePanel from "./settings/KnowledgePanel";
import AboutPanel from "./settings/AboutPanel";

type Category = "general" | "appearance" | "engine" | "hardware" | "knowledge" | "about";

export default function Settings() {
  const { t } = useI18n();
  const [cat, setCat] = useState<Category>("general");

  const categories: { key: Category; label: string; icon: ReactNode }[] = [
    { key: "general", label: t("settings.cat.general"), icon: <SlidersHorizontal className="h-4 w-4" /> },
    { key: "appearance", label: t("settings.cat.appearance"), icon: <Palette className="h-4 w-4" /> },
    { key: "engine", label: t("settings.cat.engine"), icon: <Server className="h-4 w-4" /> },
    { key: "hardware", label: t("settings.cat.hardware"), icon: <Cpu className="h-4 w-4" /> },
    { key: "knowledge", label: t("settings.cat.knowledge"), icon: <BookOpen className="h-4 w-4" /> },
    { key: "about", label: t("settings.cat.about"), icon: <Info className="h-4 w-4" /> },
  ];

  return (
    <div className="h-full flex">
      <nav className="w-52 shrink-0 border-r border-white/10 p-3 flex flex-col gap-0.5">
        <h1 className="px-2 py-2 text-sm font-semibold text-white/80">{t("settings.title")}</h1>
        {categories.map((c) => (
          <button
            key={c.key}
            onClick={() => setCat(c.key)}
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
              cat === c.key ? "bg-white/10 text-white" : "text-white/55 hover:bg-white/5 hover:text-white/85"
            }`}
          >
            <span className="text-white/60">{c.icon}</span>
            {c.label}
          </button>
        ))}
      </nav>
      <div className="flex-1 overflow-y-auto p-6 max-w-2xl">
        {cat === "general" && <GeneralPanel />}
        {cat === "appearance" && <AppearancePanel />}
        {cat === "engine" && <EnginePanel />}
        {cat === "hardware" && <HardwarePanel />}
        {cat === "knowledge" && <KnowledgePanel />}
        {cat === "about" && <AboutPanel />}
      </div>
    </div>
  );
}
