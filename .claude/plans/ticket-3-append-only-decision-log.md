# Feature: TICKET-3 — Append-Only Agent Decision Log

The following plan should be complete, but it's important to validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils/types/models. Import from the right files etc.

**Context:** This plan was produced after a short clarification round (via `plan-feature`) to resolve the two architectural forks TICKET-3's own spec explicitly leaves open ("storage backend (local file or SQLite)") plus one repo-convention question. See NOTES for the answers and rationale.

## Feature Description

This ticket builds the decision-log component: a `log_decision(...)`-style API any future agent (Triage, Compliance, Audit, Dev-Tooling) can call to record its input, retrieved context, decision, and reasoning. It is the audit trail's **source of truth** — the eventual Audit/Report Agent (TICKET-7) renders a report *from* this log, it does not replace it. No agents exist yet to call it; this ticket only builds the recorder itself, ready for TICKET-5/6/7 to write to and read from.

## User Story

As the **Triage Agent** (TICKET-5), the **Compliance Agent** (TICKET-6), and the **Audit Agent** (TICKET-7),
I want a durable, append-only place to record exactly what I saw, retrieved, decided, and why — retrievable later by payment ID, in order —
So that a compliance analyst (or this project's eval harness, TICKET-9) can trust and verify every decision against its actual reasoning trace, not just a summarized final report.

## Problem Statement

There is currently no durable record of agent reasoning. Every downstream agent ticket (TICKET-5/6/7) needs somewhere to write its decision trail, and the PRD is explicit that this must be append-only and "tamper-evident-in-spirit" — not just a log file agents happen to write lines to, but a component with no code path to alter history once written.

## Solution Statement

Build a new `data/decision_log/` subpackage: `models.py` defines `DecisionLogEntry` (a pydantic `BaseModel`); `store.py` implements a SQLite-backed `log_decision(...)` (insert-only) and `get_decisions_for_payment(...)` (ordered read) against a local `decisions.db` file, with **no update/delete function exposed anywhere in the module** — append-only by construction, not by convention. `__init__.py` re-exports the public API so callers do `from data.decision_log import log_decision, get_decisions_for_payment, DecisionLogEntry`, mirroring how `data.loader` already re-exports `load_all`/`load_by_flag_reason` at the top level.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Low-Medium (small, well-scoped module; the only real design risk is JSON-serializing arbitrary agent payloads, which is addressed explicitly below)
**Primary Systems Affected**: New `data/decision_log/` subpackage. `.gitignore` (excludes the generated `.db` file). No existing files modified.
**Dependencies**: None new — `sqlite3` and `json` are both stdlib; `pydantic` is already a project dependency.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `docs/specs/payment-compliance-exception-copilot.md` (TICKET-3 section) — Why: authoritative scope/acceptance criteria — the literal source of the `log_decision(...)` API shape, the append-only/no-update-or-delete requirement, and the "retrieve by payment ID, in order" requirement.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` line 56 — Why: "Append-only agent decision log capturing every agent's input, retrieved context, decision, and reasoning — the audit trail" — the four fields (`input`, `context`, `decision`, `reasoning`) an entry must carry, verbatim.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` line 137 — Why: "the report is a rendering of this log, not the source of truth" — this is *why* TICKET-7 (Audit Agent) must read from this log rather than duplicating state; don't build anything here that would let the two drift apart.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` line 264 (Security Scope) — Why: "Append-only, tamper-evident-in-spirit decision logging" — the literal source of the "no mutation API" design decision below (see NOTES for why this satisfies "in-spirit" without a hash-chain).
- `docs/tasks/ticket-3.md` (already written this session) — Why: the plain-language brief for this exact ticket; keep this plan's Feature Description consistent with it.
- `data/models.py` (full file, 71 lines) — Why: the established pydantic patterns to mirror: `str` `Field(pattern=...)` for identifiers, `Decimal` for money (never `float`), enums as `PascalCase` class / `snake_case` string values, `model_validator(mode="after")` style. `Payment.payment_id` uses `Field(pattern=r"^PMT-\d{4}$")` — `DecisionLogEntry.payment_id` should accept that same shape (or any string — see GOTCHA below on why we don't hard-validate it).
- `data/loader.py` (full file, 35 lines) — Why: this is the exact re-export pattern `data/decision_log/__init__.py` should mirror — a thin package-level surface (`load_all`, `load_by_flag_reason`) over implementation detail, so downstream tickets import from the package root, not a specific internal module.
- `data/tests/test_models.py` (full file, 62 lines) — Why: the established test pattern to mirror — a small `_make_*(**overrides)` helper factory, `pytest.mark.parametrize` for validation-error cases, plain `assert`, no test classes.
- `.gitignore` (13 lines, current) — Why: has no `*.db` pattern yet; this ticket must add one so the generated SQLite file is never accidentally committed (unlike TICKET-1's synthetic payment fixtures, which *are* deliberately committed — this is generated runtime state, not a reviewable fixture).

### No in-repo pattern for a stdlib `sqlite3`-backed component yet

This is the first ticket to use `sqlite3`. `data/generate_synthetic_payments.py` and `data/pain001_generator.py` establish the "stdlib over a new dependency when stdlib suffices" precedent this ticket follows (see that ticket's plan, "Why stdlib XML instead of `lxml`").

### Relevant Documentation

- [`sqlite3` — DB-API 2.0 interface for SQLite databases](https://docs.python.org/3/library/sqlite3.html) — Why: standard library, no new dependency; `sqlite3.Row` row factory (used below) gives dict-like column access without a third-party ORM.
- [`sqlite3.Connection.execute` / parameterized queries](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.execute) — Why: always use `?` placeholders, never f-string interpolation into SQL — this is a content-authoring-adjacent project but this module is real code taking real string input (`payment_id`, `agent_name`), so SQL-injection hygiene applies even though the "adversary" is only ever this project's own agents.
- [`json.dumps(obj, default=...)`](https://docs.python.org/3/library/json.html#json.dumps) — Why: the `default` callback is the standard way to teach `json.dumps` how to serialize a non-JSON-native type (here, a pydantic `BaseModel` passed directly as `input`/`context`/`decision`) without pre-serializing at every call site.
- [pydantic `model_dump(mode="json")`](https://docs.python.org/3/concepts/serialization/#modelmodel_dump) — Why: used inside the `json.dumps` `default` callback below — `mode="json"` is what correctly turns a `Payment`'s `Decimal` and `datetime` fields into JSON-safe `str` values, matching how `Payment.model_dump_json()` is already used in `data/generate_synthetic_payments.py`.

### Patterns to Follow

**Naming conventions (extends TICKET-1's established conventions):**
- Subpackage: `data/decision_log/` (`snake_case`, matches `data/`'s existing flat `snake_case.py` modules, just one level deeper).
- Pydantic model: `DecisionLogEntry` (`PascalCase`, matches `Payment`, `ProcessingLogEntry`).
- Functions: `log_decision`, `get_decisions_for_payment` (`snake_case`, matches `load_all`, `load_by_flag_reason`).

**Error handling:**
- No custom exception hierarchy. Let `pydantic.ValidationError` propagate from `DecisionLogEntry(...)` construction, and let `TypeError` propagate naturally from `json.dumps(...)` when a caller passes a genuinely non-serializable object — this matches TICKET-1's established "fail loudly on bad data" convention (see that ticket's plan, "Error handling"). Do not wrap-and-swallow either.

**Append-only by construction, not by convention:**
- The module exposes exactly two public functions: `log_decision` (insert) and `get_decisions_for_payment` (read). **No `update_decision`, no `delete_decision`, ever** — this is what "tamper-evident-in-spirit" (PRD Security Scope) means in this plan's interpretation: there is no code path in this module capable of altering a written entry, not a cryptographic guarantee. See NOTES for why a hash-chain was explicitly *not* chosen.

**JSON-serializable payloads, pydantic-model-aware:**
- `input`, `context`, and `decision` are typed `Any` on `DecisionLogEntry` (deliberately — different agents' payloads have genuinely different shapes; see GOTCHA below on why this isn't over-permissive). At write time, `store.py` serializes each with `json.dumps(value, default=_json_default)`, where `_json_default` calls `.model_dump(mode="json")` on a pydantic `BaseModel` instance and otherwise raises `TypeError` (the `json` module's own default behavior) — so a caller can pass a `Payment` object directly as `input` without pre-serializing, while a genuinely non-serializable object (e.g. an open file handle) still fails loudly and immediately, not silently or downstream.

**Other relevant patterns:**
- Real timestamps, not fixed ones: unlike TICKET-1's synthetic payment fixtures (which deliberately use fixed timestamps for reproducibility — see that ticket's plan, "Determinism"), a decision-log entry's `timestamp` is `datetime.now(UTC)` at the moment `log_decision` is called. This is a deliberate, opposite choice from TICKET-1: a log is inherently about *when something actually happened*, not a reviewable fixture.
- `payment_id` is typed `str` on `DecisionLogEntry`, **not** validated against `Payment`'s `^PMT-\d{4}$` pattern here — the decision log must not import `data.models` and couple itself to the payment ID format, since a decision log is a generic-enough component that a future ticket could plausibly log against a different kind of subject. The `str` type plus the retrieval-by-exact-match semantics is sufficient for this ticket's scope.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

**Tasks:**
- Create the `data/decision_log/` package (`__init__.py`).
- Add `data/decision_log/*.db*` to `.gitignore` (covers the main `.db` file plus SQLite's `-journal`/`-wal`/`-shm` sidecar files).

### Phase 2: Core Implementation

**Tasks:**
- Implement `data/decision_log/models.py`: `DecisionLogEntry` pydantic model.
- Implement `data/decision_log/store.py`: schema (`CREATE TABLE IF NOT EXISTS`), `log_decision(...)`, `get_decisions_for_payment(...)`, the `_json_default` serialization helper.

### Phase 3: Integration

**Tasks:**
- Implement `data/decision_log/__init__.py`'s re-exports (`log_decision`, `get_decisions_for_payment`, `DecisionLogEntry`) so downstream tickets (TICKET-5/6/7) import from the package root.

### Phase 4: Testing & Validation

**Tasks:**
- Unit tests for `data/decision_log/store.py`: insert-and-read-back, ordering, per-payment filtering, pydantic-model-as-payload serialization, empty-result case.
- Confirm no update/delete function exists in the module's public surface (documented as a design guarantee in NOTES, not a runtime-tested assertion — see TESTING STRATEGY).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE .gitignore

- **IMPLEMENT**: Add a new line: `data/decision_log/*.db*`
- **GOTCHA**: The trailing `*` after `.db` is deliberate — it also matches SQLite's `decisions.db-journal` / `decisions.db-wal` / `decisions.db-shm` sidecar files, not just `decisions.db` itself.
- **VALIDATE**: `git check-ignore -v data/decision_log/decisions.db` (after the directory exists) prints a match against the new `.gitignore` line.

### CREATE data/decision_log/__init__.py

- **IMPLEMENT**:
  ```python
  from data.decision_log.models import DecisionLogEntry
  from data.decision_log.store import get_decisions_for_payment, log_decision

  __all__ = ["DecisionLogEntry", "log_decision", "get_decisions_for_payment"]
  ```
- **PATTERN**: `data/loader.py` — same "thin re-export surface" idea, one level up (package `__init__.py` instead of a sibling module).
- **VALIDATE**: (after the two files below exist) `uv run python -c "from data.decision_log import log_decision, get_decisions_for_payment, DecisionLogEntry"` succeeds with no output.

### CREATE data/decision_log/models.py

- **IMPLEMENT**:
  ```python
  """Pydantic model for a single append-only decision-log entry."""

  from datetime import datetime
  from typing import Any

  from pydantic import BaseModel


  class DecisionLogEntry(BaseModel):
      """One immutable record of an agent's input, context, decision, and reasoning."""

      id: int
      payment_id: str
      agent_name: str
      timestamp: datetime
      input: Any
      context: Any
      decision: Any
      reasoning: str
  ```
- **IMPORTS**: `from datetime import datetime`, `from typing import Any`, `from pydantic import BaseModel`.
- **GOTCHA**: `input`/`context`/`decision` are `Any`, not stricter types — see "Patterns to Follow" above for why this is a deliberate choice, not a shortcut. `reasoning` stays `str` (always free-text, per every PRD mention of "reasoning trace").
- **VALIDATE**: `uv run python -c "from data.decision_log.models import DecisionLogEntry; print(DecisionLogEntry.model_fields.keys())"` prints all 8 field names.

### CREATE data/decision_log/store.py

- **IMPLEMENT**:
  - `DECISION_LOG_DB_PATH = Path(__file__).parent / "decisions.db"` module-level constant.
  - `_SCHEMA = """CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT NOT NULL, agent_name TEXT NOT NULL, timestamp TEXT NOT NULL, input TEXT NOT NULL, context TEXT NOT NULL, decision TEXT NOT NULL, reasoning TEXT NOT NULL)"""` plus `CREATE INDEX IF NOT EXISTS idx_decisions_payment_id ON decisions(payment_id)`.
  - `_json_default(obj: object) -> Any`: if `isinstance(obj, BaseModel)`, return `obj.model_dump(mode="json")`; else `raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")` (mirrors the stdlib `json` module's own error message style).
  - `_connect(db_path: Path | str) -> sqlite3.Connection`: `sqlite3.connect(db_path)`, set `.row_factory = sqlite3.Row`, `execute(_SCHEMA)` + the index statement, return the connection. Called fresh inside both public functions (no shared/global connection — simplest correct option at this project's scale).
  - `log_decision(*, payment_id: str, agent_name: str, input: Any, context: Any, decision: Any, reasoning: str, db_path: Path | str = DECISION_LOG_DB_PATH) -> DecisionLogEntry`: opens a connection via `_connect`, `INSERT INTO decisions (payment_id, agent_name, timestamp, input, context, decision, reasoning) VALUES (?, ?, ?, ?, ?, ?, ?)` with `timestamp = datetime.now(UTC)`, the three JSON columns via `json.dumps(value, default=_json_default)`, commits, reads back `cursor.lastrowid` to build and return the full `DecisionLogEntry` (don't just echo the inputs back — round-trip through the DB's assigned `id` and stored `timestamp` string), closes the connection.
  - `get_decisions_for_payment(payment_id: str, db_path: Path | str = DECISION_LOG_DB_PATH) -> list[DecisionLogEntry]`: opens a connection via `_connect`, `SELECT * FROM decisions WHERE payment_id = ? ORDER BY id ASC`, `json.loads(...)` back the three JSON columns, `datetime.fromisoformat(...)` the timestamp, builds one `DecisionLogEntry` per row, closes the connection, returns the list (empty list, not an error, when there are zero matches).
- **IMPORTS**: `import json`, `import sqlite3`, `from datetime import UTC, datetime`, `from pathlib import Path`, `from typing import Any`, `from pydantic import BaseModel`, `from data.decision_log.models import DecisionLogEntry`.
- **GOTCHA**: Use `?` parameterized placeholders in every `execute(...)` call — never f-string/`.format()` a value into the SQL string, even though every current caller is trusted internal code (see "Relevant Documentation" above).
- **GOTCHA**: `ORDER BY id ASC`, not `ORDER BY timestamp ASC` — `id` (an `AUTOINCREMENT` primary key) is a strictly monotonic insertion-order guarantee; two entries logged within the same microsecond could otherwise tie on `timestamp` and land in an undefined relative order.
- **VALIDATE**: `uv run python -c "from data.decision_log import log_decision, get_decisions_for_payment; e = log_decision(payment_id='PMT-0001', agent_name='triage_agent', input={'x': 1}, context={'docs': ['POL-0001']}, decision='flagged', reasoning='test'); print(e.id, e.payment_id, e.agent_name); print(get_decisions_for_payment('PMT-0001'))"` prints the new entry's id/payment_id/agent_name, then a one-element list containing an equivalent `DecisionLogEntry`. (This also creates `data/decision_log/decisions.db` as a side effect — fine, it's gitignored; delete it afterward if you want a clean tree: `rm data/decision_log/decisions.db`.)

### CREATE data/decision_log/__init__.py re-exports

- **IMPLEMENT**: (see CREATE task above — listed separately there because it must be written *after* `models.py`/`store.py` exist, but is trivial once they do.)
- **VALIDATE**: covered by the `__init__.py` task's own validation command above.

### CREATE data/tests/test_decision_log.py

- **IMPLEMENT**: Use `tmp_path` (pytest's built-in fixture) for every test's `db_path` — **never** write to the real `DECISION_LOG_DB_PATH` from a test, to keep the test suite side-effect-free and parallel-safe. Cover:
  - `test_log_decision_returns_entry_with_id_and_timestamp` — assert `entry.id` is a positive `int`, `entry.timestamp` is a `datetime`.
  - `test_get_decisions_for_payment_returns_empty_list_for_unknown_payment` — assert `get_decisions_for_payment("PMT-9999", db_path=tmp_path / "test.db") == []`.
  - `test_entries_returned_in_insertion_order` — log 3 entries for the same `payment_id` with distinct `reasoning` values, assert `get_decisions_for_payment(...)` returns them in the same order they were logged.
  - `test_get_decisions_for_payment_filters_by_payment_id` — log one entry each for `"PMT-0001"` and `"PMT-0002"`, assert each retrieval returns only its own entry.
  - `test_pydantic_model_payload_round_trips` — call `log_decision` with `input=` an actual `data.models.Payment` instance (build one via the existing `_make_payment`-style pattern, or import a fixture via `data.loader.load_all()[0]`), assert the retrieved entry's `input` is a `dict` equal to `payment.model_dump(mode="json")`.
  - `test_reasoning_is_required` — omitting `reasoning` (or passing a non-`str`) at the `log_decision` call site is a `TypeError` from Python's own keyword-argument enforcement (it's a required keyword-only-by-convention parameter) — no special test needed beyond normal Python behavior; instead test that an empty-string `reasoning` is accepted (logging is not a validation layer for reasoning *quality*, only for its presence as a field) to document that this is intentionally permissive.
- **PATTERN**: `data/tests/test_models.py` — small helper factory, `pytest.mark.parametrize` where useful, plain `assert`, no test classes.
- **IMPORTS**: `from data.decision_log import DecisionLogEntry, get_decisions_for_payment, log_decision`, `from data.loader import load_all` (for the pydantic-payload test).
- **VALIDATE**: `uv run pytest data/tests/test_decision_log.py -v`

### RUN full test suite

- **IMPLEMENT**: n/a — validation step.
- **VALIDATE**: `uv run pytest data/ -v` — all tests pass (19 existing + new decision-log tests).

---

## TESTING STRATEGY

### Unit Tests

- `data/decision_log/store.py`: insert-and-read-back correctness, insertion-order guarantee, per-`payment_id` filtering, empty-result handling, pydantic-`BaseModel`-as-payload serialization (see task list above for the full set).

### Integration Tests

Not applicable at this ticket's scope — nothing calls `log_decision` yet (TICKET-5/6/7 don't exist). The "integration" this ticket provides is the `data.decision_log` import surface those tickets will consume; that surface is covered by the unit tests above.

### Edge Cases

- Zero decisions for a given `payment_id` → empty list, not an exception (already listed as a test above).
- Two entries logged in rapid succession (same or near-identical `timestamp`) → still returned in true insertion order via `ORDER BY id`, not `ORDER BY timestamp` (see GOTCHA above).
- A caller passes a pydantic `BaseModel` instance directly as `input`/`context`/`decision` → serializes correctly via `_json_default`, not a `TypeError` (explicitly tested).
- A caller passes a genuinely non-JSON-serializable object (e.g. a raw file handle) → `TypeError` propagates immediately from `log_decision`, not silently swallowed or deferred to read time.
- No update/delete function exists anywhere in `data/decision_log/`'s public or private surface — this is a structural guarantee (nothing in the module *can* mutate a row after insert), not something a unit test asserts by calling a nonexistent function; verified by code review (this is TICKET-3's own "tamper-evident-in-spirit" requirement) rather than by an automated check.

### E2E / Browser Automation

Not applicable — this ticket has no UI or HTTP surface. No `agent-browser` validation needed.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check data/decision_log/ data/tests/test_decision_log.py
uv run ruff format --check data/decision_log/ data/tests/test_decision_log.py
```

### Level 2: Unit Tests

```bash
uv run pytest data/ -v
```

### Level 3: Integration Tests

Not applicable this ticket (see above) — Level 2 covers everything in scope.

### Level 4: Manual Validation

```bash
uv run python -c "
from data.decision_log import log_decision, get_decisions_for_payment

e1 = log_decision(payment_id='PMT-0003', agent_name='triage_agent', input={'flag': 'corridor_currency_issue'}, context={'cited_doc': 'JUR-0001'}, decision='classified: corridor_currency_issue', reasoning='EUR-GBP corridor rule matched')
e2 = log_decision(payment_id='PMT-0003', agent_name='compliance_agent', input={'triage': e1.decision}, context={'cited_doc': 'POL-0004'}, decision='Escalate', reasoning='risk threshold exceeded')

for e in get_decisions_for_payment('PMT-0003'):
    print(e.id, e.agent_name, e.decision)
"
rm data/decision_log/decisions.db  # clean up the manually-created db afterward
```
Expect two lines printed, `triage_agent` before `compliance_agent`, in that order.

### Level 5: E2E / Browser Automation

Not applicable — no UI exists at this ticket's scope.

### Level 6: Additional Validation (Optional)

None required. (Optional stretch, not blocking: `sqlite3 data/decision_log/decisions.db ".schema decisions"` to eyeball the actual created schema matches `_SCHEMA` — useful during implementation, not part of CI.)

---

## ACCEPTANCE CRITERIA

(mirrors `docs/specs/payment-compliance-exception-copilot.md` TICKET-3 verbatim, plus this plan's concrete decisions)

- [ ] A `log_decision(...)`-style API exists that any agent can call with input/context/decision/reasoning (plus `payment_id`/`agent_name`, needed for the retrieval criterion below).
- [ ] Entries are immutable once written — no update/delete function exists anywhere in `data/decision_log/`.
- [ ] A stored entry can be retrieved by payment ID (`get_decisions_for_payment`) and returns all agent invocations for that payment in order.
- [ ] `data/decision_log/decisions.db` is gitignored, never committed.
- [ ] Callers can pass a pydantic `BaseModel` (e.g. a `Payment`) directly as `input`/`context`/`decision` without pre-serializing.
- [ ] All validation commands (Levels 1, 2, 4) pass with zero errors.
- [ ] Existing test suite (19 tests) still passes unchanged.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task's inline validation command passed immediately after that task
- [ ] `uv run ruff check` / `ruff format --check` pass on the new files
- [ ] `uv run pytest data/ -v` passes (19 existing + new decision-log tests)
- [ ] `data/decision_log/decisions.db` does not appear in `git status` (confirmed gitignored)
- [ ] Manual validation (Level 4) shows entries in correct insertion order
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability (consider running the `code-review` skill before committing)

---

## NOTES

**Interview decisions (from the `plan-feature` clarification round), each with rationale:**

1. **SQLite over a plain append-only file** — chosen because the ticket's own 3rd acceptance criterion ("retrieved by payment ID") is a query, not a scan; SQLite gives an indexed `WHERE payment_id = ?` for free, atomic single-row inserts, and needs zero new dependencies (`sqlite3` is stdlib) — a better fit for the project's zero-infrastructure-cost principle than it might first appear, since "zero infrastructure" means no server/hosting cost, not "no structured storage."
2. **No mutation API, no hash-chain** — chosen as the simplest interpretation of "tamper-evident-in-spirit" (PRD Security Scope) that still means something concrete: there is no `update_decision`/`delete_decision` function anywhere in this module, so altering history requires bypassing the module entirely (editing the `.db` file directly), not calling a supported API. A hash-chain would make tampering *detectable after the fact*, which is a stronger and more complex guarantee than what a demo project with no adversarial threat model needs — explicitly deferred, not forgotten.
3. **`data/decision_log/`, not a top-level `decision_log/`** — chosen to match how this repo has actually evolved: `data/` already holds every storage-backed component (`models.py`, `synthetic_payments/`, `policy_docs/`, `sanctions_mock/`, `jurisdiction_rules/`, `iso20022_reference/`), diverging from the PRD's original §6.3 indicative flat-top-level layout. This is a **repeat** of the same divergence TICKET-2's plan already documented and the ticket owner already approved — not a new one being silently introduced here.

**Design choices made during planning (not separately interview-asked, but flagged here for visibility):**
- `log_decision`'s full signature (`payment_id`, `agent_name`, `input`, `context`, `decision`, `reasoning`) adds `payment_id` and `agent_name` beyond the ticket text's literal "input/context/decision/reasoning" — both are strictly necessary for the ticket's own 3rd acceptance criterion (retrieval by payment ID, and "all agent invocations" implies knowing *which* agent) and are not a scope expansion.
- `input`/`context`/`decision` typed `Any` rather than a stricter shared type — every future agent's payload genuinely differs in shape (Triage's classification vs. Compliance's Clear/Block/Escalate), and inventing a shared envelope type now, before any of those agents exist, would be speculative design not grounded in real usage (YAGNI).

**Scope boundary respected:** this ticket does not touch TICKET-5/6/7 (no agents call `log_decision` yet), TICKET-4 (RAG), or TICKET-9 (eval harness). The manual validation above logs two illustrative entries only to prove the API works end-to-end, then deletes the resulting `.db` file so the repo stays clean.

## Confidence Score

**8/10** for one-pass success. The clarification round resolved every open design decision ahead of time; the main residual risk is purely mechanical — getting the `sqlite3` row round-trip (JSON column encode/decode, `datetime` ISO formatting) exactly right on the first pass. The Level 4 manual validation and the `test_pydantic_model_payload_round_trips` test are specifically designed to catch exactly that class of mistake.
