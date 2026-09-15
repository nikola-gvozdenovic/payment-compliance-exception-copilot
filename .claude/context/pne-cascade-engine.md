# PNE cascade engine

On-demand context for anything under `backend/online/routing/` — especially
`live_request/` and `router.py`. Load this before touching the live routing decision
path.

---

## What this is

PayNet Easy (PNE) gets the **whole cascade decided up front**: one call computes an
ordered `gates[]` list (1-3 positions) or a close instruction, and PNE walks that list
entirely on its own side — there is no call back to SmartRouting between attempts
(`pne.py:1-31`, the Gate List API v2; see `docs/Gate_List_API_Spec_Balance.pdf`). This
replaced an earlier one-attempt-at-a-time contract (`start`/`outcome`/`backfill`,
LP-231/232) — the old per-attempt `outcome()` entry point and its EV-gated live retry
logic no longer exist.

Two public entry points, both in `pne.py`:

- `start(router, req)` — computes the entire gate list (or closes) in one pass.
- `backfill(router, req)` — bookkeeping/learning only, for a transaction PNE resolved
  entirely on its own (service unreachable, shadow mode) **or** for reporting one
  position's real outcome from a list `start()` already returned. Never computes a
  gate.

`MAX_POSITIONS = 3` (`pne.py:56`) caps list length.

## Flow

**`start()`** (`pne.py:252-327`): idempotency check via `cascade_session.prior_rows`
(replay the stored list for a repeat call on the same `correlation_id`, rather than
recomputing it) → country/currency validation (`lookup_currency`) →
`segments.segment_key(tx)` → wallet-type short-circuit (`_wallet_gate`, deterministic
first-eligible-gate, no bandit, `pne.py:105-111,295-306`) → loop over positions 1..3:
`_eligible_candidates` (gates + hard_rules + network rules + circuit breaker + rate
limits, excluding processors already used earlier in *this* list) → `_select_gate`
(position 1, general bandit) or `_pick_list_processor` (positions 2/3, decline-recovery
ranking) → `cascade_session.insert_attempt` → append to `gate_list`. The loop stops
(not an error) as soon as a position has no eligible candidates or every remaining
candidate fails its own capacity admission bar — a list shorter than 3 just means
fewer processors were eligible for this lane.

Only two close reasons are reachable from the live path today: `unmapped_country`
(BIN country doesn't map to the tx currency) and `no_eligible_gate` (empty list, or no
wallet gate for a tokenized-wallet tx). `RouteStartResponse.reason`'s other enum values
— `hard_decline`, `exhausted`, `ev_negative` — are dead: legacy values from the deleted
per-attempt retry loop, kept only so old client code switching on this field doesn't
need a new case (`backend/online/serving/data_models/schemas.py:96-110`).

**`backfill()`** (`pne.py:330-430`): the *only* path real outcomes come back through,
always asynchronous, always learning-only. PNE may call it "on any schedule that suits
PNE" — out of order, batched, or with gaps — so it has to tolerate all three without
losing a signal or double-counting a report:
- A duplicate report (attempt already resolved) is detected up front and skips the
  entire learning fan-out.
- `decline_recovery` teaching normally fires "forward" (this outcome teaches the
  transition from the immediately preceding decline, if that position is already
  resolved). If reports arrive out of order and the predecessor isn't resolved yet,
  teaching is deferred; once the predecessor *does* resolve, it checks "backward"
  whether the following position already resolved without being taught, and recovers
  that signal then. Forward and backward are mutually exclusive for any given
  transition — see the LP-233 plan for why neither double-fires.

**On any real outcome**, the learning fan-out fires in this order (`pne.py:401-428`):
`router.record_usage` → `bandit.record_outcome` → `circuit_breaker.record_outcome`
(+ `file_trip_alert` if newly tripped) → `decline_recovery.record_outcome` (only if a
predecessor decline/processor pair is resolved to teach from — see above) →
`outcomes_log.record` (audit trail). `decline_recovery.classify()` (hard vs soft,
`decline_classification.py`) is still called here, but purely to label the *teaching*
signal — nothing in `start()`'s list-build path consults it.

## Selection logic

- **Position 1**: general Way-3 bandit — `bandit.score_candidates`/`sample_winner`,
  called via `_select_gate`. A capacity admission-bar filter (edge over the best
  alternative) runs before the Thompson draw.
- **Positions 2/3** (`_pick_list_processor`, `pne.py:196-249`): ranked by
  `decline_recovery.recovery_probability`, but entered at its most-marginal hierarchy
  level (`decline_recovery.ANY` for declining_processor/decline_code/decline_class)
  since there's no real decline code yet — the whole list is decided before any
  attempt happens. This reuses the same historical+live Bayesian blending as a real
  post-decline retry, just answering "of retries in general at this position, how
  often does this candidate recover?" instead of a decline-specific question.
  Same capacity-admission-bar filter as position 1, then highest `_p_recover` wins.
- **No EV/should-retry gate exists anymore.** The old per-attempt loop's
  `decline_recovery.should_retry` and `_pick_retry_processor` are gone. List length is
  driven purely by candidate eligibility, never by whether a retry's expected value
  would justify it — see the module docstring's explicit note on this
  (`pne.py:26-30`).
- **Wallet transactions** (`apple_pay`/`google_pay`): bypass the bandit entirely —
  deterministic first-eligible-gate (`_wallet_gate`), wrapped as a 1-entry list.
- **Hard rules (`pin`)**: skip the bandit's *scoring* only, never the hard technical
  checks (network mismatch, circuit breaker, rate limit). A pinned gate that becomes
  unusable falls through to the normal candidate pool rather than closing the
  transaction (`pne.py:139-158`).
- **A list never repeats a processor** — each position's winner is added to an
  `exclude` set for every later position in the same list (`pne.py:322`).

## Known gap: no decline-code-based skip/exclude mechanism

`decline_classification.py`'s `(is_hard, decline_class)` taxonomy (hard = stolen/lost/
fraud/invalid card, "never try again") still exists and still feeds
`decline_recovery.classify()` — but only for the `backfill()` teaching signal above.
**Nothing in `start()`'s list-build path uses `is_hard` to exclude a processor from a
position.** Before the gate-list refactor, this hard/soft split gated the old live
retry loop directly; that gating was removed along with `outcome()` and was not
reintroduced for `_pick_list_processor`. There is no "skip list" / "chain strategy"
concept implemented on SmartRouting's side today — if PNE's cascade needs to stop
itself on an unrecoverable decline code, that has to come from PNE's own chain-strategy
config (populated by us, per PNE's PNE-side "Chain Strategy Skips" field), not from
anything SmartRouting computes at gate-list build time.

## Way-3 hybrid bandit / decay math

`decay.py`'s `decay_increment`/`decay_read` is "the one place the [decayed-counter]
math lives" (`backend/online/routing/live_request/live_learning/decay.py:1-13`),
reused with different half-lives by three independent learners:

| Learner | File | Half-life |
|---|---|---|
| Base approval bandit | `live_learning/bandit.py` | `RECENCY_HALFLIFE_DAYS` (14 days) |
| Circuit breaker | `live_learning/circuit_breaker.py` | `BREAKER_HALFLIFE_HOURS` (hours) |
| Decline-reason recovery | `live_learning/decline_recovery.py` | same 14-day half-life |

Decayed writes are single atomic `UPDATE`s with the decay math embedded directly in
SQL (`power(0.5, extract(epoch from (now() - table.updated_at)) / %s)` —
`decay.py:25-55`) specifically to avoid read-modify-write races under concurrent
requests.

## State passing

Plain `dict`s throughout — `tx` (`_tx_snapshot`, `pne.py:62-84`), `segment`
(`segments.segment_key`, `segments.py:41-50`), `cfg` (from `config.load_config`),
candidate lists as `list[dict]`. No dataclasses/Pydantic inside the engine — Pydantic
exists only at the FastAPI boundary and is converted to a dict immediately
(`req.model_dump()`).

Everything in this tree is **synchronous** — no `async def` anywhere in `router.py`,
`pne.py`, or any `live_request/` submodule.

## Error handling — isolate, don't crash the cascade

A single processor's model/scorer failing must never fail the whole request:
`logger.exception(...)` and continue with a safe fallback.
- `scoring.py:98-101` — "one processor's model choking on this tx shouldn't fail the
  whole cascade."
- `bandit.py:126-128` — a trained-model scoring failure is treated as uninformative
  (`p_model=0.0`), not fatal.
- `construction.py:86-87,109-110` — a broken model artifact at load time is skipped,
  not fatal.
- `pne.py:219-224` (`_pick_list_processor`'s proxy scoring) — same pattern, falls back
  to `p_model_proxy = 0.0` on failure.

Human-facing alerts go through `approval_queue`, not exceptions — same
select-existing-pending-row-then-insert shape repeated in `circuit_breaker.py:77-103`
(`file_trip_alert`), `decline_recovery.py:83-106` (`_file_unclassified_alert`), and
`gates.py:75-95` (`_insert_discovered`): `SELECT` for an existing pending row with a
matching payload → skip if found → `INSERT` with rationale/impact/risk →
`logger.warning`. Copy this shape for any new alert type rather than inventing a new
one. (The old `outcome()` loop's `_file_gate_alert` for `not_attempted`/`error`
responses no longer exists — those response kinds belonged to the deleted per-attempt
contract.)

## `Router` / `Bundle` wiring

`router.py` is a thin composition-root, not a DI framework: `Router.__init__` calls
`construction.initialize(self, ...)`, which sets `router._bundle`, `router._daily_limits`,
`router._fx_rates`, `router._db` directly as plain attributes. Nearly every other
`Router` method is a one-line delegation to a function in another module, passing
`self` as the first arg (`router.py:1-9` states this design intent explicitly, though
its own comments still call this "the PayNet Easy per-attempt cascade routing engine"
— stale wording left over from before the gate-list refactor, not a second engine).

Only fields that must hot-swap **atomically together** live inside `Bundle`
(`.models`, `.encoders`, `.proc_names`, `.cold_processors`, `.store`, `.version`) —
swapped with a single attribute assignment, `router._bundle = new_bundle`
(`backend/online/serving/startup_shutdown/lifespan.py:106`), relying on the GIL for
atomicity (`construction.py:11-18`). Everything else (`_daily_limits`, `_fx_rates`,
`_db`) is a plain `Router` attribute because it doesn't need that property. Follow
this rule when adding new router-level state: only put it in `Bundle` if it must swap
atomically with the models/encoders.

`startup/construction.py` separates `build_bundle_from_files` (disk-based,
deterministic — used by `Router()`'s default constructor and by offline eval tooling)
from `build_bundle_from_bytes` (pure, no I/O — used for the Postgres hot-reload path).
The decision to prefer Postgres over disk lives in `lifespan.py`, not in
`Router`/`construction.py` (`construction.py:122-127`) — keep that separation if you
touch either.
