import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

export type Lang = "es" | "en";
export type Theme = "dark" | "light";

export type Dict = Record<string, { es: string; en: string }>;

const dict: Dict = {
  // Chat
  "chat.greeting": { es: "Hola 👋", en: "Hello 👋" },
  "chat.howHelp": { es: "¿En qué te ayudo hoy?", en: "How can I help you today?" },
  "chat.placeholder": { es: "Pregunta lo que quieras…", en: "Ask anything…" },
  "chat.buildKnowledge": { es: "＋ Construir conocimiento", en: "＋ Build knowledge" },
  "chat.grounded": { es: "Respuestas ancladas al corpus — sin alucinaciones.", en: "Grounded answers — no hallucinations." },
  "chat.fragments": { es: "fragmento(s) fuente", en: "source fragment(s)" },
  "chat.authority": { es: "nombrado en la pregunta", en: "named in the question" },
  "chat.noDataset": { es: "Selecciona o construye conocimiento primero (pestaña Conocimiento).", en: "Select or build knowledge first (Knowledge tab)." },
  "chat.federatedTip": { es: "Router semántico MoE: busca en todos los datasets automáticamente", en: "MoE semantic router: searches all datasets automatically" },
  "chat.auto": { es: "Auto", en: "Auto" },
  "chat.autoActive": { es: "✦ Auto", en: "✦ Auto" },

  // Navigation
  "nav.knowledge": { es: "Conocimiento", en: "Knowledge" },
  "nav.models": { es: "Modelos", en: "Models" },
  "nav.compare": { es: "Comparar", en: "Compare" },
  "nav.settings": { es: "Ajustes", en: "Settings" },

  // Knowledge
  "knowledge.title": { es: "Conocimiento", en: "Knowledge" },
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
  "knowledge.fileMode": { es: "📁 Archivo", en: "📁 File" },
  "knowledge.textMode": { es: "✏️ Texto", en: "✏️ Text" },
  "knowledge.textPlaceholder": { es: "Pega aquí el texto que quieres convertir en conocimiento…", en: "Paste the text you want to turn into knowledge…" },
  "knowledge.importPdf": { es: "📄 Importar PDF", en: "📄 Import PDF" },
  "knowledge.changePdf": { es: "Cambiar PDF", en: "Change PDF" },
  "knowledge.oreganoTip": { es: "Auditar calidad anti-alucinación", en: "Audit anti-hallucination quality" },
  "knowledge.export": { es: "📦 Export", en: "📦 Export" },
  "knowledge.exportTip": { es: "Exportar como .kamvex", en: "Export as .kamvex" },
  "knowledge.dim": { es: "dim", en: "dim" },
  "knowledge.of": { es: "de", en: "of" },
  "knowledge.pages": { es: "páginas", en: "pages" },
  "knowledge.summary": { es: "Resumen", en: "Summary" },
  "knowledge.summaryTip": { es: "Resumir el documento fuente (anclado, sin alucinar)", en: "Summarize the source document (grounded, no hallucinations)" },
  "knowledge.summarizing": { es: "Generando resumen…", en: "Generating summary…" },
  "knowledge.starting": { es: "Iniciando", en: "Starting" },
  "knowledge.manage": { es: "Gestionar", en: "Manage" },
  "knowledge.manageTip": { es: "Ver detalles del dataset", en: "View dataset details" },
  "knowledge.sourceDoc": { es: "Documento origen", en: "Source document" },
  "knowledge.path": { es: "Ruta", en: "Path" },

  // Models
  "models.title": { es: "Modelos", en: "Models" },
  "models.desc": { es: "Motor de inferencia local (llama.cpp). Importa un GGUF, auto-configura los flags según tu hardware, y lanza.", en: "Local inference engine (llama.cpp). Import a GGUF, auto-tune flags for your hardware, and launch." },
  "models.model": { es: "Modelo", en: "Model" },
  "models.localModel": { es: "Modelo local", en: "Local model" },
  "models.importGguf": { es: "Importar GGUF", en: "Import GGUF" },
  "models.changeModel": { es: "Cambiar modelo", en: "Change model" },
  "models.importHint": { es: "Importa un modelo GGUF ya descargado", en: "Import an already downloaded GGUF model" },
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
  "models.downloaded": { es: "✓ Descargado", en: "✓ Downloaded" },
  "models.pause": { es: "Pausar", en: "Pause" },
  "models.resume": { es: "Reanudar", en: "Resume" },
  "models.cancel": { es: "Cancelar", en: "Cancel" },
  "models.paused": { es: "Pausado", en: "Paused" },
  "models.specDecode": { es: "spec. decode", en: "spec. decode" },
  "models.addDraft": { es: "＋ Modelo borrador", en: "＋ Draft model" },
  "models.changeDraft": { es: "Cambiar borrador", en: "Change draft" },
  "models.search": { es: "Buscar modelos…", en: "Search models…" },
  "models.noResults": { es: "Ningún modelo coincide", en: "No models match" },
  "models.mayBeSlow": { es: "Puede ser lento", en: "May be slow" },
  "models.cat.ultralight": { es: "Ultraligeros (< 1 GB)", en: "Ultralight (< 1 GB)" },
  "models.cat.light": { es: "Ligeros (1-3 GB)", en: "Light (1-3 GB)" },
  "models.cat.medium": { es: "Medios (3-6 GB)", en: "Medium (3-6 GB)" },
  "models.cat.large": { es: "Grandes (6-10 GB)", en: "Large (6-10 GB)" },
  "models.cat.xl": { es: "XL (> 10 GB)", en: "XL (> 10 GB)" },
  "models.flashAttn": { es: "flash attn", en: "flash attn" },
  "models.mlock": { es: "mlock", en: "mlock" },
  "models.on": { es: "sí", en: "on" },
  "models.off": { es: "no", en: "off" },

  // Catalog
  "catalog.models": { es: "modelos", en: "models" },
  "catalog.providers": { es: "proveedores", en: "providers" },
  "catalog.searchPlaceholder": { es: "Buscar modelos por nombre, proveedor, capacidad…", en: "Search models by name, provider, capability…" },
  "catalog.filters": { es: "Filtros", en: "Filters" },
  "catalog.provider": { es: "Proveedor", en: "Provider" },
  "catalog.allProviders": { es: "Todos", en: "All" },
  "catalog.type": { es: "Tipo", en: "Type" },
  "catalog.capability": { es: "Capacidad", en: "Capability" },
  "catalog.size": { es: "Tamaño", en: "Size" },
  "catalog.sortBy": { es: "Ordenar", en: "Sort by" },
  "catalog.clearFilters": { es: "Limpiar filtros", en: "Clear filters" },
  "catalog.localTitle": { es: "Modelos locales (GGUF)", en: "Local models (GGUF)" },
  "catalog.remoteTitle": { es: "Modelos remotos", en: "Remote models" },
  "catalog.pluggable": { es: "pluggable", en: "pluggable" },
  "catalog.explore": { es: "Explorar", en: "Explore" },
  "catalog.allTypes": { es: "Todos", en: "All" },
  "catalog.allCaps": { es: "Todas", en: "All" },
  "catalog.allSizes": { es: "Todos", en: "All" },
  "catalog.type.chat": { es: "Chat", en: "Chat" },
  "catalog.type.code": { es: "Código", en: "Code" },
  "catalog.type.reasoning": { es: "Razonamiento", en: "Reasoning" },
  "catalog.type.vision": { es: "Visión", en: "Vision" },
  "catalog.type.multimodal": { es: "Multimodal", en: "Multimodal" },
  "catalog.type.embedding": { es: "Embeddings", en: "Embeddings" },
  "catalog.cap.chat": { es: "Chat", en: "Chat" },
  "catalog.cap.tools": { es: "Herramientas", en: "Tools" },
  "catalog.cap.vision": { es: "Visión", en: "Vision" },
  "catalog.cap.reasoning": { es: "Razonamiento", en: "Reasoning" },
  "catalog.cap.code": { es: "Código", en: "Code" },
  "catalog.cap.embedding": { es: "Embeddings", en: "Embeddings" },
  "catalog.sort.name": { es: "Nombre", en: "Name" },
  "catalog.sort.size": { es: "Tamaño", en: "Size" },
  "catalog.sort.provider": { es: "Proveedor", en: "Provider" },

  // Settings
  "settings.title": { es: "Ajustes", en: "Settings" },
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
  "settings.autotuneSoon": { es: "La auto-configuración por hardware está disponible en la pestaña Modelos.", en: "Hardware auto-tuning is available in the Models tab." },
  "settings.language": { es: "Idioma", en: "Language" },
  "settings.theme": { es: "Tema", en: "Theme" },
  "settings.themeDark": { es: "Oscuro", en: "Dark" },
  "settings.themeLight": { es: "Claro", en: "Light" },
  "settings.updates": { es: "Actualizaciones", en: "Updates" },
  "settings.checkUpdates": { es: "Buscar actualizaciones", en: "Check for updates" },
  "settings.checking": { es: "Comprobando…", en: "Checking…" },
  "settings.upToDate": { es: "KAMVEX está actualizado", en: "KAMVEX is up to date" },
  "settings.updateAvailable": { es: "Actualización disponible:", en: "Update available:" },
  "settings.gpu": { es: "GPU", en: "GPU" },
  "settings.cat.general": { es: "General", en: "General" },
  "settings.cat.appearance": { es: "Apariencia", en: "Appearance" },
  "settings.cat.engine": { es: "Motor", en: "Engine" },
  "settings.cat.hardware": { es: "Hardware", en: "Hardware" },
  "settings.cat.knowledge": { es: "Conocimiento", en: "Knowledge" },
  "settings.cat.about": { es: "Acerca de", en: "About" },
  "settings.knowledgeHint": { es: "Datasets disponibles para el chat. Gestión completa en la pestaña Conocimiento.", en: "Datasets available to chat. Full management in the Knowledge tab." },
  "settings.version": { es: "Versión", en: "Version" },
  "settings.license": { es: "Licencia", en: "License" },

  // App
  "app.starting": { es: "Iniciando KAMVEX…", en: "Starting KAMVEX…" },
  "app.failed": { es: "No se pudo iniciar KAMVEX", en: "Failed to start KAMVEX" },
  "app.checkPython": { es: "Revisa que Python y las dependencias del backend estén instalados.", en: "Check that Python and backend dependencies are installed." },
  "app.startingEngine": { es: "Levantando el motor local.", en: "Starting local engine." },
  "app.newChat": { es: "＋ Nuevo chat", en: "＋ New Chat" },
  "app.recents": { es: "Recientes", en: "Recents" },
  "app.noConvos": { es: "Sin conversaciones.", en: "No conversations." },
  "app.newConvo": { es: "Nueva conversación", en: "New conversation" },
  "app.searchChats": { es: "Buscar chats…", en: "Search chats…" },

  // Mode selector (Agent B engines)
  // Spanish uses clear, non-technical terms; English keeps product names.
  "mode.statistical": { es: "Exacto", en: "Statistical" },
  "mode.grounded": { es: "Anclado", en: "LLM-grounded" },
  "mode.free": { es: "Libre", en: "LLM-free" },
  "mode.statistical.desc": {
    es: "Respuestas exactas: reordena la información del corpus sin inventar nada. No usa IA. Cero alucinación.",
    en: "Deterministic engine: rearranges and connects sentences using only vocabulary from the retrieved fragments. No LLM involved. Zero hallucination, ideal for technical data."
  },
  "mode.grounded.desc": {
    es: "La IA redacta la respuesta usando solo tu corpus. No puede inventar información. Requiere motor activo.",
    en: "The LLM acts as a formatter: it combines fragments into a fluent answer but cannot invent information outside the corpus. Requires active llama-server."
  },
  "mode.free.desc": {
    es: "Conversación libre: si tu corpus no cubre la pregunta, la IA responde por sí misma. Requiere motor activo.",
    en: "General chat with system prompt. If the corpus does not cover the question, the LLM answers freely. Requires active llama-server."
  },
  "mode.needsEngine": { es: "Requiere motor de inferencia activo", en: "Requires an active inference engine" },

  // Samplers
  "sampler.title": { es: "Samplers", en: "Samplers" },
  "sampler.temp": { es: "Temp", en: "Temp" },
  "sampler.topP": { es: "Top-p", en: "Top-p" },
  "sampler.topK": { es: "Top-k", en: "Top-k" },
  "sampler.repeat": { es: "Repetición", en: "Repeat" },

  // Metrics
  "metrics.noEngine": { es: "Motor inactivo", en: "Engine offline" },
  "metrics.noEngineHint": { es: "Selecciona un modelo LLM arriba para habilitar respuestas con IA", en: "Select an LLM model above to enable AI responses" },
  "metrics.tokensDecoded": { es: "tokens decodificados", en: "tokens decoded" },
  "metrics.tokensPerSec": { es: "tokens/s", en: "tokens/s" },
  "metrics.ttft": { es: "TTFT", en: "TTFT" },
  "metrics.context": { es: "Contexto", en: "Context" },
  "metrics.ram": { es: "RAM", en: "RAM" },
  "metrics.vram": { es: "VRAM", en: "VRAM" },
  "metrics.active": { es: "activo", en: "active" },

  // Smart flow
  "flow.needsLlm": { es: "Este modo necesita un modelo LLM. Selecciona uno en el selector de la barra superior.", en: "This mode requires an LLM model. Select one in the top bar selector." },
  "flow.needsKnowledge": { es: "Este modo necesita una base de conocimiento. Construye una en la pestaña Conocimiento.", en: "This mode requires a knowledge base. Build one in the Knowledge tab." },
  "flow.needsBoth": { es: "Este modo necesita una base de conocimiento y un modelo LLM activo.", en: "This mode requires a knowledge base and an active LLM model." },
  "flow.autoStarting": { es: "Iniciando motor de inferencia…", en: "Starting inference engine…" },
  "flow.autoStartFailed": { es: "No se pudo iniciar el motor automáticamente. Revisa la configuración en Modelos.", en: "Could not auto-start the engine. Check configuration in Models." },
  "flow.selectLlm": { es: "Modelo LLM", en: "LLM Model" },
  "flow.noLlm": { es: "Sin modelo LLM", en: "No LLM model" },
  "flow.noModels": { es: "No hay modelos descargados", en: "No downloaded models" },
  "flow.goModels": { es: "Ir a Modelos para descargar", en: "Go to Models to download" },
  "flow.llmActive": { es: "LLM activo", en: "LLM active" },
  "flow.llmStarting": { es: "Iniciando…", en: "Starting…" },
  "flow.freeModeHint": { es: "Conversación libre con IA — sin base de conocimiento", en: "Free AI conversation — no knowledge base" },

  // Compare
  "compare.title": { es: "Comparar", en: "Compare" },
  "compare.desc": { es: "Ejecuta la misma consulta con dos modos de Agent B y compara lado a lado.", en: "Run the same query with two Agent B modes and compare side by side." },
  "compare.dataset": { es: "Dataset", en: "Dataset" },
  "compare.placeholder": { es: "Consulta a comparar…", en: "Query to compare…" },
  "compare.modeA": { es: "Modo A", en: "Mode A" },
  "compare.modeB": { es: "Modo B", en: "Mode B" },
  "compare.run": { es: "▶ Comparar", en: "▶ Compare" },
  "compare.running": { es: "Comparando…", en: "Comparing…" },
  "compare.fragments": { es: "fragmentos", en: "fragments" },

  // Shared controls
  "select.placeholder": { es: "Seleccionar…", en: "Select…" },
  "select.search": { es: "Buscar…", en: "Search…" },
  "select.empty": { es: "Sin resultados", en: "No results" },
  "common.confirm": { es: "¿Seguro? Confirmar", en: "Sure? Confirm" },
  "common.cancel": { es: "Cancelar", en: "Cancel" },
  "common.delete": { es: "Eliminar", en: "Delete" },

  // Engine card (Models)
  "engine.downloaded": { es: "Modelos descargados", en: "Downloaded models" },
  "engine.noneDownloaded": { es: "Aún no hay modelos descargados. Elige uno del catálogo o importa un GGUF.", en: "No models downloaded yet. Pick one from the catalog or import a GGUF." },
  "engine.use": { es: "Usar", en: "Use" },
  "engine.inUse": { es: "En uso", en: "In use" },
  "engine.info": { es: "Información del modelo", en: "Model info" },
  "engine.arch": { es: "Arquitectura", en: "Architecture" },
  "engine.layers": { es: "Capas", en: "Layers" },
  "engine.ctxTrain": { es: "Contexto entrenado", en: "Trained context" },
  "engine.quant": { es: "Cuantización", en: "Quantization" },
  "engine.size": { es: "Tamaño", en: "Size" },
  "engine.moe": { es: "MoE", en: "MoE" },
  "engine.readingInfo": { es: "Leyendo metadatos…", en: "Reading metadata…" },
  "engine.warnings": { es: "Avisos", en: "Warnings" },
  "engine.offload": { es: "capas en GPU", en: "layers on GPU" },
  "engine.stage.autotune": { es: "Calculando flags…", en: "Computing flags…" },
  "engine.stage.binary": { es: "Verificando motor…", en: "Checking engine…" },
  "engine.stage.spawn": { es: "Lanzando llama-server…", en: "Launching llama-server…" },
  "engine.stage.loading": { es: "Cargando modelo en memoria…", en: "Loading model into memory…" },
  "engine.stage.connect": { es: "Conectando con el sidecar…", en: "Connecting to sidecar…" },
  "engine.running": { es: "Motor activo", en: "Engine running" },
  "engine.log": { es: "Log", en: "Log" },
  "engine.presetHint": { es: "Eco: mínima memoria · Balanceado: recomendado · Máx: calidad y contexto largos", en: "Eco: least memory · Balanced: recommended · Max: quality and long context" },
  "models.preset.eco": { es: "Eco", en: "Eco" },
  "models.preset.balanced": { es: "Balanceado", en: "Balanced" },
  "models.preset.max": { es: "Máx", en: "Max" },

  // Knowledge — embeddings + management
  "knowledge.embedNotReady": { es: "Motor de embeddings no listo", en: "Embedding engine not ready" },
  "knowledge.embedHint": { es: "Para construir y consultar conocimiento KAMVEX necesita el motor CPU de llama.cpp y el modelo de embeddings all-MiniLM-L6-v2 (~45 MB). Se descargan una sola vez.", en: "To build and query knowledge KAMVEX needs the llama.cpp CPU engine and the all-MiniLM-L6-v2 embedding model (~45 MB). Downloaded once." },
  "knowledge.embedSetup": { es: "Preparar embeddings", en: "Set up embeddings" },
  "knowledge.embedPreparing": { es: "Preparando…", en: "Preparing…" },
  "knowledge.embedReady": { es: "Embeddings listos", en: "Embeddings ready" },
  "knowledge.embedBackend": { es: "Motor de embeddings", en: "Embedding engine" },
  "knowledge.deleteDataset": { es: "Eliminar dataset", en: "Delete dataset" },
  "knowledge.deleting": { es: "Eliminando…", en: "Deleting…" },
  "knowledge.builtWith": { es: "Embeddings", en: "Embeddings" },

  // Settings — engine / hardware
  "settings.sidecarLaunch": { es: "Lanzamiento", en: "Launch" },
  "settings.pid": { es: "PID", en: "PID" },
  "settings.logs": { es: "Log", en: "Log" },
  "settings.dirs": { es: "Carpetas", en: "Folders" },
  "settings.dataDir": { es: "Datasets", en: "Datasets" },
  "settings.modelsDir": { es: "Modelos", en: "Models" },
  "settings.binariesDir": { es: "Binarios", en: "Binaries" },
  "settings.logsDir": { es: "Logs", en: "Logs" },
  "settings.sidecarVersion": { es: "Versión del sidecar", en: "Sidecar version" },
  "settings.dasa": { es: "DASA / SHARD", en: "DASA / SHARD" },
  "settings.embeddings": { es: "Embeddings", en: "Embeddings" },
  "settings.available": { es: "disponible", en: "available" },
  "settings.unavailable": { es: "no disponible", en: "unavailable" },
  "settings.inference": { es: "Motor de inferencia", en: "Inference engine" },
  "settings.stopped": { es: "detenido", en: "stopped" },
  "settings.vram": { es: "VRAM", en: "VRAM" },
  "settings.integrated": { es: "integrada", en: "integrated" },
  "settings.discrete": { es: "dedicada", en: "discrete" },
  "settings.isa": { es: "Instrucciones CPU", en: "CPU instructions" },
  "settings.backends": { es: "Backends", en: "Backends" },
  "settings.noGpu": { es: "Sin GPU detectada", en: "No GPU detected" },

  // Smart flow additions
  "flow.engineDied": { es: "El motor de inferencia se detuvo. Se reiniciará con el siguiente mensaje.", en: "The inference engine stopped. It will restart with the next message." },
  "app.deleteConvo": { es: "Eliminar conversación", en: "Delete conversation" },

  // Dataset catalog (pre-built bundles)
  "catalogds.title": { es: "Conocimiento listo para usar", en: "Ready-made knowledge" },
  "catalogds.desc": { es: "Datasets ya convertidos en shards + índice: se descargan, se verifican y quedan listos sin procesar nada en tu equipo.", en: "Datasets already converted into shards + index: downloaded, verified and ready without any processing on your machine." },
  "catalogds.install": { es: "Descargar e instalar", en: "Download & install" },
  "catalogds.reinstall": { es: "Reinstalar", en: "Reinstall" },
  "catalogds.installed": { es: "Instalado", en: "Installed" },
  "catalogds.import": { es: "Importar .kamvex", en: "Import .kamvex" },
  "catalogds.refresh": { es: "Actualizar catálogo", en: "Refresh catalog" },
  "catalogds.loading": { es: "Cargando catálogo…", en: "Loading catalog…" },
  "catalogds.empty": { es: "No hay datasets en el catálogo (sin conexión o catálogo vacío).", en: "No datasets in the catalog (offline or empty catalog)." },
  "catalogds.source": { es: "fuente", en: "source" },
  "catalogds.embedHint": { es: "Para consultar el dataset necesitas el motor de embeddings (Preparar embeddings).", en: "Querying the dataset needs the embedding engine (Set up embeddings)." },
  "catalogds.status.downloading": { es: "Descargando", en: "Downloading" },
  "catalogds.status.paused": { es: "Pausado", en: "Paused" },
  "catalogds.status.verifying": { es: "Verificando integridad…", en: "Verifying integrity…" },
  "catalogds.status.installing": { es: "Instalando…", en: "Installing…" },
  "knowledge.rebuild": { es: "Reconstruir índice", en: "Rebuild index" },
  "knowledge.rebuildTip": { es: "Volver a calcular embeddings e índice con el motor local (usa records.json del dataset)", en: "Recompute embeddings and index with the local engine (uses the dataset's records.json)" },
  "knowledge.rebuilding": { es: "Reconstruyendo…", en: "Rebuilding…" },

  // Experts
  "nav.experts": { es: "Expertos", en: "Experts" },
  "experts.title": { es: "Expertos", en: "Experts" },
  "experts.desc": { es: "Elige un área y KAMVEX instala el conocimiento y el modelo que lo hacen bueno en eso: responde con el corpus correcto, el modo adecuado y decodificación determinista cuando importa.", en: "Pick a field and KAMVEX installs the knowledge and the model that make it good at it: the right corpus, the right mode and deterministic decoding when it matters." },
  "experts.ready": { es: "Listo", en: "Ready" },
  "experts.active": { es: "En uso", en: "In use" },
  "experts.setup": { es: "Instalar lo que falta", en: "Install what's missing" },
  "experts.use": { es: "Usar este experto", en: "Use this expert" },
  "experts.goChat": { es: "Ir al chat", en: "Go to chat" },
  "experts.deactivate": { es: "Quitar", en: "Remove" },
  "experts.installingDataset": { es: "Instalando conocimiento: {name}…", en: "Installing knowledge: {name}…" },
  "experts.downloadingModel": { es: "Descargando modelo: {name}…", en: "Downloading model: {name}…" },
  "experts.none": { es: "Sin experto", en: "No expert" },
  "experts.pick": { es: "Experto", en: "Expert" },
  "experts.notReady": { es: "Este experto aún no tiene su conocimiento o su modelo instalados.", en: "This expert is missing its knowledge or its model." },

  // Engine — advanced flags editor
  "engine.advanced": { es: "Ajustes avanzados", en: "Advanced settings" },
  "engine.advancedHint": { es: "Sobrescribe la receta automática. Se aplica al iniciar el motor.", en: "Overrides the automatic prescription. Applied when the engine starts." },
  "engine.reset": { es: "Restablecer auto", en: "Reset to auto" },
  "engine.field.ngl": { es: "Capas en GPU (ngl)", en: "GPU layers (ngl)" },
  "engine.field.threads": { es: "Hilos", en: "Threads" },
  "engine.field.ctx": { es: "Contexto (tokens)", en: "Context (tokens)" },
  "engine.field.batch": { es: "Batch", en: "Batch" },
  "engine.field.kv": { es: "KV cache", en: "KV cache" },
  "engine.field.flash": { es: "Flash attention", en: "Flash attention" },
  "engine.field.mlock": { es: "mlock (fijar en RAM)", en: "mlock (pin in RAM)" },
  "engine.field.backend": { es: "Backend", en: "Backend" },
  "engine.modified": { es: "modificado", en: "modified" },
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
