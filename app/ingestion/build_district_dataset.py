"""ETL: normalize the messy per-district PCA tables into one tidy table per state.

Joins the key district tables into a clean schema (district, total_pop, rural_pop,
urban_pop, males, females, sex_ratio_2011, literacy_rate_2011), one row per
district, so the agent can run reliable pandas instead of parsing raw markdown.
Column positions are consistent across the three documents, so extraction is
positional. Writes CSV + DATA_DICTIONARY.md + sources.json under
data/processed/district_metrics/.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.models.documents import CorpusManifest

# Full state names as they appear in the "state total" row (dropped from districts).
_STATE_TOTAL_NAMES = {
    "Karnataka": {"karnataka"},
    "Odisha": {"odisha", "orissa"},
    "MP": {"madhya pradesh", "mp"},
}

# Each source table -> {output_column: source_column_index}. Positions verified
# consistent across all three documents.
_SOURCES = {
    "population": {
        "must": ["population", "decadal change", "residence"],
        "exclude": ["male", "scheduled", "child", "caste", "tribe"],  # 'male' also drops 'female'
        "cols": {"total_pop": 2, "rural_pop": 3, "urban_pop": 4},
    },
    "males": {
        "must": ["population", "decadal change", "residence", "male"],
        "exclude": ["female", "scheduled", "child"],
        "cols": {"males": 2},
    },
    "females": {
        "must": ["population", "decadal change", "residence", "female"],
        "exclude": ["scheduled", "child"],
        "cols": {"females": 2},
    },
    "sex_ratio": {
        "must": ["sex ratio", "residence"],
        "exclude": ["scheduled", "child", "caste", "tribe"],
        "cols": {"sex_ratio_2011": 5},
    },
    "literacy": {
        "must": ["literacy rate", "residence"],
        "exclude": ["male", "scheduled"],  # 'male' also drops 'female' -> persons table
        "cols": {"literacy_rate_2011": 8},
    },
}

_COLUMN_ORDER = [
    "district", "total_pop", "rural_pop", "urban_pop",
    "males", "females", "sex_ratio_2011", "literacy_rate_2011",
]


def _to_num(raw: str):
    s = (raw or "").strip().replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return None
    return float(s) if "." in s else int(s)


def _find_table(manifest: CorpusManifest, label: str, must, exclude):
    for doc in manifest.documents:
        if doc.label != label:
            continue
        for t in doc.tables:
            n = t.name.lower()
            if all(m in n for m in must) and not any(e in n for e in exclude):
                return t
    return None


def _parse(csv_path: Path, cols: dict[str, int], state_names: set[str]):
    """Return {district_name: {out_col: value}} for the district rows."""
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    out: dict[str, dict] = {}
    for r in rows:
        if len(r) < 2:
            continue
        code, name = r[0].strip(), r[1].strip()
        # Data rows: code is a number or '-', name is a non-numeric label.
        if not re.fullmatch(r"\d+|-", code):
            continue
        if not name or name.replace(" ", "").isdigit():
            continue
        if name.lower() in state_names:  # drop the state-total row
            continue
        rec = {out_col: _to_num(r[idx]) if idx < len(r) else None
               for out_col, idx in cols.items()}
        out[name] = rec
    return out


def build(manifest: CorpusManifest, processed_dir: Path) -> dict[str, dict]:
    out_dir = processed_dir / "district_metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}

    for label in _STATE_TOTAL_NAMES:
        state_names = _STATE_TOTAL_NAMES[label]
        merged: dict[str, dict] = {}
        source_pages: dict[str, int | None] = {}

        for src_name, spec in _SOURCES.items():
            t = _find_table(manifest, label, spec["must"], spec["exclude"])
            if t is None:
                continue
            source_pages[src_name] = t.page
            from app.config import ROOT_DIR

            parsed = _parse(ROOT_DIR / t.csv_path, spec["cols"], state_names)
            for district, rec in parsed.items():
                merged.setdefault(district, {"district": district}).update(rec)

        if not merged:
            continue

        out_path = out_dir / f"{label.lower()}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_COLUMN_ORDER, extrasaction="ignore")
            w.writeheader()
            for rec in merged.values():
                w.writerow(rec)

        summary[label] = {
            "csv": str(out_path.relative_to(ROOT_DIR)),
            "districts": len(merged),
            "source_pages": source_pages,
        }
        print(f"  {label}: {len(merged)} districts -> {out_path.name}  pages={source_pages}")

    # Machine-readable source pages so the dataset tool can emit citations.
    (out_dir / "sources.json").write_text(
        json.dumps({k: v["source_pages"] for k, v in summary.items()}, indent=2),
        encoding="utf-8",
    )
    _write_dictionary(out_dir, summary)
    return summary


def _write_dictionary(out_dir: Path, summary: dict) -> None:
    lines = [
        "# District metrics — clean dataset (data dictionary)",
        "",
        "One tidy row per district, normalized from the 2011 PCA Data Highlights "
        "tables. Use these for any district-level computation, ranking, table, or "
        "chart — they are far more reliable than the raw markdown tables.",
        "",
        "## Columns",
        "- `district` — district name",
        "- `total_pop`, `rural_pop`, `urban_pop` — population (2011, persons)",
        "- `males`, `females` — population by sex (2011)",
        "- `sex_ratio_2011` — females per 1000 males",
        "- `literacy_rate_2011` — effective literacy rate (%)",
        "",
        "## Files and how to cite",
        "When you report figures from a file, add an inline citation with the source "
        "page for that metric, e.g. `[Karnataka, p.27]` for population.",
    ]
    for label, info in summary.items():
        sp = info["source_pages"]
        pages = ", ".join(f"{k}=p.{v}" for k, v in sp.items())
        pop_page = sp.get("population")
        lines.append(
            f"- **{label}**: `{info['csv']}` — {info['districts']} districts. "
            f"Cite population/rural/urban as **[{label}, p.{pop_page}]**; "
            f"other source pages: {pages}."
        )
    (out_dir / "DATA_DICTIONARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
