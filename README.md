# Foremode — AIAG-VDA 2019 pFMEA Generator

*See the failure before it ships.*

[![CI](https://github.com/LSaiko/foremode/actions/workflows/ci.yml/badge.svg)](https://github.com/LSaiko/foremode/actions/workflows/ci.yml)
[![Coverage 75%+](https://img.shields.io/badge/coverage-75%25%2B-brightgreen)](.github/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Standard: AIAG-VDA 2019](https://img.shields.io/badge/standard-AIAG--VDA%202019-darkblue)](https://www.aiag.org/)
[![Regulatory: 21 CFR 820 | ISO 13485](https://img.shields.io/badge/regulatory-21%20CFR%20820%20%7C%20ISO%2013485-green)](https://www.fda.gov/medical-devices/quality-system-qs-regulationmedical-device-good-manufacturing-practices)

**🔗 Live demo & overview: [lsaiko.github.io/foremode](https://lsaiko.github.io/foremode/)**

A **data-driven generator** that turns a plain-YAML process description into a
**complete, professionally formatted pFMEA** following the **AIAG-VDA FMEA 4th
Edition (2019)** 7-step methodology — exported to **Excel, Word, and PDF** from a
single source of truth.

One engine ([`foremode.py`](foremode.py)), many scenarios ([`scenarios/*.yaml`](scenarios)).
Action Priority and all summary metrics are **computed**, never hand-entered, so a
workbook can't drift out of internal consistency.

- Deep knowledge of AIAG-VDA 2019 vs. legacy RPN methodology
- Medical device regulatory fluency (21 CFR 820, ISO 13485, ISO 11607, PMA Class III)
- Transparent, **auditable** risk logic (vs. black-box AI FMEA tools)
- Excel + Word + PDF output; optional **ISO 14971 risk bridge**; git-diffable scenarios

---

## Samples at a Glance

| # | Scenario (`scenarios/*.yaml`) | Device / Process | Classification | Key Standards |
|---|--------|-----------------|----------------|---------------|
| 1 | `cnc_femoral_stem` | Ti-6Al-4V Femoral Stem — CNC Machining | Class III PMA | 21 CFR 820, ISO 13485 |
| 2 | `spinal_peek_cage` | PEEK Lumbar Interbody Cage — Injection Molding | Class II 510(k) | 21 CFR 820, ASTM F2026 |
| 3 | `sterile_packaging` | Sterile Barrier Packaging — Tyvek-Film Heat Sealing | Class III support | ISO 11607-1, 21 CFR 820 |

---

## Workbook Structure — AIAG-VDA 7-Step Approach

Each generated workbook contains the same 7 sheets, populated with scenario-specific content:

| Sheet | Step | Content |
|-------|------|---------|
| **1. Scope & Planning** | Step 1 | Process name, scope, team, device classification, standards |
| **2. Structure Analysis** | Step 2 | System hierarchy: Cell / Line → Station → Components |
| **3. Function Analysis** | Step 3 | Intended functions and requirements satisfied |
| **4. Failure Analysis** | Step 4 | 6 failure modes with effects, severity, causes, controls |
| **5. Risk Rating** | Step 5 | AIAG-VDA Action Priority (AP) — NOT legacy RPN |
| **6. Optimization** | Step 6 | 4 corrective actions with owners, dates, revised AP |
| **7. Results Summary** | Step 7 | **Auto-computed** metrics, linked documents, archive location |
| *8. ISO 14971 Bridge* | *optional* | *Maps each failure to Hazard / Hazardous Situation / Harm / P1 / P2 (`--iso14971`)* |

---

## AIAG-VDA 2019 Key Differentiator: Action Priority vs. RPN

Uses **Action Priority (H/M/L)**, not legacy RPN multiplication (`S x O x D`), with
detection-weighted patient-safety logic:

```
S 9-10 + D 7-10            -> H   (undetected critical failure, any O)
S 9-10 + D 4-6 + O >= 4    -> H
S 7-8  + D 7-10 + O >= 4   -> H
All others                  -> M or L
```

**Why it matters:** an undetected failure reaching a patient is catastrophic
regardless of occurrence rate; AP weights Detection gaps more heavily than RPN.
The logic is one readable, **auditable** function — not a black-box model — and is
a documented simplification of the full handbook table. See
[`docs/ap-logic.md`](docs/ap-logic.md).

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/LSaiko/foremode.git
cd foremode
```

### 2. Install

```bash
# Option A — install as a command (recommended; works from any directory)
pip install .            # adds the `foremode` command + bundles the sample scenarios
# add formats:  pip install ".[docs]"   (Word/PDF)    or   pip install ".[all]"

# Option B — just run from the repo, no install
pip install -r requirements.txt
```

After Option A you can run `foremode ...` anywhere; with Option B use `python foremode.py ...`.

### 3. Generate a workbook

```bash
# List available scenarios
python foremode.py list

# Scaffold a brand-new scenario, then validate it
python foremode.py new my_process       # writes scenarios/my_process.yaml
python foremode.py check my_process     # validates S/O/D ranges + required fields

# Generate Excel (default)
python foremode.py generate cnc_femoral_stem
# Output: pfmea_aiag_vda_2019.xlsx

# Generate Excel + Word + PDF, plus the ISO 14971 bridge sheet
python foremode.py generate sterile_packaging --format all --iso14971

# Custom output basename
python foremode.py generate spinal_peek_cage -o out/my_pfmea

# Diff two scenario revisions into an auditable change summary
python foremode.py changelog --from old.yaml --to scenarios/cnc_femoral_stem.yaml
```

Add your own scenario by copying any file in [`scenarios/`](scenarios) and editing
the YAML — no Python required.

### 4. Standalone Word / PDF export

`export.py` also works directly on any existing workbook (the same renderer the
`--format` flag uses):

```bash
python export.py pfmea_aiag_vda_2019.xlsx                 # -> .docx and .pdf
python export.py pfmea_aiag_vda_2019.xlsx --format pdf    # -> .pdf only
python export.py pfmea_aiag_vda_2019.xlsx -o report       # custom basename
```

### 5. (Optional) Draft a new scenario from plain English — fully offline

With a local model runtime (e.g. [Ollama](https://ollama.com)) and the `llm` extra,
`draft` turns a one-line process description into a starter scenario YAML for you to
review. No cloud, no account — see [docs/llm-coldstart.md](docs/llm-coldstart.md).

```bash
pip install ".[llm]"
python foremode.py draft tyvek_seal --describe "heat-sealing Tyvek pouches for sterile implants"
# -> scenarios/tyvek_seal.yaml  (DRAFT — every S/O/D needs engineer review)
```

### 6. (Optional) Risk evidence export for a Design History File

```bash
python foremode.py generate spinal_peek_cage --evidence
# -> also writes <output>.risk.json next to the unchanged .xlsx
```

This is an additional output. The workbook it generates alongside is unchanged, and
`test_golden.py` checks that. The JSON carries `source: "foremode"` and a
`risk_controls` list. Each record matches the `RiskControl` model in
[traceability-matrix-dhf](https://github.com/LSaiko/traceability-matrix-dhf), so the
list loads directly into a `DhfProject`. The contract is vendored at
[`schemas/risk-control.schema.json`](schemas/risk-control.schema.json).

| pFMEA row | RiskControl field |
|-----------|-------------------|
| `failures[i].iso14971.hazard`, else failure mode | `hazard` |
| `failures[i].iso14971.harm`, else effect | `harm` |
| S (1-10) | `severity` = ceil(S/2), 1-5 |
| O (1-10) | `probability` = ceil(O/2), 1-5 |
| prevention + detection controls (+ planned action) | `control_measure` |
| — | `residual_risk_acceptable: null` (a QE decides this, not the tool) |

`requirement_ids` / `verification_ids` are left empty, so the links can be made on
the DHF side.

---

## Requirements

- Python 3.9+
- `openpyxl >= 3.1.2`, `PyYAML >= 6.0`
- Optional (Word/PDF export only): `python-docx`, `reportlab`

---

## Sample 1 — CNC Machining: Ti-6Al-4V Femoral Stem

**Device:** Cementless Ti-6Al-4V Femoral Stem — Implantable Hip Prosthesis
**Classification:** Class III PMA (21 CFR 814)

| # | Failure Mode | S | O | D | Initial AP | After Action |
|---|---|---|---|---|---|---|
| 1 | OD out of tolerance (oversize) | 8 | 4 | 3 | L | L |
| 2 | Surface roughness Ra > 0.8 um | 9 | 3 | 2 | M | M |
| 3 | Fixture slip / part shift | 7 | 3 | 4 | L | L |
| 4 | Coolant pressure drop / flow loss | 9 | 3 | 5 | M | M |
| 5 | Wrong program revision loaded | 8 | 2 | 3 | L | L |
| 6 | CMM inspection step skipped | 7 | 4 | 7 | **H** | L |

**Corrective Actions:**
1. Coolant flow sensor interlock — feed-hold alarm if PSI < 45
2. eDHR barcode-locked program selection — auto-archives obsolete revisions
3. Insert change interval: 150 → 100 parts; profilometer every 50 parts
4. Mandatory CMM gate-check in eDHR — part cannot advance without CMM pass record

---

## Sample 2 — Injection Molding: PEEK Lumbar Interbody Fusion Cage

**Device:** PEEK Lumbar Interbody Fusion Cage — Spinal Implant
**Classification:** Class II 510(k) (21 CFR 888.3070)

| # | Failure Mode | S | O | D | Initial AP | After Action |
|---|---|---|---|---|---|---|
| 1 | Flash / fin at parting line | 6 | 4 | 3 | L | L |
| 2 | Outer footprint or height OOS | 8 | 4 | 5 | M | L |
| 3 | Wrong PEEK grade loaded | 9 | 3 | 7 | **H** | M |
| 4 | Short shot / incomplete fill | 7 | 3 | 2 | L | L |
| 5 | Gate vestige height > 0.3 mm | 7 | 4 | 4 | M | L |
| 6 | Endplate surface texture OOS | 8 | 5 | 7 | **H** | L |

**Corrective Actions:**
1. Material barcode scan at hopper — eDHR locks start until CoA matches traveler
2. Inline profilometer at ejection — 100% Ra measurement with SPC alert
3. 100% vision system check for footprint and height — auto-reject to quarantine
4. Gate vestige height added to first-article CMM program; increased sampling to Cpk >= 1.67

---

## Sample 3 — Sterile Barrier Packaging: Tyvek-Film Pouch Heat Sealing

**Device:** Sterile Packaging Process supporting Class III Implants
**Standards:** ISO 11607-1:2019 | 21 CFR 820 | ISO 13485:2016

| # | Failure Mode | S | O | D | Initial AP | After Action |
|---|---|---|---|---|---|---|
| 1 | Incomplete / channel seal defect | 9 | 4 | 6 | **H** | M |
| 2 | Pinhole / micro-leak in film layer | 10 | 2 | 8 | **H** | M |
| 3 | Seal temperature out of range | 8 | 4 | 5 | M | L |
| 4 | Incorrect dwell time | 8 | 3 | 3 | L | L |
| 5 | UDI label / content mismatch | 8 | 2 | 4 | L | L |
| 6 | Package breach during EtO / transit | 9 | 3 | 5 | M | M |

**Corrective Actions:**
1. 100% bubble emission test per ASTM F2096 — replaces sampling; SPC peel strength
2. Dye penetration test every batch per ISO 11607-1 Annex A2.2; incoming pin-hole detection
3. Independent thermocouple with dual-channel alarm (Delta T > 3 C triggers feed-hold)
4. Post-EtO 100% visual inspection; ASTM D4169 distribution simulation semi-annually

---

## Repository Structure

```
foremode/
├── foremode.py                        # The engine + CLI (list/new/check/draft/generate/changelog)
├── export.py                       # Word (.docx) + PDF renderer (also standalone)
├── llm.py                          # Optional offline LLM cold-start (used by `draft`)
├── pyproject.toml                  # Packaging — `pip install .` adds the `foremode` command
├── test_*.py                       # pytest suite (engine, LLM, golden output, evidence)
├── golden_workbooks.json           # Pinned workbook fingerprints (python test_golden.py --update)
├── schemas/risk-control.schema.json # Vendored traceability-matrix-dhf RiskControl contract
├── .github/workflows/ci.yml        # CI: pytest + coverage floor on 3.9 / 3.13
├── scenarios/
│   ├── cnc_femoral_stem.yaml       # Sample 1: CNC Ti-6Al-4V Femoral Stem (Class III)
│   ├── spinal_peek_cage.yaml       # Sample 2: PEEK Injection Molded Spinal Cage (Class II)
│   └── sterile_packaging.yaml      # Sample 3: Sterile Barrier Packaging (ISO 11607)
├── docs/
│   ├── index.html                  # Landing page (GitHub Pages)
│   ├── ap-logic.md                 # Action Priority logic + scope
│   └── llm-coldstart.md            # Design spec: optional offline LLM drafting
├── pfmea_*.xlsx / .docx / .pdf     # Pre-generated sample outputs (3 scenarios x 3 formats)
├── requirements.txt
└── README.md
```

---

## Contributing

Built by one developer and an AI pair-programmer — collaborators welcome. The
scenario library is meant to grow: add a `scenarios/*.yaml` (start with
`foremode new <name>`, validate with `foremode check <name>`) and open a PR. Bug fixes,
new process scenarios, and renderer improvements are all fair game.

> Preliminary engineering tool. Generated pFMEAs are a starting point — a qualified
> quality engineer must review and approve them before any regulatory use.

---

## License

MIT License — free to use, modify, and adapt.

---

*Built with Python | AIAG-VDA FMEA 4th Edition 2019 | 21 CFR 820 | ISO 13485 | ISO 11607*
