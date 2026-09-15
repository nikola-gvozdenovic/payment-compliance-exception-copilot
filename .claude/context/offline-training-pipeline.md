# Offline training pipeline

On-demand context for `backend/offline/`. Load this before touching feature
engineering, the feature store, model training, or the promotion/backtest gate.

---

## Pipeline shape — two data models, on purpose

- **`dataset_building/`** (`attempt_sequencing.py`, `balanced_sampling.py`,
  `build_dataset.py`, `dataset_helpers.py`, `feature_computation.py`) is 100%
  stdlib `dict`/`list[dict]`-based — zero pandas imports, CSV written via
  `csv.DictWriter`. This is intentional: the forward pass needs O(1) mutable running
  state per row (`RunningStats`, `defaultdict`s), which pandas vectorization doesn't
  suit.
- Everything downstream — `feature_store/aggregation.py`, `db_bootstrap/*.py`,
  `training/*.py`, `evaluation/*.py` — reads that same CSV back with `pd.read_csv`
  and works in pandas/numpy.
- Know which half of the pipeline you're editing: dict-based feature computation vs.
  pandas-based aggregation/training. Don't introduce pandas into
  `dataset_building/` or dict-based logic into the pandas half without a real reason.

## CLI convention

Every runnable module uses `argparse` (never `click`) and is invoked as
`python -m backend.offline...` from repo root — documented in each file's module
docstring (e.g. `build_dataset.py:16-19`). Every one ends with the same tail:
```python
if __name__ == '__main__':
    logging.basicConfig(...)
    main()
```
(`build_dataset.py:126-128`, `store.py:74-76`, `train_model.py:202-204`,
`check_model_accuracy.py:168-170`). Match this shape for any new offline script.

## Leakage avoidance — a repeated, load-bearing invariant

"Never test on data you trained on" shows up independently at every stage:
- `feature_computation.py:107-109` — "check the scoreboards BEFORE updating them";
  running stats dicts are only updated *after* the row is emitted
  (`feature_computation.py:233-236`).
- `feature_store/aggregation.py:24-29` — train = all but the last day.
- `training/data_prep.py:31-51` — `time_split()` (train = all-but-last-day, test =
  last day) plus `walk_forward_folds()` expanding-window CV.

Any new feature or training change must preserve this — never let a feature computed
using future-relative-to-the-row data leak into training.

## `spec.py` — single source of truth

`backend/offline/features/spec.py:1-96` defines `CAT_FEATURES`/`NUM_FEATURES`/
`ALL_FEATURES`/`FIELDNAMES`/`LABEL_COLUMN`, explicitly to prevent drift across
`build_dataset.py`, `train_model.py`, and the online `router.py` (`spec.py:11-18`).
`features/__init__.py` just re-exports it for a shorter import path. **If you add or
rename a feature, `spec.py` is the one place to change it** — don't hardcode a
feature list anywhere else.

## Feature store

- `data/feature_store.json` — plain JSON dict with keys `meta, bin_processor,
  country_processor, card_type_processor, currency_processor, processor_global,
  bin_processor_attempt, processor_attempt_global, processor_amount_stats,
  processor_inventory`. Rate entries look like `{'approvals': N, 'total': N, 'rate':
  float}`.
- `aggregation.py` (`build_store(df: pd.DataFrame) -> dict`,
  `feature_store/aggregation.py:20-109`) is pure logic — groupby/agg on a DataFrame.
  `store.py` is execution-only: `pd.read_csv('data/ml_features.csv', dtype={'bin':
  str})` → `build_store` → plain `json.dump` (no indent) to `data/feature_store.json`
  (`store.py:40-47`).
- Fresh-only (attempt 1) rows feed the baseline rate tables; the full `train` set
  (all attempts) feeds the attempt-level tables (`aggregation.py:36-37,61-69`).

## DB bootstrap / seeding scripts

All 5 scripts in `db_bootstrap/` (`country_currency.py`, `decline_code_taxonomy.py`,
`decline_recovery_aggregation.py`, `seed_merchants_and_gates.py`,
`segment_bandit_seed.py`) share one shape: `pd.read_csv('data/ml_features.csv', ...)`
→ a pure aggregation function → `write_to_db()` using raw parameterized SQL with
`ON CONFLICT ... DO UPDATE` upserts, run via `python -m
backend.offline.features.db_bootstrap.<name>`, requiring `DATABASE_URL`.

These scripts reach directly into `backend/online/routing/...` internals (`database`,
`eligibility.gates`, `decline_codes.decline_classification`,
`live_learning.decline_recovery`, `live_request.scoring.segments`) — the offline
bootstrap layer is tightly coupled to online serving internals by design, not
isolated. Empirically-validated thresholds are hardcoded module constants with
rationale comments — e.g. `MIN_SUPPORT = 20`, `MIN_PURITY = 0.90`
(`country_currency.py:37-38`), `MIN_VOLUME = 10` (`seed_merchants_and_gates.py:36`).
Don't change these without the same kind of empirical justification.

## Fetching external data (`fetching/`)

- OAuth 1.0 HMAC-SHA1 signing is hand-rolled with stdlib only (`hashlib`, `hmac`,
  `base64.b64encode`, `urllib.parse`) — `fetching/oauth.py:1-53`. No
  `requests-oauthlib`.
- `fetch.py` uses stdlib `urllib.request` (not `requests`), handles gzip manually
  (`fetch.py:59-63`), decodes with `utf-8-sig` to strip a BOM (`fetch.py:63`).
- `ALTITUDEPAY_CONSUMER_KEY`/`SECRET` missing → hard `SystemExit` with a helpful
  message (`fetch.py:26-36`) — required, fails fast. Contrast with `backend/utils/
  fx.py`'s `XE_ACCOUNT_ID`/`XE_API_KEY`, which are optional and degrade to
  cached/static rates if unset (`fx.py:46-49,64-67`) — this required-vs-optional
  split is deliberate (`.env.example:4-10`).
- CSV parsing auto-detects delimiter (`;` vs `,`) and skips a possible header/banner
  line by checking whether the first field is literally `'Txid'`
  (`fetch.py:66-75`) — a defensive but fragile heuristic; be aware of it if the
  export format ever changes upstream.

## Training

- The real model is `sklearn.ensemble.HistGradientBoostingClassifier`
  (`trainer.py:15,40-51`) — **not** lightgbm or xgboost, despite both being declared
  in `pyproject.toml`. Chosen because it "handles NaN natively, no libomm
  dependency" (`train_model.py:1-4`).
- **One binary classifier per processor**, not one global model
  (`trainer.py:22-56`), with `class_weight` computed from the neg/pos ratio to
  counter class imbalance.
- Categorical encoding: `sklearn.preprocessing.OrdinalEncoder(handle_unknown=
  'use_encoded_value', unknown_value=np.nan)` (`data_prep.py:54-66`).
- CLI: `python -m backend.offline.training.train_model --save-models --models-dir
  data/models_candidate` (matches `.gitea/workflows/retrain.yml:44` exactly). Flags:
  `--input`, `--top` (default `'4'`), `--min-train-days` (default 2),
  `--min-train-rows` (default 20), `--save-models`, `--models-dir` (default
  `data/models`) — `train_model.py:53-64`.
- Saved as a dict bundle, not the bare model: `pickle.dump({'model': model,
  'encoder': enc_final, 'processor_name': proc}, f)` (`train_model.py:184-185`).
- Filename = processor name with `' '→'_'`, `'/'→'-'` (`train_model.py:182-183`) —
  e.g. `data/models/SND_MC_-_Altitudepay.pkl`. Per-**processor**, not per-merchant.
- `--save-models` clears stale `*.pkl` files in the target dir first
  (`train_model.py:138-140`) — the router loads every `.pkl` it finds, so a stale
  file would leak into serving if left behind.
- SHAP explanation is logged, not persisted — `shap.Explainer` sampled to 2000 rows
  (`shap_report.py:29-45`).

## Evaluation / promotion gate

- `check_model_accuracy.py:run()` is the shared scoring methodology, reused directly
  by `deploy_model_if_better.py` (`from ...check_model_accuracy import run as
  evaluate`) — the same function drives both the standalone accuracy report and the
  production promotion gate.
- Methodology: for every multi-attempt txid on the held-out last day that was
  eventually approved, compare the actual attempt-position of the winning processor
  vs. the model's predicted rank, restricted to processors actually tried
  (`check_model_accuracy.py:50-136`, `accuracy_check_helpers.restricted_cascade`).
- **Promotion gate**: `deploy_model_if_better.py`, invoked by `.gitea/workflows/
  retrain.yml:47` as `python -m backend.offline.evaluation.deploy_model_if_better
  --candidate-models-dir data/models_candidate`.
  - `DEFAULT_MAX_REGRESSION = 0.15` (avg attempt position may worsen by at most this
    much) — explicitly flagged in-code as "a placeholder tolerance for the business
    to tune ... not something to treat as final" (`deploy_model_if_better.py:47`).
    Don't treat this constant as sacred; it's known to need revisiting.
  - On rejection: writes an `approval_queue` row with `kind='retrain_rejected'`
    (`deploy_model_if_better.py:83-98`) and returns a controlled non-zero exit (not
    an exception) — CI consumes the exit code, production stays untouched.
  - On pass: `model_registry.push_version(pool, new_version, models, store_json)`
    where `new_version = int(time.time())` (`deploy_model_if_better.py:132-139`) —
    the real, wired integration point with online serving's model registry (see
    `.claude/context/pne-cascade-engine.md` / `database-and-config.md` for how the
    running service picks this up).
- `replay_for_demo.py` is explicitly **not** a rigorous backtest — its own docstring
  says so in bold: "this is NOT a rigorous counterfactual backtest ...
  check_model_accuracy.py already does that" (`replay_for_demo.py:7-26`). It's a
  shadow-mode demo/data-population tool, dependent on `db_bootstrap/
  seed_merchants_and_gates.py` having already run.

## Known duplication — don't add a fourth copy

The pandas-NaN guard `_s()` (pandas gives `NaN`, a truthy float, for empty CSV cells;
`val or ''` silently lets it through) is copy-pasted identically in three files:
`db_bootstrap/segment_bandit_seed.py:36-43`, `evaluation/accuracy_check_helpers.py:
21-23`, `evaluation/replay_for_demo.py:58-60`. If a fourth file needs this, centralize
it into a shared helper instead of copying it again.
