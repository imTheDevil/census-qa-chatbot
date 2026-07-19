"""Recipe tools — declarative artifact patterns.

Recipes are markdown files in `recipes/` describing how to produce an artifact
(bar chart, comparison table, summary) — the pattern plus a code template. The
agent discovers them at runtime and follows them, so artifact know-how lives in
readable files, not hardcoded Python (progressive disclosure).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import get_settings
from app.models.tools import ToolResult
from app.tools.base import RunContext, Tool


def _title_of(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#\s+(.*\S)", line)
        if m:
            return m.group(1)
    return path.stem


class ListRecipesTool(Tool):
    name = "list_recipes"
    description = (
        "List available artifact recipes — reusable patterns for producing charts, "
        "tables, and summaries. When a user asks for an artifact, list recipes, read "
        "the relevant one, then follow it with execute_python."
    )
    parameters = {"type": "object", "properties": {}}

    def __init__(self, recipes_dir: Path | None = None):
        self._dir = recipes_dir or get_settings().recipes_path

    def run(self, ctx: RunContext) -> ToolResult:
        files = sorted(self._dir.glob("*.md"))
        if not files:
            return self.ok("No recipes available.")
        rows = [f"- {p.stem}: {_title_of(p)}" for p in files]
        return self.ok("Available recipes (use read_recipe to open one):\n" + "\n".join(rows))


class ReadRecipeTool(Tool):
    name = "read_recipe"
    description = (
        "Read a recipe by name (e.g. 'bar_chart'). Returns the full pattern + code "
        "template to follow when producing the artifact."
    )
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Recipe name, e.g. 'bar_chart'."}},
        "required": ["name"],
    }

    def __init__(self, recipes_dir: Path | None = None):
        self._dir = recipes_dir or get_settings().recipes_path

    def run(self, ctx: RunContext, name: str) -> ToolResult:
        stem = Path(name).stem
        path = self._dir / f"{stem}.md"
        if not path.exists():
            available = ", ".join(p.stem for p in sorted(self._dir.glob("*.md")))
            return self.fail(f"No recipe '{stem}'. Available: {available}.")
        return self.ok(path.read_text(encoding="utf-8"))
