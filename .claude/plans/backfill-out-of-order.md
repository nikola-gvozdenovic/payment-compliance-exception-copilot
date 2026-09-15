# Feature: Backfill Out-of-Order & Duplicate Handling (LP-233)

The following plan should be complete, but it's important to validate documentation and codebase
patterns and task sanity before implementing. Pay special attention to naming of existing utils,
types, and models — import from the right files.

## Feature Description

`/route/backfill` is the only path attempt outcomes flow through now that LP-231/232 replaced
PayNet Easy's live per-attempt loop with the upfront gate-list model. PNE reports each position's
real outcome "on any schedule that suits PNE" — immediately, batched, or end-of-day — which means
reports can arrive **out of order** (position 3 before position 2) or, in principle, **duplicated**
(the same report sent twice, e.g. after a network timeout). This ticket makes `pne.backfill()`
correct under both conditions.

## User Story

As PayNet Easy's integration,
I want to report attempt outcomes in whatever order and cadence suits my system,
So that I never have to guarantee delivery ordering or exactly-once delivery just to keep
SmartRouting's learning models accurate.

## Problem Statement

Two real gaps exist in the current `backfill()` (confirmed unchanged since the LP-231/232 merge —
`git diff 978e4e3 5a1289d -- .../pne.py` shows zero delta on this function):

1. **Out-of-order reports silently lose a learning signal.** `decline_recovery` teaching
   ("did switching from processor A's decline to processor B work?") only fires when the
   *immediately preceding* position's row is already resolved at the moment the current report is
   processed. If position 3's report arrives before position 2's, that specific 2→3 teaching
   signal never fires — no crash, no error, just quietly lost forever.
2. **Duplicate reports double-count everything.** There is no check for "has this attempt already
   been resolved?" before running the learning fan-out. A resent report re-runs
   `router.record_usage` (double-counts against the processor's real daily rate limit),
   `bandit.record_outcome`, `circuit_breaker.record_outcome`, `decline_recovery.record_outcome`,
   and `outcomes_log.record` (a duplicate audit-log row) — all silently, all wrong.

## Solution Statement

- **Duplicate detection**: fetch `cascade_session.prior_rows` once, at the very top of `backfill()`,
  before doing anything else. If the row for this `attempt_number` already has a non-null
  `outcome`, this is a duplicate report — log it and return the ack immediately, skipping every
  side effect (lane lookup, `insert_attempt`, the whole learning fan-out, `outcomes_log.record`).
- **Forward teaching (unchanged behavior, kept)**: if the preceding position is already resolved
  as a decline when this report is processed, teach the transition exactly as today.
- **Backward/retroactive teaching (new)**: when a decline resolves, also check whether the
  *following* position's row is already resolved (meaning its own backfill report arrived
  earlier and missed its chance to be taught against this decline). If so, fire
  `decline_recovery.record_outcome` for that transition now, using the same fields in reversed
  roles. This and the forward path are mutually exclusive by construction — see NOTES for why
  no transition can ever be taught twice.
- **Logging**: log a line whenever forward teaching is deferred (predecessor not ready yet) and
  whenever a backward/retroactive teach actually recovers one of those deferred signals — gives
  ops visibility into how often out-of-order reports actually happen in practice.
- The single `prior_rows` fetch at the top is reused for the duplicate check, the forward-teaching
  lookup, and the backward-teaching lookup — no redundant DB round-trips added.

## Feature Metadata

**Feature Type**: Bug fix / robustness hardening
**Estimated Complexity**: Low–Medium (one function rewritten, no schema change, no new endpoint)
**Primary Systems Affected**: `backend/online/routing/live_request/cascade_decision/pne.py`
(`backfill()` only)
**Dependencies**: None new — reuses `cascade_session`, `decline_recovery`, `bandit`,
`circuit_breaker`, `outcomes_log`, all already imported in `pne.py`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `backend/online/routing/live_request/cascade_decision/pne.py` `:330-388` — the current
  `backfill()` in full (quoted below for exact reference). This is the only function being
  changed.
  ```python
  def backfill(router, req: dict) -> dict:
      """Records a transaction PNE handled entirely on its own — via PNE's own
      routing (used while SmartRouting was unreachable, or for a shadow-mode
      merchant) — after the fact. Bookkeeping/learning only, never a routing
      decision: no gate
      is computed or returned, PNE already resolved this attempt itself. Feeds
      the exact same real-outcome signals a live /route/outcome call would
      have (decline-recovery teaching if a real prior decline exists,
      record_usage, bandit, circuit breaker), so our approval-rate learning
      and daily rate-limit counts don't silently drift from reality just
      because we were unreachable for part of this transaction's cascade."""
      correlation_id = req['correlation_id']
      attempt_number = req['attempt_number']
      processor = req['processor']
      reported_outcome = req['outcome']
      decline_code = req.get('decline_code')
      approved = reported_outcome == 'approved'
      cfg = load_config(router._db)

      tx = _tx_snapshot(req)
      merchant_id = gates.get_or_create_merchant(router._db, tx['merchant'])
      shadow = gates.is_shadow(router._db, merchant_id)
      segment = segments.segment_key(tx)
      amount_usd = _deposit_value_usd(router, tx)

      lane = gates.eligible_processors_for_lane(router, merchant_id, tx['currency'])
      gate = next((g for g in lane if g['processor'] == processor), None)
      gate_id = gate['gate_id'] if gate else None

      cascade_session.insert_attempt(router._db, correlation_id, attempt_number, tx, gate_id, processor)

      prior = cascade_session.prior_rows(router._db, correlation_id)
      if attempt_number > 1:
          previous = next((r for r in prior if r['attempt_number'] == attempt_number - 1), None)
          if previous is not None and previous.get('decline_code') and previous.get('processor'):
              _, prev_class = decline_recovery.classify(router._db, previous['decline_code'])
              decline_recovery.record_outcome(
                  router._db, previous['processor'], previous['decline_code'], prev_class,
                  processor, attempt_number, approved, cfg,
              )

      router.record_usage(processor)
      bandit.record_outcome(router._db, processor, segment, attempt_number, approved, cfg)
      circuit_breaker.record_outcome(router._db, processor, segment, attempt_number, approved, cfg)
      if circuit_breaker.is_tripped(router._db, processor, segment, attempt_number, cfg):
          circuit_breaker.file_trip_alert(router._db, processor, segment, attempt_number)

      if approved:
          cascade_session.resolve_attempt(router._db, correlation_id, attempt_number, 'approved')
      else:
          cascade_session.resolve_attempt(router._db, correlation_id, attempt_number, 'declined', decline_code=decline_code)

      outcomes_log.record(
          router._db, correlation_id, merchant_id, gate_id, processor, segment,
          attempt_number, decline_code, approved, amount_usd, shadow,
          bin_value=tx.get('bin', ''), masked_card=tx.get('masked_card', ''),
      )

      return {'correlation_id': correlation_id, 'attempt': attempt_number, 'recorded': True}
  ```

- `backend/online/routing/live_request/cascade_decision/cascade_session.py` (whole file, 57
  lines, **no changes needed**) — `prior_rows(pool, correlation_id)` returns every row for a
  correlation_id, oldest first, each with `attempt_number`, `tx_snapshot`, `gate_id`, `processor`,
  `decline_code`, `outcome`, `close_reason`. `outcome` is `None` until `resolve_attempt` sets it —
  this is exactly the field the duplicate check reads. `insert_attempt` is
  `ON CONFLICT (correlation_id, attempt_number) DO NOTHING` — already idempotent for the *row*,
  just not for the *side effects*, which is what this ticket fixes.

- `backend/online/routing/live_request/live_learning/decline_recovery.py`:
  - `:62-80` `classify(pool, decline_code, decline_reason=None) -> (is_hard, decline_class)` —
    used for both forward and backward teaching. Note: `cascade_sessions` rows never store
    `decline_reason` (see `cascade_session.py:18`'s `_COLS`), only `decline_code` — so both the
    existing forward call and the new backward call correctly omit `decline_reason`, matching
    existing behavior, not a new limitation.
  - `:225-247` `record_outcome(pool, declining_processor, decline_code, decline_class,
    candidate_processor, cascade_slot, approved, cfg)` — called for both forward and backward
    teaching, just with the "declining" and "candidate" roles swapped for the backward case.

- `backend/online/routing/live_request/live_learning/bandit.py`, `circuit_breaker.py` — unchanged,
  reused exactly as today.

### New Files to Create

None.

### Patterns to Follow

**Duplicate/replay detection**: mirrors the exact idiom the old `outcome()` used before it was
deleted in LP-231/232 — `_replay_resolved_attempt` checked `current['outcome'] is not None` to
detect an already-resolved attempt and short-circuit rather than reprocess. This plan reuses that
same check (`current['outcome'] is not None`), just for `backfill()` instead.

**Structured per-subsystem logging**: `logger = logging.getLogger("smartrouting.pne")` already at
`pne.py:45` (unchanged) — reuse it for the three new `logger.info(...)` calls (duplicate detected,
teaching deferred, teaching recovered). Match the existing style: plain `%r`-formatted args, no
f-strings in log calls (see every existing `logger.warning`/`logger.exception` call in this file).

**Isolate-and-degrade**: none of this touches scoring/model code, so the existing
`try/except Exception: logger.exception(...)` pattern isn't directly relevant here — no new
try/except needed, since every operation in `backfill()` is a straightforward DB write, not a
model inference call.

---

## STEP-BY-STEP TASKS

### UPDATE `backend/online/routing/live_request/cascade_decision/pne.py` — rewrite `backfill()`

- **IMPLEMENT**: Replace the function body (keep the `def backfill(router, req: dict) -> dict:`
  signature) with:
  ```python
  def backfill(router, req: dict) -> dict:
      """Records a transaction PNE handled entirely on its own — via PNE's own
      routing (used while SmartRouting was unreachable, or for a shadow-mode
      merchant), OR reporting one position's real outcome from the gate list
      /route/start returned — after the fact. Bookkeeping/learning only,
      never a routing decision: no gate is computed or returned. PNE may call
      this "on any schedule that suits PNE" (spec) — out of order, batched,
      or with gaps — so this must tolerate all three without losing a
      learning signal or double-counting a report:

      - Duplicate reports (same attempt_number, already resolved) are
        detected up front and skip the entire learning fan-out — otherwise
        a resent report would double-count against the processor's real
        daily rate limit, the bandit/circuit-breaker posteriors, and the
        outcomes_log audit trail.
      - decline_recovery teaching normally fires "forward" (this outcome
        teaches the transition from the immediately preceding decline, if
        that position is already resolved). If reports arrive out of order
        and the preceding position isn't resolved yet, that teaching is
        deferred rather than lost: once the preceding position DOES
        resolve (via a later call), it checks "backward" whether the
        following position already resolved without being taught, and
        recovers that signal then. Forward and backward paths are mutually
        exclusive for any given transition — see pne-cascade-engine.md /
        the LP-233 plan for why neither can double-fire."""
      correlation_id = req['correlation_id']
      attempt_number = req['attempt_number']
      processor = req['processor']
      reported_outcome = req['outcome']
      decline_code = req.get('decline_code')
      approved = reported_outcome == 'approved'

      prior = cascade_session.prior_rows(router._db, correlation_id)
      current = next((r for r in prior if r['attempt_number'] == attempt_number), None)
      if current is not None and current['outcome'] is not None:
          logger.info(
              "Duplicate backfill report for correlation_id=%r attempt_number=%r — "
              "already resolved, skipping learning fan-out",
              correlation_id, attempt_number,
          )
          return {'correlation_id': correlation_id, 'attempt': attempt_number, 'recorded': True}

      cfg = load_config(router._db)
      tx = _tx_snapshot(req)
      merchant_id = gates.get_or_create_merchant(router._db, tx['merchant'])
      shadow = gates.is_shadow(router._db, merchant_id)
      segment = segments.segment_key(tx)
      amount_usd = _deposit_value_usd(router, tx)

      lane = gates.eligible_processors_for_lane(router, merchant_id, tx['currency'])
      gate = next((g for g in lane if g['processor'] == processor), None)
      gate_id = gate['gate_id'] if gate else None

      cascade_session.insert_attempt(router._db, correlation_id, attempt_number, tx, gate_id, processor)

      if attempt_number > 1:
          previous = next((r for r in prior if r['attempt_number'] == attempt_number - 1), None)
          if previous is not None and previous.get('decline_code') and previous.get('processor'):
              _, prev_class = decline_recovery.classify(router._db, previous['decline_code'])
              decline_recovery.record_outcome(
                  router._db, previous['processor'], previous['decline_code'], prev_class,
                  processor, attempt_number, approved, cfg,
              )
          else:
              logger.info(
                  "Deferred decline_recovery teaching for correlation_id=%r attempt_number=%r — "
                  "predecessor not yet resolved (out-of-order report)",
                  correlation_id, attempt_number,
              )

      router.record_usage(processor)
      bandit.record_outcome(router._db, processor, segment, attempt_number, approved, cfg)
      circuit_breaker.record_outcome(router._db, processor, segment, attempt_number, approved, cfg)
      if circuit_breaker.is_tripped(router._db, processor, segment, attempt_number, cfg):
          circuit_breaker.file_trip_alert(router._db, processor, segment, attempt_number)

      if approved:
          cascade_session.resolve_attempt(router._db, correlation_id, attempt_number, 'approved')
      else:
          cascade_session.resolve_attempt(router._db, correlation_id, attempt_number, 'declined', decline_code=decline_code)
          next_row = next((r for r in prior if r['attempt_number'] == attempt_number + 1), None)
          if next_row is not None and next_row.get('outcome') is not None and next_row.get('processor'):
              _, this_class = decline_recovery.classify(router._db, decline_code or '')
              decline_recovery.record_outcome(
                  router._db, processor, decline_code, this_class,
                  next_row['processor'], next_row['attempt_number'], next_row['outcome'] == 'approved', cfg,
              )
              logger.info(
                  "Recovered a deferred decline_recovery signal for correlation_id=%r "
                  "(attempt %r -> %r, out-of-order arrival)",
                  correlation_id, attempt_number, next_row['attempt_number'],
              )

      outcomes_log.record(
          router._db, correlation_id, merchant_id, gate_id, processor, segment,
          attempt_number, decline_code, approved, amount_usd, shadow,
          bin_value=tx.get('bin', ''), masked_card=tx.get('masked_card', ''),
      )

      return {'correlation_id': correlation_id, 'attempt': attempt_number, 'recorded': True}
  ```
- **PATTERN**: The forward-teaching block is byte-identical to today's logic, just moved to reuse
  the `prior` fetched at the top instead of a second `prior_rows` call — one fewer DB round-trip
  per request than before.
- **IMPORTS**: No new imports — `cascade_session`, `decline_recovery`, `bandit`, `circuit_breaker`,
  `outcomes_log`, `gates`, `segments`, `load_config` are all already imported at the top of
  `pne.py` (`:36-52`, unchanged).
- **GOTCHA #1**: The duplicate check must run **before** `load_config`/`_tx_snapshot`/merchant
  lookup, not after — the whole point is to skip that work too on a duplicate, not just the
  learning fan-out.
- **GOTCHA #2**: The backward-teaching check only makes sense inside the `else` (declined) branch
  — an *approved* current attempt has no `decline_code` of its own to teach a later position
  with, so there's nothing to recover retroactively when the current attempt is an approval.
- **GOTCHA #3**: `next_row['attempt_number']` is used as `cascade_slot` in the backward call — not
  `attempt_number + 1` recomputed — in case a real gap exists (e.g. positions 1 and 3 exist but
  not 2, however that shouldn't happen given `MAX_POSITIONS` sequencing, this is just defensive
  correctness matching the row's own stored value rather than an assumption).
- **VALIDATE**: covered by the manual tests in Phase "Manual Validation" below — no unit test file
  added (see Testing Strategy).

---

## TESTING STRATEGY

Per repeated project decision: **manual/scripted validation only** — no new automated test file
(would require a new `pip install` step in `.gitea/workflows/ci-cd-workflow.yaml`, out of scope;
matches the precedent set on LP-231/232).

### Edge Cases (validate manually, see Validation Commands below)

1. **Normal in-order case** (regression check): position 1 declines, position 2 backfilled next
   and approved — forward teaching must still fire exactly as before.
2. **Out-of-order, teaching deferred then recovered**: position 2 backfilled first (declined),
   then position 1 backfilled (declined) — position 1's backfill call should log "deferred" when
   it was position 2's turn... actually order for this test: backfill position **1** first
   (declined), then backfill position **3** (approved) *before* position 2 exists at all — confirm
   no crash, "deferred" log line appears referencing position 3's own predecessor (position 2,
   which doesn't exist yet). Then backfill position 2 (declined) — confirm the "recovered" log
   line appears, teaching the 2→3 transition retroactively.
3. **Duplicate report**: backfill the same `(correlation_id, attempt_number)` twice with identical
   payload — second call must log "duplicate" and return the same ack, and must NOT double-count
   (verify via `rate_limits` table / `/rate-limits` endpoint that the processor's daily count only
   incremented once).
4. **Shadow/no-start() case**: backfill a `correlation_id` that never had `/route/start` called at
   all (simulating PNE-self-routed traffic) — confirm rows are created purely by backfill calls
   and out-of-order/duplicate handling still works identically (this path shares 100% of the same
   code, so this is really the same test as #2/#3 against a correlation_id with no prior `start()`
   call).

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
python -c "import ast; ast.parse(open('backend/online/routing/live_request/cascade_decision/pne.py').read())"
python -c "import backend.online.routing.live_request.cascade_decision.pne"
```

### Level 2: Unit Tests

```bash
python -m unittest -v
```
Must still pass (only exercises the unrelated `tests/test_smoke.py`).

### Level 3: Integration Tests

None exist for this path — skipped.

### Level 4: Manual Validation

Against a locally running instance (see `.claude/plans/gate-list-response.md`'s setup steps —
`docker compose up db`, seed script, `uvicorn`):

```bash
BASE="http://localhost:8080"
CID="lp233-test-$(date +%s)"

# 1. Normal in-order: position 1 declines, position 2 approves.
curl -s -X POST $BASE/route/backfill -d "{\"correlation_id\":\"$CID\",\"attempt_number\":1,\"processor\":\"Npay Trusted Altitudepay Paytech\",\"outcome\":\"declined\",\"decline_code\":\"51\",\"merchant\":\"Qbet Alt\",\"bin\":\"411111\",\"bin_country\":\"NL\",\"ip_country\":\"NL\",\"card_type\":\"Visa\",\"currency\":\"EUR\",\"tx_type\":\"purchase\",\"is_3d\":false,\"amount\":49.99}" -H 'Content-Type: application/json' | python -m json.tool
curl -s -X POST $BASE/route/backfill -d "{\"correlation_id\":\"$CID\",\"attempt_number\":2,\"processor\":\"test-processor-2\",\"outcome\":\"approved\",\"merchant\":\"Qbet Alt\",\"bin\":\"411111\",\"bin_country\":\"NL\",\"ip_country\":\"NL\",\"card_type\":\"Visa\",\"currency\":\"EUR\",\"tx_type\":\"purchase\",\"is_3d\":false,\"amount\":49.99}" -H 'Content-Type: application/json' | python -m json.tool
# Check server logs — no "deferred" line should appear for attempt 2 here.

# 2. Out-of-order + recovery: NEW correlation_id, attempt 3 first, then attempt 2.
CID2="lp233-test-ooo-$(date +%s)"
curl -s -X POST $BASE/route/backfill -d "{\"correlation_id\":\"$CID2\",\"attempt_number\":3,\"processor\":\"test-processor-3\",\"outcome\":\"approved\",\"merchant\":\"Qbet Alt\",\"bin\":\"411111\",\"bin_country\":\"NL\",\"ip_country\":\"NL\",\"card_type\":\"Visa\",\"currency\":\"EUR\",\"tx_type\":\"purchase\",\"is_3d\":false,\"amount\":49.99}" -H 'Content-Type: application/json'
# Check logs: "Deferred decline_recovery teaching ... attempt_number=3" should appear.
curl -s -X POST $BASE/route/backfill -d "{\"correlation_id\":\"$CID2\",\"attempt_number\":2,\"processor\":\"test-processor-2\",\"outcome\":\"declined\",\"decline_code\":\"51\",\"merchant\":\"Qbet Alt\",\"bin\":\"411111\",\"bin_country\":\"NL\",\"ip_country\":\"NL\",\"card_type\":\"Visa\",\"currency\":\"EUR\",\"tx_type\":\"purchase\",\"is_3d\":false,\"amount\":49.99}" -H 'Content-Type: application/json'
# Check logs: "Recovered a deferred decline_recovery signal ... (attempt 2 -> 3)" should appear.

# 3. Duplicate: resend attempt 2 from test 2 unchanged.
curl -s -X POST $BASE/route/backfill -d "{\"correlation_id\":\"$CID2\",\"attempt_number\":2,\"processor\":\"test-processor-2\",\"outcome\":\"declined\",\"decline_code\":\"51\",\"merchant\":\"Qbet Alt\",\"bin\":\"411111\",\"bin_country\":\"NL\",\"ip_country\":\"NL\",\"card_type\":\"Visa\",\"currency\":\"EUR\",\"tx_type\":\"purchase\",\"is_3d\":false,\"amount\":49.99}" -H 'Content-Type: application/json' | python -m json.tool
# Check logs: "Duplicate backfill report ... attempt_number=2" should appear, and NOT a second
# "recovered"/"deferred" line.
```

### Level 5/6: N/A

Backend-only, no UI, no additional MCP-based validation applicable.

---

## ACCEPTANCE CRITERIA

- [ ] In-order backfill reports behave exactly as before (forward teaching fires, no regressions).
- [ ] An out-of-order report (later position resolved before an earlier one) does not crash and
      logs a "deferred" line.
- [ ] Once the earlier position resolves, the deferred decline_recovery signal is taught and a
      "recovered" line is logged.
- [ ] A duplicate report (same correlation_id + attempt_number, already resolved) is detected,
      logged, and skips the entire learning fan-out — verified via `record_usage`'s daily count
      not incrementing twice.
- [ ] `python -m unittest -v` passes.
- [ ] All four manual validation scenarios above produce the expected log lines and DB state.

## COMPLETION CHECKLIST

- [ ] `backfill()` rewritten per the Step-by-Step Tasks section
- [ ] Manual validation (all 4 scenarios) run against a local instance, log output confirmed
- [ ] `python -m unittest -v` passes
- [ ] LP-233 updated/closed in Jira with a summary of what changed
- [ ] Code reviewed for quality and maintainability

---

## NOTES

**Why forward and backward teaching can never double-fire for the same transition**: forward
teaching (inside the block handling position N+1's report) only fires if position N is *already*
resolved at that moment. Backward teaching (inside the block handling position N's report) only
fires if position N+1 is *already* resolved at that moment. For any given pair (N, N+1), exactly
one of "N resolves before N+1" or "N+1 resolves before N" is true — so exactly one of the two paths
finds its condition satisfied, never both. The only theoretical exception is two concurrent
requests racing on the same pair, which this design does not defend against (no row locking) —
consistent with the rest of this module, which has no transactional wrapping across its
multi-step fan-out either. Not worth solving here; flagging it as a known, accepted limitation
matching the codebase's existing risk posture, not a new one introduced by this change.

**Duplicate detection is keyed on "already resolved," not on exact payload match**: if PNE somehow
sent two *different* outcomes for the same `(correlation_id, attempt_number)` (a genuine data
inconsistency on their side, not a benign retry), the second one is silently dropped rather than
flagged. This mirrors the old `outcome()`'s `_replay_resolved_attempt` behavior exactly (replay,
don't reprocess) — consistent with existing precedent, not a new tradeoff introduced here. If this
ever needs to be distinguished (retry vs. genuine correction), that's a separate, larger design
question outside this ticket's scope.
