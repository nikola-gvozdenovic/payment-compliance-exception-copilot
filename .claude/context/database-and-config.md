# Database & config

On-demand context for `backend/online/routing/database/db.py`,
`backend/online/routing/configuration/config.py`, or any change that adds new
persisted state or a new tunable value. Load this before writing SQL or deciding
where a new setting should live.

---

## No ORM, no migration framework — by design

`db.py:15-17` states the design intent explicitly: "just plain SQL, run idempotently
at startup ... consistent with how the rest of this project avoids extra
dependencies." Schema lives in one large `SCHEMA` string constant
(`db.py:66-319`) using `CREATE TABLE IF NOT EXISTS` for every table, applied via
`init_schema(pool)` (`db.py:371-389`), which also seeds `decline_codes` and calls
`config.init_defaults(pool)`. A schema change means editing this one string with an
additive, idempotent statement — never a separate migration file, never a destructive
`ALTER`/`DROP` against production data without a plan for existing rows.

Offline bootstrap scripts (`backend/offline/features/db_bootstrap/*.py`) each call
`db.init_schema(pool)` defensively before writing, with the same comment repeated in
every one of them: "this script may run before the service ever has — don't depend on
run order" (e.g. `seed_merchants_and_gates.py:60`, `country_currency.py:73`). Keep
that defensive call if you add a new bootstrap script.

## Connection pooling

- Postgres via `psycopg[binary,pool]` + `psycopg_pool.ConnectionPool` — no other
  driver, no async DB client.
- `get_pool(database_url=None)` (`db.py:323-334`) reads `DATABASE_URL` from the
  environment, raises `RuntimeError` if missing — the service "refuses to start
  without it." `min_size=1`, `max_size` from `DB_POOL_MAX_SIZE` (default 10),
  `pool.wait(timeout=10)` at startup.
- **Pool sizing is load-bearing, not cosmetic** — a prior incident dropped
  `DB_POOL_MAX_SIZE` from 10 to 4 after `9 replicas × 4 uvicorn workers ×
  DB_POOL_MAX_SIZE=10` (360 max connections) exceeded Postgres's `max_connections=100`
  under sustained load (see `git log` commit "Fix Postgres connection exhaustion
  under sustained load"). Any replica-count or worker-count change needs re-checking
  against this pairing.

## Query & transaction conventions

- Always `%s` parameterized placeholders inside triple-quoted SQL strings — never
  string-interpolate a value into SQL. This applies identically in the online engine
  and every offline bootstrap script.
- `with pool.connection() as conn:` blocks; psycopg3 auto-commits on clean exit,
  rolls back on exception (standard psycopg3 behavior, not custom code here).
- Multi-statement writes that must be atomic are grouped inside a single
  `with pool.connection() as conn:` issuing sequential `conn.execute(...)` calls —
  e.g. `model_registry.push_version` (`model_registry.py:83-121`), commented
  explicitly: "all in one transaction, so the running service never observes a
  half-pushed version." Follow this shape for any new multi-table write that must be
  all-or-nothing.
- Idempotent writes use `INSERT ... ON CONFLICT (...) DO NOTHING` or `DO UPDATE SET
  ...` consistently (schema-seed inserts, `cascade_session.insert_attempt`,
  `gates.get_or_create_merchant`, `model_registry.push_version`).
- The `active_model_version` table uses a singleton-row trick:
  `id BOOLEAN PRIMARY KEY DEFAULT true CHECK (id)` to guarantee exactly one row
  (`db.py:315-318`) — copy this pattern for any other "exactly one current X" table
  rather than adding an app-level uniqueness check.
- Decayed counters (bandit/circuit-breaker/decline-recovery) update with the decay
  math embedded directly in a single atomic SQL `UPDATE`
  (`power(0.5, extract(epoch from (now() - table.updated_at)) / %s)`,
  `live_learning/decay.py:25-55`) specifically to avoid read-modify-write races —
  don't replace this with a read-then-write in application code.

## Custom DB timing instrumentation

`_instrument_pool_for_timing` (`db.py:355-367`) monkeypatches `pool.connection` to
wrap every checkout, accumulating per-thread (`threading.local()`) `total_ms`/`calls`.
`reset_db_timing()`/`get_db_timing()` are called at the top/bottom of every
`transaction_routing/routes.py` handler to log a `db_timing` line per request. This is
bespoke, not a library — if you add a new route that does real DB work, call
`reset_db_timing()` at the top and log the result the same way the existing handlers
do, for consistent capacity-planning visibility.

## Two config layers — know which one a new setting belongs in

**1. Environment variables** (`.env` / deploy-time infra config) — loaded via
`python-dotenv`'s `load_dotenv()`, called independently in each module that needs it
(`db.py:58`, `backend/utils/fx.py:34` — not centralized), read via
`os.environ.get(...)`. No `pydantic-settings`/`BaseSettings` anywhere. Current vars:
`DATABASE_URL` (required), `DB_POOL_MAX_SIZE` (optional, default 10),
`PROCESSOR_DAILY_LIMITS` (optional JSON), `XE_ACCOUNT_ID`/`XE_API_KEY` (optional),
`ALTITUDEPAY_CONSUMER_KEY`/`SECRET` (offline only), `GIT_SHA` (build-time), and
`POSTGRES_PASSWORD` (consumed only by Docker Compose itself). Full documentation of
each lives in `.env.example` — keep it updated when adding a new one.

**2. DB-tunable config** (`backend/online/routing/configuration/config.py`) — anything
ops should be able to retune **without a code deploy** (bandit half-lives,
circuit-breaker thresholds, capacity admission bars) lives in the Postgres `config`
table as JSONB. `DEFAULTS: dict[str, object]` (`config.py:25-79`) is seeded once via
`init_defaults()` using `ON CONFLICT DO NOTHING` — it never overwrites a value ops has
already tuned. Read per-request via `load_config(pool)` (`config.py:93-100`), merging
`{**DEFAULTS, **loaded}`. Explicit rationale: `config.py:1-8`, "so ops can retune them
without a code change."

**Rule of thumb**: infra/deploy-shape config (pool size, connection strings, secrets)
→ env var. Business/tuning knobs someone might want to change on the fly → the
`config` table's `DEFAULTS` dict. Don't add a new business tunable as a raw env var.
