"""Tests for the deterministic ingestion parsing — the bug-prone core."""
from __future__ import annotations

from app.ingestion.markdown_utils import (
    clean_cell,
    document_label,
    looks_numeric,
    normalize_number,
    page_for_line,
    parse_number,
    split_pages,
    strip_html,
)


class TestNumberParsing:
    def test_indian_grouping_stripped(self):
        assert normalize_number("6,10,95,297") == "61095297"
        assert parse_number("6,10,95,297") == 61095297

    def test_western_grouping_stripped(self):
        # The census markdown mixes Indian and Western grouping in the same doc.
        assert normalize_number("638,588") == "638588"
        assert parse_number("638,588") == 638588

    def test_decimals_and_negatives(self):
        assert parse_number("75.36") == 75.36
        assert parse_number("-0.26") == -0.26
        assert normalize_number("-0.26") == "-0.26"

    def test_non_numeric_untouched(self):
        assert normalize_number("Bangalore") == "Bangalore"
        assert parse_number("Bangalore") is None
        assert not looks_numeric("12 districts")

    def test_clean_cell_strips_html_then_number(self):
        assert clean_cell("<b>1,04,01,918</b>") == "10401918"
        assert clean_cell("Bangalore<br>Rural") == "BangaloreRural"


class TestDocumentLabel:
    def test_known_states(self):
        assert document_label("PC11_PCA_Data_Highlights_Karnataka.md") == "Karnataka"
        assert document_label("PC11_PCA_Data_Highlights_Odisha.md") == "Odisha"
        assert document_label("PCA Data Highlights MP.md") == "MP"

    def test_madhya_pradesh_alias(self):
        assert document_label("madhya pradesh") == "MP"


class TestPageSplitting:
    SAMPLE = "\n".join(
        [
            "intro line",  # 1  (page None)
            "<!-- page 2 -->",  # 2
            "second page text",  # 3
            "more",  # 4
            "<!-- page 3 -->",  # 5
            "third page text",  # 6
        ]
    )

    def test_pages_and_line_ranges(self):
        pages = split_pages(self.SAMPLE, "Doc")
        assert [p.page for p in pages] == [None, 2, 3]
        # First (pre-marker) chunk is line 1 only.
        assert (pages[0].line_start, pages[0].line_end) == (1, 1)
        # Marker line belongs to the page it introduces.
        assert (pages[1].line_start, pages[1].line_end) == (2, 4)
        assert (pages[2].line_start, pages[2].line_end) == (5, 6)

    def test_line_to_page_mapping(self):
        pages = split_pages(self.SAMPLE, "Doc")
        assert page_for_line(pages, 1) is None
        assert page_for_line(pages, 3) == 2
        assert page_for_line(pages, 6) == 3
        assert page_for_line(pages, 999) is None


def test_strip_html():
    assert strip_html("<b>Persons</b>") == "Persons"
    assert strip_html("a<br>b") == "ab"
