# Feature: TICKET-1 — Payment Data Model + Synthetic ISO 20022 Message Generator

The following plan should be complete, but it's important to validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils/types/models. Import from the right files etc.

**Assumption made:** `/plan-feature` was invoked with no feature description. Based on the immediately preceding conversation (priming just completed, next step flagged as "TICKET-1"), this plan targets **TICKET-1** from `docs/specs/payment-compliance-exception-copilot.md`. If that's wrong, say so before implementation starts.

## Feature Description

This is the foundational ticket for the whole project (Wave 1, no dependencies). It establishes:
1. The `Payment` data model (and a `ProcessingLogEntry` model for the processing log every payment carries) that every later agent (Triage, Compliance, Audit) and the decision log (TICKET-3) will consume.
2. A generator that produces synthetic, realistic-looking ISO 20022 `pain.001`-style XML payloads.
3. Five committed synthetic payment fixtures — one per Triage cause category defined in the PRD — that later tickets (Triage Agent, Compliance Agent, Eval harness) will reuse as a stable, reviewable dataset.

Since this is a greenfield repo (no source code exists yet — confirmed via `find`, only `pyproject.toml` and doc/tooling scaffolding are tracked), this ticket also establishes the project's baseline Python tooling (uv-managed venv, pytest, ruff) and its first source directory, `data/`.

## User Story

As the **Triage Agent** (built in TICKET-5) and the **Compliance Agent** (TICKET-6),
I want a well-typed `Payment` record with a processing log and a realistic ISO 20022 XML payload, backed by a small set of known-answer synthetic scenarios,
So that I can be built, tested, and evaluated (TICKET-9) against ground truth without depending on hand-crafted ad-hoc fixtures in every later ticket.

## Problem Statement

There is currently no data model and no synthetic payment dataset. Every downstream ticket (RAG pipeline, Triage Agent, Compliance Agent, Audit Agent, eval harness) needs a `Payment` to operate on, and the PRD requires that dataset to be domain-accurate (real ISO 20022 message shape) and to cover the five triage cause categories the Triage Agent must classify.

## Solution Statement

Define a `pydantic` `Payment` model (plus `ProcessingLogEntry`, `PaymentStatus`, `FlagReason`) in `data/models.py`. Build a small, dependency-free ISO 20022 `pain.001.001.03` XML generator in `data/pain001_generator.py` using the standard library only. Write a scenario script, `data/generate_synthetic_payments.py`, that constructs five `Payment` objects — one per `FlagReason` value — and serializes them as committed JSON fixtures under `data/synthetic_payments/`. Provide a small loader (`data/loader.py`) so later tickets can do `from data.loader import load_all` instead of re-parsing JSON themselves.

## Feature Metadata

**Feature Type**: New Capability (foundational)
**Estimated Complexity**: Medium (no code patterns exist yet to mirror; domain-accuracy of the ISO 20022 XML needs care)
**Primary Systems Affected**: New `data/` package (models, generator, synthetic dataset); `pyproject.toml` (adds first dependencies + tool config)
**Dependencies**: `pydantic` (runtime), `pytest` + `ruff` (dev) — added via `uv add` / `uv add --dev`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `docs/specs/payment-compliance-exception-copilot.md` (TICKET-1 section, "Scope" / "Acceptance criteria" / "Files touched") — Why: this ticket's authoritative scope and acceptance criteria; do not silently expand past it (TICKET-2's RAG corpus, TICKET-3's decision log, and TICKET-5/6's agents are separate tickets — don't build them here).
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §4 "MVP Scope → Core Functionality", bullet 1 — Why: "Synthetic flagged/stuck payment modeled as an ISO 20022 `pain.001`-style message, with processing log/flag reason" is the literal MVP requirement this ticket satisfies.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §5, User Story 1 — Why: gives the concrete example this ticket must make possible later: "A payment flagged for a missing remittance field is triaged as 'malformed field — missing `RmtInf`'". One of the 5 synthetic scenarios below must be exactly this case.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §7.1 "Triage Agent" — Why: the cause taxonomy the Triage Agent will classify against is "missing/malformed field, compliance hold, corridor/currency issue, timeout, duplicate" — the `FlagReason` enum below must match these five values exactly, since TICKET-5 (Triage Agent) and TICKET-9 (eval harness, hand-labeled test set) both depend on this vocabulary being stable.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §6.3 "Directory Structure (indicative)" — Why: shows `/data/` as a top-level package (flat layout, not `src/`-nested), and shows tests co-located per-package (e.g. `/guardrails/tests/`) rather than in one top-level `/tests/` — this plan follows that same co-located convention for consistency (`data/tests/`).
- `docs/PRD_Payment_Compliance_Exception_Copilot_original.md` §8 "Data Model (Synthetic)" — Why: this is the only place the exact `Payment` field list survived (it didn't make it into the restructured PRD as a standalone section): *payment ID, source/destination currency, corridor, amount, timestamp, ISO 20022 XML payload, status, flag reason (if any)*. Use this as the literal field list for `data/models.py::Payment`.
- `pyproject.toml` (current, 5 lines) — Why: has `[project]` with `dependencies = []`, `requires-python = ">=3.14"`, and **no `[build-system]` table**. This ticket must add `[tool.uv]\npackage = false` before adding dependencies — see GOTCHA below.

### No prior code patterns exist

This is the first ticket in the repo — there is no existing Python source to mirror naming/error-handling/logging conventions from. This plan is establishing those conventions, not following pre-existing ones. Downstream tickets should mirror what's built here (pydantic models, module layout, co-located `tests/`), not diverge from it.

### Relevant Documentation

- [pydantic v2 Models](https://docs.pydantic.dev/latest/concepts/models/)
  - Why: `Payment`/`ProcessingLogEntry` are pydantic `BaseModel`s so later tickets (Triage/Compliance/Audit agent outputs) can follow the same validated, `.model_dump_json()`-serializable pattern — and so the decision log (TICKET-3) has a consistent way to persist agent inputs/outputs.
- [pydantic `Field` constraints](https://docs.pydantic.dev/latest/concepts/fields/) — Why: used for currency-code regex validation and positive-amount constraints below.
- ISO 20022 `pain.001.001.03` structure (verified via web research for this plan, no single canonical free spec page — corroborated across [Cross River docs](https://docs.crossriver.com/concepts/payments/xml-batch-payments/prepare-input-xml-file/PAIN.001.001.03-input) and [ValidateFin's SEPA pain.001 guide](https://validatefin.com/en/blog/sepa-pain001-guide)):
  - Root: `Document` (namespace `urn:iso:std:iso:20022:tech:xsd:pain.001.001.03`) → `CstmrCdtTrfInitn` → `GrpHdr`, `PmtInf`.
  - `GrpHdr` children, in order: `MsgId`, `CreDtTm`, `NbOfTxs`, `CtrlSum`, `InitgPty/Nm`.
  - `PmtInf` children, in order: `PmtInfId`, `PmtMtd` (`TRF`), `NbOfTxs`, `CtrlSum`, `ReqdExctnDt/Dt`, `Dbtr/Nm`, `DbtrAcct/Id/IBAN`, `DbtrAgt/FinInstnId/BIC`, `ChrgBr` (`SLEV`), then one or more `CdtTrfTxInf`.
  - `CdtTrfTxInf` children, in order: `PmtId/EndToEndId`, `Amt/InstdAmt` (with `Ccy` XML attribute), `CdtrAgt/FinInstnId/BIC`, `Cdtr/Nm`, `CdtrAcct/Id/IBAN`, then optionally `RmtInf/Ustrd`.
  - Why this matters: `RmtInf` is genuinely optional/last in the sequence, so "omit `RmtInf` entirely" is a schema-valid way to model the missing-remittance-field scenario without producing malformed XML — it's a *business-rule* violation (this payment processor requires it), not an XML-schema violation. The plan below relies on this distinction; don't conflate "XML is well-formed" with "payment passes our policy."
- [`xml.etree.ElementTree` — The Python Standard Library](https://docs.python.org/3/library/xml.etree.elementtree.html)
  - Why: used instead of `lxml` to avoid adding a dependency for XML building alone; sufficient for this ticket's structural (not XSD) validity requirement.
  - Gotcha section: `ET.SubElement` order matters — ElementTree preserves insertion order, so children must be added in the exact sequence documented above.
- [`xml.dom.minidom.parseString(...).toprettyxml()`](https://docs.python.org/3/library/xml.dom.minidom.html)
  - Why: used purely to pretty-print the generated XML for human/reviewer readability when fixtures are committed to the repo. `toprettyxml()` inserts whitespace text nodes — fine for readability, but means the output is not byte-identical to a strict-XSD-validated minimal serialization. Note this trade-off in the module docstring rather than silently.
- [uv: Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/) and [uv: Build systems (`package = false`)](https://docs.astral.sh/uv/concepts/projects/config/#build-systems)
  - Why: `uv add` requires the project to either declare a `[build-system]` or set `[tool.uv] package = false` (application/virtual project mode) — this repo has neither yet, so the very first `uv add` would otherwise attempt to build `paymentcompliance-exceptioncopilot` as a package with no source matching that name and fail.
- [pytest `pythonpath` ini option](https://docs.pytest.org/en/stable/reference/reference.html#confval-pythonpath) (pytest ≥ 7)
  - Why: with `package = false` and a flat (non-`src`) layout, `data/` is not installed into the venv — `pythonpath = ["."]` in `[tool.pytest.ini_options]` makes `from data.models import Payment` resolve when running `uv run pytest` from the repo root.

### Patterns to Follow

**Naming conventions (established by this ticket):**
- Modules: `snake_case.py` (`models.py`, `pain001_generator.py`, `generate_synthetic_payments.py`, `loader.py`).
- Pydantic models: `PascalCase` (`Payment`, `ProcessingLogEntry`).
- Enums: `PascalCase` class, `UPPER_SNAKE_CASE` members with lowercase `snake_case` string values (so serialized JSON/log output is human-readable) — e.g. `FlagReason.CORRIDOR_CURRENCY_ISSUE = "corridor_currency_issue"`.
- Synthetic payment IDs: deterministic, not random — `PMT-0001` … `PMT-0005` — so later tickets (eval harness, tests) can reference specific payments by stable ID.

**Error handling:**
- No custom exception hierarchy needed at this scope. Let pydantic's `ValidationError` propagate naturally from `Payment(...)` construction and from `Payment.model_validate_json(...)` in the loader — this is the correct "fail loudly on bad synthetic data" behavior for a foundational data ticket. Do not wrap-and-swallow.

**Determinism (important, specific to this ticket):**
- The 5 committed fixtures must be **reproducible byte-for-byte** if `generate_synthetic_payments.py` is re-run — use fixed, hardcoded `timestamp` and `ReqdExctnDt` values per scenario (e.g. `datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)`), not `datetime.now()`. This is a deliberate departure from "realistic live data" in favor of a stable, diffable, reviewable dataset — call this out in the script's module docstring so nobody "fixes" it later by switching to `now()`.

**Money handling:**
- `amount` is a `Decimal`, never a `float` (floating-point currency amounts are a classic bug source). Pydantic v2 handles `Decimal` fields natively.

**Other relevant patterns:**
- Currency codes: `str` fields validated with `Field(pattern=r"^[A-Z]{3}$")` (ISO 4217, e.g. `"EUR"`, `"GBP"`) — this is intentionally simple regex validation, not a real ISO 4217 code-list lookup (out of scope for this ticket).
- `corridor` is stored as an explicit field (matching the original PRD's data model literally) but auto-derived from `source_currency`/`destination_currency` via a pydantic `model_validator(mode="after")` when not explicitly passed, formatted as `f"{source_currency}-{destination_currency}"` (e.g. `"EUR-GBP"`) — this avoids the two fields silently disagreeing.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

**Tasks:**
- Configure `pyproject.toml`: add `[tool.uv]\npackage = false`, then add `pydantic` as a runtime dependency and `pytest`, `ruff` as dev dependencies via `uv add`/`uv add --dev`.
- Add `[tool.pytest.ini_options]` (`pythonpath = ["."]`) and a minimal `[tool.ruff]` config to `pyproject.toml`.
- Create the `data/` package (`data/__init__.py`) and its co-located `data/tests/` package (`data/tests/__init__.py`), per the PRD's indicative directory structure.

### Phase 2: Core Implementation

**Tasks:**
- Implement `data/models.py`: `PaymentStatus` enum, `FlagReason` enum, `ProcessingLogEntry` model, `Payment` model.
- Implement `data/pain001_generator.py`: `build_pain001_xml(...)` pure function building a `pain.001.001.03`-shaped XML string from primitive arguments (no dependency on the `Payment` model itself, so it's independently testable and reusable).
- Implement `data/generate_synthetic_payments.py`: defines the 5 fixed scenarios (one per `FlagReason`), builds `Payment` objects (calling `build_pain001_xml` for each payload), and — when run as a script — writes each as pretty-printed JSON to `data/synthetic_payments/<scenario_name>.json`.

### Phase 3: Integration

**Tasks:**
- Implement `data/loader.py`: `load_all() -> list[Payment]` and `load_by_flag_reason(reason: FlagReason) -> Payment`, reading the committed JSON fixtures back into validated `Payment` objects. This is the integration point every later ticket (TICKET-5 Triage, TICKET-6 Compliance, TICKET-9 Eval) will import from.
- Run `generate_synthetic_payments.py` once during implementation to actually produce and commit the 5 JSON fixtures under `data/synthetic_payments/`.

### Phase 4: Testing & Validation

**Tasks:**
- Unit tests for `data/models.py` (validation rules, corridor auto-derivation, enum values).
- Unit tests for `data/pain001_generator.py` (structural XML checks: namespace, element order, `RmtInf` omission case).
- Unit tests for `data/generate_synthetic_payments.py` + `data/loader.py` (round-trip: generate → write → load → equals; all 5 `FlagReason` values present exactly once; `PMT-0001..0005` IDs present).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE pyproject.toml

- **IMPLEMENT**: Add `[tool.uv]\npackage = false` (must be the very first change, before any `uv add`, or `uv add` will try to build the project as a package and fail — there's no source tree matching `paymentcompliance-exceptioncopilot` yet).
- **GOTCHA**: Do this edit manually (Edit tool), then run `uv add`/`uv add --dev` below — don't run `uv add` first.
- **VALIDATE**: `cat pyproject.toml` shows the `[tool.uv]` table above `[project]` or anywhere in the file (order among top-level tables doesn't matter to TOML).

### RUN dependency installation

- **IMPLEMENT**: `uv add pydantic` then `uv add --dev pytest ruff`.
- **GOTCHA**: Run these as two separate commands (runtime vs. dev-dependency groups) so `pydantic` lands in `[project.dependencies]` and `pytest`/`ruff` land in `[dependency-groups.dev]` (uv's convention) — don't hand-edit dependency arrays instead of using `uv add`, since `uv` also resolves/pins into `uv.lock`.
- **VALIDATE**: `uv run python -c "import pydantic; print(pydantic.VERSION)"` prints a `2.x` version.

### UPDATE pyproject.toml (test/lint config)

- **IMPLEMENT**: Add:
  ```toml
  [tool.pytest.ini_options]
  pythonpath = ["."]
  testpaths = ["data"]

  [tool.ruff]
  line-length = 100
  target-version = "py314"
  ```
- **PATTERN**: None in-repo yet; these are standard uv/pytest/ruff defaults for a flat-layout Python project.
- **VALIDATE**: `uv run pytest --collect-only` runs without error (will report "no tests collected" at this point — expected, no test files exist yet).

### CREATE data/__init__.py

- **IMPLEMENT**: Empty file (marks `data` as a regular package so `data.models`, `data.loader`, etc. are importable).
- **VALIDATE**: `uv run python -c "import data"` succeeds with no output.

### CREATE data/models.py

- **IMPLEMENT**:
  - `class PaymentStatus(str, Enum)`: `FLAGGED = "flagged"`, `STUCK = "stuck"`, `CLEARED = "cleared"`, `BLOCKED = "blocked"`, `ESCALATED = "escalated"`. Docstring note: only `FLAGGED`/`STUCK` are produced by this ticket's generator — the other three are reserved for the Compliance Agent (TICKET-6) to set later.
  - `class FlagReason(str, Enum)`: `MISSING_MALFORMED_FIELD = "missing_malformed_field"`, `COMPLIANCE_HOLD = "compliance_hold"`, `CORRIDOR_CURRENCY_ISSUE = "corridor_currency_issue"`, `TIMEOUT = "timeout"`, `DUPLICATE = "duplicate"`. Docstring: **must stay in sync with the Triage Agent's classification taxonomy** (PRD §7.1) and the TICKET-9 hand-labeled eval set — changing these values is a cross-cutting change, not a local one.
  - `class ProcessingLogEntry(BaseModel)`: `timestamp: datetime`, `stage: str`, `detail: str`.
  - `class Payment(BaseModel)`:
    - `payment_id: str` (`Field(pattern=r"^PMT-\d{4}$")`)
    - `source_currency: str` (`Field(pattern=r"^[A-Z]{3}$")`)
    - `destination_currency: str` (`Field(pattern=r"^[A-Z]{3}$")`)
    - `corridor: str | None = None` — auto-derived in a `@model_validator(mode="after")` as `f"{source_currency}-{destination_currency}"` when `None`.
    - `amount: Decimal` (`Field(gt=0)`)
    - `timestamp: datetime`
    - `iso20022_xml: str`
    - `status: PaymentStatus`
    - `flag_reason: FlagReason | None = None`
    - `processing_log: list[ProcessingLogEntry] = Field(default_factory=list)`
- **IMPORTS**: `from datetime import datetime`, `from decimal import Decimal`, `from enum import Enum`, `from pydantic import BaseModel, Field, model_validator`.
- **GOTCHA**: Use `model_validator(mode="after")`, not `mode="before"` — corridor derivation needs `source_currency`/`destination_currency` already validated and coerced.
- **VALIDATE**: `uv run python -c "from data.models import Payment, PaymentStatus, FlagReason; print(list(FlagReason))"` prints all 5 enum members.

### CREATE data/pain001_generator.py

- **IMPLEMENT**: `build_pain001_xml(*, msg_id: str, payment_info_id: str, end_to_end_id: str, execution_date: date, debtor_name: str, debtor_iban: str, debtor_bic: str, creditor_name: str, creditor_iban: str, creditor_bic: str, amount: Decimal, currency: str, remittance_info: str | None = None) -> str` that builds the element tree documented in "Relevant Documentation" above (`Document` → `CstmrCdtTrfInitn` → `GrpHdr` + `PmtInf` → `CdtTrfTxInf`), setting `NbOfTxs = "1"`, `CtrlSum` = str(amount) in both `GrpHdr` and `PmtInf`, `PmtMtd = "TRF"`, `ChrgBr = "SLEV"`, `Amt/InstdAmt` with `Ccy` attribute = `currency`. Only appends `RmtInf/Ustrd` when `remittance_info is not None`. Registers the default namespace (`urn:iso:std:iso:20022:tech:xsd:pain.001.001.03`) on the root `Document` element, serializes with `ET.tostring(root, encoding="unicode")`, then pretty-prints via `xml.dom.minidom.parseString(...).toprettyxml(indent="  ")`.
- **PATTERN**: No in-repo pattern; follow the element order from "Relevant Documentation" above exactly — this is a strict-sequence schema family, not an arbitrary-order document.
- **IMPORTS**: `import xml.etree.ElementTree as ET`, `from xml.dom import minidom`, `from datetime import date`, `from decimal import Decimal`.
- **GOTCHA**: `ET.SubElement(parent, tag)` appends in call order — write the calls in the exact documented sequence, don't reorder for "readability" in the source (that would produce out-of-sequence, schema-invalid XML even though ElementTree won't complain at build time).
- **GOTCHA**: `toprettyxml()` adds a leading `<?xml version="1.0" ?>` declaration and blank lines between some elements — this is fine for readability but means don't assert on exact byte output in tests; assert on parsed structure instead (see test task below).
- **VALIDATE**: `uv run python -c "from data.pain001_generator import build_pain001_xml; from decimal import Decimal; from datetime import date; print(build_pain001_xml(msg_id='M1', payment_info_id='P1', end_to_end_id='E1', execution_date=date(2026,1,15), debtor_name='Acme', debtor_iban='DE89370400440532013000', debtor_bic='DEUTDEFF', creditor_name='Beta', creditor_iban='GB29NWBK60161331926819', creditor_bic='NWBKGB2L', amount=Decimal('1000.00'), currency='EUR', remittance_info='Invoice 123'))"` prints well-formed XML containing `RmtInf`.

### CREATE data/generate_synthetic_payments.py

- **IMPLEMENT**: Module docstring explaining the determinism requirement (fixed timestamps, not `datetime.now()` — see "Determinism" pattern above). Define a list of 5 scenario dicts / small dataclasses, one per `FlagReason`:
  1. `PMT-0001` — `FlagReason.MISSING_MALFORMED_FIELD`, `PaymentStatus.FLAGGED`, EUR→EUR domestic-ish payment, generated with `remittance_info=None` (so `RmtInf` is entirely absent from the XML — this is the "missing remittance field" case from PRD User Story 1), `processing_log` ending in `stage="validation", detail="missing RmtInf: remittance information required by policy but absent from payload"`.
  2. `PMT-0002` — `FlagReason.COMPLIANCE_HOLD`, `PaymentStatus.FLAGGED`, creditor name deliberately similar to a placeholder "sanctioned-sounding" synthetic name (e.g. `"Zed Trading Consolidated"` — clearly fictional, no real-world entity), `processing_log` ending in `stage="compliance_screen", detail="creditor name matched a watchlist-style entry pending review"`. Note in a code comment: the actual sanctions mock list is TICKET-2's scope — this scenario only needs to *look like* a compliance hold to a human reviewer; it must not hardcode a dependency on TICKET-2's not-yet-existing document.
  3. `PMT-0003` — `FlagReason.CORRIDOR_CURRENCY_ISSUE`, `PaymentStatus.FLAGGED`, `source_currency="EUR"`, `destination_currency="GBP"` (mirrors the PRD's own `EUR→GBP corridor` example in User Story 2), `processing_log` ending in `stage="corridor_check", detail="EUR-GBP corridor flagged for manual policy review"`.
  4. `PMT-0004` — `FlagReason.TIMEOUT`, `PaymentStatus.STUCK`, `processing_log` with an entry showing an elapsed-time style detail, e.g. `stage="processing", detail="no rail acknowledgement received after 48h"`.
  5. `PMT-0005` — `FlagReason.DUPLICATE`, `PaymentStatus.FLAGGED`, `processing_log` ending in `stage="duplicate_check", detail="matches EndToEndId/amount/creditor of a payment processed 2 minutes earlier"`.
  For each: call `build_pain001_xml(...)` to populate `iso20022_xml`, construct a `Payment`, and — under `if __name__ == "__main__":` — write `payment.model_dump_json(indent=2)` to `data/synthetic_payments/<flag_reason_value>.json`, creating the directory if needed.
- **IMPORTS**: `from pathlib import Path`, `from datetime import datetime, date, timezone`, `from decimal import Decimal`, `from data.models import Payment, PaymentStatus, FlagReason, ProcessingLogEntry`, `from data.pain001_generator import build_pain001_xml`.
- **GOTCHA**: Use one fixed `datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)`-style timestamp per scenario (offset by a few minutes/hours between scenarios is fine and even realistic), never `datetime.now(timezone.utc)` — re-running this script must reproduce byte-identical JSON.
- **VALIDATE**: `uv run python -m data.generate_synthetic_payments && ls data/synthetic_payments/` lists exactly 5 `.json` files.

### CREATE data/loader.py

- **IMPLEMENT**: `SYNTHETIC_PAYMENTS_DIR = Path(__file__).parent / "synthetic_payments"`; `load_all() -> list[Payment]` (glob `*.json`, `Payment.model_validate_json(path.read_text())` for each, sorted by `payment_id`); `load_by_flag_reason(reason: FlagReason) -> Payment` (filters `load_all()`, raises `ValueError` if zero or more than one match — fixtures are 1:1 with `FlagReason` by construction).
- **IMPORTS**: `from pathlib import Path`, `from data.models import Payment, FlagReason`.
- **VALIDATE**: `uv run python -c "from data.loader import load_all; ps = load_all(); print(len(ps), sorted(p.payment_id for p in ps))"` prints `5 ['PMT-0001', 'PMT-0002', 'PMT-0003', 'PMT-0004', 'PMT-0005']`.

### CREATE data/tests/__init__.py

- **IMPLEMENT**: Empty file.

### CREATE data/tests/test_models.py

- **IMPLEMENT**: Tests covering: valid `Payment` construction; `corridor` auto-derivation when omitted (`"EUR"`/`"GBP"` → `"EUR-GBP"`); `corridor` left untouched when explicitly passed; invalid currency code (`"eur"` or `"EURO"`) raises `pydantic.ValidationError`; non-positive `amount` raises `ValidationError`; all 5 `FlagReason` members equal the exact string values listed in the PRD's Triage Agent taxonomy (assert the literal list, so a future accidental rename fails this test loudly).
- **VALIDATE**: `uv run pytest data/tests/test_models.py -v`

### CREATE data/tests/test_pain001_generator.py

- **IMPLEMENT**: Parse the generator's output with `xml.etree.ElementTree.fromstring` (strip the pretty-print's XML declaration handling — `ET.fromstring` handles that fine) and assert: root tag ends in `}Document` with the correct namespace; a `CstmrCdtTrfInitn/GrpHdr/MsgId` element exists with the passed value; `CdtTrfTxInf/Amt/InstdAmt` has `Ccy` attribute matching the passed currency and text matching the amount; when `remittance_info=None`, no `RmtInf` element exists anywhere in the tree; when `remittance_info="..."`, `RmtInf/Ustrd` exists with that exact text.
- **IMPORTS**: `import xml.etree.ElementTree as ET`.
- **GOTCHA**: Namespaced elements require either querying with the full `{urn:iso:std:iso:20022:tech:xsd:pain.001.001.03}Tag` form or passing a `namespaces={"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}` dict to `.find()`/`.findall()` — bare tag names won't match.
- **VALIDATE**: `uv run pytest data/tests/test_pain001_generator.py -v`

### CREATE data/tests/test_generate_synthetic_payments.py

- **IMPLEMENT**: Run the generation as a subprocess or import-and-call its main routine into a `tmp_path` (don't overwrite the committed fixtures during test runs — either parametrize the output dir or, simpler, just assert against the **already-committed** `data/synthetic_payments/*.json` via `data.loader.load_all()` rather than re-generating in the test). Assert: exactly 5 payments load; the set of `flag_reason` values equals the set of all 5 `FlagReason` members with no duplicates; `PMT-0001`'s payment has `flag_reason == FlagReason.MISSING_MALFORMED_FIELD` and its `iso20022_xml` contains no `RmtInf` substring; every loaded `Payment.iso20022_xml` re-parses cleanly via `xml.etree.ElementTree.fromstring`.
- **VALIDATE**: `uv run pytest data/tests/test_generate_synthetic_payments.py -v`

### RUN full test suite

- **IMPLEMENT**: n/a — validation step.
- **VALIDATE**: `uv run pytest data/ -v` — all tests pass.

---

## TESTING STRATEGY

### Unit Tests

- `data/models.py`: validation rules, enum stability, corridor derivation (see task above).
- `data/pain001_generator.py`: structural XML correctness per scenario input, namespace correctness, conditional `RmtInf` presence/absence.
- `data/loader.py` (via `test_generate_synthetic_payments.py`): round-trip integrity of the committed fixtures.

### Integration Tests

Not applicable at this ticket's scope — there's nothing to integrate with yet (RAG/agents don't exist). The "integration" this ticket provides is the `data.loader` import surface that TICKET-5/6/9 will consume; that surface is covered by the unit tests above.

### Edge Cases

- Currency code lowercase or wrong length → must fail validation, not silently coerce.
- `amount <= 0` → must fail validation.
- `remittance_info=None` → `RmtInf` element must be **completely absent**, not present-but-empty (an empty `<RmtInf/>` would be a different, weaker test of the "missing field" scenario).
- Re-running `generate_synthetic_payments.py` twice → byte-identical JSON output (determinism check — worth a manual check during implementation, not necessarily an automated test given trivial risk of flakiness from float formatting; use `Decimal` + `str()` consistently to avoid this).

### E2E / Browser Automation

Not applicable — this ticket has no UI or HTTP surface. No `agent-browser` validation needed.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check data/
uv run ruff format --check data/
```

### Level 2: Unit Tests

```bash
uv run pytest data/ -v
```

### Level 3: Integration Tests

Not applicable this ticket (see above) — Level 2 covers everything in scope.

### Level 4: Manual Validation

```bash
uv run python -m data.generate_synthetic_payments
uv run python -c "
from data.loader import load_all
for p in load_all():
    print(p.payment_id, p.flag_reason, p.status, p.corridor)
"
```
Expect 5 lines, one per `PMT-000{1..5}`, each with a distinct `flag_reason`.

### Level 5: E2E / Browser Automation

Not applicable — no UI exists at this ticket's scope.

### Level 6: Additional Validation (Optional)

None required. (Optional stretch, not blocking: pipe one generated XML string through `xmllint --noout -` if `libxml2` is available locally, as a well-formedness sanity check beyond `ET.fromstring` — not required for this ticket's acceptance criteria.)

---

## ACCEPTANCE CRITERIA

(mirrors `docs/specs/payment-compliance-exception-copilot.md` TICKET-1 verbatim, plus the concrete implementation details above)

- [ ] A `Payment` model/schema exists (`data/models.py`) and is the single representation used across the repo (no parallel ad-hoc dict/TypedDict representations introduced).
- [ ] The generator (`data/pain001_generator.py`) produces valid-shaped `pain.001` XML for all 5 flag-reason scenarios.
- [ ] Generated payments are loadable by downstream code as structured `Payment` objects via `data.loader.load_all()` / `load_by_flag_reason()`, not just raw XML/JSON.
- [ ] All 5 `FlagReason` values are covered by exactly one fixture each.
- [ ] `FlagReason` enum values match the Triage Agent taxonomy in PRD §7.1 exactly.
- [ ] Regenerating fixtures via `generate_synthetic_payments.py` is deterministic (fixed timestamps, no `datetime.now()`).
- [ ] `pyproject.toml` has `[tool.uv] package = false`, `pydantic` as a runtime dependency, `pytest`/`ruff` as dev dependencies, and matching `[tool.pytest.ini_options]`/`[tool.ruff]` config.
- [ ] All validation commands (Levels 1, 2, 4) pass with zero errors.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task's inline validation command passed immediately after that task
- [ ] `uv run ruff check data/` and `uv run ruff format --check data/` pass
- [ ] `uv run pytest data/ -v` passes (all unit tests)
- [ ] `data/synthetic_payments/` contains exactly 5 committed `.json` files
- [ ] Manual validation (Level 4) output shows 5 distinct flag reasons
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability (consider running the `code-review` skill before committing)

---

## NOTES

- **Why pydantic now, for a "just data" ticket:** later tickets (Triage/Compliance/Audit agent outputs, TICKET-3's decision log) all need structured, validated, JSON-serializable objects — introducing pydantic here sets the pattern once instead of each agent ticket re-deciding how to model structured output. This is a deliberate forward-compatibility choice, not scope creep — TICKET-1's own acceptance criteria literally require the model to be "used consistently across the repo."
- **Why stdlib XML instead of `lxml`:** this ticket only needs to *build* XML, not validate against a real XSD. `lxml` would be justified the moment a ticket needs real XSD validation (not currently in scope for any ticket) — don't add it preemptively.
- **Why committed JSON fixtures instead of "generate on the fly" in every ticket that needs payments:** a stable, reviewable, git-diffable dataset is valuable for a portfolio project specifically because reviewers (the PRD's primary persona) can open `data/synthetic_payments/*.json` directly and see the input data without running code.
- **Scope boundary respected:** this ticket does *not* touch the sanctions/policy document corpus (TICKET-2), the decision log (TICKET-3), RAG (TICKET-4), or any agent (TICKET-5/6/7). The `compliance_hold`/`corridor_currency_issue` scenarios only need to be *plausible-looking* to a human reviewer at this stage — they do not reference or depend on TICKET-2's not-yet-existing documents.

## Confidence Score

**8/10** for one-pass success. The two things most likely to need a second pass: (1) exact pydantic v2 syntax details (`model_validator` decorator signature) if the implementer is on an older pydantic mental model, and (2) minor XML namespace-matching friction in tests (bare vs. namespaced tag lookups) — both are called out explicitly as gotchas above, which should cover them.
