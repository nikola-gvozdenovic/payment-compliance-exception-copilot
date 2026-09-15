# Feature: Gate List Response (LP-231 + LP-232 combined)

The following plan should be complete, but it's important to validate documentation and codebase
patterns and task sanity before implementing. Pay special attention to naming of existing utils,
types, and models — import from the right files.

## Feature Description

Replace PayNet Easy's live, per-attempt cascade loop (`/route/start` → `/route/outcome` →
`/route/outcome` → ...) with an upfront, list-based contract: `/route/start` now selects and
returns an entire ordered `gates[]` list (up to 3 positions) in one call. PayNet Easy walks that
list on its own, with **no further calls back to SmartRouting between attempts**. Real outcomes
come back only through `/route/backfill` (already live, unchanged), purely for learning — never a
routing decision.

This is a full contract replacement, not an additive change: `/route/outcome` is deleted, and the
retry-selection logic that depended on a live decline code (`decline_recovery`-driven ranking) is
redesigned to work without one, since positions 2 and 3 must be chosen before any real decline has
happened.

Source spec: `docs/Gate_List_API_Spec_Balance.pdf`. Companion visual summary (no new information):
`docs/Gate_List_Handoff.pdf`.

## User Story

As PayNet Easy's integration,
I want one call to get a full ranked list of gates to try for a transaction,
So that I can walk the cascade myself without a blocking round-trip to SmartRouting after every
decline.

## Problem Statement

Today's contract requires SmartRouting to be called synchronously between every attempt
(`/route/outcome`), which PayNet Easy's new Cascading Chain / Chain by Sequence product doesn't
need or want — it walks a locally-held ordered list itself. The current implementation
(`pne.py`) is built entirely around "one gate back per decision," including a retry-ranking model
(`decline_recovery`) that explicitly requires the real decline code just observed. That model has
no real decline code to work with if the whole list must be decided at once.

## Solution Statement

- `pne.start()` becomes a list-builder: rank position 1 exactly as today (general Way-3 bandit),
  then rank positions 2 and 3 using `decline_recovery`'s existing infrastructure entered at its
  most-marginal hierarchy level (`ANY`/`ANY`/`ANY` — "given some decline happens, regardless of
  which processor or reason, how well does this candidate recover at this slot") instead of a
  real observed decline code. This reuses `decline_recovery.recovery_probability` and its
  historical+live Bayesian blending completely unchanged — only the *keys* passed in change.
- `pne.outcome()` and everything that only exists to serve it (`_next_gate_after_skip`,
  `_handle_not_attempted`, `_handle_error`, `_replay_resolved_attempt`, `_pick_retry_processor`,
  `decline_recovery.should_retry`) is deleted — dead code once nothing calls it live.
- `cascade_sessions` needs **no schema change**: `position` is `attempt_number` (1–3), reused
  as-is. `start()` inserts up to 3 unresolved rows in one call instead of one row per live call.
  `backfill()` (unchanged, LP-233's territory) already resolves them correctly via
  `ON CONFLICT DO NOTHING` + a separate `resolve_attempt` UPDATE — confirmed compatible, no
  changes needed here.
- New `RouteStartResponse` schema matches the spec's JSON exactly: `correlation_id`, `status`
  (`gate_list`/`close`), `gates[]` (`position`/`gate_id`/`processor`), `balancing_type`, `reason`,
  `shadow`. No `attempt` field (the spec's examples don't have one).
- Wallets (`apple_pay`/`google_pay`) keep today's exact deterministic single-gate behavior,
  wrapped as a 1-entry `gates[]` list — the spec doesn't mention wallets at all (confirmed: no
  occurrence of "wallet" anywhere in `Gate_List_API_Spec_Balance.pdf`). LP-236 tracks asking
  PayNet Easy whether they want a real ranked fallback list for wallets too.

## Feature Metadata

**Feature Type**: Refactor / breaking contract change
**Estimated Complexity**: High (core routing-decision logic + response contract, no schema
migration, no automated test coverage of this path today)
**Primary Systems Affected**: `backend/online/routing/live_request/cascade_decision/pne.py`,
`backend/online/routing/live_request/live_learning/decline_recovery.py` (new marginal-lookup
call pattern, no code changes needed inside the module itself), `backend/online/serving/
data_models/schemas.py`, `backend/online/serving/transaction_routing/routes.py`,
`backend/online/serving/service.py`, `backend/online/routing/router.py`
**Dependencies**: None new — reuses existing `decline_recovery`, `bandit`, `capacity`,
`circuit_breaker`, `hard_rules`, `gates` modules as-is.

**Jira**: LP-231 ("Rework /route/start...") and LP-232 ("Redesign decline_recovery...") are
implemented together as one change per user decision — both tickets stay open and get updated
together when this lands. LP-234 (retiring `hard_decline`/`exhausted`/`ev_negative`) will likely
shrink to a doc/enum-comment cleanup only, since the code branches that produced those reasons
live entirely inside `outcome()`, which this plan deletes. LP-236 (new) tracks the wallet
fallback-list question to PayNet Easy.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `backend/online/routing/live_request/cascade_decision/pne.py` (whole file, 632 lines) — the
  entire engine. Critical sections:
  - `:1-21` module docstring — **will need rewriting**, currently states the "never a top-3
    candidate list" design explicitly; that's being reversed.
  - `:47-48` `MAX_ATTEMPTS = 3` — rename to `MAX_POSITIONS` (user decision).
  - `:82-90` `_close_response`/`_gate_response` — the old single-gate response builders; the new
    list response needs an equivalent, see Task list below.
  - `:93-99` `_wallet_gate` — unchanged logic, but its single result now needs wrapping as a
    1-entry list in `start()`.
  - `:102-155` `_eligible_candidates` — reused as-is, called once per position with a growing
    `exclude_processors` set.
  - `:158-181` `_select_gate` — reused as-is, unchanged, for position 1 only.
  - `:184-238` `_pick_retry_processor` — **being replaced**, not reused. Its shape (candidate
    scoring loop → `decline_recovery.recovery_probability` → capacity admission-bar survivor
    filter → `max` by `_p_recover`) is the pattern to mirror in the new list-building selector,
    but the `declining_processor`/`decline_code`/`decline_class` inputs change (see Solution
    Statement) and the `should_retry` EV gate is dropped (see NOTES).
  - `:241-273` `_file_gate_alert` — unaffected, still used by any future not_attempted/error
    reporting path if one is added later (none is, in this plan).
  - `:276-397` `_next_gate_after_skip`, `_handle_not_attempted`, `_handle_error`,
    `_replay_resolved_attempt` — **delete entirely**, only reachable from `outcome()`.
  - `:400-452` `start()` — **being replaced** with the list-building version.
  - `:455-570` `outcome()` — **delete entirely**.
  - `:573-631` `backfill()` — **do not touch**. Confirmed compatible with the new `start()`
    (see Solution Statement) — its own `insert_attempt` call becomes a no-op via
    `ON CONFLICT DO NOTHING` when `start()` already inserted the row, and its `resolve_attempt`
    UPDATE applies regardless of which function inserted the row first.

- `backend/online/routing/live_request/live_learning/decline_recovery.py` (whole file) — do
  **not** modify. Read to understand the marginal-lookup trick:
  - `:54` `ANY = '*'` — the sentinel already used for hierarchy fallback.
  - `:109-114` `_hierarchy_keys(declining_processor, decline_code, decline_class)` returns
    `[(declining_processor, decline_code, decline_class), (ANY, ANY, decline_class), (ANY, ANY,
    ANY)]`. Calling with `(ANY, ANY, ANY)` directly collapses this to `[(ANY,ANY,ANY)] * 3` —
    still correct, just redundant, landing straight on the coarsest real level.
  - `:188-214` `recovery_probability(pool, declining_processor, decline_code, decline_class,
    candidate_processor, cascade_slot, p_model_proxy, cfg)` — call this with
    `declining_processor=decline_recovery.ANY, decline_code=decline_recovery.ANY,
    decline_class=decline_recovery.ANY` for the new list-building selector. **No signature
    change needed.**
  - `:217-222` `should_retry` — becomes unused once `outcome()`/`_next_gate_after_skip` are
    deleted. Delete it too (see NOTES for the reasoning/tradeoff this represents).
  - `:225-247` `record_outcome` — unaffected, still called from `backfill()`.
  - `:62-80` `classify` — unaffected, still called from `backfill()` (for previous-attempt
    decline-recovery teaching) and available if ever needed elsewhere.
  - Tables: `decline_recovery_stats` (live) / `decline_recovery_history` (offline, frozen) are
    NOT segment-aware (no bin_group/currency/scheme column) — confirmed by reading every SQL
    WHERE clause in this file. The marginal `(ANY,ANY,ANY)` lookup is global, not per-segment;
    this is consistent with how the table already works today, not a new limitation introduced
    here.

- `backend/online/routing/live_request/live_learning/bandit.py` — unchanged, reused for position
  1 exactly as today (`score_candidates`/`sample_winner`, `:145-201`).

- `backend/online/routing/live_request/capacity/capacity.py` — unchanged. `admission_edge_bar`
  (`:61-82`) and `clears_admission_bar` (`:85-88`) get called per-position (sequential
  simulation, user decision), mirroring `_pick_retry_processor`'s existing survivor-filter
  pattern at `pne.py:222-236`.

- `backend/online/routing/live_request/cascade_decision/cascade_session.py` (whole file, 57
  lines) — **no changes**. `_COLS` (`:18`), `prior_rows` (`:21-28`), `insert_attempt`
  (`:31-42`, note the `ON CONFLICT (correlation_id, attempt_number) DO NOTHING`), `resolve_attempt`
  (`:45-56`) are all reused as-is. `position` == `attempt_number` (user decision), so no new
  column, no migration.

- `backend/online/routing/database/db.py` `:284-296` — `cascade_sessions` CREATE TABLE. Confirms
  PK is `(correlation_id, attempt_number)`, `gate_id`/`processor` nullable — already shaped
  correctly for inserting up to 3 unresolved rows at once.

- `backend/online/serving/data_models/schemas.py` (whole file):
  - `:76-83` `RouteDecisionResponse` — **delete** (only consumer was `route_outcome`/old
    `route_start`).
  - `:95-110` `RouteOutcomeRequest` — **delete**.
  - `:120-142` `RouteBackfillRequest`, `:146-149` `RouteBackfillResponse` — **no changes**.
  - `:55-72` `RouteStartRequest` — **no changes** (spec confirms request fields are unchanged
    from v1.0.0).

- `backend/online/serving/transaction_routing/routes.py` (whole file, 130 lines):
  - `:41-56` `route_start` — update to call the new response model; error-handling shape
    (try/except → `logger.exception` → `HTTPException(500, ...)`) stays identical — this is the
    strict contract `CLAUDE.md` mandates for PNE-facing endpoints, don't loosen it.
  - `:61-78` `route_outcome` — **delete**.
  - `:81-99` `route_backfill` — **no changes**.

- `backend/online/serving/service.py`:
  - `:54-61` imports `route_backfill, route_outcome, route_start` — remove `route_outcome`.
  - `:62-69` imports `RouteDecisionResponse` — remove; add the new `RouteStartResponse`.
  - `:93-96` route registration — remove line 96 (`app.post("/route/outcome", ...)`), update
    line 95's `response_model` to `RouteStartResponse`, update the comment above it (currently
    says "one gate ID back per decision, or a close instruction").

- `backend/online/routing/router.py`:
  - `:87-95` `route_start`/`route_outcome` — remove `route_outcome` (`:94-95`), keep
    `route_start` as a one-line delegation to `pne.start` (unchanged shape, just returns a
    different dict shape now).

### New Files to Create

None. This is entirely a modification of existing files — no new modules, no new schema, no new
endpoint (per the spec: `/route/backfill` is reused as-is, no new endpoint needed).

### Relevant Documentation

- `docs/Gate_List_API_Spec_Balance.pdf` — the actual contract: response field table (page 2),
  `gate_list`/`close` JSON examples (page 3), balancing-type guidance and the (still-open, LP-230)
  hard-decline skip question (page 4), close-reasons table (page 6-7).
- `.claude/context/pne-cascade-engine.md` — **currently describes the OLD architecture as a
  deliberate design choice**; this plan's changes make several of its statements false (see
  LP-235, which is scoped separately to rewrite it — don't rewrite it as part of this plan, but
  don't trust it as ground truth while implementing either).

### Patterns to Follow

**Naming Conventions**: `snake_case` functions/variables, single-leading-underscore for private
helpers (`_build_gate_list`, `_pick_list_processor` — see Task list), module-level constants
`SCREAMING_SNAKE_CASE` (`MAX_POSITIONS`). Matches `CLAUDE.md`'s documented conventions exactly.

**Comments explain "why", generously** — this module leans hard on this (see `pne.py`'s existing
docstrings on `_pick_retry_processor`, `_next_gate_after_skip`). The new list-building functions
need the same treatment: explain *why* the marginal `(ANY,ANY,ANY)` lookup is the right substitute
for a real decline code, not just what the code does.

**Isolate-and-degrade**: `bandit.py:126-128`'s pattern (a trained-model scoring failure treated as
uninformative `p_model=0.0`, never fatal) — the new position-2/3 selector calls
`score_processor` the same way `_pick_retry_processor` does today (`pne.py:206-212`, wrapped in
`try/except Exception: logger.exception(...)`) — keep that exact try/except.

**Structured per-subsystem logging**: `logger = logging.getLogger("smartrouting.pne")` already at
`pne.py:45` — reuse it, don't create a new logger.

**Route handler error contract**: `transaction_routing/routes.py:46-50`'s
try/except → `logger.exception` → `HTTPException(500, ...)` shape — copy exactly for the
updated `route_start`.

---

## IMPLEMENTATION PLAN

### Phase 1: Schema & Response Shape

Define the new response contract before touching engine logic, so the engine work has a concrete
target shape.

**Tasks:**
- Add `RouteStartResponse` (and a nested gate-entry model) to `schemas.py`.
- Remove `RouteDecisionResponse` and `RouteOutcomeRequest`.

### Phase 2: Engine — List Building

The core logic change, entirely inside `pne.py`.

**Tasks:**
- Rename `MAX_ATTEMPTS` → `MAX_POSITIONS`.
- Delete `outcome()` and its exclusive dependents (`_next_gate_after_skip`,
  `_handle_not_attempted`, `_handle_error`, `_replay_resolved_attempt`, `_pick_retry_processor`).
- Add `_pick_list_processor` (position 2/3 selector, marginal `decline_recovery` lookup).
- Rewrite `start()` as the list-builder (position 1 via existing `_select_gate`, positions 2/3 via
  the new selector, sequential exclude-set + per-position capacity admission bar), with idempotent
  replay from `cascade_session.prior_rows`.
- Update the module docstring to describe the new contract.

### Phase 3: Wiring — Routes, Service, Router

Propagate the new response shape and endpoint removal through the FastAPI layer.

**Tasks:**
- Update `transaction_routing/routes.py`: rewrite `route_start`, delete `route_outcome`.
- Update `service.py`: imports + route registration.
- Update `router.py`: delete `Router.route_outcome`.

### Phase 4: Cleanup — decline_recovery

Remove the now-dead EV-gate function.

**Tasks:**
- Delete `decline_recovery.should_retry` (unused once `outcome()` is gone — confirm no other
  caller exists before deleting).

### Phase 5: Manual Validation

No automated test file (per user decision — matches `CLAUDE.md`'s honest "no real coverage"
state; adding one would require a new CI pip-install step, out of scope here).

**Tasks:**
- Run `python -m unittest -v` — confirm the existing (unrelated) smoke test still passes.
- Manually exercise `/route/start` against a local instance for: a fresh transaction (verify
  1-3 position list), a repeat call with the same `correlation_id` (verify exact replay, not
  recomputation), an `unmapped_country`/`no_eligible_gate` close, and a wallet transaction
  (verify exactly 1 entry in `gates[]`).

---

## STEP-BY-STEP TASKS

Execute in order — each task is atomic and independently checkable.

### UPDATE `backend/online/serving/data_models/schemas.py`

- **IMPLEMENT**: Add a `RouteGate` model (`position: int`, `gate_id: int`, `processor: str`).
  Add `RouteStartResponse` (`correlation_id: str`, `status: Literal['gate_list', 'close']`,
  `gates: list[RouteGate] = []`, `balancing_type: str | None = None`, `reason: str | None = None`,
  `shadow: bool = False`). Remove `RouteDecisionResponse` (`:76-83`) and `RouteOutcomeRequest`
  (`:95-110`). Update the section comment above the old `RouteDecisionResponse` (`:52-53`,
  currently says "one gate ID back per decision, or a close instruction — this is the real
  integration contract") to describe the new list contract instead.
- **PATTERN**: `schemas.py:120-149` (`RouteBackfillRequest`/`Response`) for field style; existing
  `RouteDecisionResponse:76-83` for the doc-comment convention above each class.
- **IMPORTS**: `Literal` from `typing`, `BaseModel` from `pydantic` — both already imported at
  the top of the file, no new imports needed.
- **GOTCHA**: `gates` defaults to `[]` for the `close` case — don't make it `None`; the spec's
  `close` example explicitly shows `"gates": []`, not omitted or null.
- **VALIDATE**: `python -c "from backend.online.serving.data_models.schemas import RouteStartResponse, RouteGate; print(RouteStartResponse(correlation_id='x', status='gate_list', gates=[RouteGate(position=1, gate_id=1, processor='p')], balancing_type='chain_by_sequence').model_dump_json())"`

### UPDATE `backend/online/routing/live_request/cascade_decision/pne.py` — constant rename

- **IMPLEMENT**: `MAX_ATTEMPTS = 3` (`:47`) → `MAX_POSITIONS = 3`. Update every reference in the
  file (`:295`, `:543` — both inside code being deleted anyway, but grep to confirm nothing
  survives referencing the old name).
- **VALIDATE**: `grep -rn "MAX_ATTEMPTS" backend/` returns nothing.

### REMOVE dead code from `pne.py`

- **IMPLEMENT**: Delete `_next_gate_after_skip` (`:276-324`), `_handle_not_attempted`
  (`:327-346`), `_handle_error` (`:349-371`), `_replay_resolved_attempt` (`:374-397`), `outcome()`
  (`:455-570`), `_pick_retry_processor` (`:184-238`). Keep `_file_gate_alert` (`:241-273`) — it's
  a generic alert-filing helper, not exclusively tied to the deleted functions (re-check its only
  callers were inside `_handle_not_attempted`/`_handle_error` — if so, it becomes genuinely dead
  too; delete it if nothing else calls it after the above removals).
- **GOTCHA**: `_file_gate_alert`'s only callers in the current file are `_handle_not_attempted`
  (`:341`) and `_handle_error` (`:366`) — both deleted. Confirm via grep before deciding whether
  to keep or delete it; per repo convention, dead code gets deleted, not stubbed.
- **VALIDATE**: `python -c "import ast; ast.parse(open('backend/online/routing/live_request/cascade_decision/pne.py').read())"` (confirms no syntax errors after deletion) followed by `grep -n "_pick_retry_processor\|_next_gate_after_skip\|_handle_not_attempted\|_handle_error\|_replay_resolved_attempt" backend/online/routing/live_request/cascade_decision/pne.py` returning nothing.

### ADD `_pick_list_processor` to `pne.py`

- **IMPLEMENT**: New function, signature mirrors the deleted `_pick_retry_processor` minus the
  decline-specific inputs:
  ```python
  def _pick_list_processor(
      router, tx: dict, candidates: list[dict], position: int, cfg: dict, now,
  ) -> dict | None:
  ```
  Body: same shape as the old `_pick_retry_processor` (`build_shared_features` once, loop
  candidates computing `p_model_proxy` via `score_processor` wrapped in try/except, call
  `decline_recovery.recovery_probability(router._db, decline_recovery.ANY, decline_recovery.ANY,
  decline_recovery.ANY, c['processor'], position, p_model_proxy, cfg)`, then the same
  capacity-admission-bar survivor filter, then `max(survivors, key=lambda c: c['_p_recover'])`).
  Returns just the winning dict (no `should_retry` EV gate — see NOTES for why this is dropped).
- **PATTERN**: `pne.py:184-238` (the function being replaced) — copy the loop/survivor-filter
  structure, change only the `recovery_probability` call's first three arguments to
  `decline_recovery.ANY` and drop the final `should_retry` check + its `(processor, p_recover)`
  tuple return (return just `dict | None`, not a tuple, since nothing needs `p_recover` anymore
  once there's no EV gate to feed it).
- **IMPORTS**: `decline_recovery` already imported at `pne.py:38`. `build_shared_features` already
  imported at `:40`. `score_processor` already imported at `:41`.
- **GOTCHA**: `decline_recovery.ANY` is `'*'` (`decline_recovery.py:54`) — pass the module
  constant, don't hardcode the string, in case it ever changes.
- **VALIDATE**: covered by the manual `/route/start` validation in Phase 5 (no unit test per
  decision) — confirm positions 2/3 in a real `gates[]` response differ sensibly from position 1
  and from each other (no duplicate processor across positions).

### REWRITE `start()` in `pne.py`

- **IMPLEMENT**: New `start(router, req: dict) -> dict`:
  1. Same idempotency check as today (`cascade_session.prior_rows`), but replay the **full**
     list instead of just attempt 1: if `prior` is non-empty, and `prior[0]['gate_id'] is None`,
     replay the close response from `prior[0]['close_reason']`; otherwise reconstruct
     `gates = [{'position': r['attempt_number'], 'gate_id': r['gate_id'], 'processor':
     r['processor']} for r in prior if r['gate_id'] is not None]`, sorted by `attempt_number`
     (already guaranteed by `prior_rows`' `ORDER BY attempt_number`), and return a `gate_list`
     response built from it.
  2. Same tx snapshot / merchant lookup / shadow lookup / country-currency close check /
     wallet short-circuit as today (`:417-444`), EXCEPT the wallet branch now wraps its single
     gate as a 1-entry list (`gates=[{'position': 1, ...}]`, `balancing_type='chain_by_sequence'`)
     instead of the old single-gate response, and still calls `cascade_session.insert_attempt`
     once for that one row.
  3. For the card-cascade case: loop `position in range(1, MAX_POSITIONS + 1)`, maintaining an
     `exclude` set (starts empty). Each iteration: `_eligible_candidates(router, tx, segment,
     position, merchant_id, tx['currency'], exclude, cfg)`; if empty, `break` (list ends here —
     "fewer than three is valid," per spec). If `position == 1`: `_select_gate(...)` (unchanged
     call). Else: `_pick_list_processor(router, tx, candidates, position, cfg, now)`. If the
     winner is `None`, `break`. Otherwise append `{'position': position, 'gate_id':
     winner['gate_id'], 'processor': winner['processor']}` to the result list, add
     `winner['processor']` to `exclude`, and call `cascade_session.insert_attempt(router._db,
     correlation_id, position, tx, winner['gate_id'], winner['processor'])` for that row.
  4. If the resulting list is empty (position 1 itself found no candidate), close with
     `no_eligible_gate` — same as today's `winner is None` branch (`:448-449`), just without
     retrying at other positions.
  5. Otherwise return `{'correlation_id': ..., 'status': 'gate_list', 'gates': [...],
     'balancing_type': 'chain_by_sequence', 'reason': None, 'shadow': shadow}`.
- **PATTERN**: `pne.py:400-452` (current `start()`) for the setup steps (tx snapshot, merchant
  lookup, country-currency check) — unchanged, just the tail end (candidate selection → response)
  is new.
- **IMPORTS**: No new imports — everything used (`_eligible_candidates`, `_select_gate`,
  `_pick_list_processor`, `cascade_session`, `gates`, `lookup_currency`, `segments`) is already
  imported or defined in this file.
- **GOTCHA #1**: `_close_response`/`_gate_response` (`:82-90`) are shaped for the OLD one-gate
  contract (`attempt`, `gate_id`, `processor` at the top level). Replace them with new helpers
  (or inline dict construction) matching `RouteStartResponse`'s shape — don't try to reuse the
  old ones as-is, since the field set genuinely differs (no `attempt`, `gates` is a list).
- **GOTCHA #2**: the idempotent-replay path must handle the wallet case too — a replayed wallet
  transaction's `prior` will have exactly one row with a non-null `gate_id`; the generic
  "reconstruct from prior rows" logic in step 1 already handles this correctly without a special
  case, since it doesn't care how many rows exist, just that `gate_id` is non-null.
- **GOTCHA #3**: capacity admission-bar sequencing (user decision: simulate sequentially) means
  `_pick_list_processor` for position 3 must see position 2's pick already in `exclude` — this
  falls out naturally from the loop structure above (exclude is mutated after each position), but
  double-check `_eligible_candidates`' rate-limit/circuit-breaker checks (`:127-137`) are also
  being freshly evaluated per position (they already are, since `_eligible_candidates` is called
  fresh each loop iteration) — no stale-candidate-pool bug to introduce here.
- **VALIDATE**: manual `/route/start` call (Phase 5) — inspect the returned `gates[]` for
  correct `position` values (1, 2, 3 contiguous, no gaps), no duplicate `processor` across
  positions, and a repeat call with the same `correlation_id` returning byte-identical JSON.

### UPDATE `backend/online/serving/transaction_routing/routes.py`

- **IMPLEMENT**: Update `route_start` (`:41-56`) to import and return `RouteStartResponse`
  instead of `RouteDecisionResponse`. Delete `route_outcome` (`:61-78`) entirely, including its
  docstring and the blank lines around it.
- **PATTERN**: Keep the exact try/except → `logger.exception` → `HTTPException(500, ...)` shape
  at `:46-50` unchanged — this is the strict contract `CLAUDE.md` mandates for PNE-facing
  endpoints.
- **IMPORTS**: Update the `from backend.online.serving.data_models.schemas import (...)` block
  (`:24-33`): remove `RouteDecisionResponse`, `RouteOutcomeRequest`; add `RouteStartResponse`.
- **GOTCHA**: `route_start`'s db-timing log line (`:52-55`) references `req.correlation_id` —
  unaffected, `RouteStartRequest` is unchanged.
- **VALIDATE**: `python -c "import backend.online.serving.transaction_routing.routes"` (import
  succeeds with no `route_outcome`/`RouteDecisionResponse` references left).

### UPDATE `backend/online/serving/service.py`

- **IMPLEMENT**: Remove `route_outcome` from the `transaction_routing.routes` import block
  (`:54-61`). Remove `RouteDecisionResponse` from the `data_models.schemas` import block
  (`:62-69`); add `RouteStartResponse`. Remove line 96
  (`app.post("/route/outcome", response_model=RouteDecisionResponse)(route_outcome)`). Update
  line 95 to `app.post("/route/start", response_model=RouteStartResponse)(route_start)`. Update
  the comment at `:93-94` (currently "one gate ID back per decision, or a close instruction") to
  describe the new list contract.
- **PATTERN**: `:89-91` (the `/health`, `/version`, `/rate-limits` registrations) for the
  one-line-per-route registration style.
- **VALIDATE**: `uvicorn backend.online.serving.service:app --port 8080` starts without error;
  `curl -s http://localhost:8080/health` returns 200; `curl -s -X POST
  http://localhost:8080/route/outcome -d '{}'` returns 404 (route no longer exists).

### UPDATE `backend/online/routing/router.py`

- **IMPLEMENT**: Delete `route_outcome` (`:94-95`). Update the comment above `route_start`
  (`:87-90`, currently references "one gate ID back per decision, or a close instruction") to
  match the new contract.
- **VALIDATE**: `grep -n "route_outcome" backend/online/routing/router.py` returns nothing.

### REMOVE `decline_recovery.should_retry`

- **IMPLEMENT**: Delete `should_retry` (`decline_recovery.py:217-222`) once confirmed unused.
- **PATTERN**: n/a (deletion only).
- **GOTCHA**: Grep the whole `backend/` tree first — `should_retry` might be referenced from an
  offline evaluation/backtest script (`backend/offline/evaluation/`) that simulates the old live
  retry economics; if so, leave it and note why in a comment rather than deleting blindly.
- **VALIDATE**: `grep -rn "should_retry" backend/` — if the only remaining hits are inside
  `decline_recovery.py`'s own now-deleted definition, the deletion is safe. If offline code still
  references it, do not delete; flag it in the PR description instead.

---

## TESTING STRATEGY

Per user decision: **manual/scripted validation only**, matching `CLAUDE.md`'s documented honest
state (no real unit coverage of `backend/online/` today; adding a new non-stdlib test file would
require also adding a `pip install` step to `.gitea/workflows/ci-cd-workflow.yaml`, which is out
of scope for this change).

### Unit Tests

None added. `python -m unittest -v` must still pass (it only covers
`tests/test_smoke.py`'s `classify_description` assertions, untouched by this change).

### Integration Tests

None added (no CI harness exists for this path).

### Edge Cases (validate manually, see Level 4 below)

- Correlation-id idempotency: repeat `/route/start` call with the same `correlation_id` returns
  the exact same `gates[]` (byte-identical), not a recomputed list.
- Fewer than 3 eligible processors: list length is 1 or 2, no padding, contiguous positions from
  1.
- `unmapped_country` / `no_eligible_gate` close paths still work exactly as before.
- Wallet transaction (`wallet_type: apple_pay` or `google_pay`): exactly 1 entry in `gates[]`.
- Shadow-mode merchant: `shadow: true` on the response, list-building logic otherwise unaffected
  (shadow only affects `_file_gate_alert`, which no longer exists in the live path anyway).
- No duplicate `processor` across positions in the same list.
- A merchant with a `pin` hard rule: position 1 respects the pin (existing `_eligible_candidates`
  behavior, unchanged); confirm positions 2/3 correctly exclude the pinned processor if it was
  used at position 1, or correctly fall through if the pin was unusable.

### E2E / Browser Automation

**Not applicable.** This is a backend-only API contract change with no UI surface — PayNet Easy
is the only consumer, and it isn't a browser client. The `agent-browser` skill and Level 5 section
below are skipped for this change; do not fabricate a browser flow for an API-only feature.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

No linter/formatter/type-checker is configured in this repo (`CLAUDE.md`) — don't invent one.
Sanity-check with:
```bash
python -c "import ast; ast.parse(open('backend/online/routing/live_request/cascade_decision/pne.py').read())"
python -c "import backend.online.serving.service"
```

### Level 2: Unit Tests

```bash
python -m unittest -v
```
Must pass with zero failures (only exercises `tests/test_smoke.py`, unrelated to this change but
must not regress).

### Level 3: Integration Tests

None exist for this path — skipped.

### Level 4: Manual Validation

```bash
# Start the service locally (see CLAUDE.md's Docker/uvicorn instructions, or:)
uvicorn backend.online.serving.service:app --host 0.0.0.0 --port 8080

# In another shell:
BASE_URL=http://localhost:8080 python -m tests.manual_client
# Update TRANSACTIONS in tests/manual_client.py first if it still assumes the old
# start -> outcome loop's interactive prompt flow — check its current shape before running,
# since it's explicitly documented as exercising "/route/start + /route/outcome" (LP-235's
# territory to fix properly; for THIS ticket, a raw curl call is safer than trusting the script
# still works end-to-end):
curl -s -X POST http://localhost:8080/route/start -H 'Content-Type: application/json' -d '{
  "correlation_id": "<uuid>", "merchant": "Qbet Alt", "bin": "414720",
  "masked_card": "414720******1234", "bin_country": "NL", "ip_country": "NL",
  "card_type": "Visa", "currency": "EUR", "tx_type": "purchase", "is_3d": false, "amount": 49.99
}' | python -m json.tool
# Repeat the exact same call again with the same correlation_id -> confirm identical output.
```

### Level 5: E2E / Browser Automation

N/A — see above.

### Level 6: Additional Validation

None applicable (no relevant MCP servers for this change).

---

## ACCEPTANCE CRITERIA

- [ ] `/route/start` returns `gates[]` (1-3 positions, contiguous, `{position, gate_id,
      processor}`) + `balancing_type: "chain_by_sequence"` on success, or `status: "close"` +
      `reason` + `gates: []` when nothing is eligible.
- [ ] `/route/outcome` no longer exists (404).
- [ ] Repeat `/route/start` calls for the same `correlation_id` replay the stored list exactly,
      never recompute it.
- [ ] Wallet transactions return a 1-entry list, matching today's deterministic single-gate
      behavior.
- [ ] `python -m unittest -v` passes.
- [ ] No dead code left behind: `_pick_retry_processor`, `_next_gate_after_skip`,
      `_handle_not_attempted`, `_handle_error`, `_replay_resolved_attempt`,
      `decline_recovery.should_retry` (if confirmed unused elsewhere) are all deleted, not
      stubbed.
- [ ] `RouteDecisionResponse`/`RouteOutcomeRequest` removed from `schemas.py`; `RouteStartResponse`
      added and used.
- [ ] Manual validation (Level 4) performed and its output attached to the PR description.

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task's validation command run and passed
- [ ] `python -m unittest -v` passes
- [ ] No leftover references to `MAX_ATTEMPTS`, `route_outcome`, `RouteDecisionResponse`,
      `RouteOutcomeRequest` anywhere in `backend/`
- [ ] Manual validation (Level 4) performed against a locally running instance
- [ ] LP-231 and LP-232 both updated/closed in Jira with a note that they landed together
- [ ] LP-234 revisited — likely reduced to a doc/enum-comment-only ticket now that the code
      branches producing `hard_decline`/`exhausted`/`ev_negative` are deleted as part of this
      change
- [ ] `.claude/context/pne-cascade-engine.md` left untouched (explicitly out of scope — LP-235)
- [ ] Code reviewed for quality and maintainability

---

## NOTES

**Dropping the EV gate (`should_retry`) for positions 2/3 is a real behavior change, not just
plumbing.** Today, a retry only happens if `p_recover * deposit_value_usd` beats the attempt fee +
issuer-health cost — an EV-negative retry closes early (`ev_negative`) instead of burning a
low-odds attempt. Under the new model, list length is driven purely by candidate *eligibility*
(the spec: "A list may hold fewer than three gates if fewer processors are currently eligible for
this lane" — eligibility, not expected value). This plan drops the EV gate entirely for
list-building, meaning a low-value retry that would have been skipped today now always appears at
position 2/3 if a candidate is technically eligible. This is the most consequential unilateral
call in this plan — flag it explicitly in the PR description so it gets real scrutiny in review,
and consider mentioning it to PayNet Easy alongside the LP-230 hard-decline question, since it's
the same underlying tension (no live economic judgment possible once the list is fixed upfront).

**The marginal `(ANY, ANY, ANY)` decline-recovery lookup is a genuine, working reuse of existing
infrastructure — not a stub.** It's tempting to read "LP-232: redesign decline_recovery" as
requiring new tables or a new model. It doesn't: `decline_recovery_stats`/`_history` already
aggregate a fully-marginal row (ignoring declining processor, decline code, AND decline class)
as the coarsest fallback level in today's live retry path. This plan just enters that hierarchy at
the top instead of the bottom. If this turns out to perform poorly once shipped (marginalizing
away *which processor is at position 1* may lose real signal — e.g., processor A's declines
recover differently than processor B's, in aggregate, even without knowing the specific code),
the next iteration could add a `(declining_processor, ANY, ANY)` level to the hierarchy and start
writing to it in `record_outcome`. Not needed for this plan; noted for whoever picks this up next.

**No production deployment risk**: the old `/route/start` + `/route/outcome` architecture is not
running in production today — this ships as the first production version of the PNE integration,
not a live cutover of real traffic. There's no in-flight-transaction concern, no dual-running
window, and no need to sequence this with PayNet Easy beyond the ordinary "here's our new
integration, go live when ready" handoff. This also reinforces the "hard cutover, delete
`outcome()` entirely" decision — there's nothing running today that a backwards-compatibility
shim would need to protect.

**Wallet fallback lists**: LP-236 tracks asking PayNet Easy directly; this plan's 1-entry-list
interim doesn't block on their answer.
