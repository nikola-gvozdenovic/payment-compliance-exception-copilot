# PR #2 Review — feat: TICKET-3 append-only agent decision log

**Reviewer:** `piv-review-pr` agentic gate (deep pass dispatched to the `code-reviewer` subagent, fresh context)
**Branch:** `feat/ticket-3-decision-log` → `main`
**Commit reviewed:** `161c5bb`

## Summary

Reviewed every changed file in full plus the implementation plan, ticket brief, and diff. All 3 of TICKET-3's acceptance criteria are genuinely met (verified by direct `grep`, not just claimed): the `log_decision`/`get_decisions_for_payment` API exists with the right shape, no update/delete function exists anywhere in `data/decision_log/`, and retrieval-by-payment-ID-in-order is proven by real assertions, not just non-crash tests. The documented implementation-time deviation (`log_decision` now returns the JSON-normalized form instead of echoing raw objects) was independently re-verified as correct and properly tested. SQL is fully parameterized — no injection risk.

One real, if narrow-trigger, **High**-severity resource-leak bug was found in `_connect`.

## Validation

| Check | Result |
|---|---|
| `uv run pytest data/ -v` | 25 passed (19 existing + 6 new) |
| `uv run ruff check data/` | All checks passed |
| `uv run ruff format --check data/` | 42 files already formatted |
| Acceptance criteria: `log_decision`/`get_decisions_for_payment` API | ✅ |
| Acceptance criteria: no update/delete function anywhere | ✅ verified via `grep -rn "def "` (exactly 4 functions) |
| Acceptance criteria: retrieval by payment ID, in order | ✅ verified by real assertions on ordered output |
| SQL injection: all `?` placeholders, no string interpolation | ✅ |
| Deviation re-verification (`log_decision` return-value normalization) | ✅ confirmed correct and genuinely tested |
| All 6 new tests use `tmp_path`, never touch real DB path | ✅ |

## Issues Found

| # | Severity | File:Line | Description | Suggested fix |
|---|----------|-----------|-------------|----------------|
| 1 | High | `data/decision_log/store.py:47-52` (`_connect`) | If `conn.execute(_SCHEMA)` or `conn.execute(_INDEX)` raises after `sqlite3.connect()` succeeds (disk full, bad path, locked file), the open connection is never closed — `_connect` has no `try/finally` around its own `execute` calls, and the caller's `try/finally` only starts after `_connect` returns. | Wrap `_connect`'s body in `try/except: conn.close(); raise` (or a `try/finally` that closes only on the exception path) so a failed schema/index creation doesn't leak the connection. |
| 2 | Medium | `data/decision_log/models.py`, `data/decision_log/store.py` | `payment_id`/`agent_name` are unvalidated `str` — nothing stops `log_decision(payment_id="", ...)` from silently succeeding. The plan's rationale for not validating `payment_id` against `Payment`'s regex (decoupling) is sound, but a non-empty check is a different, narrower thing that's still missing. | Optional: add a non-empty check (`if not payment_id: raise ValueError(...)`) if this is a real concern, or explicitly document as accepted risk given no caller exists yet. |
| 3 | Low | `data/decision_log/store.py:59` | `input` parameter shadows the builtin `input()`. Confirmed cosmetic only (keyword-only, never called as the builtin in this file). Confirmed `ruff`'s default rule set (`E4,E7,E9,F`, since `pyproject.toml` sets no explicit `select`) does not include `flake8-builtins` (`A002`), so this was not and would not be caught by CI. | No action needed; note for awareness only. |

## What's Good

- Every acceptance criterion independently re-verified against the actual code, not taken on the PR description's word.
- The one documented implementation-time deviation was re-derived and confirmed correct, with the specific test (`test_pydantic_model_payload_round_trips`) checked to actually prove it rather than incidentally passing.
- `_json_default`'s recursive-serialization behavior (nested `BaseModel` inside a dict/list) verified against `json` module semantics, not assumed.
- Test suite genuinely exercises ordering and per-payment filtering via real assertions on ordered values, and consistently uses `tmp_path` for isolation.
- The plan's explicit choice not to unit-test "no update/delete exists" (deferring to code review) was independently judged reasonable, not just accepted.

## Recommendation

**Request changes.** The one High-severity issue (#1, connection leak in `_connect` on a schema/index-creation failure) is narrow-trigger but real and cheap to fix — a one-line `try/except` around `_connect`'s body. No critical/blocking issues; validation is otherwise clean and both acceptance criteria and the documented deviation check out. Fixing #1 (and optionally #2) should be quick, then this is ready to merge.
