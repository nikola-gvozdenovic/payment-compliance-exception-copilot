# Feature: TICKET-2 — Synthetic Policy, Sanctions, and Jurisdiction Document Corpus

The following plan should be complete, but it's important to validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils/types/models. Import from the right files etc.

**Context:** This plan was produced after an explicit interview with the user (via `plan-feature`, invoked from `docs/feature_description.txt`) to pin down implementation decisions the ticket spec leaves open. All decisions below reflect the user's answers — see NOTES for the full list and rationale.

## Feature Description

This ticket authors the RAG knowledge base's raw material: a small corpus of markdown documents the (not-yet-built) TICKET-4 retrieval pipeline will chunk and embed, and that the Triage/Compliance agents (TICKET-5/6) will cite. It is a **pure content-authoring ticket** — no Python code, no generator script, no loader module. The corpus has four categories: internal policy documents, sanctions/watchlist entries, jurisdiction/corridor rules, and an ISO 20022 field reference — each clearly labeled fictional except the ISO reference (which is our own writeup of real, public schema structure).

## User Story

As the **Triage Agent** (TICKET-5) and the **Compliance Agent** (TICKET-6),
I want a corpus of citable policy, sanctions, and jurisdiction documents — with at least one document directly explaining each of TICKET-1's five flag reasons, and 20 sanctioned entities to check against —
So that every classification and Clear/Block/Escalate decision can be grounded in a retrieved, cited source document instead of guessed.

## Problem Statement

TICKET-1 produced five synthetic flagged/stuck payments, but there is nothing yet for any agent to retrieve or cite when explaining *why* those payments are flagged, or to check a payment's creditor against for sanctions. TICKET-6's acceptance criteria already requires blocking "20/20" known-sanctioned synthetic test entities — that fixed number is a hard downstream requirement, not just an estimate.

## Solution Statement

Author 29 markdown documents under `data/`, in four new directories:

- `data/policy_docs/` — 4 fictional internal policy documents (`POL-0001`…`POL-0004`), one per non-sanctions flag reason plus a general AML/compliance-screening policy.
- `data/sanctions_mock/` — 20 fictional sanctions entries (`SANC-0001`…`SANC-0020`), one per file, one of which (`SANC-0001`) is the exact creditor name TICKET-1's `PMT-0002` already uses (`"Zed Trading Consolidated"`), so that scenario has a real, citable match.
- `data/jurisdiction_rules/` — 4 fictional corridor rules (`JUR-0001`…`JUR-0004`), covering all four corridors actually used by TICKET-1's synthetic payments (EUR→GBP, USD→CHF, EUR→EUR, USD→USD).
- `data/iso20022_reference/` — 1 factual (non-fictional) field reference document (`ISO-0001`) describing the `pain.001.001.03` fields `data/pain001_generator.py` actually produces, in our own words (not copied ISO spec text).

Every document is a markdown file with a small YAML frontmatter header (`doc_id`, `doc_type`, `version`, `date`, `fictional`, `supports_flag_reason`) so later tickets can identify, version, and (eventually) programmatically validate coverage without parsing prose.

## Feature Metadata

**Feature Type**: New Capability (content authoring, no code)
**Estimated Complexity**: Low (mechanically repetitive authoring; the only real design work — frontmatter schema, corridor/entity selection — is already decided below)
**Primary Systems Affected**: New `data/policy_docs/`, `data/sanctions_mock/`, `data/jurisdiction_rules/`, `data/iso20022_reference/` directories. No existing files change except this plan itself being added.
**Dependencies**: None (no new Python packages; this ticket produces static `.md` files only)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `docs/specs/payment-compliance-exception-copilot.md` (TICKET-2 section) — Why: authoritative scope/acceptance criteria. Note its file estimate (`/data/policy_docs/`, `/data/sanctions_mock/`) is narrower than this plan's 4-folder layout — see NOTES for why we diverged, with the user's explicit sign-off.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §6.3 "Directory Structure (indicative)" (lines 140-167) — Why: shows the PRD's own indicative `/data/policy_docs/`, `/data/sanctions_mock/` (no separate jurisdiction/ISO folders either) — same divergence noted above.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §7.5 "RAG Knowledge Base" (lines 197-204) — Why: the authoritative list of exactly 4 document categories this ticket must produce: ISO 20022 field specs (real), mock policy docs, mock sanctions/watchlist (fake, labeled), mock jurisdiction rules (fake) — this plan's 4-folder split mirrors this list directly, one folder per category.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §13 "Risks & Mitigations", item 2 (lines 349-350) — Why: "base synthetic documents on real public standards (ISO 20022 schemas) for structural realism, while clearly watermarking sanctions/policy content as fictional" — this is the literal source of the `fictional: true/false` frontmatter field and the visible in-body watermark banner.
- `docs/PRD_Payment_Compliance_Exception_Copilot.md` §10 "Success Metrics" (line 291) — Why: "Compliance Agent correctly handles all known-sanctioned synthetic test entities (target: 20/20...)" — the literal source of "build all 20 sanctions entries now" instead of a minimal set.
- `docs/specs/payment-compliance-exception-copilot.md` TICKET-6 acceptance criteria (line 62) — Why: "Correctly blocks all known-sanctioned synthetic test entities from TICKET-2 (target: 20/20 or documented equivalent)" — same 20-entity requirement, from the consuming ticket's side.
- `data/generate_synthetic_payments.py` (full file, 258 lines) — Why: this is where TICKET-1's 5 payments' exact creditor names, corridors, and flag-reason `processing_log` detail strings live. Every policy/sanctions/jurisdiction document below must line up with what's actually in this file, not a paraphrase of it:
  - `PMT-0001` (line ~31-74): `missing_malformed_field`, `remittance_info=None` — no `RmtInf` in the XML. Validation detail: `"missing RmtInf: remittance information required by policy but absent from payload"`.
  - `PMT-0002` (line ~76-116): `compliance_hold`, creditor `"Zed Trading Consolidated"` (explicitly commented `# fictional, no real entity`), USD, detail: `"creditor name matched a watchlist-style entry pending review"`.
  - `PMT-0003` (line ~118-158): `corridor_currency_issue`, `source_currency="EUR"`, `destination_currency="GBP"`, detail: `"EUR-GBP corridor flagged for manual policy review"`.
  - `PMT-0004` (line ~160-200): `timeout`, `source_currency="USD"`, `destination_currency="CHF"`, `status=STUCK`, detail: `"no rail acknowledgement received after 48h"`.
  - `PMT-0005` (line ~202-245): `duplicate`, `source_currency="EUR"`, `destination_currency="EUR"`, detail: `"matches EndToEndId/amount/creditor of a payment processed 2 minutes earlier"`.
- `data/models.py` (lines 30-42) — Why: `FlagReason` is the exact 5-value enum (`missing_malformed_field`, `compliance_hold`, `corridor_currency_issue`, `timeout`, `duplicate`) every document's `supports_flag_reason` frontmatter value must match verbatim (lowercase snake_case strings, not the PascalCase Python names).
- `data/pain001_generator.py` (full file, 116 lines, especially the module docstring and `build_pain001_xml` signature) — Why: `ISO-0001`'s field descriptions must describe *exactly* the elements this generator actually builds (`MsgId`, `PmtInfId`, `EndToEndId`, `ReqdExctnDt`, `Dbtr`/`DbtrAcct`/`DbtrAgt`, `ChrgBr`, `CdtTrfTxInf`, `Amt/InstdAmt`+`Ccy` attribute, `CdtrAgt`/`Cdtr`/`CdtrAcct`, optional trailing `RmtInf/Ustrd`) — not a generic/idealized pain.001 description that drifts from the actual generator.
- `docs/tasks/ticket-2.md` (already written this session) — Why: the plain-language brief for this exact ticket; keep this plan's Feature Description consistent with it rather than contradicting it.

### No in-repo pattern for markdown-with-frontmatter documents yet

This is the first ticket to author markdown *content* documents (as opposed to project docs like `docs/tasks/*.md`). The frontmatter schema below is being established by this ticket — downstream tickets (TICKET-4's ingestion, any future corpus additions) should follow it, not invent a second schema.

### Relevant Documentation

- [YAML frontmatter convention](https://jekyllrb.com/docs/front-matter/) — Why: `---`-delimited key/value header at the top of a markdown file is a widely-recognized convention (used by Jekyll, Hugo, many static-site/doc tools) for attaching structured metadata to prose content; TICKET-4's ingestion pipeline can parse this with a simple YAML-block splitter without adopting a heavier CMS dependency.
- ISO 20022 `pain.001.001.03` structure — same sources already verified for TICKET-1's plan (`.claude/plans/ticket-1-payment-data-model-and-pain001-generator.md`, "Relevant Documentation" section): root `Document` → `CstmrCdtTrfInitn` → `GrpHdr` (`MsgId`, `CreDtTm`, `NbOfTxs`, `CtrlSum`, `InitgPty/Nm`) + `PmtInf` (`PmtInfId`, `PmtMtd`, `NbOfTxs`, `CtrlSum`, `ReqdExctnDt/Dt`, `Dbtr/Nm`, `DbtrAcct/Id/IBAN`, `DbtrAgt/FinInstnId/BIC`, `ChrgBr`, `CdtTrfTxInf`) → `CdtTrfTxInf` (`PmtId/EndToEndId`, `Amt/InstdAmt`+`Ccy`, `CdtrAgt/FinInstnId/BIC`, `Cdtr/Nm`, `CdtrAcct/Id/IBAN`, optional `RmtInf/Ustrd`). Why: `ISO-0001` describes exactly this structure, field by field, in plain English — reuse this verified structure rather than re-deriving it.

### Patterns to Follow

**Naming conventions (established by this ticket, mirroring TICKET-1's `PMT-\d{4}` style):**
- Sanctions entries: `SANC-0001` … `SANC-0020`, filename = `data/sanctions_mock/SANC-0001.md` (id and filename stem always match).
- Policy documents: `POL-0001` … `POL-0004`, filename = `data/policy_docs/POL-0001.md`.
- Jurisdiction rules: `JUR-0001` … `JUR-0004`, filename = `data/jurisdiction_rules/JUR-0001.md`.
- ISO reference: `ISO-0001`, filename = `data/iso20022_reference/ISO-0001.md`.

**Frontmatter schema (every document, all fields required):**
```yaml
---
doc_id: POL-0001
doc_type: policy          # one of: policy | sanctions_entry | jurisdiction_rule | iso20022_reference
version: "1.0"
date: 2026-01-10          # fixed date, mirrors TICKET-1's determinism convention -- do not use "today"
fictional: true            # false only for ISO-0001
supports_flag_reason: [missing_malformed_field]   # zero or more FlagReason string values, [] if none apply
---
```
`jurisdiction_rule` documents additionally carry a `corridor: "EUR-GBP"` field (source-destination currency pair, matching `Payment.corridor`'s own `f"{source}-{destination}"` format from `data/models.py`).

**Fictional watermark (body, not just frontmatter):**
Every `fictional: true` document's very first body line (after frontmatter) is a bold banner, e.g.:
`**⚠️ SYNTHETIC / FICTIONAL — this document was authored for the Payment Compliance & Exception Copilot demo. It is not a real policy, law, or sanctions record.**`
`ISO-0001` (the one `fictional: false` doc) instead opens with: `**Authored reference based on the public ISO 20022 \`pain.001.001.03\` schema — not a copy of the official ISO specification text.**`

**Safety design choice — no real country names in sanctions data:**
Sanctions entries use a synthetic risk-jurisdiction code (`SYN-J1` … `SYN-J5`) instead of any real country name. This avoids the corpus ever reading as a claim about a real country's sanctions status, while still giving the Compliance Agent (TICKET-6) a jurisdiction dimension to reason about. This is a judgment call made during planning (not asked to the user directly) — flag it explicitly if you disagree before implementing.

**Other relevant patterns:**
- Fixed, non-`datetime.now()`-style dates (`date: 2026-01-10` for all docs, matching TICKET-1's determinism convention) — these are static content files, but keeping the frontmatter date fixed avoids meaningless git diffs on re-save.
- `supports_flag_reason` values are exactly the lowercase `FlagReason` string values from `data/models.py` (`missing_malformed_field`, `compliance_hold`, `corridor_currency_issue`, `timeout`, `duplicate`) — never the PascalCase Python enum member names.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

**Tasks:**
- Create the four new directories: `data/policy_docs/`, `data/sanctions_mock/`, `data/jurisdiction_rules/`, `data/iso20022_reference/`.
- No `__init__.py` needed in any of them — these are pure content directories, not Python packages (nothing imports from them yet; TICKET-4 will add its own ingestion module elsewhere).

### Phase 2: Core Implementation — Policy Documents

**Tasks:** author all 4 files in `data/policy_docs/`, one per non-sanctions flag reason plus one general compliance-screening policy (see Step-by-Step Tasks for exact content specs).

### Phase 3: Core Implementation — Sanctions Entries

**Tasks:** author all 20 files in `data/sanctions_mock/`, using the exact entity table in Step-by-Step Tasks. `SANC-0001` must use the literal name `"Zed Trading Consolidated"`.

### Phase 4: Core Implementation — Jurisdiction Rules & ISO Reference

**Tasks:** author the 4 corridor-rule files in `data/jurisdiction_rules/` and the 1 field-reference file in `data/iso20022_reference/`.

### Phase 5: Coverage Validation

**Tasks:** manually verify (via `grep`, see VALIDATION COMMANDS) that every one of the 5 `FlagReason` values appears in at least one document's `supports_flag_reason` frontmatter, and that all 20 sanctions entries and both counts (4 policy, 4 jurisdiction) are present.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently verifiable.

### CREATE data/policy_docs/, data/sanctions_mock/, data/jurisdiction_rules/, data/iso20022_reference/

- **IMPLEMENT**: `mkdir -p data/policy_docs data/sanctions_mock data/jurisdiction_rules data/iso20022_reference`
- **VALIDATE**: `ls -d data/policy_docs data/sanctions_mock data/jurisdiction_rules data/iso20022_reference` lists all four with no error.

### CREATE data/policy_docs/POL-0001.md — Remittance Information Requirement Policy

- **IMPLEMENT**: Frontmatter `doc_type: policy`, `fictional: true`, `supports_flag_reason: [missing_malformed_field]`. Body: a short policy stating every outbound cross-border credit transfer must carry a populated `RmtInf` (remittance information) field per this institution's policy, explains why (traceability/AML reference matching), and states a payment missing it is held as `missing_malformed_field` pending manual review. Reference `RmtInf` by its literal ISO 20022 tag name so it lines up with `ISO-0001` and with `PMT-0001`'s validation detail string.
- **VALIDATE**: `grep -l "supports_flag_reason: \[missing_malformed_field\]" data/policy_docs/*.md` includes this file.

### CREATE data/policy_docs/POL-0002.md — Payment Processing SLA & Timeout Escalation Policy

- **IMPLEMENT**: `supports_flag_reason: [timeout]`. Body: states the institution's expected rail-acknowledgement SLA (e.g. 24h standard, 48h maximum before escalation), and that a payment with no acknowledgement after 48h is flagged `timeout` and moved to `stuck` status pending manual intervention — mirror `PMT-0004`'s exact "no rail acknowledgement received after 48h" language so the citation reads as a direct match.
- **VALIDATE**: `grep -l "supports_flag_reason: \[timeout\]" data/policy_docs/*.md` includes this file.

### CREATE data/policy_docs/POL-0003.md — Duplicate Payment Detection Policy

- **IMPLEMENT**: `supports_flag_reason: [duplicate]`. Body: defines a duplicate as a payment matching another's `EndToEndId`, amount, and creditor within a short window (mirror `PMT-0005`'s "2 minutes earlier"), states such payments are held under `duplicate` pending confirmation the second instance wasn't a legitimate re-send.
- **VALIDATE**: `grep -l "supports_flag_reason: \[duplicate\]" data/policy_docs/*.md` includes this file.

### CREATE data/policy_docs/POL-0004.md — AML / Sanctions Screening Policy

- **IMPLEMENT**: `supports_flag_reason: [compliance_hold]`. Body: describes the institution's screening process (every creditor/debtor name is checked against the sanctions watchlist in `data/sanctions_mock/`), states a name match (exact or fuzzy) results in a `compliance_hold` flag pending Compliance Agent review, and explicitly notes a match alone is never an automatic block — cross-reference the escalate-by-default rule from TICKET-6's scope (`docs/specs/...md` TICKET-6) without implementing it here.
- **VALIDATE**: `grep -l "supports_flag_reason: \[compliance_hold\]" data/policy_docs/*.md` includes this file.

### CREATE 20 files under data/sanctions_mock/ (SANC-0001.md … SANC-0020.md)

- **IMPLEMENT**: One file per row below. Every file: `doc_type: sanctions_entry`, `fictional: true`, `supports_flag_reason: [compliance_hold]` (all 20 support this same flag reason — that's expected, only `SANC-0001` needs to match a real fixture). Body fields: **Entity**, **Entity type** (Company/Individual), **Risk jurisdiction** (the `SYN-Jn` code), **Listed reason** (one sentence, varied wording — "designated for facilitating prohibited cross-border financial transactions," "designated for suspected trade-based money laundering," etc., all clearly synthetic-sounding, never referencing a real sanctions program by name), **Aliases** ("none on file" is fine for all).

  | ID | Entity | Type | Jurisdiction |
  |----|--------|------|--------------|
  | SANC-0001 | Zed Trading Consolidated | Company | SYN-J2 |
  | SANC-0002 | Halden Vantree Holdings | Company | SYN-J1 |
  | SANC-0003 | Petrusenko Marina Corp | Company | SYN-J3 |
  | SANC-0004 | Mstislav Renko | Individual | SYN-J2 |
  | SANC-0005 | Coral Bastion Trading LLC | Company | SYN-J4 |
  | SANC-0006 | Yusuke Tanaka-Voss | Individual | SYN-J1 |
  | SANC-0007 | Obsidian Bridge Capital | Company | SYN-J5 |
  | SANC-0008 | Farida Al-Mansoori | Individual | SYN-J2 |
  | SANC-0009 | Northgate Ferrous Metals Co | Company | SYN-J3 |
  | SANC-0010 | Grenholm Maritime Partners | Company | SYN-J1 |
  | SANC-0011 | Ilya Dobrenko | Individual | SYN-J4 |
  | SANC-0012 | Vantage Crescent Traders | Company | SYN-J5 |
  | SANC-0013 | Talia Reyes-Okonkwo | Individual | SYN-J3 |
  | SANC-0014 | Silverline Bulk Shipping SA | Company | SYN-J2 |
  | SANC-0015 | Dmitri Kovalenko-Reyes | Individual | SYN-J1 |
  | SANC-0016 | Emberrock Commodities Group | Company | SYN-J4 |
  | SANC-0017 | Priya Nandakumar | Individual | SYN-J5 |
  | SANC-0018 | Falkenhurst Industrial Supply | Company | SYN-J3 |
  | SANC-0019 | Baroness Trading & Export Co | Company | SYN-J2 |
  | SANC-0020 | Rudra Al-Farsi | Individual | SYN-J1 |

- **GOTCHA**: `SANC-0001`'s `Entity:` value must be the exact string `Zed Trading Consolidated` (byte-for-byte match with `data/generate_synthetic_payments.py` line ~86) — a paraphrase breaks the "directly supports" acceptance criterion for `PMT-0002`.
- **VALIDATE**: `ls data/sanctions_mock/*.md | wc -l` prints `20`. `grep -l "Zed Trading Consolidated" data/sanctions_mock/*.md` prints exactly `data/sanctions_mock/SANC-0001.md`.

### CREATE data/jurisdiction_rules/JUR-0001.md — EUR → GBP Corridor Rule

- **IMPLEMENT**: `doc_type: jurisdiction_rule`, `corridor: "EUR-GBP"`, `supports_flag_reason: [corridor_currency_issue]`. Body: a corridor-specific rule requiring enhanced review for EUR→GBP transfers above a threshold amount — mirror the PRD's own example language ("EUR→GBP corridor requires X") and `PMT-0003`'s "EUR-GBP corridor flagged for manual policy review" detail.
- **VALIDATE**: `grep -l 'corridor: "EUR-GBP"' data/jurisdiction_rules/*.md` includes this file.

### CREATE data/jurisdiction_rules/JUR-0002.md — USD → CHF Corridor Rule

- **IMPLEMENT**: `corridor: "USD-CHF"`, `supports_flag_reason: []` (this corridor's actual fixture, `PMT-0004`, is flagged `timeout`, not a corridor issue — this document adds retrieval breadth per the user's "broader set" choice, but doesn't force a flag-reason link that isn't real). Body: a plausible corridor rule (e.g. additional beneficiary-bank verification for USD→CHF transfers above a threshold).
- **VALIDATE**: `grep -l 'corridor: "USD-CHF"' data/jurisdiction_rules/*.md` includes this file.

### CREATE data/jurisdiction_rules/JUR-0003.md — EUR → EUR (Domestic/Eurozone-Internal) Rule

- **IMPLEMENT**: `corridor: "EUR-EUR"`, `supports_flag_reason: []`. Body: baseline domestic-transfer handling rule (lighter review threshold than cross-currency corridors).
- **VALIDATE**: `grep -l 'corridor: "EUR-EUR"' data/jurisdiction_rules/*.md` includes this file.

### CREATE data/jurisdiction_rules/JUR-0004.md — USD → USD (Domestic) Rule

- **IMPLEMENT**: `corridor: "USD-USD"`, `supports_flag_reason: []`. Body: baseline domestic-transfer handling rule, US-specific reference (e.g. same-day ACH vs wire threshold note) to differentiate it from `JUR-0003` rather than being a copy-paste twin.
- **VALIDATE**: `grep -l 'corridor: "USD-USD"' data/jurisdiction_rules/*.md` includes this file.

### CREATE data/iso20022_reference/ISO-0001.md — pain.001.001.03 Field Reference

- **IMPLEMENT**: `doc_type: iso20022_reference`, `fictional: false`, `supports_flag_reason: [missing_malformed_field]` (it's the natural retrieval target for explaining what `RmtInf` is and that it's optional). Body: plain-English description of each field `data/pain001_generator.py` actually emits, organized by element (`GrpHdr`: `MsgId`, `CreDtTm`, `NbOfTxs`, `CtrlSum`, `InitgPty/Nm`; `PmtInf`: `PmtInfId`, `PmtMtd`, `ReqdExctnDt`, `Dbtr`/`DbtrAcct`/`DbtrAgt`, `ChrgBr`; `CdtTrfTxInf`: `PmtId/EndToEndId`, `Amt/InstdAmt`+`Ccy` attribute, `CdtrAgt`/`Cdtr`/`CdtrAcct`, optional trailing `RmtInf/Ustrd`). Call out explicitly: "`RmtInf` is optional and always the last element in `CdtTrfTxInf` — its absence produces schema-valid XML, which is what makes 'missing remittance info' a business-policy violation (see `POL-0001`) rather than a malformed-XML error."
- **VALIDATE**: `grep -c "RmtInf" data/iso20022_reference/ISO-0001.md` returns a non-zero count.

### RUN full coverage check

- **IMPLEMENT**: n/a — validation step, confirms the ticket's core acceptance criterion.
- **VALIDATE**:
  ```bash
  for r in missing_malformed_field compliance_hold corridor_currency_issue timeout duplicate; do
    echo "== $r =="
    grep -rl "supports_flag_reason:.*$r" data/policy_docs data/sanctions_mock data/jurisdiction_rules data/iso20022_reference
  done
  ```
  Every one of the 5 sections must print at least one matching file path.

---

## TESTING STRATEGY

### Unit Tests

Not applicable — per the user's explicit choice, this ticket is static-content-only, no Python code. No `data/tests/` additions this ticket. (A future ticket — likely TICKET-4's ingestion work — is the natural place for a corpus-coverage validator, if one gets built.)

### Integration Tests

Not applicable at this ticket's scope — nothing consumes this corpus yet (TICKET-4 doesn't exist).

### Edge Cases

- `SANC-0001`'s entity name must byte-match `PMT-0002`'s creditor name exactly — verified by the `grep` validation command above, not just eyeballed.
- Every `fictional: true` document must have the watermark banner as its first body line, not buried lower in the file — a reviewer or future automated scan skimming just the top of the file should immediately see it.
- `supports_flag_reason` values must be valid `FlagReason` strings (lowercase snake_case) — a typo here silently breaks the "one doc per flag reason" acceptance criterion without erroring anywhere, since there's no code enforcing it yet.

### E2E / Browser Automation

Not applicable — no UI or HTTP surface exists at this ticket's scope.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

Not applicable — no Python code changes. (Optional: `uv run ruff check data/` to confirm this ticket didn't accidentally touch any `.py` file.)

### Level 2: Unit Tests

Not applicable this ticket (see above). `uv run pytest data/ -v` should still show the same 19 passing tests as before this ticket (proves nothing existing broke).

### Level 3: Integration Tests

Not applicable this ticket.

### Level 4: Manual Validation

```bash
# File counts
ls data/policy_docs/*.md | wc -l          # expect 4
ls data/sanctions_mock/*.md | wc -l       # expect 20
ls data/jurisdiction_rules/*.md | wc -l   # expect 4
ls data/iso20022_reference/*.md | wc -l   # expect 1

# Zed Trading Consolidated links PMT-0002 to its sanctions entry
grep -l "Zed Trading Consolidated" data/sanctions_mock/*.md   # expect exactly SANC-0001.md

# Every FlagReason has at least one supporting document (see full loop in Step-by-Step Tasks)
for r in missing_malformed_field compliance_hold corridor_currency_issue timeout duplicate; do
  grep -rl "supports_flag_reason:.*$r" data/policy_docs data/sanctions_mock data/jurisdiction_rules data/iso20022_reference || echo "MISSING: $r"
done

# Every fictional doc is watermarked
grep -rL "SYNTHETIC / FICTIONAL" data/policy_docs data/sanctions_mock data/jurisdiction_rules
# (expect no output -- an empty result means every file in these 3 dirs contains the banner)
```

### Level 5: E2E / Browser Automation

Not applicable — no UI exists at this ticket's scope.

### Level 6: Additional Validation (Optional)

None required.

---

## ACCEPTANCE CRITERIA

(mirrors `docs/specs/payment-compliance-exception-copilot.md` TICKET-2 verbatim, plus this plan's concrete decisions)

- [ ] Policy/sanctions/jurisdiction documents exist as versioned markdown files (frontmatter `version` field + git history).
- [ ] At least one document directly supports each of the 5 `FlagReason` scenarios from TICKET-1 (verified via the coverage-check command above).
- [ ] Sanctions entries are clearly labeled synthetic/fictional in-file (watermark banner + `fictional: true` frontmatter, all 20 files).
- [ ] `SANC-0001` uses the literal creditor name from `PMT-0002` (`"Zed Trading Consolidated"`).
- [ ] Real, public ISO 20022 `pain.001` field-spec content exists in the corpus (`ISO-0001`), accurately describing what `data/pain001_generator.py` actually builds.
- [ ] All 4 directories exist with the exact file counts above (4 + 20 + 4 + 1 = 29 files).
- [ ] Existing test suite (`uv run pytest data/ -v`) still passes unchanged (19 tests) — this ticket touches no existing code.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task's inline validation command passed immediately after that task
- [ ] Full coverage-check loop (Level 4) prints no `MISSING:` lines
- [ ] Watermark check (Level 4) prints no output (all fictional docs watermarked)
- [ ] `uv run pytest data/ -v` still passes (no regression)
- [ ] Acceptance criteria all met
- [ ] Code/content reviewed for quality and consistency (consider running the `code-review` skill before committing, even though this is content not code)

---

## NOTES

**Interview decisions (from the `plan-feature` clarification round), each with rationale:**

1. **4 categorized folders**, not the 2 named in the ticket/PRD estimate — `policy_docs/`, `sanctions_mock/`, `jurisdiction_rules/`, `iso20022_reference/`. Chosen by the user over the spec-literal 2-folder layout for clearer separation. This is a deliberate, acknowledged divergence from `docs/specs/...md` and the PRD's §6.3 indicative structure — flagged here rather than silently expanded.
2. **Markdown with a frontmatter version header** — chosen over plain `.txt` with git-only versioning, to give each document machine-readable metadata (`doc_id`, `version`, `supports_flag_reason`) that TICKET-4's ingestion and future citation logic can key off without parsing prose.
3. **All 20 sanctions entries built now**, not a minimal 3-5 — chosen because TICKET-6's "20/20" acceptance criterion is a fixed, already-known number (PRD §10, line 291); deferring it would just create a guaranteed follow-up task.
4. **Static files only, no generator/loader code** — chosen because this ticket's acceptance criteria describe content, not code, unlike TICKET-1. A loader will be added when TICKET-4 actually needs to ingest this corpus, not preemptively here.
5. **Our own authored ISO 20022 field-reference doc**, not fetched/copied real ISO spec text — avoids reuse/copyright ambiguity around official ISO 20022 specification text, stays consistent with the project's zero-infrastructure/local-only ethos, and mirrors exactly what `data/pain001_generator.py` (already verified against real pain.001.001.03 structure in TICKET-1's plan) actually produces rather than an idealized/generic description.
6. **Broader jurisdiction-rule set (4 corridors)**, matched to the corridors TICKET-1's actual payments use (EUR-GBP, USD-CHF, EUR-EUR, USD-USD) rather than inventing unrelated corridors — maximizes future RAG retrieval relevance against real fixtures.
7. **`PMT-`-style prefixed IDs** (`SANC-`, `POL-`, `JUR-`, `ISO-`) as both frontmatter `doc_id` and filename stem — mirrors the existing `PMT-0001` convention exactly, for consistency and so citations (TICKET-4/5/6 need "source doc, chunk id") have a stable, predictable identifier scheme.
8. **`supports_flag_reason` frontmatter tag on every document** — costs nothing now, makes the "one document per flag reason" acceptance criterion machine-checkable by a future validator instead of relying on manual review forever.

**Judgment call made during planning (not asked directly — flag before implementing if you disagree):**
- Sanctions entries use synthetic `SYN-J1`…`SYN-J5` risk-jurisdiction codes instead of any real country name, so the corpus can never be read as an assertion about a real country's actual sanctions status. This is stricter than the PRD requires (which only asks for fictional *entities*, not fictional *jurisdictions*) but costs nothing and removes any ambiguity.

**Scope boundary respected:** this ticket does not touch TICKET-4 (RAG ingestion/embedding), TICKET-5/6 (agents), or TICKET-3 (decision log). The corpus is authored to be *ready* for those tickets, not integrated with them.

## Confidence Score

**8/10** for one-pass success. The interview above resolved every open design decision ahead of time; the main residual risk is purely mechanical — 29 similarly-shaped files is a lot of repetitive authoring, and the most likely slip is a copy-paste frontmatter mismatch (wrong `doc_id` vs filename, or a `supports_flag_reason` typo) rather than a design gap. The Level 4 validation commands are specifically designed to catch exactly that class of mistake.
