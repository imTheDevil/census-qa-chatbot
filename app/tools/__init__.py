"""Tool registry assembly.

`build_registry()` wires up the default tool set the agent is given. Tools are the
agent's only way to touch the world: retrieval (text lane), data discovery, recipes,
and code execution (data lane).
"""
from app.tools.base import RunContext, Tool, ToolRegistry
from app.tools.code_exec import ExecutePythonTool
from app.tools.datasets import DescribeDatasetsTool
from app.tools.outline import GetOutlineTool, ReadSectionTool
from app.tools.recipes import ListRecipesTool, ReadRecipeTool
from app.tools.search import (
    ListDocumentsTool,
    ListTablesTool,
    ReadPageTool,
    SearchDocumentsTool,
)


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ListDocumentsTool(),
            SearchDocumentsTool(),
            ReadPageTool(),
            GetOutlineTool(),
            ReadSectionTool(),
            DescribeDatasetsTool(),
            ListTablesTool(),
            ListRecipesTool(),
            ReadRecipeTool(),
            ExecutePythonTool(),
        ]
    )


__all__ = ["RunContext", "Tool", "ToolRegistry", "build_registry"]
