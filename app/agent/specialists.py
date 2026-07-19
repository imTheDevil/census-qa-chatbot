"""The two specialist agents (role-configured engine.Agent instances).

Retrieval specialist (text lane): search/outline/read tools for lookups + summaries.
Data specialist (data lane): datasets/tables/recipes/code tools for computation +
charts. Each sees only its own ~5 tools.
"""
from __future__ import annotations

from app.agent.engine import Agent
from app.agent.llm import make_llm
from app.agent.prompts import DATA_PROMPT, RETRIEVAL_PROMPT
from app.config import get_settings
from app.tools.base import ToolRegistry
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


def build_retrieval_agent(llm=None) -> Agent:
    settings = get_settings()
    registry = ToolRegistry([
        ListDocumentsTool(),
        SearchDocumentsTool(),
        GetOutlineTool(),
        ReadSectionTool(),
        ReadPageTool(),
    ])
    return Agent(
        name="retrieval",
        system_prompt=RETRIEVAL_PROMPT,
        registry=registry,
        llm=llm or make_llm(settings.model_for("retrieval")),
        # All its tools are "discovery"; cap prevents endless searching.
        throttle_tools={"search_documents", "get_outline", "read_section",
                        "read_page", "list_documents"},
        throttle_cap=7,
        throttle_message=(
            "Enough searching. Answer now from what you've read with [Document, p.N] "
            "citations, or reply 'NOT_FOUND:' if it isn't in the documents."
        ),
    )


def build_data_agent(llm=None) -> Agent:
    settings = get_settings()
    registry = ToolRegistry([
        DescribeDatasetsTool(),
        ListTablesTool(),
        ListRecipesTool(),
        ReadRecipeTool(),
        ExecutePythonTool(),
    ])
    return Agent(
        name="data",
        system_prompt=DATA_PROMPT,
        registry=registry,
        llm=llm or make_llm(settings.model_for("data")),
        # Discovery tools only; execute_python is the goal, not throttled.
        throttle_tools={"describe_datasets", "list_tables", "list_recipes", "read_recipe"},
        throttle_cap=6,
        throttle_message=(
            "Stop discovering. Call execute_python NOW: read the relevant CSV with "
            "pandas and compute/plot. Or reply 'NOT_FOUND:' if the data isn't available."
        ),
    )
