"""Retrieval tools — the text lane.

The knowledge base is the page-anchored markdown itself. `search_documents` scans
it (a pure-Python, grep-style keyword search that ranks lines by query-term overlap) and turns every match into a Citation via
the page index, so provenance is structural, not guessed. `read_page` pulls a full
page for summarization; `list_documents`/`list_tables` let the agent discover what
exists (and support Table-of-Contents style navigation when a keyword search misses).
"""
from __future__ import annotations

import re

from app.ingestion.corpus_store import CorpusStore, get_corpus_store
from app.models.citation import Citation
from app.models.tools import ToolResult
from app.tools.base import RunContext, Tool

_MAX_SNIPPET = 240  # chars per matched line (keeps tool output token-lean)
_MAX_PAGE_CHARS = 3500  # cap read_page output so a big table page can't blow the context


# Domain/English stopwords dropped from queries so verbose questions still match on
# the meaningful terms (e.g. "literacy rate in Odisha 2011 PCA Data Highlights").
_STOP = {
    "the", "a", "an", "in", "of", "for", "to", "and", "or", "is", "was", "were",
    "what", "which", "how", "many", "according", "about", "give", "show", "tell",
    "me", "on", "by", "with", "at", "from", "2011", "2001", "pca", "data",
    "highlights", "census", "india", "report", "document", "documents", "state",
    "district", "districts",
}


def _tokenize(query: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2 and t not in _STOP]
    return toks or [w for w in re.findall(r"[a-z0-9]+", query.lower())][:1]


def _token_search(path, query, max_results):
    """Rank lines by how many query tokens they contain (skips table/image lines).

    Token matching (not exact-substring) makes search robust to verbose queries — a
    line matching most key terms surfaces even if the full phrase never appears.
    Returns [(line_no, line_text)] best-first.
    """
    tokens = _tokenize(query)
    scored: list[tuple[int, int, str]] = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, start=1):
            stripped = line.lstrip()
            if stripped.startswith("|") or stripped.startswith("!["):
                continue
            low = line.lower()
            score = sum(1 for t in tokens if t in low)
            if score:
                scored.append((score, i, line.rstrip("\n")))
    # Highest token overlap first, then document order for ties.
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(i, text) for _, i, text in scored[:max_results]]


class SearchDocumentsTool(Tool):
    name = "search_documents"
    description = (
        "Keyword-search the census documents and return matching lines with their "
        "document + page, so you can cite them. Use the exact term you expect in the "
        "text (e.g. census wording: 'sex ratio' not 'gender imbalance'; 'literacy "
        "rate' not 'education level'). If a search returns nothing, retry with a "
        "synonym or the official census term."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to search for (case-insensitive)."},
            "document": {
                "type": "string",
                "description": "Optional: restrict to one document (Karnataka, Odisha, MP).",
            },
            "max_results": {"type": "integer", "description": "Max matches (default 8)."},
        },
        "required": ["query"],
    }

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext, query: str, document: str | None = None,
            max_results: int = 8) -> ToolResult:
        max_results = max(1, min(int(max_results), 25))
        if document:
            label = self._store.resolve_label(document)
            if label is None:
                return self.fail(
                    f"Unknown document '{document}'. Available: {', '.join(self._store.labels())}."
                )
            labels = [label]
        else:
            labels = self._store.labels()

        lines_out: list[str] = []
        citations: list[Citation] = []
        # The text lane answers from narrative prose (where state-level facts + prose
        # rankings live); _token_search already skips table/image lines.
        for label in labels:
            path = self._store.source_path(label)
            for line_no, text in _token_search(path, query, max_results):
                page = self._store.page_for_line(label, line_no)
                snippet = text.strip()
                if len(snippet) > _MAX_SNIPPET:
                    snippet = snippet[:_MAX_SNIPPET] + "..."
                lines_out.append(f"[{label} p.{page} L{line_no}] {snippet}")
                citations.append(
                    Citation(document=label, page=page, snippet=snippet,
                             line_start=line_no, line_end=line_no)
                )
                if len(citations) >= max_results:
                    break

        if not citations:
            return self.ok(
                f"No matches for '{query}'. Try a synonym or the official census term, "
                f"or use list_documents / read_page to navigate by section.",
            )
        return ToolResult(
            tool_call_id="", name=self.name, ok=True,
            content=f"{len(citations)} match(es) for '{query}':\n" + "\n".join(lines_out),
            citations=citations,
        )


class ReadPageTool(Tool):
    name = "read_page"
    description = (
        "Read the full markdown of one page of a document. Use for summarizing a "
        "section or reading around a search hit. Returns text you can cite to that page."
    )
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "Karnataka, Odisha, or MP."},
            "page": {"type": "integer", "description": "Page number to read."},
        },
        "required": ["document", "page"],
    }

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext, document: str, page: int) -> ToolResult:
        label = self._store.resolve_label(document)
        if label is None:
            return self.fail(f"Unknown document '{document}'.")
        result = self._store.read_page(label, int(page))
        if result is None:
            return self.fail(f"Page {page} not found in {label} (it may not have been converted).")
        text, line_start, line_end = result
        truncated = len(text) > _MAX_PAGE_CHARS
        shown = text[:_MAX_PAGE_CHARS] + "\n...[truncated]" if truncated else text
        citation = Citation(
            document=label, page=int(page),
            snippet=text.strip()[:200], line_start=line_start, line_end=line_end,
        )
        return ToolResult(
            tool_call_id="", name=self.name, ok=True,
            content=f"{label} page {page}:\n\n{shown}", citations=[citation],
        )


class ListDocumentsTool(Tool):
    name = "list_documents"
    description = (
        "List the available census documents with page counts. Call this first if "
        "you're unsure which documents exist or how to name them."
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext) -> ToolResult:
        rows = [
            f"- {d.label}: {d.num_pages} pages, {len(d.tables)} data tables "
            f"(source: {d.source_file})"
            for d in self._store.manifest.documents
        ]
        return self.ok(
            "Available census documents (India Census 2011, PCA Data Highlights):\n"
            + "\n".join(rows)
        )


class ListTablesTool(Tool):
    name = "list_tables"
    description = (
        "List extracted data tables (as CSV files) available for computation. Filter "
        "by document and/or a keyword in the table name. Use the returned csv_path with "
        "execute_python (pandas) to compute or chart. Prefer this over parsing raw "
        "markdown tables yourself."
    )
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "Optional: Karnataka, Odisha, MP."},
            "keyword": {"type": "string", "description": "Optional: filter table names."},
            "limit": {"type": "integer", "description": "Max tables to list (default 20)."},
        },
    }

    def __init__(self, store: CorpusStore | None = None):
        self._store = store or get_corpus_store()

    def run(self, ctx: RunContext, document: str | None = None,
            keyword: str | None = None, limit: int = 20) -> ToolResult:
        limit = max(1, min(int(limit), 60))
        # Forgiving match: rank tables by how many keyword words appear in the name,
        # so "district population" still surfaces "Population and decadal change..."
        # instead of returning nothing on an exact-phrase miss.
        words = [w for w in re.split(r"\s+", (keyword or "").lower()) if len(w) > 2]

        scored: list[tuple[int, str]] = []
        for doc in self._store.manifest.documents:
            if document and self._store.resolve_label(document) != doc.label:
                continue
            for t in doc.tables:
                name_l = t.name.lower()
                score = sum(1 for w in words if w in name_l) if words else 1
                if words and score == 0:
                    continue
                # Deprioritize chart-derived tables (their long image-alt-text names
                # match keywords spuriously and crowd out the real data tables).
                if "chart" in name_l or len(t.name) > 80:
                    score -= 2
                name = t.name if len(t.name) <= 80 else t.name[:77] + "..."
                row = f"- [{t.document} p.{t.page}] {name} — {t.row_count} rows — {t.csv_path}"
                scored.append((score, row))

        if not scored:
            return self.ok(
                "No tables matched that keyword. Call list_tables again with a broader "
                "keyword (e.g. 'population') or no keyword to see all tables."
            )
        scored.sort(key=lambda x: -x[0])
        rows = [r for _, r in scored[:limit]]
        return self.ok(f"{len(rows)} table(s) (most relevant first):\n" + "\n".join(rows))
