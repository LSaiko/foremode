"""Self-checks for the pFMEA engine. Run: python test_pfmea.py  (or pytest)."""
import json
import tempfile
from pathlib import Path

import foremode


def _base_sc(failure=None, rating=None):
    """Minimal scenario dict satisfying REQUIRED_KEYS, with one optional
    failure/rating pair for exercising the gauge cross-check."""
    sc = {
        "process_name": "Test Process",
        "scope": [], "structure": [], "function": [],
        "failures": [], "risk_note": "note",
        "ratings": [], "actions": [],
        "results": {"documents": [], "archive": ""},
    }
    if failure is not None:
        sc["failures"] = [failure]
        sc["ratings"] = [rating]
    return sc


def _write_gauge(tmp_path, status, ndc):
    p = Path(tmp_path) / "grr_export.json"
    p.write_text(json.dumps({"schema_version": 1, "metrics": {"status": status, "ndc": ndc}}),
                 encoding="utf-8")
    return p.name


def test_action_priority_known_cases():
    assert foremode.get_action_priority(8, 4, 3)[0] == "L"
    assert foremode.get_action_priority(9, 3, 2)[0] == "M"
    assert foremode.get_action_priority(7, 4, 7)[0] == "H"
    assert foremode.get_action_priority(10, 2, 8)[0] == "H"   # S>=9 + D>=7
    assert foremode.get_action_priority(3, 2, 2)[0] == "L"


def test_action_priority_validates_range():
    for bad in [(11, 1, 1), (5, 0, 5), (5, 5, 11)]:
        try:
            foremode.get_action_priority(*bad)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass


def test_metrics_consistent_with_ap():
    sc, _ = foremode.load_scenario("cnc_femoral_stem")
    metrics = dict(foremode.compute_metrics(sc))
    initial_h = sum(1 for r in sc["ratings"]
                    if foremode.get_action_priority(r[1], r[2], r[3])[0] == "H")
    assert metrics["Initial High (H) Action Priority"] == initial_h
    assert metrics["Total Failure Modes Analyzed"] == len(sc["ratings"])


def test_all_scenarios_build():
    for sid in ("cnc_femoral_stem", "spinal_peek_cage", "sterile_packaging"):
        sc, _ = foremode.load_scenario(sid)
        wb = foremode.build_workbook(sc, iso14971=True)
        assert len(wb.worksheets) == 8   # 7 steps + ISO 14971 bridge


def test_suggest_detection_lookup():
    assert foremode.suggest_detection({"metrics": {"status": "ACCEPTABLE", "ndc": 6}})[0] == 2
    assert foremode.suggest_detection({"metrics": {"status": "ACCEPTABLE", "ndc": 3}})[0] == 4
    assert foremode.suggest_detection({"metrics": {"status": "MARGINAL", "ndc": 4}})[0] == 6
    assert foremode.suggest_detection({"metrics": {"status": "UNACCEPTABLE", "ndc": 1}})[0] == 8


def test_gauge_ref_disagreement_warns():
    with tempfile.TemporaryDirectory() as tmp:
        fname = _write_gauge(tmp, "UNACCEPTABLE", 2)   # suggested D=8
        failure = {"step": "S", "mode": "M", "effect": "E", "severity": 8, "cause": "C",
                   "prevention": "P", "detection": "D", "gauge_ref": fname}
        sc = _base_sc(failure, ["M", 8, 3, 2])          # manual D=2, |2-8|=6 > 2
        errs = foremode.validate_scenario(sc, base_dir=Path(tmp))
        assert any(e.startswith("WARNING") and "gauge-suggested D=8" in e for e in errs)


def test_gauge_ref_agreement_no_warning():
    with tempfile.TemporaryDirectory() as tmp:
        fname = _write_gauge(tmp, "ACCEPTABLE", 6)      # suggested D=2
        failure = {"step": "S", "mode": "M", "effect": "E", "severity": 8, "cause": "C",
                   "prevention": "P", "detection": "D", "gauge_ref": fname}
        sc = _base_sc(failure, ["M", 8, 3, 3])          # manual D=3, |3-2|=1 <= 2
        errs = foremode.validate_scenario(sc, base_dir=Path(tmp))
        assert errs == []


def test_gauge_ref_missing_file_skips_gracefully():
    with tempfile.TemporaryDirectory() as tmp:
        failure = {"step": "S", "mode": "M", "effect": "E", "severity": 8, "cause": "C",
                   "prevention": "P", "detection": "D", "gauge_ref": "does_not_exist.json"}
        sc = _base_sc(failure, ["M", 8, 3, 2])
        errs = foremode.validate_scenario(sc, base_dir=Path(tmp))   # must not raise
        assert any(e.startswith("WARNING") and "gauge_ref not found" in e for e in errs)
        assert not any("gauge-suggested" in e for e in errs)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok  {name}")
    print("all checks passed")
