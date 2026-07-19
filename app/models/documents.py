"""Document / corpus contracts produced by ingestion.

The text index is a list of `DocumentPage`s (a page of markdown with its line
range), and the corpus manifest lists what's available plus the extracted table
CSVs. Tools read these to answer lookups and to know what data exists.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentPage(BaseModel):
    """One page of a source document, sliced on `<!-- page N -->` markers."""

    document: str = Field(description="Document label, e.g. 'Karnataka'.")
    page: int | None = Field(description="Page number, or None for pre-first-marker text.")
    text: str = Field(description="Markdown text of this page.")
    line_start: int = Field(description="1-based first line in the source file.")
    line_end: int = Field(description="1-based last line in the source file.")


class TableAsset(BaseModel):
    """A structured table extracted to CSV for computation."""

    document: str
    name: str = Field(description="Slug identifying the table, e.g. 'figures_at_a_glance'.")
    csv_path: str = Field(description="Path to the CSV relative to repo root.")
    page: int | None = Field(default=None, description="Source page, for citation.")
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0


class DocumentInfo(BaseModel):
    """Manifest entry for one source document."""

    label: str
    source_file: str
    num_pages: int
    tables: list[TableAsset] = Field(default_factory=list)


class CorpusManifest(BaseModel):
    """Top-level manifest written by ingestion and read by tools at startup."""

    documents: list[DocumentInfo] = Field(default_factory=list)

    def labels(self) -> list[str]:
        return [d.label for d in self.documents]
