"""Build a navigable section outline per document (for summaries/topic questions).

Parses the body markdown headings (not the printed TOC, whose page numbers don't
match our `<!-- page N -->` markers) into a section tree with marker pages + line
ranges. Output: data/processed/outlines.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.ingestion.corpus_store import CorpusStore
from app.ingestion.markdown_utils import split_pages, page_for_line

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Boilerplate headings that aren't useful navigation targets.
_SKIP = {"graphs", "maps", "census of india 2011", "contents"}


def clean_heading(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)          # HTML tags
    text = text.replace("&amp;", "&")
    text = re.sub(r"[*#`]", "", text)            # markdown emphasis
    return re.sub(r"\s+", " ", text).strip()


def extract_outline(text: str, label: str) -> list[dict]:
    lines = text.splitlines()
    pages = split_pages(text, label)

    raw: list[dict] = []
    for i, line in enumerate(lines, start=1):
        m = _HEADING.match(line)
        if not m:
            continue
        title = clean_heading(m.group(2))
        if len(title) < 3 or title.lower() in _SKIP:
            continue
        raw.append({"title": title, "level": len(m.group(1)), "line_start": i,
                    "page": page_for_line(pages, i)})

    # A section runs until the next heading (any level); cap the last one at EOF.
    out: list[dict] = []
    for idx, sec in enumerate(raw):
        end = raw[idx + 1]["line_start"] - 1 if idx + 1 < len(raw) else len(lines)
        # Skip near-empty sections (heading immediately followed by another).
        if end - sec["line_start"] < 1:
            continue
        sec["line_end"] = end
        out.append(sec)
    return out


def build(store: CorpusStore, processed_dir: Path) -> dict[str, list[dict]]:
    outlines: dict[str, list[dict]] = {}
    for label in store.labels():
        text = store.source_path(label).read_text(encoding="utf-8")
        sections = extract_outline(text, label)
        outlines[label] = sections
        print(f"  {label}: {len(sections)} sections")
    (processed_dir / "outlines.json").write_text(
        json.dumps(outlines, indent=2), encoding="utf-8"
    )
    return outlines
