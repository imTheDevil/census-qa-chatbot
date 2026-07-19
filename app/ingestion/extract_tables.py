"""Extract each markdown table block into a CSV (HTML stripped, commas removed from
numbers). Table shapes vary too much to force one schema here, so this keeps them
per-table; the district-level ETL (build_district_dataset) does the normalization.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from app.ingestion.markdown_utils import clean_cell, safe_relpath, split_pages
from app.models.documents import DocumentPage, TableAsset

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")  # |---|:--:| divider rows
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)")  # markdown heading text


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into cleaned cells."""
    cells = line.strip().strip("|").split("|")
    return [clean_cell(c) for c in cells]


def _caption_for(lines: list[str], block_start: int) -> str:
    """Nearest preceding non-empty, non-table, non-image line — names the table."""
    for i in range(block_start - 1, max(block_start - 8, -1), -1):
        raw = lines[i].strip()
        # Skip blanks, table rows, and image lines (their alt-text is long + noisy).
        if not raw or _TABLE_ROW_RE.match(raw) or raw.startswith("!["):
            continue
        heading = _HEADING_RE.match(raw)
        text = heading.group(1) if heading else raw
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # strip inline images
        text = re.sub(r"</?[^>]+>", "", text).strip()
        if text:
            return text
    return ""


def _slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:48] or fallback


def _page_for_block(pages: list[DocumentPage], line_no: int) -> int | None:
    for p in pages:
        if p.line_start <= line_no <= p.line_end:
            return p.page
    return None


def extract_tables(
    text: str, document: str, out_dir: Path, repo_root: Path
) -> list[TableAsset]:
    """Find markdown table blocks in `text`, write each to a CSV under `out_dir`.

    Returns a TableAsset per extracted table. Skips trivial blocks (fewer than two
    data rows or fewer than two columns).
    """
    lines = text.splitlines()
    pages = split_pages(text, document)
    out_dir.mkdir(parents=True, exist_ok=True)

    assets: list[TableAsset] = []
    i = 0
    table_idx = 0
    while i < len(lines):
        if not _TABLE_ROW_RE.match(lines[i]):
            i += 1
            continue

        block_start = i
        block: list[list[str]] = []
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            if not _SEPARATOR_RE.match(lines[i]):
                block.append(_split_row(lines[i]))
            i += 1

        width = max((len(r) for r in block), default=0)
        if len(block) < 2 or width < 2:
            continue

        # Pad ragged rows so the CSV is rectangular.
        block = [r + [""] * (width - len(r)) for r in block]
        page = _page_for_block(pages, block_start + 1)
        caption = _caption_for(lines, block_start)
        table_idx += 1
        slug = _slugify(caption, f"table_{table_idx}")
        name = f"{document.lower()}__p{page}__{slug}"
        csv_path = out_dir / f"{name}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(block)

        assets.append(
            TableAsset(
                document=document,
                name=caption or slug,
                csv_path=safe_relpath(csv_path, repo_root),
                page=page,
                columns=block[0],
                row_count=len(block) - 1,
            )
        )
    return assets
