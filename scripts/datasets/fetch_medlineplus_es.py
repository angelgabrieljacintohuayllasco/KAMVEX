"""
MedlinePlus — temas de salud en español (National Library of Medicine, EE. UU.).

Source: the MedlinePlus health-topic XML export (https://medlineplus.gov/xml.html),
public domain. One record per Spanish topic: title, summary (HTML stripped),
"también llamado" aliases, groups and the canonical URL.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from common import http_get, log, save_records, strip_html

INDEX_URL = "https://medlineplus.gov/xml.html"
XML_BASE = "https://medlineplus.gov/xml/"


def latest_xml_name() -> str:
    page = http_get(INDEX_URL).decode("utf-8", "replace")
    names = sorted(set(re.findall(r"mplus_topics_\d{4}-\d{2}-\d{2}\.xml", page)))
    if not names:
        raise SystemExit("no mplus_topics_*.xml link found on the index page")
    return names[-1]


def main() -> None:
    name = latest_xml_name()
    log(f"downloading {name} …")
    raw = http_get(XML_BASE + name, timeout=300)
    log(f"{len(raw) / 1e6:.1f} MB, parsing")
    root = ET.fromstring(raw)
    records: list[dict] = []
    for topic in root.iter("health-topic"):
        if topic.get("language", "").lower() != "spanish":
            continue
        title = (topic.get("title") or "").strip()
        summary_el = topic.find("full-summary")
        summary = strip_html(summary_el.text or "") if summary_el is not None else ""
        if not title or len(summary) < 80:
            continue
        aliases = [a.text.strip() for a in topic.findall("also-called") if a.text]
        groups = [g.text.strip() for g in topic.findall("group") if g.text]
        records.append({
            "id": topic.get("id") or title,
            "title": title,
            "content": summary,
            "tambien_llamado": ", ".join(aliases),
            "grupos": ", ".join(groups),
            "source_url": topic.get("url") or "",
        })
    records.sort(key=lambda r: r["title"].lower())
    if len(records) < 500:
        raise SystemExit(f"only {len(records)} Spanish topics parsed")
    save_records("medlineplus-salud-es", records, {
        "name": "MedlinePlus — Salud en español",
        "description": "Temas de salud de MedlinePlus (Biblioteca Nacional de Medicina de EE. UU.) en español: qué es cada enfermedad o condición, síntomas, causas y tratamientos.",
        "language": "es",
        "license": "Dominio público (MedlinePlus, NLM/NIH); ver medlineplus.gov/about/using/usingcontent",
        "source_url": "https://medlineplus.gov/spanish/",
        "source_file": name,
    })


if __name__ == "__main__":
    main()
