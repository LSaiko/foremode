"""
llm.py — Optional, fully-offline local-LLM cold-start module for the AIAG-VDA pFMEA generator.
Requires no new *required* dependencies; all extras are lazy-imported.

Runtime support
---------------
  Ollama            http://localhost:11434/api/generate   (format: json)
  OpenAI-compat     http://*/v1/chat/completions          (response_format json_object)
  Claude API        https://api.anthropic.com/v1/messages  (ANTHROPIC_API_KEY env var)

Public API
----------
  draft_scenario(description, model, endpoint, scenarios_dir, use_rag, out_path, force) -> dict

# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION
# The following ~6-line block should be added to foremode.py's argparse CLI
# inside the 'generate' subcommand (or as its own 'llm-draft' subcommand)
# to wire the --llm-generate / --describe / --model / --endpoint / --rag / --force flow.
# ─────────────────────────────────────────────────────────────────────────────
#
#     parser.add_argument("--llm-generate", action="store_true",
#                         help="Draft a scenario YAML via a local LLM (offline).")
#     parser.add_argument("--describe", metavar="TEXT",
#                         help="Free-text process description for --llm-generate.")
#     parser.add_argument("--model", default="llama3.1:8b",
#                         help="Local model name (default: llama3.1:8b).")
#     parser.add_argument("--endpoint", default="http://localhost:11434",
#                         help="Local runtime base URL (Ollama or OpenAI-compat).")
#     parser.add_argument("--rag", action="store_true",
#                         help="Ground the draft with the closest existing scenario.")
#     parser.add_argument("--force", action="store_true",
#                         help="Allow overwriting an existing scenario file.")
#
#     # Then, early in the generate() handler:
#     if args.llm_generate:
#         import llm as _llm
#         out = Path(args.output) if args.output else None
#         _llm.draft_scenario(args.describe, model=args.model,
#                             endpoint=args.endpoint, use_rag=args.rag,
#                             out_path=out, force=args.force)
#         return  # drafted YAML is the end product; engineer reviews before re-running
#
# ─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # PyYAML — already a declared dependency


# ---------------------------------------------------------------------------
# Minimal schema validator (used when jsonschema is absent)
# ---------------------------------------------------------------------------

_REQUIRED_TOP = {
    "id", "process_name", "footer", "output", "properties",
    "scope", "structure", "function", "failures", "risk_note",
    "ratings", "actions", "results",
}
_REQUIRED_FAILURE_KEYS = {"step", "mode", "effect", "severity", "cause", "prevention", "detection"}


def _manual_validate(data: dict) -> List[str]:
    """Return a list of warning strings; raises ValueError on fatal schema errors."""
    warnings_out: List[str] = []
    missing = _REQUIRED_TOP - set(data.keys())
    if missing:
        raise ValueError(f"LLM output missing required top-level keys: {missing}")

    props = data.get("properties", {})
    for k in ("title", "subject", "keywords", "description"):
        if k not in props:
            warnings_out.append(f"properties.{k} missing from LLM output")

    for i, f in enumerate(data.get("failures", [])):
        missing_f = _REQUIRED_FAILURE_KEYS - set(f.keys())
        if missing_f:
            raise ValueError(f"failures[{i}] missing keys: {missing_f}")

    for i, r in enumerate(data.get("ratings", [])):
        if not (isinstance(r, list) and len(r) == 4):
            raise ValueError(f"ratings[{i}] must be a 4-element list [mode, s, o, d]")

    for i, a in enumerate(data.get("actions", [])):
        for k in ("mode", "action", "owner", "target"):
            if k not in a:
                warnings_out.append(f"actions[{i}].{k} missing")

    return warnings_out


def _validate(data: dict) -> List[str]:
    """Validate *data* against the scenario schema.  Returns list of warning strings."""
    try:
        import jsonschema  # noqa: F401 — optional
        # We do lightweight manual validation even when jsonschema is present
        # because the full JSON Schema for this project isn't bundled.
    except ImportError:
        pass
    return _manual_validate(data)


# ---------------------------------------------------------------------------
# HTTP transport — single private function so tests can monkeypatch it
# ---------------------------------------------------------------------------

def _call_runtime(endpoint: str, model: str, system: str, user: str) -> str:
    """POST to the local LLM runtime and return the raw response string.

    Auto-detects API flavour from the endpoint path:
      - contains 'anthropic.com' → Anthropic Claude Messages API
      - contains '/v1/chat/completions' → OpenAI-compatible
      - else → Ollama /api/generate
    """
    base = endpoint.rstrip("/")
    # Only allow http(s): prevents an endpoint like file:// or gopher:// being
    # handed to urlopen. Local-tool defence-in-depth, not a remote attack surface.
    if not base.startswith(("http://", "https://")):
        raise ValueError(f"endpoint must be an http(s) URL, got: {endpoint!r}")

    if "anthropic.com" in base:
        # Anthropic Claude API — the one runtime here that isn't local/offline.
        # Uses an already-issued API key from the environment; no new pip
        # dependency (no `anthropic` package) — plain urllib like the other
        # two branches.
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. Export an "
                "already-issued Anthropic API key to use --endpoint "
                "https://api.anthropic.com."
            )
        url = base if base.endswith("/v1/messages") else base + "/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read())
        # Messages API response: content is a list of blocks; text blocks
        # carry a "text" field. _SYSTEM_PROMPT already instructs the model to
        # return only JSON (no forced-JSON mode exists in this API, unlike
        # OpenAI's response_format).
        return raw["content"][0]["text"]

    elif "/v1/chat/completions" in base:
        # OpenAI-compatible (LM Studio, llama.cpp server, etc.)
        url = base if base.endswith("/v1/chat/completions") else base + "/v1/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read())
        return raw["choices"][0]["message"]["content"]

    else:
        # Ollama /api/generate
        url = base + "/api/generate"
        payload = {
            "model": model,
            "prompt": f"<system>\n{system}\n</system>\n\n{user}",
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2},
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read())
        return raw["response"]


# ---------------------------------------------------------------------------
# Few-shot example loader
# ---------------------------------------------------------------------------

def _load_few_shot(scenarios_dir: Path, max_examples: int = 2) -> List[dict]:
    """Return up to *max_examples* smallest scenario dicts from scenarios_dir."""
    yamls = sorted(scenarios_dir.glob("*.yaml"), key=lambda p: p.stat().st_size)
    examples = []
    for p in yamls[:max_examples]:
        try:
            with open(p, encoding="utf-8") as fh:
                examples.append(yaml.safe_load(fh))
        except Exception:
            pass
    return examples


# ---------------------------------------------------------------------------
# RAG: token-overlap similarity
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set:
    import re
    return set(re.findall(r"[a-z]+", text.lower()))


def _rag_top2(description: str, scenarios_dir: Path) -> List[dict]:
    """Return the 2 most description-similar scenarios using token-overlap."""
    desc_tokens = _tokenize(description)
    scored: List[tuple] = []
    for p in scenarios_dir.glob("*.yaml"):
        try:
            with open(p, encoding="utf-8") as fh:
                sc = yaml.safe_load(fh)
            candidate = sc.get("process_name", "") + " " + sc.get("footer", "")
            for f in sc.get("failures", []):
                candidate += " " + f.get("mode", "") + " " + f.get("effect", "")
            overlap = len(desc_tokens & _tokenize(candidate))
            scored.append((overlap, sc))
        except Exception:
            pass
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sc for _, sc in scored[:2]]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a medical-device process-FMEA assistant operating under ISO 13485 and 21 CFR 820.
    Return ONLY valid JSON — no markdown fences, no prose, no explanation.
    The JSON must exactly match the scenario schema shown below.
    S/O/D values must be integers in [1, 10].
    AP (action priority) must NOT appear in the JSON — it is computed externally.
    Every value you draft is preliminary; mark risk_note to indicate DRAFT status.

    SCHEMA (field types):
      id: str
      process_name: str
      footer: str
      output: str
      properties: {title: str, subject: str, keywords: str, description: str}
      scope: [[field, value], ...]
      structure: [[level, name, description], ...]
      function: [[component, function_text, reference], ...]
      failures: [{step, mode, effect, severity(int 1-10), cause, prevention, detection}, ...]
      risk_note: str
      ratings: [[mode, s(int), o(int), d(int)], ...]
      actions: [{mode, action, owner, target, revised:[s,o,d]}, ...]
      results: {documents: [[title, rev, date, owner], ...], archive: str}
""")


def _build_user_prompt(description: str, examples: List[dict]) -> str:
    lines = [f"Draft a complete pFMEA scenario for the following process:\n\n{description}\n"]
    if examples:
        lines.append("Use the following validated scenario(s) as structural examples "
                     "(match the schema exactly):\n")
        for ex in examples:
            # Trim to keep prompt manageable
            trimmed = {k: ex[k] for k in
                       ("id", "process_name", "failures", "ratings") if k in ex}
            lines.append(json.dumps(trimmed, indent=2))
    lines.append("\nReturn ONLY the JSON object. No markdown. No extra keys.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# S/O/D clamping
# ---------------------------------------------------------------------------

def _clamp_sod(data: dict) -> List[str]:
    """Clamp all S/O/D integers to [1, 10] in-place.  Returns list of warning messages."""
    clamp_warnings: List[str] = []

    def clamp(val: Any, label: str) -> int:
        try:
            v = int(val)
        except (TypeError, ValueError):
            clamp_warnings.append(f"{label}: non-integer value {val!r} replaced with 5")
            return 5
        if v < 1:
            clamp_warnings.append(f"{label}: value {v} clamped to 1")
            return 1
        if v > 10:
            clamp_warnings.append(f"{label}: value {v} clamped to 10")
            return 10
        return v

    for i, f in enumerate(data.get("failures", [])):
        f["severity"] = clamp(f.get("severity"), f"failures[{i}].severity")

    for i, r in enumerate(data.get("ratings", [])):
        if isinstance(r, list) and len(r) == 4:
            r[1] = clamp(r[1], f"ratings[{i}].s")
            r[2] = clamp(r[2], f"ratings[{i}].o")
            r[3] = clamp(r[3], f"ratings[{i}].d")

    for i, a in enumerate(data.get("actions", [])):
        if "revised" in a and isinstance(a["revised"], list) and len(a["revised"]) == 3:
            a["revised"][0] = clamp(a["revised"][0], f"actions[{i}].revised[s]")
            a["revised"][1] = clamp(a["revised"][1], f"actions[{i}].revised[o]")
            a["revised"][2] = clamp(a["revised"][2], f"actions[{i}].revised[d]")

    return clamp_warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draft_scenario(
    description: str,
    model: str = "llama3.1",
    endpoint: str = "http://localhost:11434",
    scenarios_dir: Path = Path("scenarios"),
    use_rag: bool = False,
    out_path: Optional[Path] = None,
    force: bool = False,
) -> dict:
    """Draft a pFMEA scenario dict from a free-text *description*.

    Parameters
    ----------
    description:    Free-text process description.
    model:          Local model name (e.g. 'llama3.1:8b', 'mistral:7b-instruct').
    endpoint:       Base URL of the local LLM runtime.
    scenarios_dir:  Directory containing existing *.yaml scenarios (for few-shot/RAG).
    use_rag:        If True, select the most similar scenarios as few-shot examples.
    out_path:       If given, write the draft YAML here + sidecar <out_path>.audit.log.
    force:          Allow overwriting an existing out_path.

    Returns
    -------
    The validated, annotated scenario dict (ready for foremode.py's render pipeline).
    """
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")

    scenarios_dir = Path(scenarios_dir)

    # --- Overwrite guard (pre-flight) ---
    if out_path is not None:
        out_path = Path(out_path)
        if out_path.exists() and not force:
            raise FileExistsError(
                f"{out_path} already exists. Pass force=True to overwrite."
            )

    # --- Select few-shot examples ---
    if use_rag and scenarios_dir.is_dir():
        examples = _rag_top2(description, scenarios_dir)
    elif scenarios_dir.is_dir():
        examples = _load_few_shot(scenarios_dir, max_examples=2)
    else:
        examples = []

    # --- Build prompts ---
    system_prompt = _SYSTEM_PROMPT
    user_prompt = _build_user_prompt(description, examples)

    # --- Call runtime ---
    timestamp = datetime.now(timezone.utc).isoformat()
    raw_response: str = _call_runtime(endpoint, model, system_prompt, user_prompt)

    # --- Parse JSON ---
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON response. Raw output:\n\n{raw_response}"
        ) from exc

    # --- Clamp S/O/D ---
    clamp_warnings = _clamp_sod(data)
    for w in clamp_warnings:
        warnings.warn(f"[llm] S/O/D clamp: {w}", stacklevel=2)

    # --- Validate schema ---
    schema_warnings = _validate(data)
    for w in schema_warnings:
        warnings.warn(f"[llm] schema: {w}", stacklevel=2)

    all_warnings = clamp_warnings + schema_warnings

    # --- Inject metadata ---
    data["_llm_draft"] = True
    data["_llm_model"] = model
    data["_llm_timestamp"] = timestamp

    # Ensure risk_note carries the DRAFT watermark
    existing_note = data.get("risk_note", "")
    draft_banner = "DRAFT — REQUIRES ENGINEER REVIEW. S/O/D ratings are LLM suggestions only."
    if draft_banner not in existing_note:
        data["risk_note"] = f"{draft_banner} {existing_note}".strip()

    # --- Overwrite guard (post-parse, in case out_path was None until now) ---
    if out_path is not None and out_path.exists() and not force:
        raise FileExistsError(
            f"{out_path} already exists. Pass force=True to overwrite."
        )

    # --- Write output ---
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, allow_unicode=True, sort_keys=False)

        audit_path = Path(str(out_path) + ".audit.log")
        audit_lines = [
            f"timestamp:  {timestamp}",
            f"model:      {model}",
            f"endpoint:   {endpoint}",
            f"out_path:   {out_path}",
            "",
            "=== SYSTEM PROMPT ===",
            system_prompt,
            "",
            "=== USER PROMPT ===",
            user_prompt,
            "",
            "=== RAW RESPONSE ===",
            raw_response,
            "",
            "=== WARNINGS ===",
        ] + (all_warnings if all_warnings else ["(none)"])
        with open(audit_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(audit_lines) + "\n")

        print(
            f"[llm] Draft written to {out_path}\n"
            f"[llm] Audit log:        {audit_path}\n"
            f"[llm] WARNING: All S/O/D values are DRAFT — engineer review required.",
            file=sys.stderr,
        )

    # --- Self-check ---
    assert data.get("_llm_draft") is True, "post-condition: _llm_draft must be True"

    return data
