"""Retrieval + citation tests.

These use a tiny synthetic corpus (built via the real ingestion + CorpusStore) so
they assert the citation logic — that a matched line is cited to the correct page —
without depending on the full census files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.build_corpus import build
from app.ingestion.corpus_store import CorpusStore
from app.tools.search import ReadPageTool, SearchDocumentsTool


@pytest.fixture
def store(tmp_path: Path) -> CorpusStore:
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "PC11_PCA_Data_Highlights_Karnataka.md").write_text(
        "\n".join(
            [
                "<!-- page 9 -->",
                "The Sex Ratio in Karnataka has increased from 965 to 973 in 2011.",
                "<!-- page 10 -->",
                "The Literacy Rate of the State has increased to 75.36 per cent in 2011.",
            ]
        ),
        encoding="utf-8",
    )
    build(md_dir, tmp_path / "processed")
    return CorpusStore(tmp_path / "processed")


def test_search_cites_correct_page(store, run_ctx):
    tool = SearchDocumentsTool(store=store)
    res = tool.run(run_ctx, query="literacy rate")
    assert res.ok
    assert len(res.citations) == 1
    c = res.citations[0]
    assert c.document == "Karnataka"
    assert c.page == 10  # the literacy line lives on page 10, not 9
    assert "75.36" in c.snippet


def test_search_is_case_insensitive(store, run_ctx):
    tool = SearchDocumentsTool(store=store)
    res = tool.run(run_ctx, query="SEX RATIO")
    assert res.ok and res.citations[0].page == 9


def test_empty_search_returns_guidance_not_error(store, run_ctx):
    tool = SearchDocumentsTool(store=store)
    res = tool.run(run_ctx, query="gender imbalance")  # wording not in the text
    assert res.ok  # not a failure — the agent should retry with a synonym
    assert res.citations == []
    assert "synonym" in res.content.lower() or "no matches" in res.content.lower()


def test_unknown_document_fails_cleanly(store, run_ctx):
    tool = SearchDocumentsTool(store=store)
    res = tool.run(run_ctx, query="literacy", document="Kerala")
    assert not res.ok and "Unknown document" in res.content


def test_read_page_returns_page_with_citation(store, run_ctx):
    tool = ReadPageTool(store=store)
    res = tool.run(run_ctx, document="karnataka", page=10)
    assert res.ok
    assert "75.36" in res.content
    assert res.citations[0].page == 10
