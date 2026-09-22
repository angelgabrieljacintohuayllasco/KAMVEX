"""
Documentación oficial de Python en español — un registro por función, clase o método.

Sources:
  - https://github.com/python/python-docs-es (branch 3.13): the official Spanish
    translation, as gettext `.po` catalogs (msgid = English, msgstr = Spanish).
  - https://github.com/python/cpython (branch 3.13, Doc/): the English `.rst` sources.

Sphinx does not put the `.. function::` directives into the catalogs, so the symbol a
paragraph belongs to has to come from the `.rst`. The line numbers in the `#:` comments
cannot be trusted (the catalogs are regenerated on their own schedule and drift from the
branch), so each English `msgid` is *located by content* inside the `.rst`: the directive
that precedes that position owns the paragraph. Joining both yields records like
"functools.lru_cache" with their own Spanish explanation — exactly what
"¿qué hace functools.lru_cache?" needs.

Usage:
    git clone --filter=blob:none --sparse --depth 1 -b 3.13 https://github.com/python/cpython.git E:/corpus-src/cpython
    cd E:/corpus-src/cpython && git sparse-checkout set Doc
    curl -L -o p.zip https://github.com/python/python-docs-es/archive/refs/heads/3.13.zip && unzip p.zip -d E:/corpus-src
    python scripts/datasets/fetch_python_docs_es.py --po E:/corpus-src/python-docs-es-3.13 --rst E:/corpus-src/cpython/Doc
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import clean_text, log, save_records

MIN_CHARS = 120
MAX_CHARS = 4000
AREAS = ("library", "tutorial", "reference", "howto", "faq")

DIRECTIVE_RE = re.compile(
    r"^(\s*)\.\.\s+(?:py:)?(function|class|method|decorator|data|attribute|exception|module|classmethod|staticmethod)::\s*(.+?)\s*$")
CONT_RE = re.compile(r"^(\s*)(\w[\w.]*\s*\(.*\)|\w[\w.]*)\s*$")
ROLE_RE = re.compile(r":[a-z:]+:`~?([^`<]+?)(?:\s*<[^`>]*>)?`")
LITERAL_RE = re.compile(r"``([^`]+)``")
REF_RE = re.compile(r"`([^`<]+?)\s*<[^`>]*>`_+")
PO_REF_RE = re.compile(r"\.\./Doc/([\w./-]+\.rst):(\d+)")


# ── .rst: symbol blocks located by character offset ─────────────────────────

def _norm(text: str) -> str:
    """Collapse whitespace so `.rst` line wrapping and `.po` wrapping compare equal."""
    return " ".join(text.split())


class RstIndex:
    """Directives of one `.rst`, with the normalized text for content lookups."""

    def __init__(self, rst: Path, module_default: str):
        raw = rst.read_text(encoding="utf-8", errors="replace")
        self.norm = _norm(raw)
        # offset of every line inside `self.norm`
        self.blocks: list[tuple[int, str, str, str]] = []   # (offset, symbol, kind, signature)
        module = module_default
        class_stack: list[tuple[int, str]] = []
        offset = 0
        for line in raw.splitlines():
            n = _norm(line)
            m = DIRECTIVE_RE.match(line)
            if m:
                indent, kind, sig = len(m.group(1)), m.group(2), m.group(3).strip()
                name = sig.split("(")[0].strip().rstrip(":").strip()
                name = name.split()[-1] if " " in name else name
                if kind == "module":
                    module = name or module
                    class_stack.clear()
                    if name:
                        self.blocks.append((offset, module, "module", ""))
                elif name:
                    while class_stack and class_stack[-1][0] >= indent:
                        class_stack.pop()
                    if kind == "class":
                        full = name if "." in name else (f"{module}.{name}" if module else name)
                        class_stack.append((indent, full))
                    elif class_stack and "." not in name:
                        full = f"{class_stack[-1][1]}.{name}"
                    else:
                        full = name if "." in name else (f"{module}.{name}" if module else name)
                    self.blocks.append((offset, full, kind, sig))
            offset += len(n) + (1 if n else 0)
        self.offsets = [b[0] for b in self.blocks]

    def owner(self, english: str) -> tuple[str, str, str] | None:
        """(symbol, kind, signature) of the block containing this English paragraph."""
        needle = _norm(english)[:140]
        if len(needle) < 25:
            return None
        pos = self.norm.find(needle)
        if pos < 0:
            return None
        import bisect
        i = bisect.bisect_right(self.offsets, pos) - 1
        if i < 0:
            return None
        _, symbol, kind, sig = self.blocks[i]
        return symbol, kind, sig


# ── .po parsing ─────────────────────────────────────────────────────────────

def parse_po(path: Path) -> list[tuple[list[tuple[str, int]], str, str]]:
    """(refs, msgid, msgstr) per entry, where refs = [(rst_file, line), …].

    The `#: file:line` comments precede the entry they belong to, so they are
    collected into `pending` and attached when the next `msgid` opens an entry.
    """
    entries: list[tuple[list[tuple[str, int]], str, str]] = []
    pending: list[tuple[str, int]] = []
    refs: list[tuple[str, int]] = []
    msgid: list[str] = []
    msgstr: list[str] = []
    target: list[str] | None = None

    def flush():
        if msgid or msgstr:
            entries.append((refs, "".join(msgid), "".join(msgstr)))

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        if line.startswith("#:"):
            for m in PO_REF_RE.finditer(line):
                pending.append((m.group(1), int(m.group(2))))
            continue
        if line.startswith("#") or not line:
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr = [], []
            refs, pending = pending, []
            target = msgid
            line = line[len("msgid "):]
        elif line.startswith("msgstr "):
            target = msgstr
            line = line[len("msgstr "):]
        elif line.startswith("msgid_plural ") or line.startswith("msgstr["):
            target = None
            continue
        if target is None:
            continue
        if line.startswith('"') and line.endswith('"'):
            target.append(line[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\"))
    flush()
    return entries[1:] if entries else []


def rst_to_text(text: str) -> str:
    text = ROLE_RE.sub(r"\1", text)
    text = REF_RE.sub(r"\1", text)
    text = LITERAL_RE.sub(r"\1", text)
    text = re.sub(r"\.\.\s+\w+::.*", "", text)
    text = re.sub(r"\|[a-z_]+\|", "", text)
    return clean_text(text)


def signature_of(rst_lines: list[str], symbol: str) -> str:
    for line in rst_lines:
        m = DIRECTIVE_RE.match(line)
        if m:
            sig = m.group(3).strip()
            name = sig.split("(")[0].strip()
            if symbol.endswith(name):
                return sig
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--po", default="E:/corpus-src/python-docs-es-3.13")
    ap.add_argument("--rst", default="E:/corpus-src/cpython/Doc")
    args = ap.parse_args()
    po_root, rst_root = Path(args.po), Path(args.rst)
    for p in (po_root, rst_root):
        if not p.is_dir():
            raise SystemExit(f"not found: {p}")

    indexes: dict[str, RstIndex | None] = {}

    def get_index(rel: str) -> "RstIndex | None":
        if rel not in indexes:
            f = rst_root / rel
            indexes[rel] = RstIndex(f, Path(rel).stem if rel.startswith("library/") else "") if f.is_file() else None
        return indexes[rel]

    by_symbol: dict[str, dict] = {}
    unmatched = 0
    for po in sorted(po_root.rglob("*.po")):
        rel = po.relative_to(po_root)
        area = rel.parts[0] if len(rel.parts) > 1 else ""
        if area not in AREAS:
            continue
        for refs, msgid, msgstr in parse_po(po):
            text = rst_to_text((msgstr or msgid).strip())
            if not text or len(text) < 25:
                continue
            rel_rst = refs[0][0] if refs else ""
            index = get_index(rel_rst) if rel_rst else None
            owner = index.owner(msgid) if index else None
            if not owner:
                unmatched += 1
                continue
            name, kind, sig = owner
            rec = by_symbol.get(name)
            if rec is None:
                page = Path(rel_rst).with_suffix("").as_posix()
                rec = by_symbol[name] = {
                    "id": name, "title": name, "content": (sig + "\n") if sig else "",
                    "kind": kind, "modulo": name.split(".")[0],
                    "source_url": f"https://docs.python.org/es/3/{page}.html",
                }
            if len(rec["content"]) < MAX_CHARS and text not in rec["content"]:
                rec["content"] += "\n" + text

    records = []
    for name, rec in by_symbol.items():
        rec["content"] = clean_text(rec["content"])
        if len(rec["content"]) >= MIN_CHARS and ("." in name or rec["kind"] == "module"):
            records.append(rec)
    records.sort(key=lambda r: r["title"].lower())
    log(f"python-docs: {len(records)} symbols ({unmatched} paragraphs without a symbol)")
    if len(records) < 1500:
        raise SystemExit(f"only {len(records)} records parsed")
    save_records("python-docs-es", records, {
        "name": "Documentación de Python en español",
        "description": "La biblioteca estándar de Python explicada en español, un registro por función, clase o método: qué hace, qué parámetros recibe y qué devuelve.",
        "language": "es",
        "license": "PSF License (traducción oficial python-docs-es, misma licencia que Python)",
        "source_url": "https://docs.python.org/es/3/",
    })


if __name__ == "__main__":
    main()
