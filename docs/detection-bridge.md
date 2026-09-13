# Detection / Gauge Cross-Check (bridge to grr-analysis-tool)

A pFMEA's Detection (D) rating is normally just hand-typed by the engineer,
with no link to whether the measurement system actually used for that
detection control can reliably discriminate defects. `suggest_detection()` in
[`foremode.py`](../foremode.py) closes that gap as a **cross-check, never a
silent override** — the manually-entered D in `ratings` always wins.

## How it works

Add an optional `gauge_ref: "path/to/grr_export.json"` to any entry in a
scenario's `failures` list, pointing at a `--json` gage-study summary produced
by the sibling tool `grr-analysis-tool`. It's correlated to its `ratings` row
by position — `failures[i]` and `ratings[i]` are already kept in lockstep this
way across every scenario (same order; `ratings` just uses a shorter mode
label).

`python foremode.py check <scenario>` then:
- loads the JSON (a missing or malformed file is a soft skip, printed but never fatal)
- computes a suggested D from the gauge study's `status` and `ndc`
- emits a `WARNING` line if the manual D and the suggested D differ by more than 2

`python foremode.py generate` adds an extra "Gauge-Suggested D (source)" column
to Sheet 5 (Risk Rating) whenever any failure in the scenario uses `gauge_ref`.
Scenarios that don't use it render an identical Sheet 5 to before.

## Expected JSON shape (from grr-analysis-tool)

```json
{
  "schema_version": 1,
  "metrics": { "ndc": 6, "status": "ACCEPTABLE" }
}
```
(Only `metrics.status` and `metrics.ndc` are read; other fields — `pct_grr`,
`equipment`, `characteristic`, etc. — are ignored, except `characteristic`
which is used to label the Sheet 5 column when present.)

## The lookup (deliberate simplification, like AP)

```
status == ACCEPTABLE + ndc >= 5   -> D=2  (adequate discrimination)
status == ACCEPTABLE + ndc <  5   -> D=4  (may be too coarse to trust fully)
status == MARGINAL                -> D=6  (moderate detection risk)
status == UNACCEPTABLE             -> D=8  (treat detection control as unreliable)
```

This is not a full MSA statistical treatment — it is a transparent, auditable
4-bucket mapping from the gage study's headline verdict to a D suggestion, in
the same spirit as `get_action_priority`'s AP table (see
[ap-logic.md](ap-logic.md)).
