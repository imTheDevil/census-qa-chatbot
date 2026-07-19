"""Outline navigation tools (PageIndex-style).

Let the agent navigate a document's section structure instead of grepping blindly:
`get_outline` returns the section tree; `read_section` reads a whole section by
name (with a page citation). Best for summaries and "tell me about section X".
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.ingestion.corpus_store import CorpusStore, get_corpus_store
from app.models.citation import Citation
from app.models.tools import ToolResult
from app.tools.base import RunContext, Tool


@lru_cache
def _load_outlines(processed_dir: str) -> dict:
    path = Path(processed_dir) / "outlines.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _score(query: str, title: str) -> int:
    q, t = query.lower(), title.lower()
    if q == t:
        return 100
    if q in t or t in q:
        return 50
    qs, ts = set(q.split()), set(t.split())
    return len(qs & ts)


class GetOutlineTool(Tool):
    name = "get_outline"
    description = (
        "Get a document's section outline (headings + page numbers). Use this to plan "
        "a summary or to find which section covers a topic, then call read_section. "
        "Sections come from the 'Data Highlights' narrative (e.g. POPULATION, SEX "
        "RATIO, LITERATES, WORKERS)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "Karnataka, Odisha, or MP."}
        },
        "required": ["document"],
    }

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext, document: str) -> ToolResult:
        label = self._store.resolve_label(document)
        if label is None:
            return self.fail(f"Unknown document '{document}'.")
        outlines = _load_outlines(str(get_settings().processed_path))
        sections = outlines.get(label, [])
        if not sections:
            return self.fail(f"No outline for {label} — run `python -m app.ingestion`.")
        # Keep the outline compact: the narrative sections (levels 2-4).
        rows = [
            f"- {'  ' * (s['level'] - 2)}{s['title']} (p.{s['page']})"
            for s in sections
            if 2 <= s["level"] <= 4
        ]
        return self.ok(f"Outline of {label}:\n" + "\n".join(rows))


class ReadSectionTool(Tool):
    name = "read_section"
    description = (
        "Read a whole section of a document by its heading (e.g. 'SEX RATIO', "
        "'LITERATES'). Returns the section text with a page citation. Best for "
        "summarizing a topic. Use get_outline first if unsure of section names."
    )
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "Karnataka, Odisha, or MP."},
            "section": {"type": "string", "description": "Section heading or topic."},
        },
        "required": ["document", "section"],
    }

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext, document: str, section: str) -> ToolResult:
        label = self._store.resolve_label(document)
        if label is None:
            return self.fail(f"Unknown document '{document}'.")
        sections = _load_outlines(str(get_settings().processed_path)).get(label, [])
        if not sections:
            return self.fail(f"No outline for {label}.")

        best = max(sections, key=lambda s: _score(section, s["title"]), default=None)
        if best is None or _score(section, best["title"]) == 0:
            titles = ", ".join(s["title"] for s in sections if 2 <= s["level"] <= 4)
            return self.ok(f"No section matched '{section}'. Available: {titles}")

        lines = self._store.source_path(label).read_text(encoding="utf-8").splitlines()
        text = "\n".join(lines[best["line_start"] - 1 : best["line_end"]]).strip()
        citation = Citation(
            document=label, page=best["page"], snippet=best["title"],
            line_start=best["line_start"], line_end=best["line_end"],
        )
        return ToolResult(
            tool_call_id="", name=self.name, ok=True,
            content=f"{label} — section '{best['title']}' (p.{best['page']}):\n\n{text}",
            citations=[citation],
        )
