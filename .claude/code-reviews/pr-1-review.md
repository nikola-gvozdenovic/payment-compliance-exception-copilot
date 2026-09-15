# PR #1 Review — feat: TICKET-2 synthetic policy, sanctions, and jurisdiction corpus

**Reviewer:** `piv-review-pr` agentic gate (deep pass dispatched to the `code-reviewer` subagent, fresh context)
**Branch:** `feat/ticket-2-synthetic-policy-corpus` → `main`
**Scope note:** this PR is 29 new static markdown documents plus 5 deleted stale `.claude/context/*.md` files (leftover scaffolding from an unrelated project template). No Python code was added or changed. The repo's `.claude/agents/code-reviewer.md` rubric (FastAPI/SQLAlchemy/type-safety) does not apply to this content — reviewed on the ticket's own terms instead (see Recommendations).

## Summary

Verified against `docs/specs/payment-compliance-exception-copilot.md` (TICKET-2), the implementation plan (`.claude/plans/ticket-2-synthetic-policy-sanctions-jurisdiction-corpus.md`), and the actual source files the corpus claims to describe/support (`data/models.py`, `data/generate_synthetic_payments.py`, `data/pain001_generator.py`). All 8 plan-documented decisions were followed faithfully; the one solo judgment call (synthetic `SYN-J1..J5` jurisdiction codes instead of real countries) is sound. **No critical, high, or medium issues found.**

## Validation

| Check | Result |
|---|---|
| `uv run pytest data/ -v` | 19 passed (no regression) |
| `uv run ruff check data/` | All checks passed |
| `uv run ruff format --check data/` | 38 files already formatted |
| `SANC-0001` byte-matches `PMT-0002` creditor name | ✅ exact match, only file |
| All 5 `FlagReason` values have ≥1 supporting doc | ✅ verified |
| Every `doc_id` matches its filename stem (29/29) | ✅ |
| Every `supports_flag_reason` value is a valid `FlagReason` string | ✅ zero typos |
| Every `fictional: true` doc has watermark as first body line | ✅ 29/29 |
| `fictional: false` only on `ISO-0001`, correct banner | ✅ |
| Corridor codes match `Payment.corridor` format | ✅ |
| No duplicate/real-entity-resembling sanctions names | ✅ |
| `docs/tasks/ticket-2.md` + SVGs match as-built content | ✅ |
| File counts (4 + 20 + 4 + 1 = 29) | ✅ exact |

## Issues Found

| # | Severity | File | Description | Suggested fix |
|---|----------|------|-------------|----------------|
| 1 | Low | `data/jurisdiction_rules/JUR-0002.md` | Prose references handling a failed BIC check as `missing_malformed_field`, but this doc's own `supports_flag_reason` frontmatter is `[]` (correct per plan — `PMT-0004`'s real flag reason is `timeout`, not this). Minor prose/frontmatter asymmetry; `POL-0001` already owns that tag, so this is harmless. | Optional: reword the prose to avoid implying a frontmatter link that isn't there, or leave as-is. |
| 2 | Low | `.claude/agents/code-reviewer.md` (meta, not this PR's content) | Agent rubric (type safety, FastAPI, SQLAlchemy async patterns) is inapplicable to this repo's actual greenfield/content-authoring nature — will produce noise on future automated reviews. | Update or replace the agent definition to match this repo's actual stack in a follow-up ticket. |

## What's Good

- Full cross-check against source code, not just internal consistency — `ISO-0001`'s field descriptions and `POL-0002`/`JUR-0001`'s processing-log detail strings verified verbatim against `pain001_generator.py` and `generate_synthetic_payments.py`.
- Automated (script-based) validation of all 29 files' frontmatter — exactly the class of error (a silent `supports_flag_reason` typo) the plan itself flagged as unguarded by any code today.
- Every one of the plan's 8 documented decisions and its one solo judgment call were followed and are internally consistent across the whole corpus.
- No regressions: existing 19-test suite and lint/format checks all pass unchanged.

## Recommendations

- Consider a lightweight frontmatter/coverage validator as part of TICKET-4's ingestion work, so future corpus additions get the same scrutiny this review did manually.
- Low priority: reconcile the `JUR-0002` prose/frontmatter asymmetry (issue #1) — optional, costs nothing functionally.
- Separately: `.claude/agents/code-reviewer.md` should be updated to match this project's actual stack (issue #2) — not a blocker for this PR.

## Recommendation

**Approve.** Zero critical/high/medium issues; both findings are low-severity polish/meta notes. Validation is clean and every ticket acceptance criterion is verified against source, not just eyeballed.
