# Feature: LP-140 — Dashboard Login

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types and models. Import from the right files etc.

## Feature Description

The SmartRouting operator dashboard (`frontend/dashboard/`, served by FastAPI's `/dashboard/api/*` routes) is currently fully open: no login page, no route guards in `App.jsx`, and no auth check on any dashboard endpoint. Anyone who can reach the service can view live approval rates, create/deactivate hard rules that override the routing bandit, resolve approval-queue items, and flip a merchant's shadow-mode flag. This feature adds email/password authentication gating the entire dashboard surface, while leaving the PNE-facing cascade API (`/route/*`, `/health`, `/version`, `/rate-limits`) untouched — that's a machine-to-machine integration contract with PayNet Easy, not something a human logs into.

## User Story

As a SmartRouting operator
I want to log in with an email and password before I can see or change anything in the dashboard
So that hard rules, approval-queue decisions, and merchant shadow-mode toggles can't be made by anyone who merely has network access to the service

## Problem Statement

`backend/online/serving/dashboard/routes.py` has zero authentication on any handler, and `frontend/dashboard/src/App.jsx` renders every route unconditionally. There is no `users` concept anywhere in the schema (`backend/online/routing/database/db.py`'s `SCHEMA` string).

## Solution Statement

- Add a `users` table (email + bcrypt password hash + a `role` of `'viewer'` or `'admin'`) and a `sessions` table (one row per issued token, so logout can revoke it server-side) to the single `SCHEMA` string in `db.py`.
- Issue a JWT on login whose `jti` claim matches a `sessions.id` row; a FastAPI dependency (`require_auth`) decodes the bearer token, checks it against `sessions` (not expired, not revoked), and 401s otherwise. A second dependency (`require_admin`) does the same resolution and additionally 403s any non-admin — every read (`GET`) dashboard endpoint gets `require_auth`, every mutating (`POST`) one gets `require_admin`. Add these as `dependencies=[Depends(...)]` to every existing `/dashboard/api/*` route registration in `service.py` — no restructuring into an `APIRouter`, matching the file's existing per-route wiring style.
- `POST /dashboard/api/login` (unauthenticated, generic error on failure) and `POST /dashboard/api/logout` (authenticated, revokes the session row).
- Frontend: a `Login.jsx` page, a small auth gate in `App.jsx` (plain prop/state, no Context), and `api.js` updated to attach `Authorization: Bearer <token>` to every request and to clear+reload on a 401. A viewer hitting a write action still sees the same UI as an admin — the 403 from the API is the only enforcement (no role-conditional rendering); this keeps the frontend diff small and was an explicit scope call, not an oversight.
- A one-off bootstrap script (mirroring `backend/offline/features/db_bootstrap/seed_merchants_and_gates.py`) to create users one at a time, with a required `--role` flag (`viewer` or `admin`, no default) — since the ticket doesn't call for a signup endpoint or an in-dashboard user-management UI.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium (role-based access adds a `role` column and a second FastAPI dependency, but reuses the same session-resolution query — no separate infrastructure)
**Primary Systems Affected**: `backend/online/routing/database/db.py` (schema), `backend/online/routing/dashboard/` (new `auth.py`), `backend/online/serving/dashboard/routes.py` + `service.py` (wiring), `backend/online/serving/data_models/schemas.py`, `frontend/dashboard/src/` (App.jsx, api.js, new Login.jsx)
**Dependencies**: `bcrypt` (password hashing), `PyJWT` (session tokens) — neither currently in `pyproject.toml`/Dockerfile

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `backend/online/routing/database/db.py:64-65,325-334` — the required-secret fail-fast pattern (`ENV_VAR = 'DATABASE_URL'`, `os.environ.get`, `raise RuntimeError` if missing) to mirror exactly for `SESSION_SECRET`. Also read the `SCHEMA` string's existing table blocks (lines ~76-318) for the idempotent `CREATE TABLE IF NOT EXISTS` style, comment banners (`-- ── Section ─...`), and `SERIAL PRIMARY KEY` / `TIMESTAMPTZ NOT NULL DEFAULT now()` conventions to copy for `users`/`sessions`.
- `backend/online/routing/live_request/eligibility/hard_rules.py` (whole file) — the canonical shape for a new routing-layer module: module docstring, `#### Import libraries ####` banner, `logger = logging.getLogger("smartrouting.hard_rules")`, plain functions taking `pool: ConnectionPool` as first arg, `with pool.connection() as conn: conn.execute(...)`. Mirror this exactly for the new `backend/online/routing/dashboard/auth.py`.
- `backend/online/routing/configuration/config.py:1-8` — read for the "two config layers" rationale; confirms `SESSION_SECRET` (a secret, not an ops-tunable) belongs as a required env var, NOT a row in the `config` table.
- `backend/online/serving/dashboard/routes.py` (whole file) — the thin-wrapper pattern every dashboard handler follows: `router = get_router()` then delegate to a routing-layer module, return a plain dict. New `login`/`logout`/`require_auth` functions go in this file, following this shape, but — because this is security-sensitive — with an explicit `try/except` around `login` (unlike the file's usual looser convention), matching the strict pattern from `transaction_routing/routes.py:41-50` closely enough to guarantee a generic error message.
- `backend/online/serving/transaction_routing/routes.py:1-50` — the strict try/except → `logger.exception` → `HTTPException` contract; mirror the shape (not necessarily every line) for `login`.
- `backend/online/serving/service.py:79-99` — exact routes to add `dependencies=[Depends(require_auth)]` to. Every line in this range except the new `login` route needs it (`logout` needs it too, since it must resolve `require_auth` to a user/session to revoke). Also shows the `app.get(path)(handler)` / `app.post(path)(handler)` two-step call style — `app.post(path, dependencies=[...])(handler)` is a drop-in extension of this, no restructuring needed.
- `backend/online/serving/data_models/schemas.py:159-179` — `CreateRuleRequest` / `ResolveApprovalRequest` / `SetShadowModeRequest` as the pattern for the new `LoginRequest`/`LoginResponse` models (plain `BaseModel`, no `Field(...)` metadata used anywhere in this file).
- `backend/online/serving/startup_shutdown/lifespan.py:get_router()` — how every route handler gets the `Router` (and therefore `router._db`, the `ConnectionPool`) — the exact same accessor the new auth handlers use.
- `backend/offline/features/db_bootstrap/seed_merchants_and_gates.py` — pattern for a standalone bootstrap script (CLI args via `argparse` or plain `sys.argv`, connects via `get_pool()`, does one-shot inserts) to mirror for `create_dashboard_user.py`.
- `.env.example` — where to document the new required `SESSION_SECRET` var, following the existing comment style for `DATABASE_URL`.
- `frontend/dashboard/src/App.jsx` (whole file) — where the route guard and login route go; the `NavLink`/`Routes` structure to extend.
- `frontend/dashboard/src/api.js` (whole file) — the `request()` helper every API call goes through; this is the one place to add the `Authorization` header and centralized 401 handling.
- `frontend/dashboard/src/pages/RulesManager.jsx:1-80` — the best existing example of a controlled form (`useState` form object, `update(field, value)`, `submit(e)` with `e.preventDefault()`, inline `error` state) to mirror for `Login.jsx`.
- `frontend/dashboard/src/styles.css:144-146,340-399` — `.error` class and the `.rule-form`/`.rule-form-row`/`.rule-form label`/`.rule-form input` classes to reuse for the login form (don't invent new CSS classes for a simple email/password form).
- `frontend/dashboard/vite.config.js` — dev-time proxy list (`/route`, `/health`, `/rate-limits`, `/dashboard/api`) — no change needed since login/logout live under `/dashboard/api`, but confirms why `api.js` never needs a base URL.
- `Dockerfile:24-31` — the exact pinned pip install list that ships in production; `bcrypt`/`PyJWT` must be added here with pinned versions, or the shipped image will 500 on every login attempt despite tests passing locally.
- `pyproject.toml:1-19` — where `bcrypt`/`PyJWT` get added for local dev/`uv.lock`.
- `kubernetes/deployment.yaml:83-110` — how `DATABASE_URL` is wired from a `secretKeyRef`; the pattern to mirror if/when `SESSION_SECRET` is wired into the cluster (see NOTES — this is flagged as a manual follow-up, not part of this plan's automated tasks, since it requires provisioning a real secret value).

### New Files to Create

- `backend/online/routing/dashboard/auth.py` — password hashing/verification, session creation/revocation/lookup, `SESSION_SECRET` fail-fast accessor.
- `backend/offline/features/db_bootstrap/create_dashboard_user.py` — one-off CLI to insert the first dashboard user.
- `frontend/dashboard/src/pages/Login.jsx` — the login form page.

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [PyJWT — Usage Examples](https://pyjwt.readthedocs.io/en/stable/usage.html#encoding-decoding-tokens-with-hs256)
  - `jwt.encode(payload, key, algorithm="HS256")` / `jwt.decode(token, key, algorithms=["HS256"])`
  - Why: exact API for issuing/validating the session JWT; note `jwt.decode` raises `jwt.ExpiredSignatureError` / `jwt.InvalidTokenError` (both subclasses of `jwt.PyJWTError`) — catch these, not a bare `except Exception`, so a genuinely unexpected bug doesn't get silently treated as "just log out the user".
- [PyJWT — Registered Claim Names](https://pyjwt.readthedocs.io/en/stable/api.html#jwt.encode)
  - `exp` (expiry, a `datetime` or int timestamp) is checked automatically by `jwt.decode`; `sub`/`jti` are just dict keys PyJWT does not special-case beyond `exp`/`nbf`/`aud`/`iss` — this codebase should set `sub` (user id, as a string per JWT spec — `jwt.encode` won't auto-stringify) and `jti` (the `sessions.id` UUID, also as a string) manually.
  - Why: need to know which claims are validated for you (`exp`) vs. which are just data you look up yourself (`jti` against the `sessions` table for revocation).
- [bcrypt PyPI — Usage](https://pypi.org/project/bcrypt/)
  - `bcrypt.hashpw(password.encode(), bcrypt.gensalt())` / `bcrypt.checkpw(password.encode(), hashed)`
  - Why: exact API for hashing/verifying; note both take/return `bytes`, so the DB column stores `hashed.decode()` and verification re-encodes with `.encode()`.

### Patterns to Follow

**Naming Conventions:**
- New Python module: `backend/online/routing/dashboard/auth.py`, `snake_case` functions (`hash_password`, `verify_password`, `create_session`, `revoke_session`, `resolve_session`), module constant `ENV_VAR = 'SESSION_SECRET'` (`SCREAMING_SNAKE_CASE`, mirroring `db.py:64`).
- New Pydantic models: `LoginRequest`, `LoginResponse` (`PascalCase`, matching `CreateRuleRequest` etc.).
- New React file: `Login.jsx` (`PascalCase.jsx` matching the exported component, per `MerchantManager.jsx`/`ARBar.jsx`).
- New logger: `logging.getLogger("smartrouting.auth")` — its own name, not a copy of `"smartrouting.dashboard"` (see CLAUDE.md's warning about the `scoring.py`/`rate_limits.py` copy-paste-logger-name slip; don't repeat that mistake here).

**Error Handling:**
- `auth.py` functions raise `ValueError` for "not authenticated" conditions (bad token, expired, revoked, unknown user) — mirrors `router.route_outcome`'s `ValueError` → routes.py's `except ValueError: raise HTTPException(404, ...)` pattern (`transaction_routing/routes.py:65-66`), just mapped to 401 instead of 404 in the dashboard routes.
- `login()` in `dashboard/routes.py` never distinguishes "email not found" vs. "wrong password" in the response or the exception type — both paths must produce the exact same generic `HTTPException(401, "Invalid email or password")`, per the ticket's no-user-enumeration acceptance criterion. Do the comparison in constant-ish time by always calling `bcrypt.checkpw` even when the email doesn't exist (check against a dummy hash) — see Task list below.

**Logging Pattern:**
- Log successful/failed login attempts and logout at `INFO` (not `DEBUG`) since this is a security-relevant audit trail, same spirit as `hard_rules.create_rule`'s `logger.info("Created hard_rule id=%s type=%s by=%s reason=%r", ...)` (`hard_rules.py:132`). Never log the password or the raw token — only email and success/failure.

**Other Relevant Patterns:**
- Required-secret fail-fast: `SESSION_SECRET` must raise `RuntimeError` at import/first-use time if unset, exactly like `DATABASE_URL` (`db.py:325-327`) — not a soft fallback like `XE_API_KEY` (`fx.py:46-49`).
- Frontend fetch guard pattern (`cancelled` flag in `useEffect`) applies to any page that fetches on mount — `Login.jsx` doesn't fetch on mount (it's a pure form), so this pattern doesn't apply there, but note it if `App.jsx`'s route guard ends up doing an async "is this token still valid" check (it shouldn't — see Task list, the guard is a synchronous "is there a token in localStorage" check only, matching acceptance criteria which don't require server round-trip validation before rendering).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

- Add `bcrypt` and `PyJWT` to `pyproject.toml` and lock via `uv add bcrypt pyjwt` (updates `uv.lock` too).
- Add `users` and `sessions` tables to `db.py`'s `SCHEMA` string.
- Add `SESSION_SECRET` to `.env.example` with a comment matching `DATABASE_URL`'s.

### Phase 2: Core Implementation

- Implement `backend/online/routing/dashboard/auth.py`: password hashing, session issue/verify/revoke.
- Implement `LoginRequest`/`LoginResponse` schemas.
- Implement `login`, `logout`, `require_auth` in `backend/online/serving/dashboard/routes.py`.
- Implement `backend/offline/features/db_bootstrap/create_dashboard_user.py` bootstrap CLI.

### Phase 3: Integration

- Wire `login`/`logout` routes and `dependencies=[Depends(require_auth)]` on every existing dashboard route in `service.py`.
- Add `bcrypt`/`PyJWT` pinned versions to `Dockerfile`'s pip install list.
- Frontend: `api.js` token storage + `Authorization` header + 401 handling; `Login.jsx`; `App.jsx` route guard.

### Phase 4: Testing & Validation

- Run `python -m unittest -v` (must still pass — no new stdlib-only test is required by the ticket, but the existing suite must not regress).
- Manual validation: bootstrap a user, log in via curl, hit a dashboard endpoint with/without a token, log out, confirm the revoked token is rejected.
- Browser (`agent-browser`) validation of the full login/logout/redirect flow.

---

## STEP-BY-STEP TASKS

### UPDATE pyproject.toml (add dependencies)

- **IMPLEMENT**: Run `uv add bcrypt pyjwt` from repo root — updates both `pyproject.toml`'s `dependencies` list and `uv.lock` in one step (don't hand-edit the lock file).
- **PATTERN**: `pyproject.toml:5-18`'s existing dependency list style (`"psycopg[binary,pool]>=3.2"`).
- **GOTCHA**: the PyPI package name is `PyJWT`; the import name is `jwt`. Don't confuse it with the unrelated `jwt` package on PyPI — `uv add pyjwt` (lowercase) resolves to the correct one.
- **VALIDATE**: `python -c "import bcrypt, jwt; print(bcrypt.__name__, jwt.__name__)"`

### UPDATE backend/online/routing/database/db.py (schema)

- **IMPLEMENT**: Add a new section to the `SCHEMA` string (after the `hard_rules` block, before `-- ── Decline-code taxonomy...`, or any clearly-delimited spot — follow the file's existing `-- ── Section Name ──...` banner style):
  ```sql
  -- ── Dashboard auth (LP-140) ─────────────────────────────────────────────

  CREATE TABLE IF NOT EXISTS users (
      id            SERIAL PRIMARY KEY,
      email         TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role          TEXT NOT NULL CHECK (role IN ('viewer', 'admin')),
      created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  -- One row per issued session (its id is the JWT's `jti` claim). The JWT
  -- itself is stateless and can't be un-issued, so logout (and any future
  -- forced-revocation need) works by marking this row revoked — every
  -- dashboard request checks both the JWT signature/expiry AND this row.
  CREATE TABLE IF NOT EXISTS sessions (
      id         UUID PRIMARY KEY,
      user_id    INT NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ
  );
  ```
- **PATTERN**: `db.py:76-91` (`merchants`/`gates` table style — `SERIAL PRIMARY KEY`, `TIMESTAMPTZ NOT NULL DEFAULT now()`).
- **GOTCHA**: this is additive-only — `CREATE TABLE IF NOT EXISTS`, no `ALTER TABLE` on existing tables. Don't add a migration framework; this file is the only schema source (per CLAUDE.md hard rule).
- **VALIDATE**: start the app locally against a scratch Postgres (or reuse `docker/docker-compose.yml`'s `db` service) and confirm `init_schema()` runs without error: `docker compose -f docker/docker-compose.yml up -d db && DATABASE_URL=postgresql://smartrouting:<pw>@localhost:5432/smartrouting python -c "from backend.online.routing.database.db import get_pool, init_schema; init_schema(get_pool())"`

### UPDATE .env.example

- **IMPLEMENT**: Add, after the `DATABASE_URL` block:
  ```
  # Required. Secret used to sign dashboard login session tokens
  # (backend/online/routing/dashboard/auth.py). The service refuses to
  # start without it, same as DATABASE_URL. Generate with e.g.
  # `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
  SESSION_SECRET=
  ```
- **PATTERN**: `.env.example`'s existing `DATABASE_URL` comment block.
- **VALIDATE**: `grep -q SESSION_SECRET .env.example`

### CREATE backend/online/routing/dashboard/auth.py

- **IMPLEMENT**:
  ```python
  """Dashboard auth block (LP-140): password hashing, session issuance and
  revocation for the operator dashboard's login.

  In plain words: this is where "does this email/password match a real
  user?" and "is this bearer token still good?" get answered. A session is
  a JWT (so verifying it doesn't need a DB round trip to check a signature)
  whose `jti` claim also names a row in the `sessions` table — that row is
  what makes logout actually revoke a token instead of just deleting it
  client-side, since a JWT can't be un-issued once signed.
  """

  ####################
  # Import libraries #
  ####################
  from __future__ import annotations

  import datetime
  import logging
  import os
  import uuid

  import bcrypt
  import jwt
  from psycopg_pool import ConnectionPool

  logger = logging.getLogger("smartrouting.auth")

  ########################################################################################################################

  ENV_VAR = 'SESSION_SECRET'
  ALGORITHM = 'HS256'
  SESSION_TTL_HOURS = 12

  # A fixed dummy hash checked when an email doesn't exist, so a login
  # attempt for a nonexistent user takes the same bcrypt-verify time as one
  # for a real user with a wrong password — without this, response timing
  # alone would leak which emails have accounts.
  _DUMMY_HASH = bcrypt.hashpw(b'not-a-real-password', bcrypt.gensalt())


  def _session_secret() -> str:
      secret = os.environ.get(ENV_VAR)
      if not secret:
          raise RuntimeError(f"{ENV_VAR} is not set — a session secret is required to start this service")
      return secret


  def hash_password(password: str) -> str:
      return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


  def _verify_password(password: str, password_hash: str) -> bool:
      return bcrypt.checkpw(password.encode(), password_hash.encode())


  def authenticate(pool: ConnectionPool, email: str, password: str) -> int | None:
      """Returns the user id if email+password match a real user, else None —
      callers must turn None into a generic "invalid email or password"
      response, never distinguishing "no such user" from "wrong password"."""
      with pool.connection() as conn:
          row = conn.execute(
              "SELECT id, password_hash FROM users WHERE email = %s", (email,),
          ).fetchone()
      if row is None:
          _verify_password(password, _DUMMY_HASH.decode())  # constant-time-ish: still pay the bcrypt cost
          return None
      user_id, password_hash = row
      if not _verify_password(password, password_hash):
          return None
      return user_id


  def create_session(pool: ConnectionPool, user_id: int) -> str:
      """Inserts a new sessions row and returns a signed JWT whose `jti`
      names it."""
      session_id = uuid.uuid4()
      expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=SESSION_TTL_HOURS)
      with pool.connection() as conn:
          conn.execute(
              "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
              (session_id, user_id, expires_at),
          )
      token = jwt.encode(
          {'sub': str(user_id), 'jti': str(session_id), 'exp': expires_at},
          _session_secret(), algorithm=ALGORITHM,
      )
      logger.info("Issued session %s for user_id=%s", session_id, user_id)
      return token


  def resolve_session(pool: ConnectionPool, token: str) -> tuple[int, str]:
      """Decodes and validates a bearer token, returning (user_id, role) —
      raises ValueError for any reason it isn't currently valid (bad
      signature, expired, or revoked/unknown in `sessions`), so callers can
      map that straight to a 401. Joins `users` in the same query so
      `require_admin` doesn't need a second round trip just to check role."""
      try:
          payload = jwt.decode(token, _session_secret(), algorithms=[ALGORITHM])
      except jwt.PyJWTError as exc:
          raise ValueError("Invalid or expired token") from exc
      with pool.connection() as conn:
          row = conn.execute(
              """
              SELECT sessions.revoked_at, users.role
              FROM sessions JOIN users ON users.id = sessions.user_id
              WHERE sessions.id = %s
              """,
              (payload['jti'],),
          ).fetchone()
      if row is None or row[0] is not None:
          raise ValueError("Session revoked or not found")
      return int(payload['sub']), row[1]


  def revoke_session(pool: ConnectionPool, token: str) -> None:
      """Marks a session revoked (logout) — tolerant of an already-invalid
      token (nothing to revoke) rather than raising, since logout should
      always succeed from the client's point of view."""
      try:
          payload = jwt.decode(token, _session_secret(), algorithms=[ALGORITHM], options={'verify_exp': False})
      except jwt.PyJWTError:
          return
      with pool.connection() as conn:
          conn.execute(
              "UPDATE sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
              (payload['jti'],),
          )
      logger.info("Revoked session %s", payload['jti'])
  ```
- **PATTERN**: `hard_rules.py`'s whole-file shape (docstring → import banner → logger → functions taking `pool: ConnectionPool`).
- **IMPORTS**: `bcrypt`, `jwt` (from `PyJWT`), `psycopg_pool.ConnectionPool` (same import `hard_rules.py:25` uses).
- **GOTCHA**: `jwt.decode` requires `algorithms=[...]` (a list) even for one algorithm, or it raises; `revoke_session` must pass `options={'verify_exp': False}` since an already-expired token should still be revocable (defensive — a client might call logout right at token expiry).
- **GOTCHA**: `payload['sub']` must be cast back to `int` — JWT numeric claims are conventionally strings; storing it as an int elsewhere (e.g. `merchant_id` foreign key patterns in this codebase) will break comparisons if left as `str`.
- **GOTCHA**: `resolve_session` returns role fetched live from `users` on every call, not a role embedded in the JWT at login time — since there's no way to change a user's role short of re-running the bootstrap script (`ON CONFLICT ... DO UPDATE`, see its task below), a live lookup means a role change takes effect on that user's very next request, not just their next login. Don't "optimize" this into a JWT claim; it would go stale silently.
- **VALIDATE**: `python -c "
  import os; os.environ['SESSION_SECRET']='test-secret'
  from backend.online.routing.dashboard import auth
  h = auth.hash_password('correct-horse')
  assert auth._verify_password('correct-horse', h)
  assert not auth._verify_password('wrong', h)
  print('ok')
  "`

### UPDATE backend/online/serving/data_models/schemas.py

- **IMPLEMENT**: Add near the bottom, under a new `# ── Dashboard auth (LP-140) ──` banner:
  ```python
  class LoginRequest(BaseModel):
      email: str
      password: str


  class LoginResponse(BaseModel):
      token: str
  ```
- **PATTERN**: `schemas.py:159-179` (`CreateRuleRequest`, `SetShadowModeRequest`) — plain `BaseModel`, no extra validators.
- **VALIDATE**: `python -c "from backend.online.serving.data_models.schemas import LoginRequest, LoginResponse; LoginRequest(email='a@b.com', password='x')"`

### UPDATE backend/online/serving/dashboard/routes.py

- **IMPLEMENT**: Add imports (`Depends`, `Header`, `HTTPException` already imported — add `Depends`/`Header`; `auth` module) and five new functions (`_resolve_bearer`, `require_auth`, `require_admin`, `login`, `logout`):
  ```python
  from fastapi import Depends, Header, HTTPException

  from backend.online.routing.dashboard import approval_queue, auth, dashboard_data
  ...
  from backend.online.serving.data_models.schemas import (
      CreateRuleRequest, LoginRequest, LoginResponse, ResolveApprovalRequest, SetShadowModeRequest,
  )

  # ── Auth (LP-140) ────────────────────────────────────────────────────────
  def _resolve_bearer(authorization: str | None) -> tuple[int, str]:
      """Shared by require_auth/require_admin: extracts + validates the
      bearer token, or 401s. Not itself a FastAPI dependency (it needs the
      already-extracted header value, not to declare its own Header param)."""
      if not authorization or not authorization.startswith('Bearer '):
          raise HTTPException(status_code=401, detail="Not authenticated")
      router = get_router()
      try:
          return auth.resolve_session(router._db, authorization.removeprefix('Bearer '))
      except ValueError:
          raise HTTPException(status_code=401, detail="Not authenticated")


  def require_auth(authorization: str | None = Header(default=None)) -> int:
      """FastAPI dependency gating every read (GET) /dashboard/api/* route.
      Resolves the bearer token to a user id, or 401s. Any authenticated
      user — viewer or admin — passes this."""
      user_id, _role = _resolve_bearer(authorization)
      return user_id


  def require_admin(authorization: str | None = Header(default=None)) -> int:
      """FastAPI dependency gating every mutating (POST) /dashboard/api/*
      route: create/deactivate a rule, resolve an approval-queue item, or
      toggle shadow mode. Same token validation as require_auth, plus a
      403 for anyone whose role isn't 'admin' — a viewer is authenticated
      but not authorized for these."""
      user_id, role = _resolve_bearer(authorization)
      if role != 'admin':
          raise HTTPException(status_code=403, detail="Admin role required")
      return user_id


  def login(req: LoginRequest) -> LoginResponse:
      router = get_router()
      try:
          user_id = auth.authenticate(router._db, req.email, req.password)
      except Exception:
          logger.exception("Login failed unexpectedly for email=%r", req.email)
          raise HTTPException(status_code=500, detail="Login failed")
      if user_id is None:
          logger.info("Failed login attempt for email=%r", req.email)
          raise HTTPException(status_code=401, detail="Invalid email or password")
      logger.info("Successful login for email=%r user_id=%s", req.email, user_id)
      return LoginResponse(token=auth.create_session(router._db, user_id))


  def logout(authorization: str | None = Header(default=None), user_id: int = Depends(require_auth)) -> dict:
      router = get_router()
      auth.revoke_session(router._db, authorization.removeprefix('Bearer '))
      return {'logged_out': True}
  ```
- **PATTERN**: rest-of-file's `router = get_router()` → delegate → return dict shape; strictness borrowed from `transaction_routing/routes.py:41-50` specifically for `login`/`require_auth` since these are security-critical, per CLAUDE.md's carve-out for justified exceptions to the "looser dashboard style".
- **GOTCHA**: `logout`'s parameter order matters for FastAPI dependency resolution — `user_id: int = Depends(require_auth)` still runs `require_auth` (and therefore still 401s an already-invalid/missing token) even though `user_id` itself isn't used in the body; keep it rather than removing it as "unused", since it's what makes `POST /dashboard/api/logout` itself require a valid session (you can't revoke a session that never proved it was authenticated). `logout` uses `require_auth`, not `require_admin` — a viewer must be able to log themselves out.
- **GOTCHA**: don't collapse `require_auth`/`require_admin` into one function with a role parameter — FastAPI dependencies are resolved by their callable identity via `Depends(...)`, and two distinctly-named zero-config functions are what makes `service.py`'s per-route wiring readable (`dependencies=[Depends(require_auth)]` vs `dependencies=[Depends(require_admin)]` is self-documenting at the call site; a parameterized factory would need `Depends(require_role('admin'))`-style plumbing for no real benefit at this scale — only two roles, four mutating endpoints).
- **VALIDATE**: `python -c "import backend.online.serving.dashboard.routes"` (import-time syntax/reference check)

### UPDATE backend/online/serving/service.py

- **IMPLEMENT**: Add `Depends` to the fastapi import, import `login`, `logout`, `require_auth`, `require_admin` from `dashboard.routes`, add:
  ```python
  from fastapi import Depends, FastAPI
  ...
  from backend.online.serving.dashboard.routes import (
      create_rule,
      deactivate_rule,
      get_bad_bin_benchmark,
      get_decline_anomalies,
      get_live_ar,
      get_merchant_quality,
      get_processor_performance,
      get_rollout_status,
      get_stale_rules,
      list_approval_queue,
      list_merchants,
      list_rules,
      login,
      logout,
      require_admin,
      require_auth,
      resolve_approval,
      set_shadow_mode,
  )
  from backend.online.serving.data_models.schemas import (
      HealthResponse,
      LoginResponse,
      RateLimitsResponse,
      RouteBackfillResponse,
      RouteDecisionResponse,
      VersionResponse,
  )
  ...
  app.post("/dashboard/api/login", response_model=LoginResponse)(login)
  app.post("/dashboard/api/logout", dependencies=[Depends(require_auth)])(logout)

  # Every dashboard route below requires a valid session (require_auth);
  # the four mutating ones additionally require the admin role
  # (require_admin) — a viewer can see everything but change nothing.
  _viewer = [Depends(require_auth)]
  _admin = [Depends(require_admin)]
  app.get("/dashboard/api/live-ar", dependencies=_viewer)(get_live_ar)
  app.get("/dashboard/api/rules", dependencies=_viewer)(list_rules)
  app.get("/dashboard/api/rules/stale", dependencies=_viewer)(get_stale_rules)
  app.post("/dashboard/api/rules", dependencies=_admin)(create_rule)
  app.post("/dashboard/api/rules/{rule_id}/deactivate", dependencies=_admin)(deactivate_rule)
  app.get("/dashboard/api/approval-queue", dependencies=_viewer)(list_approval_queue)
  app.post("/dashboard/api/approval-queue/{item_id}/resolve", dependencies=_admin)(resolve_approval)
  app.get("/dashboard/api/rollout", dependencies=_viewer)(get_rollout_status)
  app.get("/dashboard/api/merchants", dependencies=_viewer)(list_merchants)
  app.post("/dashboard/api/merchants/{merchant_id}/shadow-mode", dependencies=_admin)(set_shadow_mode)
  app.get("/dashboard/api/processor-performance", dependencies=_viewer)(get_processor_performance)
  app.get("/dashboard/api/decline-anomalies", dependencies=_viewer)(get_decline_anomalies)
  app.get("/dashboard/api/merchant-quality/{merchant_id}", dependencies=_viewer)(get_merchant_quality)
  app.get("/dashboard/api/bad-bin-benchmark/{merchant_id}", dependencies=_viewer)(get_bad_bin_benchmark)
  ```
- **PATTERN**: `service.py:79-99`'s existing `app.get(path)(handler)` two-step calls — this only adds a `dependencies=` kwarg to the first call, no structural change.
- **GOTCHA**: `/route/*`, `/health`, `/version`, `/rate-limits` are explicitly OUT of scope — do not add `require_auth`/`require_admin` to any of those; they're the PNE machine-to-machine contract, and the ticket only covers `/dashboard/api/*`.
- **GOTCHA**: don't forget `/dashboard/api/login` must NOT get either dependency (it's how you get a token in the first place) — only `logout` and everything else under `/dashboard/api/` gets one of the two.
- **GOTCHA**: every `app.post(...)` under `/dashboard/api/` except `login` must use `_admin`, not `_viewer` — this is the one place a copy-paste from a neighboring line silently under-protects a mutating endpoint. Double-check each POST line individually against the list above rather than bulk-find-replacing.
- **VALIDATE**: `python -c "from backend.online.serving.service import app; print(sorted(r.path for r in app.routes if r.path.startswith('/dashboard/api')))"` then manually confirm: every path except `/dashboard/api/login` has `require_auth` or `require_admin` in its `dependencies`, and specifically that `create_rule`/`deactivate_rule`/`resolve_approval`/`set_shadow_mode`'s routes carry `require_admin` (inspect via `[r for r in app.routes if r.path=='/dashboard/api/rules' and r.methods=={'POST'}][0].dependant.dependencies`).

### UPDATE Dockerfile (and docker/Dockerfile if both are real — see GOTCHA)

- **IMPLEMENT**: Add pinned versions to the `pip install --no-cache-dir` list:
  ```
      "psycopg[binary,pool]==3.3.4" \
      bcrypt==4.2.1 \
      pyjwt==2.10.1
  ```
  (Check `uv.lock` after the `uv add` step above for the exact resolved versions and pin those instead of guessing — the file's header comment explicitly says "Versions are pinned to match uv.lock exactly".)
- **PATTERN**: `Dockerfile:24-31`'s existing pinned list.
- **GOTCHA**: this repo has both `./Dockerfile` and `./docker/Dockerfile` with near-identical (possibly byte-identical) content — the CI workflow (`.gitea/workflows/ci-cd-workflow.yaml`) builds `docker build ... .` from the repo root, so `./Dockerfile` (not `docker/Dockerfile`) is the one that actually ships. Check whether they're kept in sync (`diff Dockerfile docker/Dockerfile`) and update both if so, to avoid the two silently drifting.
- **VALIDATE**: `docker build --build-arg GIT_SHA=$(git rev-parse HEAD) --tag smartrouting-lp140-test .` completes without a pip resolution error.

### CREATE backend/offline/features/db_bootstrap/create_dashboard_user.py

- **IMPLEMENT**: A small CLI mirroring `seed_merchants_and_gates.py`'s shape — read `--email`/`--role` args plus a `--password` arg (or prompt via `getpass` if password isn't passed, so it never ends up in shell history). `--role` is `required=True, choices=['viewer', 'admin']` — no default, so whoever runs this always consciously picks a role rather than accidentally minting an over-privileged account. Call `auth.hash_password`, insert into `users` with `ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role` (so re-running it for an existing email resets both the password and the role, rather than erroring — useful for promoting a viewer to admin later without a dedicated "change role" tool).
- **PATTERN**: `backend/offline/features/db_bootstrap/seed_merchants_and_gates.py`'s file-header docstring/import-banner convention and its use of `get_pool()` from `db.py`.
- **IMPORTS**: `argparse`, `getpass`, `backend.online.routing.database.db.get_pool`, `backend.online.routing.dashboard.auth.hash_password`.
- **GOTCHA**: this script needs `SESSION_SECRET` NOT set to run (it only hashes a password, never touches JWTs) — don't accidentally import anything from `auth.py` that triggers `_session_secret()` at import time; `hash_password` doesn't, so this is safe as designed above.
- **VALIDATE**: `DATABASE_URL=<local> python -m backend.offline.features.db_bootstrap.create_dashboard_user --email test@example.com --role admin` (prompts for password), then `psql <local> -c "select email, role from users"` shows the row with `role = admin`. Also confirm running it with no `--role` fails argparse validation (`error: the following arguments are required: --role`).

### UPDATE frontend/dashboard/src/api.js

- **IMPLEMENT**: Add token storage helpers and wire them into `request()`:
  ```js
  const TOKEN_KEY = 'smartrouting-dashboard-token'

  export function getToken() {
    return window.localStorage.getItem(TOKEN_KEY)
  }

  export function setToken(token) {
    window.localStorage.setItem(TOKEN_KEY, token)
  }

  export function clearToken() {
    window.localStorage.removeItem(TOKEN_KEY)
  }

  async function request(path, options) {
    const token = getToken()
    const headers = { ...options?.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
    const res = await fetch(path, { ...options, headers })
    if (res.status === 401 && path !== '/dashboard/api/login') {
      clearToken()
      window.location.reload()
      throw new Error('Session expired')
    }
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`${options?.method ?? 'GET'} ${path} -> ${res.status}: ${detail}`)
    }
    return res.json()
  }

  export function login(email, password) {
    return request('/dashboard/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  }

  export function logout() {
    return request('/dashboard/api/logout', { method: 'POST' })
  }
  ```
- **PATTERN**: `api.js`'s existing `request()`/`createRule()` shape (same `Content-Type`/`JSON.stringify` convention as `createRule`).
- **GOTCHA**: the `path !== '/dashboard/api/login'` guard matters — a *failed login* also returns 401, but that must surface as a normal caught error in `Login.jsx` (a wrong-password message), not trigger the global "session expired, reload" behavior.
- **VALIDATE**: `cd frontend/dashboard && npm run build` (catches syntax errors; no test script exists per CLAUDE.md).

### CREATE frontend/dashboard/src/pages/Login.jsx

- **IMPLEMENT**:
  ```jsx
  import { useState } from 'react'
  import { login, setToken } from '../api.js'

  export default function Login({ onLogin }) {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState(null)
    const [submitting, setSubmitting] = useState(false)

    async function submit(e) {
      e.preventDefault()
      setSubmitting(true)
      setError(null)
      try {
        const { token } = await login(email, password)
        setToken(token)
        onLogin()
      } catch (e) {
        setError('Invalid email or password')
      } finally {
        setSubmitting(false)
      }
    }

    return (
      <div className="app">
        <main>
          <form className="rule-form" onSubmit={submit} style={{ maxWidth: 360, margin: '80px auto' }}>
            <div className="rule-form-section-title">Sign in</div>
            <div className="rule-form-row">
              <label>
                Email
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </label>
              <label>
                Password
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </label>
            </div>
            {error && <p className="error">{error}</p>}
            <div className="rule-form-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </div>
          </form>
        </main>
      </div>
    )
  }
  ```
- **PATTERN**: `RulesManager.jsx`'s controlled-form shape (`useState` per field, `submit(e)` with `e.preventDefault()`, `error` state rendered via `.error` class); reuses `.rule-form`/`.rule-form-row`/`.rule-form-actions` classes from `styles.css:340-399` rather than inventing new ones.
- **GOTCHA**: the generic `'Invalid email or password'` message must be shown regardless of what the backend actually returned (don't render `e.message`, which would leak the raw `401: Invalid email or password` HTTP detail text verbatim — that's fine content-wise here since the backend detail is already generic, but keep the frontend hardcoding it too as defense-in-depth against a future backend change).
- **VALIDATE**: visual check via Level 5 browser validation below.

### UPDATE frontend/dashboard/src/App.jsx

- **IMPLEMENT**: Add a token `useState` (initialized from `getToken()`), a `/login` route, and gate the rest:
  ```jsx
  import { useEffect, useState } from 'react'
  import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
  import Overview from './pages/Overview.jsx'
  import MerchantManager from './pages/MerchantManager.jsx'
  import PartnerManager from './pages/PartnerManager.jsx'
  import RulesManager from './pages/RulesManager.jsx'
  import ApprovalQueuePage from './pages/ApprovalQueuePage.jsx'
  import Login from './pages/Login.jsx'
  import { clearToken, getToken, logout } from './api.js'

  ...

  export default function App() {
    const [theme, setTheme] = useState(getInitialTheme)
    const [token, setTokenState] = useState(getToken)

    useEffect(() => {
      document.documentElement.dataset.theme = theme
      window.localStorage.setItem(THEME_KEY, theme)
    }, [theme])

    if (!token) {
      return <Login onLogin={() => setTokenState(getToken())} />
    }

    async function handleLogout() {
      try {
        await logout()
      } finally {
        clearToken()
        setTokenState(null)
      }
    }

    return (
      <div className="app">
        <header className="app-header">
          ...
          <button type="button" className="theme-toggle-btn" onClick={handleLogout}>
            Log out
          </button>
          <button type="button" className="theme-toggle-btn" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
          </button>
        </header>
        <main>
          ... (unchanged nav + Routes, plus:)
          <Routes>
            <Route path="/login" element={<Navigate to="/overview" replace />} />
            ... (existing routes unchanged)
          </Routes>
        </main>
      </div>
    )
  }
  ```
- **PATTERN**: `App.jsx`'s existing `useState`/`useEffect` theme-toggle shape — the auth gate uses the exact same "plain `useState`, no Context" convention, just an early `return <Login .../>` instead of a `<Route>`-level guard, since login isn't really part of the same nav-having shell.
- **GOTCHA**: a logged-in user manually navigating to `/login` should just land on `/overview` (the `<Route path="/login" element={<Navigate to="/overview" replace />} />` above) — since `token` is truthy by the time `<Routes>` renders at all, `/login` as a real route only matters for that edge case, not for the primary gate (which is the `if (!token) return <Login .../>` short-circuit before `<Routes>` is reached).
- **VALIDATE**: covered by Level 5 browser validation below.

---

## TESTING STRATEGY

Per CLAUDE.md's "Testing conventions — honest state": this codebase has zero automated coverage for `backend/online/` or `frontend/dashboard/`, and CI's `python -m unittest -v` step installs no dependencies. Since `auth.py` needs `bcrypt`/`PyJWT` (not stdlib), a `unittest.TestCase` for it would break CI exactly as CLAUDE.md warns — adding one is explicitly out of scope unless a `pip install` step is also added to `.gitea/workflows/ci-cd-workflow.yaml`, which the ticket doesn't ask for. This plan therefore relies on manual + browser validation, matching this repo's actual (not aspirational) testing posture.

### Unit Tests

None added — see rationale above. The one existing test (`tests/test_smoke.py`) must still pass unmodified.

### Integration Tests

None added (no DB-backed test harness exists in this repo today — would be a separate, larger effort).

### Edge Cases

- Login with a nonexistent email → generic 401, same message/timing profile as a wrong password for a real email (`_DUMMY_HASH` check in `auth.authenticate`).
- Expired token → `jwt.decode` raises `ExpiredSignatureError` → `resolve_session` raises `ValueError` → 401.
- Revoked (logged-out) token reused → `sessions.revoked_at IS NOT NULL` → `ValueError` → 401.
- Malformed/missing `Authorization` header → `require_auth`'s own check → 401 (never reaches `resolve_session`).
- Logout called twice with the same token → second call is a no-op (`WHERE revoked_at IS NULL` guard in `revoke_session`'s `UPDATE`), still returns `{'logged_out': True}`.
- `/route/*`, `/health`, `/version`, `/rate-limits` remain reachable with zero auth — regression-check this explicitly, it's the easiest thing to break by over-applying `require_auth`/`require_admin`.
- A `viewer`-role user hitting a read endpoint (e.g. `GET /dashboard/api/rules`) → 200, same as `admin`.
- A `viewer`-role user hitting a mutating endpoint (e.g. `POST /dashboard/api/rules`) → 403 (authenticated, not authorized) — distinct from the 401 an unauthenticated request gets.
- An `admin`-role user hitting every endpoint (read and write) → 200 in all cases.

### E2E / Browser Automation

- Happy path: load `/dashboard/overview` while logged out → redirected to the login form (no dashboard chrome visible) → submit a bootstrapped admin user's real credentials → land on `/dashboard/overview` with the nav bar and live-AR data visible → click "Log out" → redirected back to the login form.
- Error paths: submit wrong password → generic "Invalid email or password" shown inline, still on the login form, no navigation; submit empty fields → browser's native `required` validation blocks submission (no request sent — confirm via network inspection or `agent-browser errors`); log in as a bootstrapped viewer, navigate to Rules, submit the create-rule form → since the UI doesn't hide write controls for a viewer, this should visibly fail (an error surfaced from the 403 — whatever `RulesManager.jsx`'s existing `catch (e) { setError(e.message) }` renders) rather than silently succeeding or crashing the page.
- Screenshots required: login form (empty), login form (error state after wrong password), dashboard overview immediately after successful admin login, the 403 error state after a viewer attempts a write action, login form again immediately after logout.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

No linter/formatter configured in this repo (CLAUDE.md) — skip. Rely on Python import checks and `npm run build` as the syntax gate:
```bash
python -c "import backend.online.serving.service"
cd frontend/dashboard && npm run build
```

### Level 2: Unit Tests

```bash
python -m unittest -v
```

### Level 3: Integration Tests

N/A — none exist in this repo for this layer (see Testing Strategy).

### Level 4: Manual Validation

```bash
# 1. Bring up Postgres + the service locally (adjust to however you normally run it, e.g. docker/docker-compose.yml)
export DATABASE_URL=postgresql://smartrouting:<pw>@localhost:5432/smartrouting
export SESSION_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Bootstrap an admin and a viewer
python -m backend.offline.features.db_bootstrap.create_dashboard_user --email admin@example.com --role admin
python -m backend.offline.features.db_bootstrap.create_dashboard_user --email viewer@example.com --role viewer

# 3. Start the API
uvicorn backend.online.serving.service:app --port 8080 &

# 4. Confirm the dashboard is locked without a token
curl -i http://localhost:8080/dashboard/api/merchants   # expect 401

# 5. Log in as each
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8080/dashboard/api/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"<whatever was entered>"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
VIEWER_TOKEN=$(curl -s -X POST http://localhost:8080/dashboard/api/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"viewer@example.com","password":"<whatever was entered>"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 6. Confirm both tokens can read
curl -i http://localhost:8080/dashboard/api/merchants -H "Authorization: Bearer $ADMIN_TOKEN"   # expect 200
curl -i http://localhost:8080/dashboard/api/merchants -H "Authorization: Bearer $VIEWER_TOKEN"  # expect 200

# 7. Confirm only the admin can write
curl -i -X POST http://localhost:8080/dashboard/api/rules -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"rule_type":"hold","created_by":"test","reason":"smoke test"}'   # expect 200/201
curl -i -X POST http://localhost:8080/dashboard/api/rules -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H 'Content-Type: application/json' -d '{"rule_type":"hold","created_by":"test","reason":"smoke test"}'   # expect 403

# 8. Confirm PNE-facing routes are untouched
curl -i http://localhost:8080/health   # expect 200, no auth needed

# 9. Log out the admin, then confirm that token is now rejected
curl -i -X POST http://localhost:8080/dashboard/api/logout -H "Authorization: Bearer $ADMIN_TOKEN"
curl -i http://localhost:8080/dashboard/api/merchants -H "Authorization: Bearer $ADMIN_TOKEN"   # expect 401
```

### Level 5: E2E / Browser Automation

Run the `agent-browser` skill to validate the feature end-to-end in a real browser.

```bash
# Start dev server
cd frontend/dashboard && npm run dev &
# ...with the FastAPI backend also running per Level 4 steps 1-3

agent-browser open http://localhost:5173/dashboard/overview
agent-browser snapshot -i
agent-browser screenshot screenshots/LP-140-login-empty.png

# Wrong password
agent-browser fill <email-input> ops@example.com
agent-browser fill <password-input> wrong-password
agent-browser click <sign-in-button>
agent-browser screenshot screenshots/LP-140-login-error.png

# Correct password
agent-browser fill <password-input> <real-password>
agent-browser click <sign-in-button>
agent-browser snapshot -i
agent-browser screenshot screenshots/LP-140-dashboard-after-login.png

# Logout
agent-browser click <logout-button>
agent-browser screenshot screenshots/LP-140-after-logout.png

# Viewer role: log in as the bootstrapped viewer, attempt a write action
agent-browser fill <email-input> viewer@example.com
agent-browser fill <password-input> <viewer-password>
agent-browser click <sign-in-button>
agent-browser click <rules-nav-link>
# ... fill and submit the create-rule form ...
agent-browser screenshot screenshots/LP-140-viewer-403.png

agent-browser errors
agent-browser close
```

Save all screenshots to `screenshots/` and include the paths in the completion checklist.
See `.claude/skills/agent-browser/SKILL.md` for the full command reference and E2E Testing Protocol.

### Level 6: Additional Validation (Optional)

None applicable — no relevant MCP servers configured for this repo's stack beyond what's already covered above.

---

## ACCEPTANCE CRITERIA

- [ ] Unauthenticated access to any dashboard page redirects to login.
- [ ] Valid login issues a token; invalid credentials return a generic error (no user-enumeration).
- [ ] All `/dashboard/api/*` endpoints reject requests without a valid token (401).
- [ ] Logout clears session both client- and server-side.
- [ ] Passwords hashed, never logged or stored plaintext.
- [ ] `python -m unittest -v` still passes.
- [ ] `/route/*`, `/health`, `/version`, `/rate-limits` remain unauthenticated (explicit regression check, not in the original ticket text but implied by "don't break the PNE integration").
- [ ] A `viewer`-role user can read every dashboard analytics endpoint but gets 403 on all four mutating endpoints (create/deactivate rule, resolve approval, set shadow mode) — added scope beyond the original ticket text, confirmed explicitly in planning.
- [ ] An `admin`-role user can do everything a `viewer` can plus all four mutating actions.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (`python -m unittest -v`)
- [ ] `npm run build` passes with no errors
- [ ] Level 5 agent-browser E2E validation passed (screenshots saved to `screenshots/`)
- [ ] Manual testing (Level 4) confirms the full login → protected-call → logout → rejected-call cycle
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

This plan's design decisions below were made through direct discussion, not assumed — recorded here so the rationale survives past this planning session:

- **Role-based access (viewer/admin) is IN scope**, decided in planning even though the ticket text itself never mentions roles — it only asks for authenticated-vs-not. The team confirmed a handful of named individuals will use this, some of whom should only observe (analytics, rule/queue state) without being able to change hard rules, resolve approvals, or flip shadow mode. The GET=viewer / POST=admin split was confirmed to map cleanly onto the existing endpoint list with zero exceptions — no endpoint needed special-casing outside that rule.
- **No role-conditional UI rendering** — a viewer sees the exact same dashboard as an admin, including write controls; clicking one just surfaces a 403 error. This was an explicit trade-off (smaller, lower-risk frontend diff now) over hiding/disabling controls per role, which would have touched `RulesManager.jsx`, `ApprovalQueuePage.jsx`, and `MerchantManager.jsx`. Revisit if viewer confusion becomes a real complaint.
- **User provisioning stays CLI-only** (`create_dashboard_user.py`, `--role` required) — no admin UI for creating/promoting users. Confirmed appropriate for the current team size; would need revisiting (a real user-management page) if the operator roster grows significantly or turns over often.
- **No account lockout / brute-force rate limiting** and **no password complexity policy** — both explicitly descoped. The threat model here is a small set of named, trusted operators with bcrypt-hashed passwords, not a public-facing signup surface; both would add real implementation surface (a counter/lockout table and unlock path, or password-strength validation) for marginal benefit at this scale. Revisit if this dashboard's exposure ever changes (e.g. becomes internet-facing beyond a VPN).
- **No new automated tests, no CI pip-install step** — confirmed explicitly rather than just inherited from the rest of the codebase's zero-coverage posture, since this is security-sensitive logic where "should we test this" is a real question, not an oversight. Manual curl walkthrough (Level 4) plus `agent-browser` E2E (Level 5) are the actual validation for this ticket.
- **JWT + DB-backed sessions, not pure stateless JWT**: the ticket's acceptance criteria require logout to work server-side ("Logout clears session both client- and server-side"), which a pure stateless JWT can't do without a way to invalidate an already-issued token before its `exp`. The `sessions` table (checked on every request) is the minimal way to get that without introducing a separate cache/store this codebase doesn't otherwise have — it costs one extra point-read per authenticated request, in a codebase that already does several DB round trips per dashboard request (see `dashboard/routes.py`'s existing handlers).
- **`dependencies=[Depends(require_auth)]` per-route, not an `APIRouter`**: considered wrapping all `/dashboard/api/*` routes in an `APIRouter(dependencies=[...])` for a smaller diff and less risk of forgetting one route, but rejected it — `service.py` doesn't use `APIRouter` anywhere today, and introducing one just for this would be a structural change beyond what the ticket needs. The trade-off: a future new dashboard endpoint could forget the dependency. Flagging this explicitly since it's a real, if small, foot-gun — worth a one-line reminder comment in `service.py` above the dashboard route block.
- **Kubernetes/CI secret wiring is NOT part of this plan's tasks**: `kubernetes/deployment.yaml` sources `DATABASE_URL` from a `secretKeyRef` populated by `.gitea/workflows/ci-cd-workflow.yaml`'s `# GNC_KUBERNETES_SECRET_COMMANDS_BEGIN/END` block (which looks auto-generated by an internal scaffolding tool, per `pyproject.toml`'s `[tool.gnc.repository] extends = "python-service"`). Deploying this feature to the actual cluster will additionally require: (1) a real `SESSION_SECRET` value added to Gitea's repo/org secrets, (2) a new `kubectl create secret` step in the CI workflow mirroring the existing `db-credentials` one, (3) a new env entry in `deployment.yaml` referencing it. This is an ops/deploy action requiring a human to actually generate and store the secret value — it's called out here so it isn't missed, but isn't listed as an automated task since it can't be done blindly by an implementation agent.
- **Session TTL** is a hardcoded `SESSION_TTL_HOURS = 12` constant in `auth.py`, not a `config` table entry — it's not something ops needs to retune without a redeploy per the ticket, so putting it in the DB-backed config layer would be unjustified complexity for this feature (see CLAUDE.md's "two config layers" guidance).
- **`requirements.txt`** at repo root is stale/unused (references `SQLAlchemy`/`redis`, neither used anywhere in `backend/`; the real Docker build installs from `Dockerfile`'s hardcoded list, and CI's test step installs nothing). Deliberately not touching it — adding `bcrypt`/`PyJWT` there would imply it matters when it doesn't.

**Confidence Score: 8/10** for one-pass implementation success. The three biggest risks: (1) exact PyJWT error-handling edge cases (make sure `jwt.PyJWTError` catches both `ExpiredSignatureError` and `InvalidSignatureError` — it does, they're both subclasses), (2) the `agent-browser` E2E step's selectors will need to be filled in against the actual rendered DOM (the plan gives placeholders like `<email-input>` since the real accessibility tree isn't known until the page is built and running), and (3) the `service.py` wiring task's easiest-to-miss mistake: pasting `_viewer` instead of `_admin` on one of the four mutating routes — the VALIDATE step there specifically checks for this, don't skip it.
