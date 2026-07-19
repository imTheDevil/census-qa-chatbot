"""Citation contract.

Every factual claim the agent makes must carry at least one Citation. Citations
are *structural*, not guessed: retrieval tools return the source location alongside
the text, so the page number comes from the document's `<!-- page N -->` marker
rather than the LLM inventing it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A pointer back to the exact source of a factual claim."""

    document: str = Field(description="Document label, e.g. 'Karnataka'.")
    page: int | None = Field(
        default=None,
        description="Page number from the source `<!-- page N -->` marker, if known.",
    )
    snippet: str = Field(
        description="Verbatim source text supporting the claim (kept short)."
    )
    line_start: int | None = Field(
        default=None, description="1-based start line in the source markdown."
    )
    line_end: int | None = Field(
        default=None, description="1-based end line in the source markdown."
    )

    def render(self) -> str:
        """Human-readable citation used in chat output."""
        loc = self.document
        if self.page is not None:
            loc += f", p.{self.page}"
        snippet = self.snippet.strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        return f"[{loc}] “{snippet}”"
