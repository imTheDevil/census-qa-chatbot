"""Citation reconciliation tests — precise sourcing from inline references."""
from __future__ import annotations

from app.agent.engine import dedupe_citations as _dedupe_citations
from app.agent.engine import reconcile_citations as _reconcile
from app.models.citation import Citation


def _c(doc, page, snip="x"):
    return Citation(document=doc, page=page, snippet=snip)


GATHERED = [
    _c("Karnataka", 3, "toc"),
    _c("Karnataka", 9, "sex ratio 1094 Udupi"),
    _c("Karnataka", 10, "literacy 75.36"),
    _c("Odisha", 5, "unrelated"),
]


def test_reconcile_ascii_bracket_with_comma():
    text = "Literacy was 75.36% [Karnataka, p.10]."
    out = _reconcile(text, GATHERED)
    assert [(c.document, c.page) for c in out] == [("Karnataka", 10)]


def test_reconcile_cjk_bracket_without_comma():
    # gpt-oss on Groq emits 【Karnataka p.9】 in practice.
    text = "Udupi had the highest sex ratio 【Karnataka p.9】."
    out = _reconcile(text, GATHERED)
    assert [(c.document, c.page) for c in out] == [("Karnataka", 9)]


def test_reconcile_multiple_refs():
    text = "Literacy [Karnataka, p.10] and sex ratio [Karnataka, p.9]."
    out = _reconcile(text, GATHERED)
    pages = sorted(c.page for c in out)
    assert pages == [9, 10]


def test_no_inline_refs_returns_all_deduped():
    text = "Some answer with no citations."
    out = _reconcile(text, GATHERED)
    assert len(out) == len(GATHERED)


def test_dedupe():
    dups = [_c("Karnataka", 10), _c("Karnataka", 10), _c("Karnataka", 9)]
    assert len(_dedupe_citations(dups)) == 2
