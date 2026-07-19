"""Tests for the PageIndex-style outline extraction + navigation tools."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.build_corpus import build
from app.ingestion.build_outline import clean_heading, extract_outline
from app.ingestion.corpus_store import CorpusStore
from app.tools.outline import GetOutlineTool, ReadSectionTool, _score

SAMPLE = "\n".join(
    [
        "<!-- page 7 -->",           # 1
        "## **POPULATION**",          # 2
        "- Karnataka has 6.1 crore people.",  # 3
        "<!-- page 8 -->",           # 4
        "### SEX RATIO",              # 5
        "- The sex ratio is 973.",    # 6
        "- Highest in Udupi.",        # 7
        "### LITERATES",              # 8
        "- Literacy rate is 75.36%.", # 9
    ]
)


def test_clean_heading():
    assert clean_heading("## **POPULATION**") == "POPULATION"
    assert clean_heading("Scheduled Castes &amp; Tribes") == "Scheduled Castes & Tribes"


def test_extract_outline_titles_pages_and_ranges():
    out = extract_outline(SAMPLE, "Karnataka")
    titles = [s["title"] for s in out]
    assert titles == ["POPULATION", "SEX RATIO", "LITERATES"]
    pop = out[0]
    assert pop["page"] == 7
    # POPULATION runs until just before SEX RATIO's heading line.
    assert pop["line_start"] == 2 and pop["line_end"] == 4
    assert out[1]["page"] == 8  # SEX RATIO


def test_score_prefers_exact_and_substring():
    assert _score("sex ratio", "SEX RATIO") == 100
    assert _score("literacy", "LITERATES") >= 0
    assert _score("literates", "LITERATES") == 100
    assert _score("workers", "SEX RATIO") == 0


@pytest.fixture
def store(tmp_path: Path) -> CorpusStore:
    md = tmp_path / "markdown"
    md.mkdir()
    (md / "PC11_PCA_Data_Highlights_Karnataka.md").write_text(SAMPLE, encoding="utf-8")
    build(md, tmp_path / "processed")
    return CorpusStore(tmp_path / "processed")


def test_read_section_returns_text_and_citation(store, run_ctx, monkeypatch):
    # Point the outline loader at this test's processed dir.
    import app.tools.outline as outline_mod
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_processed_dir", str(store.processed_dir))
    outline_mod._load_outlines.cache_clear()

    tool = ReadSectionTool(store=store)
    res = tool.run(run_ctx, document="Karnataka", section="sex ratio")
    assert res.ok
    assert "973" in res.content
    assert res.citations[0].page == 8
