# FastAPI serving layer

On-demand context for `backend/online/serving/`. Load this before adding or changing
an HTTP endpoint, a response schema, or startup/shutdown behavior.

---

## App wiring

- `backend/online/serving/service.py:77-81` — a single module-level `FastAPI(...)`
  instance, `app`, constructed with `lifespan=lifespan`. No app-factory function.
- Routes are **not** `@app.get`-decorated inline handlers and there is no
  `APIRouter()` anywhere in the codebase. Handler functions live in separate
  `routes.py` files as plain functions, imported into `service.py` and registered by
  calling `app.get(...)`/`app.post(...)` on them (`service.py:84-115`).
- HTTP method convention: POST for anything mutating or decision-making
  (`/route/start`, `/route/outcome`, `/route/backfill`, `/dashboard/api/rules`,
  `/dashboard/api/rules/{rule_id}/deactivate`), GET for reads. Multi-word dashboard
  path segments are kebab-case (`rate-limits`, `approval-queue`,
  `bad-bin-benchmark`).
- `_SPAStaticFiles` (`service.py:128-146`) is a `StaticFiles` subclass that catches
  Starlette's `HTTPException` on a 404 and serves `index.html` instead, so the React
  SPA's client-side routes work. Dashboard static assets are mounted only if
  `frontend/dashboard/dist` exists on disk (`service.py:157,161-163`) — absent on a
  plain checkout, present only after `npm run build` or in the Docker image.
- Route handlers are **synchronous `def`**, not `async def`, everywhere in both
  `routes.py` files — FastAPI runs them in its own threadpool automatically.

## Lifespan / startup / hot-reload

`backend/online/serving/startup_shutdown/lifespan.py`:

- `@contextlib.asynccontextmanager async def lifespan(app)` (`lifespan.py:46-81`).
- Startup loads a `Router()` from disk first (deterministic baseline,
  `lifespan.py:57`) — if that fails, `logger.critical(..., exc_info=True)` then
  re-raise; the service refuses to come up (`lifespan.py:58-61`).
- Then prefers whatever model version is active in Postgres if it's newer
  (`_load_active_version_if_newer`, `lifespan.py:63,85-110`).
- A background task polls for a newer model version every `POLL_INTERVAL_SECONDS =
  600` (10 min — "twice-daily retrains don't need fast polling"),
  `asyncio.create_task(_poll_for_new_version())` at `lifespan.py:71`. Because this is
  a bare asyncio task and not a FastAPI path op, it does **not** get FastAPI's
  automatic sync-to-threadpool wrapping — the blocking psycopg check inside it is
  explicitly wrapped in `asyncio.to_thread(...)` (`lifespan.py:118-121,125`). Keep
  this in mind if you add another background task: it needs the same manual wrapping
  for any blocking call.
- Model swap is a single attribute assignment, `router._bundle = new_bundle`
  (`lifespan.py:106`), deliberately atomic under the GIL — see
  `.claude/context/pne-cascade-engine.md` for why `Bundle` groups exactly these
  fields.
- Shutdown cancels the poll task (`contextlib.suppress(asyncio.CancelledError)`) then
  closes the psycopg pool (`lifespan.py:75-80`).
- Module-level global `_router: Router | None = None` (`lifespan.py:39`) is the
  shared state, accessed via `get_router()` — raises `HTTPException(503, ...)` if not
  ready (`lifespan.py:130-135`) — and `get_router_or_none()`, used only by `/health`
  (`lifespan.py:139-141`).

## Route error-handling — two deliberately different contracts

**`transaction_routing/routes.py`** (PNE-facing, hardened contract — follow this for
any new customer/partner-facing endpoint):
- Every handler calls `reset_db_timing()` first, gets the router via `get_router()`,
  wraps the core call: `try/except Exception: logger.exception(...); raise
  HTTPException(500, detail=...)` (`routes.py:46-50,70-72,91-93`).
- `route_outcome` additionally catches `ValueError` and maps it to `HTTPException(404,
  ...)` (`routes.py:68-69`) — because `pne.outcome()` raises `ValueError` for an
  unknown `(correlation_id, attempt_number)`. This is the only place a 404-vs-500
  distinction is made by exception type.
- Every handler logs a `db_timing` line after success — `correlation_id`, `db_ms`,
  `db_calls` — via the module logger `logging.getLogger("smartrouting.service")`
  (`routes.py:52-55,74-77,95-98`), fed by the custom timing instrumentation in
  `database/db.py` (see `.claude/context/database-and-config.md`).
- All response shapes are strict Pydantic `response_model`s.

**`dashboard/routes.py`** (internal/analytics, deliberately looser — do not copy this
for a new PNE-facing endpoint):
- Read endpoints return plain `dict`/`list`, no `response_model`, mostly no
  try/except at all — explicitly justified in the module docstring
  (`dashboard/routes.py:9-13`: "their shape is still settling ... a strict Pydantic
  response_model per query would just churn").
- Only mutating endpoints validate via Pydantic request models; only
  `set_shadow_mode`/`list_merchants` raise `HTTPException` directly (404 for a missing
  merchant, `dashboard/routes.py:97-98`).
- Uses its own module logger, `logging.getLogger("smartrouting.dashboard")` pattern
  (`dashboard/routes.py:30`) — matches the per-subsystem logger naming convention.

There is **no shared `@app.exception_handler`** anywhere — each route module is fully
responsible for its own error handling.

## Schemas (`data_models/schemas.py`)

- All Pydantic v2 `BaseModel`s, PascalCase, named `...Request`/`...Response`
  (`RouteStartRequest`, `CreateRuleRequest`).
- Fields are snake_case, no camelCase aliasing.
- `Literal[...]` is used instead of `Enum` for enum-like fields — e.g. `status:
  Literal['gate', 'close', 'approved']` (`schemas.py:79`), `outcome: Literal[
  'approved', 'declined', 'not_attempted', 'error']` (`schemas.py:104`).
- Optional strings default to `""` rather than `None` where "not applicable" and
  "genuinely absent" are meaningfully different (`project: str = ""`) — preserve that
  distinction rather than collapsing both to `None`.
- Business-meaning comments sit directly above fields/classes — e.g.
  `schemas.py:86-94` explains why `not_attempted`/`error` must never be reported as
  `declined`. Keep writing these; don't strip them for brevity.
- `RouteBackfillRequest` intentionally duplicates every field of `RouteStartRequest`
  instead of inheriting/reusing it, because a backfill may have no prior
  `cascade_sessions` row (`schemas.py:117-119`) — a deliberate non-DRY choice, not an
  oversight. Don't "clean it up" by introducing shared inheritance.
- No `pydantic-settings`/`BaseSettings` usage anywhere — config loading is manual (see
  `.claude/context/database-and-config.md`).

## `/version` and `/health`

- `/version` returns the `GIT_SHA` baked in at Docker build time (`os.environ.get(
  'GIT_SHA', 'unknown')`, `routes.py:115`) — lets a deploy be confirmed without
  visibility into the CI runner.
- `/health` reports readiness plus trained/cold/rate-limited processor counts pulled
  straight off `router._bundle` (`routes.py:119-129`) — returns `status: "not_ready"`
  gracefully if the router hasn't finished loading yet, rather than erroring.
