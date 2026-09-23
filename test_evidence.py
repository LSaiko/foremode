"""RiskControl evidence export validates against traceability-matrix-dhf's contract."""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

import foremode
from test_golden import SCENARIOS

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "risk-control.schema.json")
                    .read_text(encoding="utf-8"))
DHF = Path(__file__).resolve().parent.parent / "traceability-matrix-dhf"


def _payload(sid):
    sc, _ = foremode.load_scenario(sid)
    return sc, foremode.to_risk_records(sc, sid)


@pytest.mark.parametrize("sid", SCENARIOS)
def test_records_validate_against_schema(sid):
    sc, p = _payload(sid)
    assert p["source"] == "foremode" and p["scenario_id"] == sid
    assert len(p["risk_controls"]) == len(sc["failures"])
    for r in p["risk_controls"]:
        jsonschema.validate(r, SCHEMA)


def test_scale_mapping_and_mitigation():
    sc, p = _payload("cnc_femoral_stem")
    label, s, o, _ = sc["ratings"][0]
    r = p["risk_controls"][0]
    assert (r["severity"], r["probability"]) == ((s + 1) // 2, (o + 1) // 2)
    assert r["harm"] == sc["failures"][0]["effect"]
    assert sc["failures"][0]["prevention"] in r["control_measure"]
    assert r["residual_risk_acceptable"] is None
    planned = {a["mode"] for a in sc["actions"]}
    for (lbl, *_), rec in zip(sc["ratings"], p["risk_controls"]):
        assert ("Planned action:" in rec["control_measure"]) == (lbl in planned)


def test_mismatched_rows_refused():
    sc, _ = foremode.load_scenario("cnc_femoral_stem")
    sc["ratings"] = sc["ratings"][:-1]
    with pytest.raises(ValueError):
        foremode.to_risk_records(sc, "x")


def test_cli_evidence_flag(tmp_path):
    foremode.main(["generate", "sterile_packaging", "--evidence", "-o", str(tmp_path / "pkg")])
    p = json.loads((tmp_path / "pkg.risk.json").read_text(encoding="utf-8"))
    assert p["source"] == "foremode" and p["risk_controls"]


@pytest.mark.skipif(not DHF.exists() or sys.version_info < (3, 11),
                    reason="sibling traceability-matrix-dhf checkout not present")
@pytest.mark.parametrize("sid", SCENARIOS)
def test_records_ingest_into_live_dhf_model(sid):
    """Drift guard: vendored schema == DHF's model, and records load into DhfProject."""
    sys.path.insert(0, str(DHF))
    try:
        models = pytest.importorskip("schemas.models")
    finally:
        sys.path.remove(str(DHF))
    assert models.RiskControl.model_json_schema(mode="validation") == SCHEMA
    _, p = _payload(sid)
    proj = models.DhfProject(project_id=sid, name=p["process_name"], iec_62304_class="C",
                             risk_controls=p["risk_controls"])
    assert len(proj.risk_controls) == len(p["risk_controls"])
