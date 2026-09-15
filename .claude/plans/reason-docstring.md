# Feature: Explain the Retired Close Reasons in RouteStartResponse (LP-234)

The following plan should be complete, but it's important to validate documentation and codebase
patterns and task sanity before implementing.

## Feature Description

`RouteStartResponse.reason` (`backend/online/serving/data_models/schemas.py:99`) is currently a
plain `str | None` with a one-line comment ("Present when status is 'close'. Same enum as
before."). It doesn't say what the five possible values actually are, or that three of them
(`hard_decline`, `exhausted`, `ev_negative`) can never be returned by the live path anymore —
they're carried only for backward compatibility with client code that already switches on this
field. This ticket fixes the docstring so a future reader doesn't have to go dig through the spec
PDF or git history to know that.

## User Story

As a developer reading `schemas.py` for the first time,
I want the `reason` field's docstring to explain every value it can hold and why,
So that I don't have to reverse-engineer which of the five enum values are actually reachable.

## Problem Statement

LP-231/LP-232 deleted every code path that used to produce `hard_decline`/`exhausted`/
`ev_negative` (they lived entirely inside `outcome()` and `_next_gate_after_skip()`, both removed).
The original LP-234 ticket asked to "audit and remove" that code, but it was already gone by the
time this ticket was picked up. What's left is that the schema's own documentation never caught up
— it still just says "same enum as before" with no explanation of which three values are now dead.

## Solution Statement

Replace the one-line comment above `reason: str | None = None` with a docstring-style comment
block enumerating all five values and their meaning, split clearly into "returned by the live
path today" (`unmapped_country`, `no_eligible_gate`) vs. "legacy-only, kept for backward
compatibility, never returned" (`hard_decline`, `exhausted`, `ev_negative`). Wording pulled directly
from `docs/Gate_List_API_Spec_Balance.pdf`'s "Close reasons" table (page 6-7) and its explanatory
paragraph on page 7, so it stays traceable to the actual source of truth rather than being
paraphrased from memory.

## Feature Metadata

**Feature Type**: Documentation only (no logic change)
**Estimated Complexity**: Low
**Primary Systems Affected**: `backend/online/serving/data_models/schemas.py` (one field's comment)
**Dependencies**: None

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `backend/online/serving/data_models/schemas.py:86-100` — `RouteStartResponse`, the class being
  touched. Confirmed unchanged since LP-231 (re-verified during this ticket's priming). Only
  line 98's comment (`# Present when status is 'close'. Same enum as before.`) and line 99
  (`reason: str | None = None`) are affected — everything else in the class is untouched.

### Relevant Documentation

- `docs/Gate_List_API_Spec_Balance.pdf`, "Close reasons" section (page 6-7) — the exact source
  text for the five values:
  - `unmapped_country` — "The card's BIN country doesn't map to the transaction currency under
    current routing rules."
  - `no_eligible_gate` — "No processor is currently eligible for this merchant, currency, and
    card combination."
  - `hard_decline` / `exhausted` / `ev_negative` — each: "Not applicable to a fresh list —
    retained for compatibility with the v1.0.0 enum." Page 7's explanatory paragraph: "Because
    the whole list is decided up front, hard_decline, exhausted, and ev_negative no longer occur
    at /route/start — a transaction either gets a full list or closes as unmapped_country /
    no_eligible_gate. The three retry-time reasons are kept in the enum only so client code that
    already switches on this field doesn't need a new case."

### Patterns to Follow

**Comments explain "why", generously** (`CLAUDE.md`'s documented house style) — this ticket is a
direct application of that: the new comment should explain not just what each value means but
*why* three of them are unreachable now, matching the density of other doc-comments already in
this same file (e.g. `RouteOutcomeRequest`'s old comment block on `not_attempted`/`error`, or
`RouteBackfillRequest`'s comment on why it repeats `RouteStartRequest`'s fields).

---

## STEP-BY-STEP TASKS

### UPDATE `backend/online/serving/data_models/schemas.py`

- **IMPLEMENT**: Replace the single-line comment above `reason: str | None = None` (currently
  `:98`) with:
  ```python
  # Present when status is 'close'. Five possible values total — only the
  # first two are ever actually returned by the live gate-list path:
  #   unmapped_country — the card's BIN country doesn't map to the
  #     transaction currency under current routing rules.
  #   no_eligible_gate — no processor is currently eligible for this
  #     merchant, currency, and card combination.
  #   hard_decline / exhausted / ev_negative — legacy values from the old
  #     per-attempt retry loop (see pne.py's history). Because the whole
  #     list is decided up front now, these can no longer occur — a
  #     transaction either gets a full list or closes as one of the two
  #     reasons above. Kept in the enum only so client code that already
  #     switches on this field doesn't need a new case.
  reason: str | None = None
  ```
- **PATTERN**: `RouteStartResponse.gates`/`balancing_type`'s existing multi-line comment style
  immediately above this field (`:89-97`) — match that indentation/wrapping convention exactly.
- **IMPORTS**: None.
- **GOTCHA**: This is a comment-only change — do not alter the field's type (`str | None`) or
  default (`None`). No `Literal[...]` enum was introduced for `reason` anywhere in this codebase
  (deliberately — see `RouteStartRequest`/`RouteDecisionResponse`'s history, `reason` has always
  been a plain string field, not a typed enum) — don't add one as a "helpful" side effect, that's
  out of scope and would be a real (if small) behavior/validation change, not a doc change.
- **VALIDATE**: `python -c "import ast; ast.parse(open('backend/online/serving/data_models/schemas.py').read())"` and `python -c "from backend.online.serving.data_models.schemas import RouteStartResponse; print(RouteStartResponse(correlation_id='x', status='close', reason='hard_decline').model_dump_json())"` — confirms the field still accepts any string, including the three legacy values, unchanged behavior.

---

## TESTING STRATEGY

### Unit Tests
None — comment-only change, nothing to test. `python -m unittest -v` must still pass (unaffected).

### Integration Tests
N/A.

### Edge Cases
N/A — no logic changed.

### E2E / Browser Automation
N/A — backend-only doc comment, no UI surface, no user-facing behavior change at all.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
python -c "import ast; ast.parse(open('backend/online/serving/data_models/schemas.py').read())"
```

### Level 2: Unit Tests
```bash
python -m unittest -v
```

### Level 3–6
N/A for a comment-only change.

---

## ACCEPTANCE CRITERIA

- [ ] `reason`'s comment explains all 5 possible values and why 3 are unreachable.
- [ ] No behavior change: `python -c "..."` sanity check (above) confirms the field still accepts
      any string value, unchanged.
- [ ] `python -m unittest -v` passes.

## COMPLETION CHECKLIST

- [ ] `schemas.py`'s `reason` comment updated
- [ ] Validation commands run and passed
- [ ] LP-234 updated/closed in Jira

---

## NOTES

This plan is intentionally lightweight — the ticket is a single comment block, not a feature. Most
of the template's sections (Phase 1-4 breakdown, integration tests, E2E/browser validation,
security considerations) don't apply and are marked N/A rather than padded out.
