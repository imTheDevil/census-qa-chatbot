"""Pure, testable helpers for parsing the census markdown.

Kept free of I/O so they can be unit-tested directly: page splitting on
`<!-- page N -->` markers, document labelling, HTML stripping, and — the fiddly
one — normalizing the census number formats (mixed Indian and Western comma
grouping) into clean numeric strings.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.models.documents import DocumentPage

PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->")


def safe_relpath(path: Path, root: Path) -> str:
    """Path relative to `root` when it lives under it, else an absolute path string.

    Lets ingestion run against markdown/output outside the repo (e.g. temp dirs in
    tests) without blowing up on Path.relative_to.
    """
    path = Path(path).resolve()
    root = Path(root).resolve()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)

# Cells arrive with bold/line-break HTML from the PDF conversion.
_HTML_TAG_RE = re.compile(r"</?(?:b|br|i|sup|sub)\s*/?>", re.IGNORECASE)

# A token that is purely a (possibly comma-grouped, possibly signed/decimal) number.
# Commas may be Indian (6,10,95,297) or Western (638,588) — grouping is irrelevant
# because we simply strip the separators.
_NUMERIC_RE = re.compile(r"^-?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")

_KNOWN_LABELS = {
    "karnataka": "Karnataka",
    "odisha": "Odisha",
    "madhya pradesh": "MP",
    "mp": "MP",
}


def document_label(source_file: str | Path) -> str:
    """Derive a short document label from a source filename."""
    stem = Path(source_file).stem.lower()
    for key, label in _KNOWN_LABELS.items():
        if key in stem:
            return label
    # Fallback: last whitespace/underscore-separated token, title-cased.
    token = re.split(r"[\s_]+", Path(source_file).stem)[-1]
    return token.title()


def strip_html(text: str) -> str:
    """Remove the inline HTML the PDF→markdown conversion leaves in table cells."""
    return _HTML_TAG_RE.sub("", text).strip()


def looks_numeric(text: str) -> bool:
    """True if the (html-stripped) text is a single numeric token."""
    return bool(_NUMERIC_RE.match(text.strip()))


def normalize_number(text: str) -> str:
    """Strip comma separators from a numeric token; leave non-numbers untouched.

    '6,10,95,297' -> '61095297'   '638,588' -> '638588'   '-0.26' -> '-0.26'
    'Bangalore'   -> 'Bangalore'  (unchanged)
    """
    t = text.strip()
    return t.replace(",", "") if looks_numeric(t) else t


def parse_number(text: str) -> float | int | None:
    """Parse a numeric token to int/float, or None if it isn't a number."""
    if not looks_numeric(text):
        return None
    cleaned = normalize_number(text)
    if re.fullmatch(r"-?\d+", cleaned):
        return int(cleaned)
    return float(cleaned)


def clean_cell(raw: str) -> str:
    """Full cell cleaning: drop HTML, then normalize numbers (strip commas)."""
    return normalize_number(strip_html(raw))


def split_pages(text: str, document: str) -> list[DocumentPage]:
    """Slice raw markdown into pages on `<!-- page N -->` markers.

    Text before the first marker is emitted with page=None. The marker line
    belongs to the page it introduces. Line numbers are 1-based and match what
    ripgrep reports, so retrieval can map a matched line to its page.
    """
    lines = text.splitlines()
    pages: list[DocumentPage] = []
    current_page: int | None = None
    buf: list[str] = []
    start = 1

    def flush(end_line: int) -> None:
        if buf:
            pages.append(
                DocumentPage(
                    document=document,
                    page=current_page,
                    text="\n".join(buf),
                    line_start=start,
                    line_end=end_line,
                )
            )

    for i, line in enumerate(lines, start=1):
        m = PAGE_RE.search(line)
        if m:
            flush(i - 1)
            current_page = int(m.group(1))
            buf = [line]
            start = i
        else:
            buf.append(line)
    flush(len(lines))
    return pages


def page_for_line(pages: list[DocumentPage], line_no: int) -> int | None:
    """Map a 1-based source line number to its page number."""
    for p in pages:
        if p.line_start <= line_no <= p.line_end:
            return p.page
    return None
