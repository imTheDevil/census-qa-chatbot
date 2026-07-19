"""Clean-dataset discovery tool.

Surfaces the normalized per-district dataset (built by the ETL) and its schema so
the agent uses reliable structured data for computation/artifacts instead of
re-parsing messy markdown tables. This is the entrypoint for the data lane.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.models.citation import Citation
from app.models.tools import ToolResult
from app.tools.base import RunContext, Tool

_METRIC_SNIPPET = {
    "population": "district population (total/rural/urban), 2011",
    "males": "district male population, 2011",
    "females": "district female population, 2011",
    "sex_ratio": "district sex ratio, 2011",
    "literacy": "district literacy rate, 2011",
}


class DescribeDatasetsTool(Tool):
    name = "describe_datasets"
    description = (
        "Get the clean, ready-to-use district datasets and their schema. USE THIS "
        "FIRST for any district-level computation, ranking, comparison, table, or "
        "chart (e.g. 'top 5 districts by population', 'average literacy', 'urban vs "
        "rural'). Returns one tidy CSV per state with reliable columns — read it with "
        "pandas in execute_python. Cite the source page listed here."
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, processed_dir: Path | None = None):
        self._dir = (processed_dir or get_settings().processed_path) / "district_metrics"

    def run(self, ctx: RunContext) -> ToolResult:
        dictionary = self._dir / "DATA_DICTIONARY.md"
        if not dictionary.exists():
            return self.fail(
                "No clean datasets found — run `python -m app.ingestion` first."
            )
        # Emit a citation per (state, metric) source page so that when the agent
        # writes e.g. [Karnataka, p.27], it reconciles to a real source.
        citations: list[Citation] = []
        sources_path = self._dir / "sources.json"
        if sources_path.exists():
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            for label, pages in sources.items():
                for metric, page in pages.items():
                    citations.append(
                        Citation(
                            document=label,
                            page=page,
                            snippet=_METRIC_SNIPPET.get(metric, f"{metric} (2011)"),
                        )
                    )
        return ToolResult(
            tool_call_id="", name=self.name, ok=True,
            content=dictionary.read_text(encoding="utf-8"), citations=citations,
        )
