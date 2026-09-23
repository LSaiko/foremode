"""Pins the openpyxl output: any change to generated cell values fails here.

Regenerate after an INTENDED output change:  python test_golden.py --update
"""
import hashlib
import json
import sys
from pathlib import Path

import foremode

SCENARIOS = ("cnc_femoral_stem", "spinal_peek_cage", "sterile_packaging")
GOLDEN = Path(__file__).parent / "golden_workbooks.json"


def fingerprint(sid, iso14971):
    sc, path = foremode.load_scenario(sid)
    for row in sc["scope"]:          # "auto" date -> today; pin it
        if row[0] == "Date":
            row[1] = "2000-01-01"
    wb = foremode.build_workbook(sc, iso14971=iso14971, base_dir=path.parent)
    h = hashlib.sha256()
    for ws in wb.worksheets:
        h.update(ws.title.encode())
        for row in ws.iter_rows(values_only=True):
            h.update(repr(row).encode())
    return h.hexdigest()


def current():
    return {f"{s}{'+iso' if iso else ''}": fingerprint(s, iso)
            for s in SCENARIOS for iso in (False, True)}


def test_workbook_output_unchanged():
    assert current() == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_cli_generate_all_formats(tmp_path):
    for sid in SCENARIOS:
        foremode.main(["generate", sid, "--format", "all", "--iso14971", "-o", str(tmp_path / sid)])
        for ext in (".xlsx", ".docx", ".pdf"):
            assert (tmp_path / sid).with_suffix(ext).stat().st_size > 0


if __name__ == "__main__" and "--update" in sys.argv:
    GOLDEN.write_text(json.dumps(current(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
