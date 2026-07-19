"""Ingestion entrypoint (`python -m app.ingestion`).

Reads the markdown docs and writes to data/processed/: pages.json (line->page map
for citations), manifest.json (documents + extracted tables), and tables/*.csv. The
raw markdown stays the source of truth for text.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.config import ROOT_DIR, get_settings
from app.ingestion.extract_tables import extract_tables
from app.ingestion.markdown_utils import document_label, safe_relpath, split_pages
from app.models.documents import CorpusManifest, DocumentInfo


def build(markdown_dir: Path, processed_dir: Path) -> CorpusManifest:
    processed_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = processed_dir / "tables"

    md_files = sorted(markdown_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No markdown files found in {markdown_dir}")

    # Make ingestion idempotent: clear prior generated outputs so a re-run doesn't
    # leave orphaned CSVs (table slugs can change between runs).
    for stale in ("tables", "district_metrics"):
        shutil.rmtree(processed_dir / stale, ignore_errors=True)

    pages_index: dict[str, dict] = {}
    manifest = CorpusManifest()

    for md in md_files:
        text = md.read_text(encoding="utf-8")
        label = document_label(md.name)
        pages = split_pages(text, label)

        pages_index[label] = {
            "source_file": safe_relpath(md, ROOT_DIR),
            "pages": [
                {"page": p.page, "line_start": p.line_start, "line_end": p.line_end}
                for p in pages
            ],
        }

        tables = extract_tables(text, label, tables_dir, ROOT_DIR)
        num_pages = sum(1 for p in pages if p.page is not None)
        manifest.documents.append(
            DocumentInfo(
                label=label,
                source_file=safe_relpath(md, ROOT_DIR),
                num_pages=num_pages,
                tables=tables,
            )
        )
        print(f"  {label}: {num_pages} pages, {len(tables)} tables from {md.name}")

    (processed_dir / "pages.json").write_text(
        json.dumps(pages_index, indent=2), encoding="utf-8"
    )
    (processed_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    # ETL: normalize district-level tables into one clean dataset per state.
    from app.ingestion.build_district_dataset import build as build_districts

    print("Building clean district datasets...")
    build_districts(manifest, processed_dir)

    # PageIndex-style navigable section outline per document.
    from app.ingestion.build_outline import build as build_outlines
    from app.ingestion.corpus_store import CorpusStore

    print("Building document outlines...")
    build_outlines(CorpusStore(processed_dir), processed_dir)
    return manifest


def main() -> None:
    settings = get_settings()
    print(f"Ingesting markdown from {settings.markdown_path} ...")
    manifest = build(settings.markdown_path, settings.processed_path)
    total_tables = sum(len(d.tables) for d in manifest.documents)
    print(
        f"Done. {len(manifest.documents)} documents, {total_tables} tables. "
        f"Wrote index to {settings.processed_path}"
    )


if __name__ == "__main__":
    main()
