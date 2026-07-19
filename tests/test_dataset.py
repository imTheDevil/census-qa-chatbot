"""Tests for the district-dataset ETL parsing (the join/normalize logic)."""
from __future__ import annotations

from pathlib import Path

from app.ingestion.build_district_dataset import _parse, _to_num


def test_to_num():
    assert _to_num("61095297") == 61095297
    assert _to_num("75.36") == 75.36
    assert _to_num("1,211,195") == 1211195  # stray commas tolerated
    assert _to_num("-") is None
    assert _to_num("KARNATAKA") is None


def _write(tmp_path: Path, rows: list[list[str]]) -> Path:
    import csv

    p = tmp_path / "pop.csv"
    with p.open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return p


def test_parse_skips_headers_and_state_total(tmp_path):
    # Mirrors the real population table shape.
    rows = [
        ["State / District Code", "State / District", "Population 2011", "", ""],
        ["", "", "Total", "Rural", "Urban"],
        ["1", "2", "3", "4", "5"],
        ["-", "KARNATAKA", "61095297", "37469335", "23625962"],  # state total -> dropped
        ["555", "Belgaum", "4779661", "3568466", "1211195"],
        ["556", "Bagalkot", "1889752", "1291906", "597846"],
    ]
    csv_path = _write(tmp_path, rows)
    out = _parse(csv_path, {"total_pop": 2, "rural_pop": 3, "urban_pop": 4}, {"karnataka"})

    assert set(out) == {"Belgaum", "Bagalkot"}  # headers + state total excluded
    assert out["Belgaum"] == {"total_pop": 4779661, "rural_pop": 3568466, "urban_pop": 1211195}


def test_parse_handles_state_total_with_numeric_code(tmp_path):
    # Odisha/MP put the state code (not '-') on the total row; drop by name.
    rows = [
        ["Code", "District", "Population2011", "", ""],
        ["", "", "Total", "Rural", "Urban"],
        ["1", "2", "3", "4", "5"],
        ["21", "ODISHA", "41974218", "34970562", "7003656"],  # dropped by name
        ["01", "Bargarh", "1481255", "1360689", "120566"],
    ]
    csv_path = _write(tmp_path, rows)
    out = _parse(csv_path, {"total_pop": 2}, {"odisha", "orissa"})
    assert set(out) == {"Bargarh"}
    assert out["Bargarh"]["total_pop"] == 1481255
