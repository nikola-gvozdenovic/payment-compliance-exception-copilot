# Frontend dashboard

On-demand context for `frontend/dashboard/` — a React + Vite operator dashboard for
SmartRouting (merchant/partner management, approval queue, rules, live overview). Load
this before adding a page, a component, or an API call.

---

## Stack

- React 18.3.1 + react-dom 18.3.1 (`package.json:12-13`), Vite 8.1.4 with
  `@vitejs/plugin-react` (`package.json:17-18`), `react-router-dom ^6.28.0` as the
  only routing library (`package.json:14`). Pure JS/JSX — no TypeScript, no
  `.ts`/`.tsx` files anywhere.
- No state-management library, no CSS framework, no charting library, no HTTP client
  library (no axios) — only 3 runtime deps total.
- Scripts: `npm run dev` / `npm run build` / `npm run preview`
  (`package.json:7-9`). **No `lint` or `test` script exists**, and no
  `.eslintrc`/`eslint.config.*`/`.prettierrc` file exists anywhere — despite one
  stray `// eslint-disable-next-line react-hooks/exhaustive-deps` comment
  (`ApprovalQueuePage.jsx:26`) implying an ESLint setup was assumed at some point but
  never checked in. Don't assume a lint gate exists.
- `vite.config.js:6-18` — `base: '/dashboard/'` matches where FastAPI mounts the
  built assets in production (see `backend/online/serving/service.py`'s
  `StaticFiles` mount). The dev server proxies `/route`, `/health`, `/rate-limits`,
  `/dashboard/api` to `http://localhost:8080` so the app is always same-origin, dev
  and prod — there is no CORS handling anywhere because of this. Keep any new backend
  route under one of these proxied prefixes if the dashboard needs to call it in dev.
- **No tests exist for the frontend at all** — no `*.test.jsx`, no testing library in
  `package.json`. Be honest about this; don't claim frontend test coverage.

## Entry point / routing

- `main.jsx:7-13` — standard Vite/React 18 entry:
  `ReactDOM.createRoot(...).render(<React.StrictMode><BrowserRouter
  basename={import.meta.env.BASE_URL}><App /></BrowserRouter></React.StrictMode>)`.
- `App.jsx` is the single top-level component; all routing lives in one file — five
  flat top-level `<Route>`s (`App.jsx:75-82`), `<Navigate to="/overview" replace />`
  as the default redirect. No nested/dynamic route params, no lazy-loading or
  code-splitting.
- Nav styling helper: `navClass({isActive}) => isActive ? 'active' : ''`
  (`App.jsx:15-17`) used with `<NavLink>` — reuse this for any new nav link.
- Theme (dark/light) is the only "global" client state in the app: local `useState` +
  `useEffect`, persisted to `localStorage` under `smartrouting-dashboard-theme`,
  applied via `document.documentElement.dataset.theme` (`App.jsx:9-25`). It lives in
  `App.jsx`, not a dedicated store/context — there is no Context API usage anywhere
  in the codebase (`useContext`/`createContext` don't appear).

## API layer (`src/api.js`)

- Plain `fetch`, no axios. One wrapper, `request(path, options)` (`api.js:4-11`):
  awaits `fetch`, throws `new Error(`${method} ${path} -> ${status}: ${detail}`)` on
  `!res.ok` (reading the error body as text), otherwise returns `res.json()`. Use
  this wrapper for any new API call rather than calling `fetch` directly.
- **No base URL** anywhere — every call is a relative path (`/health`,
  `/dashboard/api/...`); the dev proxy + prod same-origin serving make this
  unnecessary.
- **No auth header handling anywhere** — no `Authorization` header, no token
  storage/refresh. If auth is ever added, it doesn't exist yet as a pattern to copy.
- `qs(params)` (`api.js:20-25`) filters `undefined`/`null`/`''` and URL-encodes —
  used by every GET-with-params call. Use it for any new filtered GET.
- POST calls each inline `headers: {'Content-Type': 'application/json'}, body:
  JSON.stringify(...)` — no shared POST-JSON helper; this repetition (13 exported
  one-liner functions total, `api.js:13-93`) is the existing convention, not
  something to "fix" unilaterally in an unrelated change.
- Every exported function name is `get*`/`create*`/`set*`/`resolve*`/`deactivate*`,
  one per backend endpoint — name new ones the same way.
- `api.js:18` cross-references the backend handler location
  (`backend/online/serving/dashboard/routes.py`) directly in a comment — keep doing
  this for new endpoints so the frontend/backend pairing stays discoverable.

## Pages (`src/pages/*.jsx`)

All five pages (`ApprovalQueuePage`, `MerchantManager`, `Overview`, `PartnerManager`,
`RulesManager`) are function components using only local `useState`/`useEffect` — no
custom hooks exist anywhere.

- **Preferred data-fetching pattern** (use this for a new page): a `cancelled`-guard
  inside `useEffect`:
  ```jsx
  useEffect(() => {
    let cancelled = false
    async function load() {
      // ...fetch...
      if (!cancelled) setState(result)
    }
    load()
    return () => { cancelled = true }
  }, [deps])
  ```
  Seen in `MerchantManager.jsx:36-58`, `Overview.jsx:31-51`,
  `PartnerManager.jsx:30-55`. This avoids stale-state updates when dependencies
  change rapidly (e.g. `MerchantManager.jsx:38,55-57` toggling `merchantId`).
- `ApprovalQueuePage.jsx:14-27` and `RulesManager.jsx:40-53` instead use an
  unguarded `refresh()` called from `useEffect` on mount **and again after a
  mutation** (`ApprovalQueuePage.jsx:34-35`, `RulesManager.jsx:85,93`). This
  refresh-after-write reuse is a legitimate, distinct need — not simply a worse
  version of the guarded pattern — keep it for post-mutation reloads, but prefer the
  `cancelled`-guarded shape for a page's initial/dependency-driven load.
- **Polling** exists only in `Overview.jsx`: `POLL_MS = 15000`
  (`Overview.jsx:5`), `setInterval(load, POLL_MS)` inside the effect, cleared on
  unmount. No other page polls.
- **Filtering**: raw fetched data stays in state; `filtered*` values are derived via
  `.filter(...)` in the render body (not memoized with `useMemo` anywhere), against
  one `useState` per filter field (e.g. `Overview.jsx:18-29` has 7 separate filter
  state variables). Follow this — don't introduce `useMemo` or a filter-reducer
  pattern that doesn't match the rest of the app.
- **`uniqueSorted(values)`** (`[...new Set(values)].sort()`) is currently
  re-declared locally in three files (`MerchantManager.jsx:5-7`, `Overview.jsx:7-9`,
  `PartnerManager.jsx:7-9`) instead of a shared util. **Don't add a fourth copy** — if
  a fourth page needs it, extract it into a new `src/utils.js`.
- **Error handling**: every page has one `error` state (`useState(null)`), set from
  `e.message` in a `catch`, rendered as `{error && <p className="error">{error}</p>}`
  directly under the panel header — identical across all five pages. Match this for
  any new page.
- Naming: components are `PascalCase` function declarations matching the filename
  exactly, `export default function ComponentName()`. Helper functions inside
  components are `camelCase` (`refresh`, `load`, `act`, `togglePause`,
  `lifecycleFor`, `submit`, `handleDeactivate`, `update`).
- No PropTypes, no TypeScript — no prop-shape validation anywhere. Don't add one in
  isolation; it wouldn't match anything else in the app.
- Each page's top comment cites a spec section ("brief §5.1" etc.) and the backend
  file it corresponds to (e.g. `ApprovalQueuePage.jsx:4-7` →
  `backend/online/routing/dashboard/approval_queue.py:resolve`) — keep this
  cross-referencing convention for new pages.

## Shared component (`src/components/ARBar.jsx`)

The only reusable component in the app. Pattern: derive a `tier` (`good`/`warn`/
`critical`) from threshold props (`ar`, `goodAt = 0.8`, `warnAt = 0.6`), map to a CSS
class suffix (`ar-bar-${tier}`), guard `null`/`undefined` by rendering `<span
className="muted">no data</span>` (`ARBar.jsx:6-9`). Use this null-guard-then-render
idiom for any new small-value display component. Its top comment references reusing
a `.usage-bar` pattern from a `RateLimitsPanel.jsx` — **that file doesn't exist
anywhere in the repo**; it's a dangling/stale comment, ignore the reference.

## Styling (`src/styles.css`)

Single global plain CSS file (no CSS Modules, no Tailwind, no styled-components/
Emotion), imported once at `main.jsx:5`. CSS custom properties for a design-token
system (`:root { --bg, --panel-bg, --text, --accent, ... }`, `styles.css:1-28`), with
a light-theme override under `:root[data-theme='light']` (`styles.css:30-40`), driven
by the `data-theme` attribute `App.jsx` sets. Class naming is plain kebab-case,
semantic/BEM-ish (`panel-header-row`, `data-table`, `usage-bar-fill`, `badge-ok`).
Add new styles to this one file following the same token/class-naming approach —
don't introduce a second styling system for one component.
