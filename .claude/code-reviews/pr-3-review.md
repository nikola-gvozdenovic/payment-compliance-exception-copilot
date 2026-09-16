# PR #3 Review — feat: TICKET-4 RAG ingestion, embedding, and retrieval pipeline

**Reviewer:** `piv-review-pr` agentic gate (deep pass dispatched to the `code-reviewer` subagent, fresh context)
**Branch:** `feat/ticket-4-rag-pipeline` → `main`
**Commit reviewed:** `ab60156`

## Summary

Reviewed every changed file in full plus the implementation plan and corpus files the pipeline actually ingests. Both real bugs documented in the PR body (unquoted `date` → `datetime.date`, empty-list metadata) were independently re-verified as correctly fixed — `_normalize_metadata_value` runs before any value reaches Chroma, and both have targeted tests plus end-to-end confirmation via a full-corpus ingestion test. All 3 of the ticket's acceptance criteria are genuinely met, including the literal EUR→GBP spot-check (a real assertion, not a weaker non-empty check).

One **High**-severity, previously-undocumented content-loss bug was found and independently confirmed: `chunk_document` silently drops all text between the `# ` title and the first `##` section heading for every multi-section document — including the fictional watermark/disclaimer banner and any intro prose. Confirmed live: the watermark banner ("Authored reference based on the public ISO 20022...") is completely absent from every chunk of `ISO-0001.md`.

## Validation

| Check | Result |
|---|---|
| `uv run pytest -v` | 37 passed (25 existing + 12 new) |
| `uv run ruff check data/ rag/` | All checks passed |
| `uv run ruff format --check data/ rag/` | 50 files already formatted |
| Acceptance criteria: queryable local Chroma store | ✅ |
| Acceptance criteria: `retrieve(query, k)` with citation metadata | ✅ |
| Acceptance criteria: EUR→GBP spot-check returns `JUR-0001` in top results | ✅ verified as a real assertion |
| Both documented bug fixes (date normalization, empty-list metadata) | ✅ re-verified correct and tested |
| `chromadb` Python 3.14 compatibility claim | ✅ re-confirmed working |
| `collection.upsert()` (not `.add()`) used for idempotency | ✅ |
| Watermark/disclaimer banner present in ingested chunks | ❌ **absent from every multi-section document's chunks** (see Issues) |

## Issues Found

| # | Severity | File:Line | Description | Suggested fix |
|---|----------|-----------|-------------|----------------|
| 1 | High | `rag/chunking.py` (`chunk_document`) | For every document with 2+ `##` sections (9 of ~29 corpus files: `POL-0001..4`, `JUR-0001..4`, `ISO-0001`), all text between the `# ` title and the first `##` heading is silently dropped — the `# {title}` prefix is re-added manually per chunk, but the original intro paragraph and the fictional watermark/disclaimer banner (`**⚠️ SYNTHETIC / FICTIONAL...**` or the ISO doc's "Authored reference..." line) are not carried into any chunk. Independently confirmed: `any('Authored reference' in c.text for c in chunks)` on `ISO-0001.md` is `False`. Not documented in the plan or PR body as an intentional limitation — it wasn't caught because every test fixture puts `##` immediately after the title with no intervening text. | Include the pre-first-match text as part of chunk 0 (e.g. prepend it to the first section's text), or explicitly carry the watermark banner into every chunk's metadata/text if full inclusion in chunk 0 is deemed sufficient. Either way, add a test with intro prose before the first `##` to catch regressions. |
| 2 | Medium | `rag/ingestion.py` (`ingest`) | Idempotency is overwrite-only, not sync: `upsert` never deletes stale ids, so if a document's section count shrinks between two ingestion runs, its now-orphaned higher-index chunk ids remain in the store permanently. Not tested, not documented. Acceptable for this ticket's static-corpus scope (YAGNI), but worth a one-line docstring caveat before TICKET-5+ agents start depending on retrieval freshness across corpus edits. | Add a short docstring note on `ingest()`, or defer to a future ticket if corpus mutation becomes a real workflow. |
| 3 | Low | `rag/tests/test_ingestion_and_retrieval.py` | `assert count > 40` is a loose bound (actual is 55) — would still pass if an entire corpus subdirectory were accidentally skipped from ingestion. | Consider asserting per-directory counts, or an exact number with a comment explaining the expected total. |

## What's Good

- Both bugs documented in the PR body were independently re-derived and confirmed correct, including live verification that the full corpus (with the date and empty-list edge cases) ingests cleanly end-to-end.
- The chunking boundary case (exactly one `##` section → single chunk, not a degenerate split) is correct and has a dedicated test.
- `parse_document`'s frontmatter-splitting and the `##`-only (not `###`) section regex were checked against the real corpus, not assumed — no file has a stray `---` in its body or uses sub-headings that would be misclassified.
- Deterministic chunk ids and `upsert` genuinely deliver the idempotency the plan claims (tested).
- All acceptance criteria — including the literal EUR→GBP retrieval spot-check — are exercised by real assertions, not weaker proxies.
- Appropriately KISS/YAGNI for this project's greenfield script-based style: full type hints, small functions, `CORPUS_DIRS`'s relative-path fragility explicitly flagged in the plan as an accepted tradeoff (correctly not re-raised as a fresh issue here).

## Recommendation

**Request changes.** The High-severity content-loss bug (#1) is real, independently confirmed, and affects nearly a third of the corpus's documents — including the compliance-relevant "clearly watermarked as fictional" disclaimer text this project's PRD specifically calls out as a risk mitigation. It should be fixed (or explicitly documented as an accepted limitation, if that's the actual intent) before merge. The Medium/Low items are fine to defer or note as follow-ups.
