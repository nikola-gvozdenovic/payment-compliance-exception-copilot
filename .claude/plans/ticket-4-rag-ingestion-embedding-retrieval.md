# Feature: TICKET-4 — RAG Ingestion, Embedding, and Retrieval Pipeline (Chroma)

The following plan should be complete, but it's important to validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils/types/models. Import from the right files etc.

**Context:** This plan was produced after a clarification round (via `plan-feature`) resolving the embedding-model choice, chunking granularity, and store-persistence questions TICKET-4's spec leaves open, **plus direct compatibility verification** of `chromadb` against this project's Python 3.14 runtime (see NOTES — this was not assumed from documentation, it was tested).

## Feature Description

This ticket builds the actual search engine behind "look up the real rulebook": a pipeline that chunks TICKET-2's 29-document corpus (policy docs, sanctions entries, jurisdiction rules, the ISO 20022 reference), embeds each chunk, stores them in a local Chroma vector store, and exposes a `retrieve(query, k)` function returning ranked chunks with citation metadata (source doc, chunk id). No agent calls this yet (TICKET-5/6 don't exist) — this ticket makes retrieval *possible*, not integrated.

## User Story

As the **Triage Agent** (TICKET-5) and the **Compliance Agent** (TICKET-6),
I want to query a local vector store and get back the most relevant document chunks, each traceable to its exact source document and chunk id,
So that every classification and decision I make can cite a real, retrievable piece of the corpus instead of guessing from parametric memory.

## Problem Statement

TICKET-2 produced 29 real documents, but nothing can search them yet — there's no way to find the one paragraph relevant to a specific question without reading every file by hand. Every downstream agent ticket needs a working `retrieve(query, k)` to exist before it can be grounded in anything.

## Solution Statement

Build a new top-level `rag/` package (matching TICKET-4's own "Files touched" estimate literally — `/rag/ingestion/`, `/rag/embeddings/`, `/rag/retriever.py` — realized as flat modules rather than subpackages, see NOTES): `rag/chunking.py` parses a corpus markdown file's YAML frontmatter and splits its body by top-level `##` sections (whole document as one chunk when it has fewer than 2 sections); `rag/embeddings.py` explicitly wires in Chroma's bundled local embedding function (`all-MiniLM-L6-v2` via ONNX — no Ollama, no external service); `rag/ingestion.py` walks all 4 corpus directories, chunks every document, and upserts into a local `PersistentClient` Chroma collection (idempotent via deterministic `chunk_id`s); `rag/retriever.py` exposes `retrieve(query: str, k: int) -> list[RetrievedChunk]`.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium (the pipeline itself is straightforward; the real risk was the new heavy dependency's compatibility with this project's Python version, which has been directly verified — see NOTES)
**Primary Systems Affected**: New `rag/` package. `pyproject.toml` (adds `chromadb`, `pyyaml`, and `rag` to `testpaths`). `.gitignore` (excludes the generated Chroma store directory). No existing files modified beyond that.
**Dependencies**: `chromadb` (new, ~1.5.9 confirmed working on Python 3.14.5 — see NOTES), `pyyaml` (new, already a transitive dependency of `chromadb`, added directly since this ticket calls `yaml.safe_load` itself rather than relying on an undeclared transitive dependency).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `docs/specs/payment-compliance-exception-copilot.md` (TICKET-4 section) — Why: authoritative scope/acceptance criteria — the literal source of the `retrieve(query, k)` signature requirement, the "queryable local Chroma store" requirement, and the EUR→GBP spot-check example this plan's test directly implements.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` lines 197-204 ("RAG Knowledge Base") — Why: names the exact 4 document categories (already built by TICKET-2) and states "Vector store: Chroma, run locally and file-based — chosen explicitly... free, no server or hosting cost" — the literal source of "no Ollama for embeddings, no external server" as a project-level constraint, not just this ticket's clarification-round answer.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` line 359 (Risk 5 mitigation) — Why: "structurally require the citation to be a retrieved chunk ID/reference the system can verify against the vector store, not free-text the model invents" — this is *why* `RetrievedChunk` must carry a real, stable `chunk_id`, not a synthetic/random one.
- `docs/tasks/ticket-4.md` (already written this session) — Why: the plain-language brief for this exact ticket; keep this plan's Feature Description consistent with it.
- `data/policy_docs/POL-0001.md` (full file, 26 lines) — Why: **the concrete shape every corpus document actually has** — YAML frontmatter (lines 1-8: `doc_id`, `doc_type`, `version`, `date`, `fictional`, `supports_flag_reason`), a watermark banner line, an `# H1` title, then **4 `##` sections** (`## Rule`, `## Rationale`, `## Enforcement`, `## Related documents`). This directly informs the chunker: most policy/jurisdiction docs have *multiple* `##` sections, not just the longer `ISO-0001` — verify this against the real files, don't assume from their line counts alone.
- `data/jurisdiction_rules/JUR-0001.md` (full file, ~37 lines) — Why: same shape as `POL-0001.md` (frontmatter + watermark + H1 + multiple `##` sections, including a `corridor: "EUR-GBP"` frontmatter field) — this is the exact file the ticket's own spot-check example ("EUR→GBP corridor rule") must retrieve.
- `data/sanctions_mock/SANC-0001.md` (full file, ~22 lines) — Why: the one corpus shape with **no `##` headers at all** (bold field labels — `**Entity:**`, `**Entity type:**`, etc. — instead), so the chunker's "whole document as one chunk when fewer than 2 sections" fallback is not a hypothetical edge case, it's how all 20 sanctions files are actually structured.
- `data/iso20022_reference/ISO-0001.md` (full file, ~76 lines) — Why: has 5 `##` sections and `fictional: false` (the only such document) — confirms the chunker must not special-case on the `fictional` flag, only on section count.
- `data/decision_log/store.py` (full file, 130 lines, from TICKET-3) — Why: **the pattern to mirror directly** — a module-level path constant (`DECISION_LOG_DB_PATH`) with a same-named parameter default (`db_path: Path | str = DECISION_LOG_DB_PATH`) on every public function, so tests can override it via `tmp_path` without touching the real generated store. `rag/ingestion.py`/`rag/retriever.py` should follow the exact same shape (`persist_path` parameter, `CHROMA_STORE_PATH` constant).
- `data/loader.py` (full file, 35 lines) — Why: the established "thin package re-export" pattern `rag/__init__.py` should mirror.
- `.gitignore` (current, 14 lines after TICKET-3's addition) — Why: has `data/decision_log/*.db*` but nothing for a Chroma store yet; this ticket adds a matching entry for the same reason (generated runtime index, not source content).
- `pyproject.toml` (current, 25 lines) — Why: `[tool.pytest.ini_options] testpaths = ["data"]` must become `testpaths = ["data", "rag"]`; no `[tool.ruff]` `select` override exists, so default ruff rules apply to the new code too.

### Relevant Documentation

- [Chroma Python client — Collections](https://docs.trychroma.com/docs/collections/manage-collections) — Why: `PersistentClient(path=...)` for a local, file-based store (matches the PRD's explicit "no server" requirement); `get_or_create_collection(name, embedding_function=...)` for idempotent collection setup across repeated ingestion runs.
- [Chroma Python client — Adding data / `upsert`](https://docs.trychroma.com/docs/collections/add-data) — Why: `collection.upsert(ids=..., documents=..., metadatas=...)` is what makes re-running ingestion idempotent — re-ingesting with the same deterministic `chunk_id`s overwrites in place rather than duplicating (`.add()` would raise on a duplicate id instead).
- [Chroma — Embedding functions](https://docs.trychroma.com/docs/embeddings/embedding-functions) — Why: `chromadb.utils.embedding_functions.DefaultEmbeddingFunction()` is the bundled local `all-MiniLM-L6-v2` (ONNX) function this ticket wires in explicitly in `rag/embeddings.py`, rather than relying on the client's implicit default — makes the choice visible and swappable later (e.g. to an Ollama-backed function) without touching ingestion/retrieval call sites.
- [PyYAML — `yaml.safe_load`](https://pyyaml.org/wiki/PyYAMLDocumentation) — Why: parses each document's YAML frontmatter block (including its one list-valued field, `supports_flag_reason`) into a plain `dict`; `safe_load` (not `load`) is the standard, injection-safe choice for parsing untrusted-shape YAML, even though every current corpus file is trusted internal content.

### Patterns to Follow

**Naming conventions (extends TICKET-1/TICKET-3's established conventions):**
- Package: `rag/` (top-level, matching the ticket's own literal file estimate — a deliberate exception to TICKET-1/2/3's `data/`-centralization pattern; see NOTES).
- Modules: `chunking.py`, `embeddings.py`, `ingestion.py`, `retriever.py` (flat `snake_case.py`, not the PRD's indicative `ingestion/`/`embeddings/` subdirectories — see NOTES).
- Pydantic models: `Chunk`, `RetrievedChunk` (`PascalCase`, matching `Payment`, `DecisionLogEntry`).
- Functions: `parse_document`, `chunk_document`, `ingest`, `retrieve` (`snake_case`, matching `load_all`, `log_decision`).
- Chunk IDs: deterministic, `f"{doc_id}::chunk-{index}"` (e.g. `POL-0001::chunk-0`) — mirrors TICKET-1's deterministic `PMT-0001` fixture IDs; never a random UUID, since a stable id is what makes ingestion idempotent (`upsert`) and what makes a citation reproducibly verifiable (PRD Risk 5 mitigation, cited above).

**Error handling:**
- No custom exception hierarchy. Let `yaml.safe_load` raise `yaml.YAMLError` naturally on a malformed frontmatter block, and let `KeyError`/`pydantic.ValidationError` propagate on a missing required frontmatter field — matches TICKET-1/TICKET-3's established "fail loudly on bad data" convention. Do not wrap-and-swallow.

**Test-overridable storage path (mirrors TICKET-3 exactly):**
- `CHROMA_STORE_PATH = Path(__file__).parent / "chroma_store"` module-level constant in `rag/ingestion.py`. Both `ingest(..., persist_path: Path | str = CHROMA_STORE_PATH)` and `retrieve(..., persist_path: Path | str = CHROMA_STORE_PATH)` take the same override parameter, so tests always pass `persist_path=tmp_path` and never touch (or need) the real generated store.

**Idempotent ingestion:**
- `ingest()` always uses `collection.upsert(...)`, never `.add()` — re-running ingestion after a corpus document changes overwrites that document's chunks in place under the same deterministic ids, rather than erroring on a duplicate id or silently accumulating stale duplicates.

**Chunking contract (established by this ticket):**
- Each corpus file's body (everything after the frontmatter's closing `---`) is scanned for top-level `## ` section headers.
  - **2 or more matches** → one chunk per section, chunk text = `f"# {title}\n\n{section_heading_and_body}"` (the document's `# H1` title is prepended to every chunk so it reads sensibly standalone, since a retrieved chunk on its own has no other document context).
  - **Fewer than 2 matches** (0 or 1) → the whole body is one chunk, same `f"# {title}\n\n{body}"` prefixing.
- Every chunk's Chroma metadata is the full parsed frontmatter dict (`doc_id`, `doc_type`, `version`, `date`, `fictional`, `supports_flag_reason`, plus `corridor` when present) with `chunk_index: int` added — **verified directly that Chroma 1.5.9 accepts a native Python `list` as a metadata value** (see NOTES), so `supports_flag_reason` does not need to be comma-joined into a string.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

**Tasks:**
- `uv add chromadb pyyaml`.
- Add `rag/chroma_store/` to `.gitignore`.
- Update `pyproject.toml`'s `testpaths` to `["data", "rag"]`.
- Create the `rag/` package (`__init__.py`) and its co-located `rag/tests/` package (`__init__.py`), matching TICKET-1's established co-located-tests convention.

### Phase 2: Core Implementation — Parsing & Chunking

**Tasks:**
- Implement `rag/chunking.py`: `parse_document(path)` (frontmatter + title + body), `chunk_document(doc_id, title, body)` (the `##`-section-splitting logic above), `Chunk` pydantic model.

### Phase 3: Core Implementation — Embedding & Ingestion

**Tasks:**
- Implement `rag/embeddings.py`: `get_embedding_function()`.
- Implement `rag/ingestion.py`: `CHROMA_STORE_PATH`, `CORPUS_DIRS`, `ingest(persist_path=CHROMA_STORE_PATH) -> int` (walks all 4 corpus directories, chunks every `.md` file, upserts, returns total chunk count).

### Phase 4: Integration — Retrieval

**Tasks:**
- Implement `rag/retriever.py`: `RetrievedChunk` pydantic model, `retrieve(query, k=5, persist_path=CHROMA_STORE_PATH) -> list[RetrievedChunk]`.
- Implement `rag/__init__.py` re-exports (`ingest`, `retrieve`, `Chunk`, `RetrievedChunk`).

### Phase 5: Testing & Validation

**Tasks:**
- Unit tests for `chunking.py` (no Chroma/embedding involved — fast).
- Integration-style tests for `ingestion.py`/`retriever.py` against a real (but `tmp_path`-isolated) Chroma store, including the ticket's own literal EUR→GBP spot-check.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### RUN dependency installation

- **IMPLEMENT**: `uv add chromadb pyyaml`.
- **GOTCHA**: `chromadb`'s default embedding function downloads a ~79MB ONNX model (`all-MiniLM-L6-v2`) to `~/.cache/chroma/onnx_models/` on **first use** (not first install) — this happens the first time `ingest()` or `retrieve()` actually runs, not at `uv add` time, and needs network access that one time. Already verified working end-to-end on this machine during planning (see NOTES) — the cache is user-level (`~/.cache/chroma/`), so it persists across this project's test runs once warmed.
- **VALIDATE**: `uv run python -c "import chromadb, yaml; print(chromadb.__version__)"` prints `1.5.9` (or newer).

### UPDATE .gitignore

- **IMPLEMENT**: Add a new line: `rag/chroma_store/`
- **VALIDATE**: (after the directory exists) `git check-ignore -v rag/chroma_store/chroma.sqlite3` prints a match.

### UPDATE pyproject.toml

- **IMPLEMENT**: Change `testpaths = ["data"]` to `testpaths = ["data", "rag"]` under `[tool.pytest.ini_options]`.
- **VALIDATE**: `uv run pytest --collect-only 2>&1 | tail -5` runs without error (will still show only `data/` tests until `rag/tests/` exists).

### CREATE rag/__init__.py and rag/tests/__init__.py

- **IMPLEMENT**: Empty `rag/tests/__init__.py`. `rag/__init__.py` populated at the end of Phase 4 (listed here as a placeholder empty file for now so `rag/` is importable from the start).
- **VALIDATE**: `uv run python -c "import rag"` succeeds with no output.

### CREATE rag/chunking.py

- **IMPLEMENT**:
  ```python
  import re
  from pathlib import Path
  from typing import Any

  from pydantic import BaseModel
  import yaml

  _H2_PATTERN = re.compile(r"^##\s+.+$", re.MULTILINE)
  _H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


  class Chunk(BaseModel):
      chunk_id: str
      text: str
      metadata: dict[str, Any]


  def parse_document(path: Path) -> tuple[dict[str, Any], str, str]:
      """Split a corpus markdown file into (frontmatter, title, body-after-frontmatter)."""
      _, frontmatter_raw, body = path.read_text().split("---", 2)
      frontmatter = yaml.safe_load(frontmatter_raw)
      body = body.strip()
      title_match = _H1_PATTERN.search(body)
      title = title_match.group(1).strip() if title_match else frontmatter["doc_id"]
      return frontmatter, title, body


  def chunk_document(doc_id: str, title: str, body: str, metadata: dict[str, Any]) -> list[Chunk]:
      """Split by top-level ## sections; whole body as one chunk if fewer than 2 sections."""
      matches = list(_H2_PATTERN.finditer(body))
      if len(matches) < 2:
          return [
              Chunk(
                  chunk_id=f"{doc_id}::chunk-0",
                  text=f"# {title}\n\n{body}",
                  metadata={**metadata, "chunk_index": 0},
              )
          ]
      chunks = []
      for i, match in enumerate(matches):
          start = match.start()
          end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
          section_text = body[start:end].strip()
          chunks.append(
              Chunk(
                  chunk_id=f"{doc_id}::chunk-{i}",
                  text=f"# {title}\n\n{section_text}",
                  metadata={**metadata, "chunk_index": i},
              )
          )
      return chunks
  ```
- **IMPORTS**: `re`, `from pathlib import Path`, `from typing import Any`, `from pydantic import BaseModel`, `import yaml`.
- **GOTCHA**: `path.read_text().split("---", 2)` assumes exactly one frontmatter block delimited by `---` at the very start of the file (matching every TICKET-2 document's actual shape — verified above) — it is **not** a general-purpose Markdown-horizontal-rule-safe parser, and would break if a document body ever contained a literal `---` line. None of the 29 current corpus files do; don't over-engineer a stricter parser for a case that doesn't exist yet.
- **VALIDATE**: `uv run python -c "
  from pathlib import Path
  from rag.chunking import parse_document, chunk_document
  fm, title, body = parse_document(Path('data/policy_docs/POL-0001.md'))
  chunks = chunk_document(fm['doc_id'], title, body, fm)
  print(title, len(chunks), [c.chunk_id for c in chunks])
  "` prints `Remittance Information Requirement Policy 4 ['POL-0001::chunk-0', 'POL-0001::chunk-1', 'POL-0001::chunk-2', 'POL-0001::chunk-3']`.

### CREATE rag/embeddings.py

- **IMPLEMENT**:
  ```python
  """Explicit wiring for the embedding function every ingestion/retrieval call uses.

  Chroma's bundled default (all-MiniLM-L6-v2, run locally via ONNX -- no external
  service, no Ollama) is used deliberately over an Ollama-backed embedding model, so
  ingestion and retrieval (and every test that exercises them) never depend on an
  Ollama server actually running. See .claude/plans/ticket-4-rag-ingestion-embedding-retrieval.md
  NOTES for the full rationale.
  """

  from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
  from chromadb.utils.embedding_functions.default_embedding_function import DefaultEmbeddingFunction as _EF


  def get_embedding_function() -> _EF:
      return DefaultEmbeddingFunction()
  ```
- **IMPORTS**: `from chromadb.utils.embedding_functions import DefaultEmbeddingFunction`.
- **GOTCHA**: Verify the exact import path against the installed `chromadb==1.5.9` (`python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; print(DefaultEmbeddingFunction)"`) before writing this file — embedding-function import paths have moved between Chroma versions historically; don't assume the path above is still current without checking it against the actual installed package first.
- **VALIDATE**: `uv run python -c "from rag.embeddings import get_embedding_function; ef = get_embedding_function(); print(ef(['hello world'])[0][:5])"` prints the first 5 floats of an embedding vector.

### CREATE rag/ingestion.py

- **IMPLEMENT**:
  ```python
  from pathlib import Path

  import chromadb

  from rag.chunking import chunk_document, parse_document
  from rag.embeddings import get_embedding_function

  CHROMA_STORE_PATH = Path(__file__).parent / "chroma_store"
  COLLECTION_NAME = "compliance_corpus"
  CORPUS_DIRS = [
      Path("data/policy_docs"),
      Path("data/sanctions_mock"),
      Path("data/jurisdiction_rules"),
      Path("data/iso20022_reference"),
  ]


  def ingest(persist_path: Path | str = CHROMA_STORE_PATH) -> int:
      """Chunk and embed the full corpus into a local Chroma collection. Idempotent."""
      client = chromadb.PersistentClient(path=str(persist_path))
      collection = client.get_or_create_collection(
          COLLECTION_NAME, embedding_function=get_embedding_function()
      )

      all_chunks = []
      for corpus_dir in CORPUS_DIRS:
          for path in sorted(corpus_dir.glob("*.md")):
              frontmatter, title, body = parse_document(path)
              all_chunks.extend(chunk_document(frontmatter["doc_id"], title, body, frontmatter))

      collection.upsert(
          ids=[c.chunk_id for c in all_chunks],
          documents=[c.text for c in all_chunks],
          metadatas=[c.metadata for c in all_chunks],
      )
      return len(all_chunks)
  ```
- **IMPORTS**: `from pathlib import Path`, `import chromadb`, `from rag.chunking import chunk_document, parse_document`, `from rag.embeddings import get_embedding_function`.
- **GOTCHA**: `CORPUS_DIRS` uses paths relative to the current working directory (`Path("data/policy_docs")`, not `Path(__file__).parent / ...`) — this matches `data/decision_log`'s own precedent of assuming `uv run` is always invoked from the repo root, but is worth flagging explicitly since a future caller running from a different cwd would silently ingest zero documents rather than erroring.
- **VALIDATE**: `uv run python -c "
  from pathlib import Path
  from rag.ingestion import ingest
  import tempfile
  with tempfile.TemporaryDirectory() as d:
      count = ingest(persist_path=Path(d))
      print('chunks ingested:', count)
  "` prints a chunk count around 55-60 (4 policy docs × ~4 sections + 4 jurisdiction docs × ~4 sections + 20 sanctions × 1 + 1 ISO doc × ~5 sections).

### CREATE rag/retriever.py

- **IMPLEMENT**:
  ```python
  from pathlib import Path
  from typing import Any

  import chromadb
  from pydantic import BaseModel

  from rag.embeddings import get_embedding_function
  from rag.ingestion import CHROMA_STORE_PATH, COLLECTION_NAME


  class RetrievedChunk(BaseModel):
      chunk_id: str
      doc_id: str
      text: str
      distance: float
      metadata: dict[str, Any]


  def retrieve(
      query: str, k: int = 5, persist_path: Path | str = CHROMA_STORE_PATH
  ) -> list[RetrievedChunk]:
      client = chromadb.PersistentClient(path=str(persist_path))
      collection = client.get_or_create_collection(
          COLLECTION_NAME, embedding_function=get_embedding_function()
      )
      results = collection.query(query_texts=[query], n_results=k)

      return [
          RetrievedChunk(
              chunk_id=results["ids"][0][i],
              doc_id=results["metadatas"][0][i]["doc_id"],
              text=results["documents"][0][i],
              distance=results["distances"][0][i],
              metadata=results["metadatas"][0][i],
          )
          for i in range(len(results["ids"][0]))
      ]
  ```
- **IMPORTS**: `from pathlib import Path`, `from typing import Any`, `import chromadb`, `from pydantic import BaseModel`, `from rag.embeddings import get_embedding_function`, `from rag.ingestion import CHROMA_STORE_PATH, COLLECTION_NAME`.
- **GOTCHA**: `retrieve()` calling `get_or_create_collection` (not `get_collection`) means querying an never-ingested `persist_path` returns an **empty result** (`results["ids"] == [[]]`, so the list comprehension returns `[]`), not an error — document this as intentional (empty result for "nothing ingested yet" is more useful than a raised exception for a caller that just wants ranked chunks or nothing) rather than a silently swallowed bug.
- **VALIDATE**: `uv run python -c "
  from pathlib import Path
  from rag.ingestion import ingest
  from rag.retriever import retrieve
  import tempfile
  with tempfile.TemporaryDirectory() as d:
      p = Path(d)
      ingest(persist_path=p)
      results = retrieve('EUR to GBP corridor rule', k=3, persist_path=p)
      for r in results:
          print(r.chunk_id, round(r.distance, 4))
  "` prints 3 results, with a `JUR-0001::chunk-*` id at or near the top.

### CREATE rag/__init__.py (final content)

- **IMPLEMENT**:
  ```python
  from rag.chunking import Chunk
  from rag.ingestion import ingest
  from rag.retriever import RetrievedChunk, retrieve

  __all__ = ["Chunk", "RetrievedChunk", "ingest", "retrieve"]
  ```
- **PATTERN**: `data/loader.py`, `data/decision_log/__init__.py` — same thin re-export shape.
- **VALIDATE**: `uv run python -c "from rag import ingest, retrieve, Chunk, RetrievedChunk"` succeeds with no output.

### CREATE rag/tests/test_chunking.py

- **IMPLEMENT**: Cover, using inline string fixtures (not the real corpus files, so these tests don't depend on `data/` content staying byte-identical):
  - `test_parse_document_extracts_frontmatter_and_title` (write a small fixture `.md` to `tmp_path`, assert frontmatter dict and title match).
  - `test_chunk_document_splits_by_h2_when_two_or_more_sections` (body with 3 `##` sections → 3 chunks, correct `chunk_id`s, each chunk's text starts with `# {title}`).
  - `test_chunk_document_single_chunk_when_no_sections` (body with zero `##` headers, mirroring a sanctions-entry shape → exactly 1 chunk).
  - `test_chunk_document_single_chunk_when_exactly_one_section` (body with exactly one `##` header → still 1 chunk, per the "fewer than 2" rule, not split into a degenerate single-section chunk).
  - `test_chunk_metadata_includes_frontmatter_and_chunk_index` (assert `metadata["doc_id"]`, `metadata["chunk_index"]` present and correct).
- **PATTERN**: `data/tests/test_models.py`, `data/tests/test_decision_log.py` — small helper factories, plain `assert`, no test classes.
- **VALIDATE**: `uv run pytest rag/tests/test_chunking.py -v`

### CREATE rag/tests/test_ingestion_and_retrieval.py

- **IMPLEMENT**: Every test uses `tmp_path` as `persist_path` — **never** the real `CHROMA_STORE_PATH`. Cover:
  - `test_ingest_returns_chunk_count_matching_corpus` — `ingest(persist_path=tmp_path)` returns a count in the range asserted above (assert `count > 40` as a loose sanity bound rather than hardcoding the exact number, so a future corpus addition doesn't spuriously break this test).
  - `test_ingest_is_idempotent` — call `ingest(persist_path=tmp_path)` twice, assert both calls return the same count (proves `upsert` overwrites rather than duplicates).
  - `test_retrieve_eur_gbp_corridor_rule_returns_relevant_chunk_in_top_results` — **this is the ticket's own literal acceptance criterion.** `ingest(persist_path=tmp_path)`, then `retrieve("EUR to GBP corridor rule", k=3, persist_path=tmp_path)`, assert any result's `doc_id == "JUR-0001"`.
  - `test_retrieve_returns_citation_metadata` — assert every returned `RetrievedChunk` has a non-empty `chunk_id`, a `doc_id` matching the `{doc_id}::chunk-N` prefix of its own `chunk_id`, and `metadata["doc_type"]` present.
  - `test_retrieve_on_empty_store_returns_empty_list` — call `retrieve(...)` against a fresh `tmp_path` with no prior `ingest()` call, assert `== []`, not an exception (documents the GOTCHA above as tested behavior).
- **PATTERN**: `data/tests/test_decision_log.py` — `tmp_path`-isolated storage, no shared/global state between tests.
- **IMPORTS**: `from rag.ingestion import ingest`, `from rag.retriever import retrieve`.
- **GOTCHA**: These tests are meaningfully slower than the rest of the suite (loading the ONNX model + embedding ~55 chunks per `ingest()` call) — expect low single-digit seconds per test after the model is cached, longer on the very first run on a machine that's never used `chromadb` before (downloads the model once). Do not add a `pytest.mark.slow`/skip infrastructure for this ticket — no such infrastructure exists yet in this project, and introducing one is out of scope here (YAGNI).
- **VALIDATE**: `uv run pytest rag/tests/test_ingestion_and_retrieval.py -v`

### RUN full test suite

- **IMPLEMENT**: n/a — validation step.
- **VALIDATE**: `uv run pytest -v` (now covers both `data/` and `rag/` per the updated `testpaths`) — all tests pass (25 existing + new `rag/` tests).

---

## TESTING STRATEGY

### Unit Tests

- `rag/chunking.py`: frontmatter/title parsing, section-splitting logic across all 3 real shapes found in the corpus (0 sections, 1 section, 2+ sections), metadata assembly. Fast, no Chroma/embedding model involved.

### Integration Tests

- `rag/ingestion.py` + `rag/retriever.py` together, against a real (but `tmp_path`-isolated) Chroma `PersistentClient` and the real bundled embedding model — this is the only way to genuinely test the ticket's 3rd acceptance criterion (retrieval quality), since a mocked embedding function would prove nothing about actual semantic relevance.

### Edge Cases

- A document with exactly one `##` section → still treated as "whole document, one chunk" (not a degenerate 1-section chunk) — explicitly tested.
- Querying an empty (never-ingested) store → empty list, not an exception — explicitly tested.
- Re-running `ingest()` against an already-ingested store → same chunk count, not doubled (idempotency) — explicitly tested.
- `supports_flag_reason: []` (the empty-list case, present on `JUR-0002`/`JUR-0003`/`JUR-0004` per TICKET-2) round-trips through Chroma metadata correctly as an empty list, not `null`/omitted — worth a quick manual spot-check during implementation even though not called out as a dedicated test (low risk given the direct verification already done — see NOTES).

### E2E / Browser Automation

Not applicable — this ticket has no UI or HTTP surface. No `agent-browser` validation needed.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check rag/
uv run ruff format --check rag/
```

### Level 2: Unit Tests

```bash
uv run pytest -v
```

### Level 3: Integration Tests

Covered by Level 2 (`rag/tests/test_ingestion_and_retrieval.py` runs in the same `pytest` invocation) — no separate command needed.

### Level 4: Manual Validation

```bash
uv run python -c "
from rag import ingest, retrieve

count = ingest()
print(f'Ingested {count} chunks into rag/chroma_store/')

for r in retrieve('EUR to GBP corridor rule', k=3):
    print(f'{r.chunk_id:30s} distance={r.distance:.4f} doc_type={r.metadata[\"doc_type\"]}')
"
rm -rf rag/chroma_store  # clean up the manually-created store afterward
```
Expect a chunk count in the 50s, and a `JUR-0001::chunk-*` id in the top 3 results.

### Level 5: E2E / Browser Automation

Not applicable — no UI exists at this ticket's scope.

### Level 6: Additional Validation (Optional)

None required. (Optional stretch, not blocking: `uv run python -c "from rag.ingestion import ingest; from pathlib import Path; import tempfile; d=tempfile.mkdtemp(); ingest(Path(d)); import chromadb; c=chromadb.PersistentClient(path=d).get_collection('compliance_corpus'); print(c.count())"` as a second, independent way to sanity-check the ingested count.)

---

## ACCEPTANCE CRITERIA

(mirrors `docs/specs/payment-compliance-exception-copilot.md` TICKET-4 verbatim, plus this plan's concrete decisions)

- [ ] Running ingestion (`ingest()`) against the TICKET-2 corpus produces a queryable local Chroma store.
- [ ] A `retrieve(query, k)`-style function returns ranked chunks with enough metadata (`doc_id`, `chunk_id` via the model, plus full frontmatter) to support citation.
- [ ] Retrieval quality spot-checked: querying `"EUR to GBP corridor rule"` returns a `JUR-0001` chunk in the top 3 results (explicitly tested, not just manually eyeballed once).
- [ ] `rag/chroma_store/` is gitignored, never committed.
- [ ] Ingestion is idempotent (`upsert`, not `add`) — re-running it doesn't duplicate chunks.
- [ ] `chromadb` genuinely works on this project's Python 3.14 runtime (verified directly during planning, re-confirmed by the implementation's own test suite passing).
- [ ] All validation commands (Levels 1, 2, 4) pass with zero errors.
- [ ] Existing test suite (25 tests) still passes unchanged.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task's inline validation command passed immediately after that task
- [ ] `uv run ruff check rag/` / `ruff format --check rag/` pass
- [ ] `uv run pytest -v` passes (25 existing + new `rag/` tests)
- [ ] `rag/chroma_store/` does not appear in `git status` (confirmed gitignored)
- [ ] Manual validation (Level 4) shows a `JUR-0001` chunk in the top 3 EUR→GBP results
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability (consider running the `code-review` skill before committing)

---

## NOTES

**Interview decisions (from the `plan-feature` clarification round), each with rationale:**

1. **Chroma's bundled default embedding function**, not an Ollama embedding endpoint — chosen because it keeps ingestion/retrieval (and every test that exercises them) fully self-contained, with no dependency on an Ollama server actually running. This is also a better fit for the PRD's own explicit framing of Chroma as "local and file-based... no server or hosting cost" (line 204) — extending that same zero-server principle to the embedding step, not just the vector store.
2. **Split by markdown `##` section**, not one chunk per whole document — chosen for more precise, individually-citable chunks. **Important correction from the interview framing**: this isn't only relevant for the longer `ISO-0001` — direct inspection of the actual corpus files (see CONTEXT REFERENCES) shows all 4 policy docs and all 4 jurisdiction docs have 3-5 `##` sections each; only the 20 sanctions entries (no `##` headers at all) and stay single-chunk. The chosen strategy is still correct and well-justified, just for a wider set of documents than the interview question implied.
3. **Gitignored, regenerated store** — chosen to match TICKET-3's precedent (a derived index is not source content); `rag/chroma_store/` added to `.gitignore` alongside `data/decision_log/*.db*`.

**Directly verified during planning (not assumed from documentation):**
- **`chromadb` 1.5.9 installs and runs correctly on Python 3.14.5** (this project's exact runtime). This mattered because a real, still-open GitHub issue (chroma-core/chroma#5643, filed October 2025) reports `chromadb` failing to install on Python 3.14 due to a `lz4` dependency's C-extension build failure. That issue is nearly a year old relative to this planning session; installing `chromadb` fresh into an isolated Python 3.14 venv and running an actual `create_collection` → `add` → `query` round-trip succeeded cleanly, so whatever caused that issue has since been resolved upstream (a newer `lz4` wheel, most likely). This was tested directly, not inferred from the issue being old.
- **Chroma 1.5.9's metadata accepts a native Python `list` value directly** (tested: added a chunk with `metadata={"supports_flag_reason": ["compliance_hold", "timeout"]}` and read it back as a real Python list, not a stringified/coerced value). This simplified the metadata design — `supports_flag_reason` doesn't need comma-joining or JSON-stringifying.

**Design choices made during planning (not separately interview-asked, but flagged here for visibility):**
- **Top-level `rag/`, not `data/rag/`** — unlike TICKET-2/3 (where the ticket text left storage location genuinely open and this repo's `data/`-centralization pattern was the tiebreaker), TICKET-4's own "Files touched" estimate explicitly names `/rag/ingestion/`, `/rag/embeddings/`, `/rag/retriever.py` as top-level paths — the ticket text itself settles this, so it wasn't re-litigated as an interview question.
- **Flat modules (`chunking.py`, `embeddings.py`, `ingestion.py`, `retriever.py`) instead of the PRD's indicative `ingestion/`/`embeddings/` subdirectories** — the PRD's own §6.3 heading calls that layout "indicative," and at this ticket's actual scope (one function's worth of logic per concern), a subdirectory per concern would be empty ceremony. A future ticket that genuinely needs multiple ingestion strategies could split `ingestion.py` into a subpackage then, without breaking `rag/__init__.py`'s public re-export surface.
- **`RetrievedChunk.distance` is Chroma's raw L2 distance, not a normalized similarity score** — exposed as-is (lower is more relevant) rather than transformed into a 0-1 "confidence," since no downstream ticket (TICKET-5/6) exists yet to specify what scale it actually needs; transforming it now would be speculative (YAGNI). Document this in the field if a future ticket needs a different scale.

**Scope boundary respected:** this ticket does not touch TICKET-5/6 (no agent calls `retrieve()` yet) or TICKET-9 (eval harness). The manual validation above ingests and queries the real corpus only to prove the pipeline works end-to-end, then deletes the resulting store so the repo stays clean.

## Confidence Score

**7/10** for one-pass success. The clarification round and direct compatibility verification resolved the two biggest risks (embedding-model choice, and whether `chromadb` even installs on this project's Python version) ahead of time. The remaining risk is narrower and mechanical: the exact `chromadb.utils.embedding_functions` import path is version-sensitive (flagged as an explicit GOTCHA with a verification command in the `rag/embeddings.py` task), and getting the `##`-section regex splitting exactly right against all 3 real corpus shapes (0/1/2+ sections) needs care — both are called out explicitly enough above that a single pass should catch them without a second research round.
