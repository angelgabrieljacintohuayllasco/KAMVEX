import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

export type Lang = "es" | "en";
export type Theme = "dark" | "light";

export type Dict = Record<string, { es: string; en: string }>;

const dict: Dict = {
  // Chat
  "chat.greeting": { es: "Hola 👋", en: "Hello 👋" },
  "chat.howHelp": { es: "¿En qué te ayudo hoy?", en: "How can I help you today?" },
  "chat.placeholder": { es: "Pregunta lo que quieráŠ¦", en: "Ask anything…" },
  "chat.buildKnowledge": { es: "＋ Construir conocimiento", en: "＋ Build knowledge" },
  "chat.grounded": { es: "Respuestas ancladas al corpus — sin alucinaciones.", en: "Grounded answers — no hallucinations." },
  "chat.fragments": { es: "fragmento(s) fuente", en: "source fragment(s)" },
  "chat.noDataset": { es: "Selecciona o construye conocimiento primero (pestaña Knowledge).", en: "Select or build knowledge first (Knowledge tab)." },

  // Knowledge
  "knowledge.title": { es: "Knowledge", en: "Knowledge" },
  "knowledge.desc": { es: "Construye inteligencia anclada a tus datos (DASA + SHARD). Cada base es una fuente que el chat puede usar sin alucinar.", en: "Build intelligence grounded in your data (DASA + SHARD). Each base is a source the chat can use without hallucinating." },
  "knowledge.build": { es: "Construir desde un archivo", en: "Build from file" },
  "knowledge.pickFile": { es: "Elegir archivo (JSON / JSONL / CSV)", en: "Choose file (JSON / JSONL / CSV)" },
  "knowledge.changeFile": { es: "Cambiar archivo", en: "Change file" },
  "knowledge.name": { es: "Nombre", en: "Name" },
  "knowledge.profile": { es: "Perfil del índice", en: "Index profile" },
  "knowledge.buildBtn": { es: "Construir índice", en: "Build index" },
  "knowledge.building": { es: "Construyendo…", en: "Building…" },
  "knowledge.built": { es: "Inteligencias construidas", en: "Built intelligences" },
  "knowledge.empty": { es: "Aún no hay datasets. Construye uno arriba.", en: "No datasets yet. Build one above." },
  "knowledge.records": { es: "registros", en: "records" },
  "knowledge.profileLabel": { es: "perfil", en: "profile" },
  "knowledge.oregano": { es: "🧪 Oregano Test", en: "🧪 Oregano Test" },
  "knowledge.auditing": { es: "Auditando…", en: "Auditing…" },
  "knowledge.confidence": { es: "/ 100 confianza anti-alucinación", en: "/ 100 anti-hallucination confidence" },
  "knowledge.testsPassed": { es: "tests pasaron", en: "tests passed" },
  "knowledge.hallucinations": { es: "alucinaciones detectadas", en: "hallucinations detected" },
  "knowledge.detail": { es: "Detalle", en: "Detail" },
  "knowledge.termsHalled": { es: "términos alucinados", en: "hallucinated terms" },

  // Models
  "models.title": { es: "Models", en: "Models" },
  "models.desc": { es: "Motor de inferencia local (llama.cpp). Importa un GGUF, auto-configura los flags según tu hardware, y lanza.", en: "Local inference engine (llama.cpp). Import a GGUF, auto-tune flags for your hardware, and launch." },
  "models.model": { es: "Modelo", en: "Model" },
  "models.importGguf": { es: "Importar GGUF", en: "Import GGUF" },
  "models.changeModel": { es: "Cambiar modelo", en: "Change model" },
  "models.sizeMb": { es: "Tamaño aproximado (MB)", en: "Approximate size (MB)" },
  "models.autotune": { es: "Auto-tune", en: "Auto-tune" },
  "models.preset": { es: "Preset", en: "Preset" },
  "models.computeFlags": { es: "Calcular flags óptimos", en: "Compute optimal flags" },
  "models.binary": { es: "Binario", en: "Binary" },
  "models.downloadBinary": { es: "Descargar llama-server", en: "Download llama-server" },
  "models.ready": { es: "✓ Listo", en: "✓ Ready" },
  "models.downloading": { es: "Descargando…", en: "Downloading…" },
  "models.start": { es: "▶ Iniciar inferencia", en: "▶ Start inference" },
  "models.starting": { es: "Iniciando…", en: "Starting…" },
  "models.stop": { es: "■ Detener", en: "■ Stop" },
  "models.stopping": { es: "Deteniendo…", en: "Stopping…" },
  "models.active": { es: "activo", en: "active" },
  "models.hub": { es: "Descargar desde HuggingFace", en: "Download from HuggingFace" },
  "models.hubLoading": { es: "Cargando lista…", en: "Loading list…" },
  "models.download": { es: "↓ Descargar", en: "↓ Download" },

  // Settings
  "settings.title": { es: "Settings", en: "Settings" },
  "settings.backend": { es: "Backend (sidecar)", en: "Backend (sidecar)" },
  "settings.port": { es: "Puerto", en: "Port" },
  "settings.status": { es: "Estado", en: "Status" },
  "settings.active": { es: "activo ✓", en: "active ✓" },
  "settings.starting": { es: "iniciando…", en: "starting…" },
  "settings.hardware": { es: "Hardware", en: "Hardware" },
  "settings.cpu": { es: "CPU", en: "CPU" },
  "settings.physicalCores": { es: "Núcleos físicos", en: "Physical cores" },
  "settings.logicalCores": { es: "Hilos lógicos", en: "Logical threads" },
  "settings.totalRam": { es: "RAM total", en: "Total RAM" },
  "settings.availableRam": { es: "RAM disponible", en: "Available RAM" },
  "settings.detecting": { es: "Detectando…", en: "Detecting…" },
  "settings.autotuneSoon": { es: "La auto-configuración por hardware (recomendar modelo + perfil + flags) llega en el siguiente slice.", en: "Hardware auto-tuning (model + profile + flags recommendation) coming in the next slice." },
  "settings.language": { es: "Idioma", en: "Language" },
  "settings.theme": { es: "Tema", en: "Theme" },
  "settings.themeDark": { es: "Oscuro", en: "Dark" },
  "settings.themeLight": { es: "Claro", en: "Light" },

  // App
  "app.starting": { es: "Iniciando KAMVEX…", en: "Starting KAMVEX…" },
  "app.failed": { es: "No se pudo iniciar KAMVEX", en: "Failed to start KAMVEX" },
  "app.checkPython": { es: "Revisa que Python y las dependencias del backend estén instalados.", en: "Check that Python and backend dependencies are installed." },
  "app.startingEngine": { es: "Levantando el motor local.", en: "Starting local engine." },
  "app.newChat": { es: "＋ New Chat", en: "＋ New Chat" },
  "app.recents": { es: "Recents", en: "Recents" },
  "app.noConvos": { es: "Sin conversaciones.", en: "No conversations." },
  "app.newConvo": { es: "Nueva conversación", en: "New conversation" },

  // Mode selector
  "mode.statistical": { es: "Statistical", en: "Statistical" },
  "mode.grounded": { es: "LLM-grounded", en: "LLM-grounded" },
  "mode.free": { es: "LLM-free", en: "LLM-free" },
  "mode.statistical.desc": { es: "0 alucinación — vocabulario bloqueado", en: "0 hallucination — vocabulary locked" },
  "mode.grounded.desc": { es: "LLM formatea sin inventar", en: "LLM formats without inventing" },
  "mode.free.desc": { es: "Chat libre con system prompt", en: "Free chat with system prompt" },

  // Samplers
  "sampler.title": { es: "Samplers", en: "Samplers" },
  "sampler.temp": { es: "Temp", en: "Temp" },
  "sampler.topP": { es: "Top-p", en: "Top-p" },
  "sampler.topK": { es: "Top-k", en: "Top-k" },
  "sampler.repeat": { es: "Repeat", en: "Repeat" },

  // Metrics
  "metrics.noEngine": { es: "Sin motor", en: "No engine" },
  "metrics.tokensDecoded": { es: "tokens decodificados", en: "tokens decoded" },
};

type I18nContextType = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
  theme: Theme;
  setTheme: (t: Theme) => void;
};

const I18nContext = createContext<I18nContextType | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem("kamvex-lang");
    return (saved === "es" || saved === "en") ? saved : "es";
  });
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("kamvex-theme");
    return (saved === "light") ? "light" : "dark";
  });

  function updateLang(l: Lang) {
    setLang(l);
    localStorage.setItem("kamvex-lang", l);
  }

  function updateTheme(t: Theme) {
    setTheme(t);
    localStorage.setItem("kamvex-theme", t);
    document.documentElement.setAttribute("data-theme", t);
  }

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  function t(key: string): string {
    const entry = dict[key];
    if (!entry) return key;
    return entry[lang];
  }

  return (
    <I18nContext.Provider value={{ lang, setLang: updateLang, t, theme, setTheme: updateTheme }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
