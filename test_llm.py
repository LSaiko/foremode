"""Self-checks for llm.py — no network, no model, no GPU.
Run: python test_llm.py   (or pytest)
"""
import json
import os
import tempfile
from pathlib import Path

import llm

# Other tests in this file monkeypatch llm._call_runtime (module-level, never
# restored) to stub out draft_scenario's network call. Capture the real
# function here, before any test can clobber it, so the _call_runtime-level
# tests below still exercise the genuine implementation regardless of test
# execution order.
_REAL_CALL_RUNTIME = llm._call_runtime


# ---------------------------------------------------------------------------
# Minimal valid scenario JSON the monkeypatched runtime returns
# ---------------------------------------------------------------------------

_MINIMAL_SCENARIO = {
    "id": "test_draft",
    "process_name": "Test Welding Process",
    "footer": "AIAG-VDA FMEA 2019",
    "output": "pfmea_test_draft",
    "properties": {
        "title": "pFMEA - Test",
        "subject": "Test pFMEA",
        "keywords": "pFMEA, test",
        "description": "A minimal test scenario.",
    },
    "scope": [["Process Name", "Test Welding Process"]],
    "structure": [["Level 1", "Welder", "Joins parts"]],
    "function": [["Welder", "Join two metal parts", "ISO 1234"]],
    "failures": [
        {
            "step": "Welding",
            "mode": "Incomplete fusion",
            "effect": "Joint failure under load",
            "severity": 8,
            "cause": "Low heat input",
            "prevention": "Calibrated power supply",
            "detection": "X-ray inspection",
        }
    ],
    "risk_note": "Initial draft.",
    "ratings": [["Incomplete fusion", 8, 4, 3]],
    "actions": [
        {
            "mode": "Incomplete fusion",
            "action": "Increase weld current",
            "owner": "Process Eng",
            "target": "2024-12-01",
            "revised": [8, 2, 3],
        }
    ],
    "results": {
        "documents": [["pFMEA Report", "A", "2024-01-01", "QE"]],
        "archive": "network/share/pfmea",
    },
}


def _make_runtime(scenario_dict: dict):
    """Return a monkeypatch for llm._call_runtime that yields *scenario_dict* as JSON."""
    def _fake(endpoint, model, system, user):
        return json.dumps(scenario_dict)
    return _fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_llm_draft_flag_set():
    """draft_scenario must set _llm_draft: true on returned dict."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    result = llm.draft_scenario(
        "Laser welding of titanium implant components",
        scenarios_dir=Path("scenarios"),
    )
    assert result.get("_llm_draft") is True, "_llm_draft must be True"
    assert "_llm_model" in result
    assert "_llm_timestamp" in result


def test_llm_model_recorded():
    """_llm_model must reflect the model argument passed in."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    result = llm.draft_scenario(
        "Ultrasonic welding of polymer housing",
        model="mistral:7b",
        scenarios_dir=Path("scenarios"),
    )
    assert result["_llm_model"] == "mistral:7b"


def test_sod_clamping_high():
    """S/O/D values above 10 must be clamped to 10."""
    sc = json.loads(json.dumps(_MINIMAL_SCENARIO))  # deep copy
    sc["ratings"] = [["Incomplete fusion", 15, 12, 10]]
    sc["failures"][0]["severity"] = 15

    llm._call_runtime = _make_runtime(sc)
    import warnings
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = llm.draft_scenario("test process", scenarios_dir=Path("scenarios"))

    assert result["failures"][0]["severity"] == 10, "severity 15 should clamp to 10"
    r = result["ratings"][0]
    assert r[1] == 10, f"s=15 should clamp to 10, got {r[1]}"
    assert r[2] == 10, f"o=12 should clamp to 10, got {r[2]}"
    assert r[3] == 10, f"d=10 should stay 10, got {r[3]}"


def test_sod_clamping_low():
    """S/O/D values below 1 must be clamped to 1."""
    sc = json.loads(json.dumps(_MINIMAL_SCENARIO))
    sc["ratings"] = [["Incomplete fusion", 0, -5, 1]]
    sc["failures"][0]["severity"] = 0

    llm._call_runtime = _make_runtime(sc)
    import warnings
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = llm.draft_scenario("test process", scenarios_dir=Path("scenarios"))

    assert result["failures"][0]["severity"] == 1, "severity 0 should clamp to 1"
    r = result["ratings"][0]
    assert r[1] == 1, f"s=0 should clamp to 1, got {r[1]}"
    assert r[2] == 1, f"o=-5 should clamp to 1, got {r[2]}"
    assert r[3] == 1, f"d=1 should stay 1, got {r[3]}"


def test_overwrite_guard_raises_without_force():
    """draft_scenario must raise FileExistsError if out_path exists and force=False."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "draft.yaml"
        out.write_text("existing content")  # pre-create
        try:
            llm.draft_scenario(
                "injection molding of PEEK implants",
                out_path=out,
                force=False,
                scenarios_dir=Path("scenarios"),
            )
            assert False, "Expected FileExistsError was not raised"
        except FileExistsError:
            pass


def test_overwrite_allowed_with_force():
    """With force=True, draft_scenario must overwrite an existing file."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "draft.yaml"
        out.write_text("old content")
        result = llm.draft_scenario(
            "injection molding of PEEK implants",
            out_path=out,
            force=True,
            scenarios_dir=Path("scenarios"),
        )
        assert result.get("_llm_draft") is True
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "test_draft" in content or "process_name" in content


def test_audit_log_written():
    """Audit sidecar must be created alongside the output YAML."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "draft.yaml"
        llm.draft_scenario(
            "electron beam welding of CoCr femoral heads",
            out_path=out,
            scenarios_dir=Path("scenarios"),
        )
        audit = Path(str(out) + ".audit.log")
        assert audit.exists(), "audit sidecar must be created"
        text = audit.read_text(encoding="utf-8")
        assert "SYSTEM PROMPT" in text
        assert "USER PROMPT" in text
        assert "RAW RESPONSE" in text


def test_draft_banner_in_risk_note():
    """risk_note must contain the DRAFT watermark."""
    llm._call_runtime = _make_runtime(_MINIMAL_SCENARIO)
    result = llm.draft_scenario("test process", scenarios_dir=Path("scenarios"))
    assert "DRAFT" in result.get("risk_note", ""), "risk_note must contain DRAFT banner"


def test_empty_description_raises():
    """Empty description must raise ValueError immediately."""
    try:
        llm.draft_scenario("   ", scenarios_dir=Path("scenarios"))
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# _call_runtime — Claude branch (mocks urllib.request.urlopen directly,
# since this is testing _call_runtime itself rather than draft_scenario)
# ---------------------------------------------------------------------------

class _FakeHTTPResponse:
    """Minimal stand-in for the context-manager object urlopen() returns."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_call_runtime_claude_branch():
    """A https://api.anthropic.com endpoint must POST to /v1/messages with the
    Anthropic headers/body shape, and return content[0].text unparsed."""
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return _FakeHTTPResponse({"content": [{"type": "text", "text": '{"ok": true}'}]})

    old_urlopen = llm.urllib.request.urlopen
    old_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
    llm.urllib.request.urlopen = _fake_urlopen
    try:
        result = _REAL_CALL_RUNTIME(
            "https://api.anthropic.com", "claude-sonnet-5", "sys prompt", "user prompt"
        )
    finally:
        llm.urllib.request.urlopen = old_urlopen
        if old_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_key

    assert result == '{"ok": true}', "must return content[0].text unparsed"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"]["model"] == "claude-sonnet-5"
    assert captured["body"]["max_tokens"] == 4096
    assert "temperature" not in captured["body"], "claude-sonnet-5 rejects temperature"
    assert captured["body"]["system"] == "sys prompt"
    assert captured["body"]["messages"] == [{"role": "user", "content": "user prompt"}]


def test_call_runtime_claude_endpoint_path_not_doubled():
    """A caller-supplied endpoint that already includes /v1/messages must not
    have the path appended twice."""
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeHTTPResponse({"content": [{"type": "text", "text": "{}"}]})

    old_urlopen = llm.urllib.request.urlopen
    old_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
    llm.urllib.request.urlopen = _fake_urlopen
    try:
        _REAL_CALL_RUNTIME(
            "https://api.anthropic.com/v1/messages", "claude-sonnet-5", "sys", "user"
        )
    finally:
        llm.urllib.request.urlopen = old_urlopen
        if old_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_key

    assert captured["url"] == "https://api.anthropic.com/v1/messages"


def test_call_runtime_claude_missing_api_key_raises_before_network():
    """Missing ANTHROPIC_API_KEY must raise (not an opaque 401) before any
    network call is attempted."""
    def _fake_urlopen(req, timeout=None):
        raise AssertionError("urlopen must not be called when ANTHROPIC_API_KEY is unset")

    old_urlopen = llm.urllib.request.urlopen
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    llm.urllib.request.urlopen = _fake_urlopen
    try:
        try:
            _REAL_CALL_RUNTIME("https://api.anthropic.com", "claude-sonnet-5", "sys", "user")
            assert False, "Expected ValueError for missing ANTHROPIC_API_KEY"
        except ValueError:
            pass
    finally:
        llm.urllib.request.urlopen = old_urlopen
        if old_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = old_key


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all checks passed")
