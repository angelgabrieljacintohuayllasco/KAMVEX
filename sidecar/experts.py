"""
Expertos — perfiles de dominio que hacen a KAMVEX más preciso en un área concreta.

Un experto ata todo lo que define "ser bueno en X":

    corpus        qué datasets del catálogo necesita (conocimiento del dominio)
    modelo        qué GGUF rinde mejor ahí (código → Qwen2.5-Coder, general → Qwen2.5)
    modo          Exacto / Anclado / Libre por defecto para ese tipo de pregunta
    prompt        instrucciones de sistema del dominio (modo Libre)
    samplers      temperatura y penalizaciones adecuadas (código = determinista)
    retrieval     cuántos fragmentos y con qué umbral

No es fine-tuning: es especialización por recuperación + decodificación, que es lo
que de verdad mueve la precisión de un modelo pequeño corriendo en local.

El catálogo vive en `experts_catalog.json` (junto a este archivo) para poder
publicar expertos nuevos sin tocar código; este módulo lo carga y lo valida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import paths

HERE = paths.SIDECAR_DIR
CATALOG_FILE = HERE / "experts_catalog.json"

MODES = ("statistical", "grounded", "free")


@dataclass
class ExpertModel:
    """A GGUF recommendation for an expert (catalog id + why)."""
    id: str
    name: str
    repo: str = ""
    file: str = ""
    size_mb: int = 0
    reason: str = ""

    @classmethod
    def from_json(cls, d: dict) -> "ExpertModel":
        return cls(id=str(d.get("id", "")), name=str(d.get("name", d.get("id", ""))),
                   repo=str(d.get("repo", "")), file=str(d.get("file", "")),
                   size_mb=int(d.get("size_mb", 0) or 0), reason=str(d.get("reason", "")))


@dataclass
class Expert:
    id: str
    name: str
    description: str = ""
    icon: str = ""
    datasets: list[str] = field(default_factory=list)
    models: list[ExpertModel] = field(default_factory=list)
    default_mode: str = "grounded"
    system_prompt: str = ""
    samplers: dict = field(default_factory=dict)
    top_k: int = 5
    min_score: float | None = None
    examples: list[str] = field(default_factory=list)
    language: str = "es"

    @classmethod
    def from_json(cls, d: dict) -> "Expert":
        mode = str(d.get("default_mode", "grounded"))
        if mode not in MODES:
            mode = "grounded"
        return cls(
            id=str(d["id"]),
            name=str(d.get("name", d["id"])),
            description=str(d.get("description", "")),
            icon=str(d.get("icon", "")),
            datasets=[str(x) for x in d.get("datasets", [])],
            models=[ExpertModel.from_json(m) for m in d.get("models", [])],
            default_mode=mode,
            system_prompt=str(d.get("system_prompt", "")),
            samplers=dict(d.get("samplers", {})),
            top_k=int(d.get("top_k", 5) or 5),
            min_score=(float(d["min_score"]) if d.get("min_score") is not None else None),
            examples=[str(x) for x in d.get("examples", [])],
            language=str(d.get("language", "es")),
        )

    def to_json(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description, "icon": self.icon,
            "datasets": self.datasets,
            "models": [m.__dict__ for m in self.models],
            "default_mode": self.default_mode, "system_prompt": self.system_prompt,
            "samplers": self.samplers, "top_k": self.top_k, "min_score": self.min_score,
            "examples": self.examples, "language": self.language,
        }


def load_catalog(path: Path | None = None) -> list[Expert]:
    """Read the expert catalog. Returns [] when the file is missing or invalid."""
    f = path or CATALOG_FILE
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[Expert] = []
    for d in data.get("experts", []):
        if not isinstance(d, dict) or not d.get("id"):
            continue
        try:
            out.append(Expert.from_json(d))
        except (KeyError, TypeError, ValueError):
            continue
    return out


# Un modelo cuantizado necesita su tamaño en RAM más el contexto y el propio programa.
# Con estos márgenes, 8 GB dan para un 3B, 16 GB para un 7B y 32 GB para un 9B holgado.
RAM_FRACTION = 0.45
RAM_RESERVE_MB = 3500


def recommend(models: list[ExpertModel], ram_total_mb: float | None) -> ExpertModel | None:
    """El modelo más capaz que cabe en esta máquina, no el primero de la lista.

    El catálogo va de mayor a menor. Elegir siempre el primero obliga a todos a bajar el
    grande; elegir siempre el último desperdicia una máquina con 32 GB. Se mide.
    """
    if not models:
        return None
    if not ram_total_mb or ram_total_mb <= 0:
        return models[-1]                      # sin dato fiable, el más prudente
    budget = min(ram_total_mb * RAM_FRACTION, ram_total_mb - RAM_RESERVE_MB)
    fits = [m for m in models if (m.size_mb or 0) <= budget]
    if fits:
        return max(fits, key=lambda m: m.size_mb or 0)
    return min(models, key=lambda m: m.size_mb or 0)


def status(expert: Expert, installed_datasets: set[str], local_model_files: set[str],
           ram_total_mb: float | None = None) -> dict:
    """Which pieces of the expert are present on this machine."""
    missing_datasets = [d for d in expert.datasets if d not in installed_datasets]
    model_present = next((m.id for m in expert.models if m.file and m.file in local_model_files), None)
    best = recommend(expert.models, ram_total_mb)
    return {
        "ready": not missing_datasets and (model_present is not None or expert.default_mode == "statistical"),
        "missing_datasets": missing_datasets,
        "installed_datasets": [d for d in expert.datasets if d in installed_datasets],
        "model_present": model_present,
        "recommended_model": best.id if best else None,
    }
