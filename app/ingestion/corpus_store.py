"""Read-side access to the ingested corpus.

Loads the page index and manifest written by build_corpus, and provides the two
lookups retrieval needs: map a (document, line) to its page, and resolve a
document label to its raw markdown path for reading/grepping.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import ROOT_DIR, get_settings
from app.models.documents import CorpusManifest


class CorpusStore:
    """Lazily-loaded view over processed/pages.json + manifest.json."""

    def __init__(self, processed_dir: Path):
        self.processed_dir = processed_dir
        self._pages: dict[str, dict] | None = None
        self._manifest: CorpusManifest | None = None

    # --- loading ---
    def _load_pages(self) -> dict[str, dict]:
        if self._pages is None:
            path = self.processed_dir / "pages.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} missing — run `python -m app.ingestion` first."
                )
            self._pages = json.loads(path.read_text(encoding="utf-8"))
        return self._pages

    @property
    def manifest(self) -> CorpusManifest:
        if self._manifest is None:
            path = self.processed_dir / "manifest.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} missing — run `python -m app.ingestion` first."
                )
            self._manifest = CorpusManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return self._manifest

    # --- lookups ---
    def labels(self) -> list[str]:
        return list(self._load_pages().keys())

    def resolve_label(self, name: str) -> str | None:
        """Case-insensitive / alias / partial match of a doc name to a label."""
        from app.ingestion.markdown_utils import document_label

        pages = self._load_pages()
        low = name.strip().lower()
        for label in pages:
            if label.lower() == low:
                return label
        # Known aliases, e.g. "madhya pradesh" -> "MP".
        aliased = document_label(name)
        if aliased in pages:
            return aliased
        for label in pages:
            if low in label.lower() or label.lower() in low:
                return label
        return None

    def source_path(self, label: str) -> Path:
        stored = self._load_pages()[label]["source_file"]
        p = Path(stored)
        return p if p.is_absolute() else ROOT_DIR / p

    def page_for_line(self, label: str, line_no: int) -> int | None:
        for entry in self._load_pages().get(label, {}).get("pages", []):
            if entry["line_start"] <= line_no <= entry["line_end"]:
                return entry["page"]
        return None

    def read_page(self, label: str, page: int) -> tuple[str, int, int] | None:
        """Return (text, line_start, line_end) for a page, reading the raw markdown."""
        for entry in self._load_pages().get(label, {}).get("pages", []):
            if entry["page"] == page:
                lines = self.source_path(label).read_text(encoding="utf-8").splitlines()
                text = "\n".join(lines[entry["line_start"] - 1 : entry["line_end"]])
                return text, entry["line_start"], entry["line_end"]
        return None


@lru_cache
def get_corpus_store() -> CorpusStore:
    return CorpusStore(get_settings().processed_path)
