# Product Requirements Document
## Payment Compliance & Exception Copilot

**Author:** Nikola Gvozdenovic
**Status:** Draft v1.0
**Purpose:** Personal portfolio project targeting AI Engineer roles in fintech/payment processing, built with Sokin's AI Engineer job description in mind.

---

## 1. Executive Summary

Payment Compliance & Exception Copilot is a multi-agent AI system that investigates flagged or stuck cross-border payments, checks them against compliance rules, and produces a human-readable, citation-backed audit report — the kind of judgment-and-explanation work a compliance analyst currently does by hand.

The author currently builds **Smart & Live Routing** in production — Gradient Boosting for offline policy learning and Thompson Sampling for online exploration, selecting the optimal payment gate/processor per transaction. That system is deterministic and statistical: it optimizes a numeric objective (approval rate, cost) and must be fast and reproducible. This project deliberately addresses the *complementary* problem: the parts of payment processing that involve judgment and unstructured reasoning rather than a scoring function — why a payment is stuck, whether it violates a compliance rule, and how to explain that decision to an auditor or merchant. The goal is not to replace deterministic systems with LLMs, but to demonstrate where agentic AI genuinely adds value in a regulated payments environment.

The MVP is an end-to-end pipeline — Triage Agent → Compliance Agent → Audit Agent — that ingests a simulated flagged payment (modeled as an ISO 20022 `pain.001` message), grounds every agent decision in retrieved source documents (RAG, never model memory alone), and produces a structured report with visible citations at each step. A separate Dev-Tooling Agent, operating on the codebase itself rather than on payments, generates unit tests in CI to demonstrate agentic SDLC integration. The entire system must be buildable and demoable at zero infrastructure cost, using local/open-source tooling throughout.

---

## 2. Mission

**Mission statement:** Show that agentic AI can take over the judgment-and-explanation layer of payment operations — triage, compliance reasoning, and audit reporting — safely, auditably, and without displacing the deterministic systems that should keep making the numeric decisions.

**Core principles:**

1. **Grounded, not guessed.** Every agent decision must be backed by retrieved source documents (RAG). No unattributed decisions — if an agent can't cite the rule or spec it used, it hasn't made a valid decision.
2. **Auditability over autonomy.** The system produces a full decision trail (inputs, retrieved context, reasoning, output) for every payment. High-risk decisions are always escalated to a human, never auto-executed.
3. **Zero-cost, production-shaped.** No paid cloud services or APIs beyond free tiers — proving the system is built with genuine engineering discipline (guardrails, evaluation, CI/CD, containerization), not proving access to a company card.
4. **Right tool for the job.** LLMs are used only where the problem is genuinely judgment-shaped (triage, compliance reasoning, explanation). Numeric/optimization problems (like live routing) stay with deterministic, statistical systems — this project exists specifically to draw that line clearly.
5. **Domain-accurate simulation.** The system models real-world standards (ISO 20022 messaging) and a realistic business shape (multi-currency, cross-border, SWIFT/local rails) using entirely synthetic data — no real PII, no real banking connections.

---

## 3. Target Users

**Primary: Hiring managers and engineers evaluating this as a portfolio artifact.**
- Technical comfort level: high — reviewers are engineers/technical hiring managers who will read code, architecture diagrams, and eval results, not just a demo video.
- Key needs: evidence of production-mindset AI engineering (agentic orchestration, RAG, guardrails, eval, CI/CD, containerization) and clear reasoning about *when* to use agentic AI vs. deterministic systems.
- Pain point being addressed: a portfolio project that only "looks like a demo" without evaluation numbers, guardrail tests, or CI integration doesn't differentiate a candidate — this project is designed specifically to show real engineering rigor.

**Simulated end user within the product: a payments compliance analyst.**
- Technical comfort level: moderate — comfortable with payment operations tooling and policy documents, not necessarily with ML/AI internals.
- Key needs: quickly understand why a payment is stuck, see the specific rule or policy invoked, and get a decision (Clear/Block/Escalate) they can trust and defend to an auditor or regulator.
- Pain point being addressed: today this analyst manually inspects payment metadata, cross-references policy documents and sanctions lists by hand, and writes up explanations — a process that is slow, inconsistent across analysts, and doesn't scale with transaction volume.

---

## 4. MVP Scope

### Core Functionality
- ✅ Synthetic flagged/stuck payment modeled as an ISO 20022 `pain.001`-style message, with processing log/flag reason
- ✅ Triage Agent: classifies likely cause (missing/malformed field, compliance hold, corridor/currency issue, timeout, duplicate), grounded in retrieved policy/spec docs, with confidence + citation
- ✅ Compliance Agent: checks payment against mock sanctions list, AML rule set, and jurisdiction-specific policy docs; decides Clear / Block / Escalate with cited rule(s) and reasoning trace
- ✅ Audit/Report Agent: synthesizes Triage + Compliance outputs into a structured, plain-English report (Markdown/PDF-style) per payment
- ✅ RAG knowledge base (ISO 20022 field specs, mock internal policy docs, mock sanctions/watchlist, mock jurisdiction rules) chunked and embedded in a local vector store
- ✅ Append-only agent decision log capturing every agent's input, retrieved context, decision, and reasoning — the audit trail

### Technical
- ✅ PII guardrail: no raw account numbers, names, or identifiers ever enter an LLM prompt — all identifiers tokenized/masked first, proven by a red-team-style test
- ✅ Escalation ceiling: Compliance Agent decisions above a risk threshold are never auto-executed — always routed to "Escalate," even within the simulation's own logic
- ✅ Evaluation harness (RAGAS or custom) measuring retrieval precision/faithfulness and Compliance Agent accuracy against a hand-labeled synthetic test set, with results published in the README
- ✅ Dev-Tooling Agent that generates unit tests for new/changed functions in the agent codebase itself, running in CI on every PR
- ✅ Dockerized system (Docker Compose) runnable entirely locally

### Integration
- ✅ Model-agnostic LLM integration (via an LLM abstraction layer) defaulting to a local open-weight model, so a hosted API can be swapped in later without a rewrite
- ✅ GitHub Actions CI running the Dev-Tooling Agent's generated tests and reporting coverage on every PR

### Deployment
- ✅ Local, zero-cost deployment via Docker Compose as the primary demo path
- ❌ Live payment routing/gate selection — that is covered separately by the author's production Smart Routing work (GBM + Thompson Sampling) and is explicitly out of scope
- ❌ Connections to real banking rails, real sanctions databases, or real customer/PII data — all data is synthetic
- ❌ Claims of production-grade regulatory compliance accuracy — this is a portfolio demonstration of architecture and engineering practice, not a certified compliance tool
- ❌ Real cloud deployment as a requirement — an optional free-tier deployment (e.g., Render/Railway free tier) may be added if time allows, but is not required to demonstrate containerization

---

## 5. User Stories

1. **As a compliance analyst**, I want a flagged payment automatically triaged with a likely cause and supporting citation, so that I don't have to manually re-derive why it was flagged from raw logs and specs.
   - *Example:* A payment flagged for a missing remittance field is triaged as "malformed field — missing `RmtInf`," citing the specific ISO 20022 `pain.001` field spec.

2. **As a compliance analyst**, I want the system to check a flagged payment against sanctions/AML/jurisdiction rules and produce a Clear/Block/Escalate decision with the exact rule cited, so that I can trust and defend the decision without re-checking every source myself.
   - *Example:* A payment routed through a jurisdiction with a corridor-specific rule ("EUR→GBP corridor requires X") is automatically checked against that rule and the citation is shown alongside the decision.

3. **As a compliance analyst**, I want a plain-English audit report generated per payment, so that I can hand it directly to an auditor or regulator without additional write-up work.
   - *Example:* A "Block" decision produces a Markdown report stating the cause, the cited sanctions entry, and the recommended next step.

4. **As a compliance analyst**, I want any high-risk decision to be escalated to a human rather than auto-executed, so that no autonomous system ever blocks or clears funds without oversight.
   - *Example:* A borderline sanctions-list name match is never auto-blocked; it is always routed to "Escalate."

5. **As a hiring manager/reviewer**, I want to see retrieval citations at every step of the pipeline, so that I can verify the system reasons from real source documents rather than model memory.

6. **As a hiring manager/reviewer**, I want published evaluation numbers (retrieval faithfulness, compliance accuracy against a labeled test set), so that I can assess real system quality rather than a claimed capability.

7. **As a hiring manager/reviewer**, I want to see a guardrail test that proves PII never reaches the LLM, so that I can trust the system was built with production compliance/privacy discipline in mind.

**Technical user stories:**

8. **As the codebase maintainer**, I want a Dev-Tooling Agent to generate unit tests for new or changed functions and run them in CI on every PR, so that test coverage keeps pace with a fast-moving agent codebase without manual test-writing overhead.

9. **As the codebase maintainer**, I want the LLM integration to be model-agnostic, so that I can run the whole system for free against a local model by default, while still being able to point it at a hosted model (e.g., for a demo recording) without rewriting agent logic.

---

## 6. Core Architecture & Patterns

### 6.1 High-Level Architecture

```
[Simulated Payment Event]
        |
        v
 [Triage Agent] --(RAG: policy docs)--> classification
        |
        v
 [Compliance Agent] --(RAG: sanctions/policy)--> decision + citation
        |
        v
 [Audit Agent] --> human-readable report
        |
        v
 [Output: report.md / dashboard]

(separate track)
[Codebase] --> [Dev-Tooling Agent] --> generates tests --> [GitHub Actions CI] --> pass/fail + coverage report
```

The payment-reasoning pipeline (Triage → Compliance → Audit) is a linear agent handoff: each agent consumes the prior agent's structured output plus its own RAG retrieval, and never makes a decision without a supporting citation. The Dev-Tooling Agent is architecturally and operationally separate — it runs against the codebase, not against payments, and is triggered by CI events (PRs), not by the payment pipeline.

### 6.2 Key Design Patterns

- **Retrieval-before-reasoning:** every agent retrieves relevant source documents from the vector store *before* producing a classification/decision — retrieval is not optional context, it's a required step, and the citation is part of the agent's output contract.
- **No unattributed decisions:** the Compliance Agent's output schema requires at least one cited rule/document; an agent output without a citation is treated as invalid, not as a valid low-confidence answer.
- **Escalate-by-default on risk:** the Compliance Agent's decision space is Clear / Block / Escalate, but any decision above a configured risk threshold is forced to Escalate regardless of the agent's raw output — this is enforced outside the LLM call, not requested of the LLM.
- **PII never enters the prompt boundary:** identifiers are tokenized/masked at the data-ingestion layer, before any agent sees the payment — this is a hard boundary enforced and tested independently of agent behavior, not a prompting convention.
- **Append-only audit log:** every agent invocation (input, retrieved context, decision, reasoning) is logged append-only, forming the audit trail independent of the final report — the report is a rendering of this log, not the source of truth.
- **Model-agnostic LLM layer:** agent logic is written against an LLM abstraction (e.g., LangChain's LLM interface) so the default local model can be swapped for a hosted model via configuration only.

### 6.3 Directory Structure (indicative)

```
/agents
  triage_agent.py
  compliance_agent.py
  audit_agent.py
  dev_tooling_agent.py
/rag
  ingestion/
  embeddings/
  retriever.py
/data
  synthetic_payments/
  policy_docs/
  sanctions_mock/
/guardrails
  pii_masking.py
  tests/
/eval
  ragas_harness.py
  labeled_test_set/
/infra
  Dockerfile
  docker-compose.yml
.github/workflows/
  ci.yml
```

---

## 7. Tools/Features

### 7.1 Triage Agent
- **Purpose:** classify why a flagged/stuck payment needs attention.
- **Input:** a flagged/stuck payment (ISO 20022 `pain.001`-style) + its processing log.
- **Operations:** retrieve relevant policy/spec docs via RAG → classify cause (missing/malformed field, compliance hold, corridor/currency issue, timeout, duplicate) → attach confidence + citation.
- **Key features:** retrieval-grounded classification (never guesses from parametric knowledge alone); structured output (cause, confidence, citation) consumed directly by the Compliance Agent.

### 7.2 Compliance Agent
- **Purpose:** determine whether a payment should be cleared, blocked, or escalated.
- **Input:** payment + Triage Agent output.
- **Operations:** retrieve relevant sanctions/AML/jurisdiction policy docs via RAG → check payment against them → decide Clear / Block / Escalate → cite the specific rule/document used.
- **Key features:** no unattributed decisions (citation required); escalate-by-default enforcement above a risk threshold; reasoning trace attached to every decision.

### 7.3 Audit / Report Agent
- **Purpose:** turn Triage + Compliance outputs into a report a human can act on or file.
- **Input:** Triage Agent output + Compliance Agent output (including citations and reasoning traces).
- **Operations:** synthesize into a structured, plain-English report.
- **Key features:** Markdown/PDF-style output suitable for a compliance officer or auditor; retains and surfaces the citations from upstream agents rather than summarizing them away.

### 7.4 Dev-Tooling Agent
- **Purpose:** demonstrate agentic code generation and AI-assisted SDLC integration — separate from the payments-reasoning pipeline.
- **Input:** new/changed functions in the agent codebase (via PR diff).
- **Operations:** generate unit tests for new/changed functions → run in CI → flag missing coverage.
- **Key features:** runs automatically on every PR; produces a pass/fail + coverage signal in GitHub Actions.

### 7.5 RAG Knowledge Base
Synthetic but realistic documents, chunked and embedded:
- ISO 20022 `pain.001` field specifications (real public schema docs)
- Mock internal routing/compliance policy documents (authored to resemble real policy docs)
- Mock sanctions/watchlist entries (synthetic names/entities, clearly labeled as fake)
- Mock jurisdiction-specific rules (e.g., "EUR→GBP corridor requires X")

Vector store: **Chroma**, run locally and file-based — chosen explicitly (not left abstract), free, no server or hosting cost.

### 7.6 Guardrails
- No raw account numbers, names, or other PII ever enter an LLM prompt — all identifiers are tokenized/masked before agents see them.
- A test suite proves this: a red-team-style test feeds a payment with embedded PII and asserts the LLM never receives or outputs it.
- Compliance Agent decisions above a risk threshold are never auto-executed — always routed to "Escalate" for human review (no autonomous blocking of real funds, even in the simulation's own logic).

### 7.7 Evaluation
- RAGAS or a custom eval harness measuring:
  - Retrieval precision/faithfulness for Triage and Compliance agents.
  - Compliance Agent accuracy against a hand-labeled synthetic test set (e.g., "20/20 correctly blocks known sanctioned test entities").
- Results published in the README with actual numbers, not just claimed capability.

---

## 8. Technology Stack

All choices selected specifically because they have a genuinely free option, not just a "free trial" — this is a hard constraint on the project, not a preference.

| Layer | Choice | Why it's free |
|---|---|---|
| Orchestration | LangChain or CrewAI | Open-source, no license cost |
| LLM | **Ollama running a local open-weight model** (e.g., Llama 3.1 8B or Mistral 7B) as the default | Runs entirely on the local machine, zero API cost, no usage limits. Written model-agnostically (via LangChain's LLM abstraction) so it can be pointed at a hosted API later — but the default path costs nothing |
| Vector DB | **Chroma** (local, file-based) | Runs in-process, no server, no hosting cost — simpler than pgvector for a local-only setup |
| Backend | Python | Free |
| Containerization | Docker + Docker Compose | Free to use locally |
| CI/CD | GitHub Actions | Free/unlimited minutes on public repositories |
| "Cloud deployment" | Skip real cloud, or use a free tier only (e.g., Render/Railway free web-service tier, or an AWS/GCP always-free tier resource) — entirely optional | Avoids recurring cost; Docker Compose running locally already proves containerization skill |
| Eval | RAGAS | Open-source Python library, free |
| Data format | ISO 20022 XML (`pain.001`) | Public schema, free to use |

**Note on LLM choice:** Anthropic's Claude API is not free beyond a small initial trial credit, so it is not the default. If a demo/walkthrough video should show Claude specifically (relevant for a Claude-centric role, since the target JD references "Claude Code" as an example tool), one short segment can be recorded using Claude's free trial credit or a very small number of calls — with the README disclosing that the system runs fully free using local models via Ollama, with optional hosted-model support.

### Dependencies
- LangChain or CrewAI (orchestration)
- Ollama (local LLM runtime)
- Chroma (vector store)
- RAGAS (evaluation)
- Docker / Docker Compose

### Optional Dependencies
- A hosted LLM API (e.g., Claude) for an optional demo segment only — not required for the system to run.
- A free-tier hosting provider (Render/Railway) for an optional live deployment.

---

## 9. Security & Configuration

### Authentication/Authorization
- Not applicable for the MVP — this is a local/demo system with no multi-tenant access or real customer data. If a dashboard/API is exposed beyond localhost, it should sit behind, at minimum, a basic auth gate before any non-local deployment.

### Configuration Management
- LLM provider/model selectable via configuration (environment variable or config file), defaulting to the local Ollama model.
- Risk threshold for forced escalation configurable, not hardcoded inline in agent logic.
- Paths to the RAG document corpus and vector store location configurable via environment variables.

### Security Scope

**In-scope:**
- PII masking/tokenization guardrail before any data reaches an LLM prompt, with an explicit test proving it.
- Append-only, tamper-evident-in-spirit decision logging (every agent input/retrieval/decision recorded).
- Enforced human-escalation ceiling on high-risk compliance decisions, implemented outside the LLM call.
- Clear README disclosure that all data (payments, sanctions entries, policy docs) is synthetic — no real PII, no real banking connections, no claim of production regulatory rigor.

**Out-of-scope:**
- Real authentication/authorization systems, secrets management, or multi-tenant isolation (no real users or real data exist in this system).
- Real sanctions/watchlist data or connections to real banking rails.
- Formal regulatory certification or compliance sign-off — this is a portfolio demonstration of architecture and engineering practice, not a production compliance product.

### Deployment Considerations
- Primary deployment target: local Docker Compose — zero cost, fully reproducible.
- Optional secondary target: a free-tier cloud host (Render/Railway) or an always-free cloud tier resource, purely to additionally demonstrate deployment skill — not required for the core demo.

---

## 10. Success Criteria

**MVP success is defined as:**
- ✅ End-to-end demo: a flagged synthetic payment goes in, a full audit report comes out, with visible retrieval citations at each step.
- ✅ Guardrail test passes and is shown explicitly (PII never reaches the LLM).
- ✅ At least one real evaluation metric with numbers, not just a claim (retrieval faithfulness and/or compliance accuracy against a labeled test set).
- ✅ CI pipeline visibly runs on a real PR with Dev-Tooling-Agent-generated tests.
- ✅ README clearly explains the "why" — the reasoning about where agentic AI belongs vs. deterministic systems, tying back to the author's Smart Routing production experience.

**Quality indicators:**
- Every Compliance Agent decision carries at least one citation; zero unattributed decisions in the eval test set.
- Zero instances of raw PII observed in LLM prompts/outputs across the guardrail test suite.
- Compliance Agent correctly handles all known-sanctioned synthetic test entities (target: 20/20 or equivalent, published in the README).

**User experience goals:**
- A compliance analyst persona reading a generated report should be able to understand the cause, the decision, and the specific rule cited without needing to consult the underlying policy documents directly.
- A reviewer should be able to trace any decision back to its source document within the report/decision log, without digging through code.

---

## 11. Implementation Phases

### Phase 1 — Foundation & Data
**Goal:** establish the synthetic domain data the rest of the system reasons over.
- ✅ Data model design (payment record, policy document store, sanctions mock list, agent decision log)
- ✅ Synthetic payment + policy dataset
- ✅ ISO 20022 `pain.001` message generator
**Validation:** a set of synthetic flagged payments exists, each with a plausible flag reason, and can be loaded by downstream components.

### Phase 2 — Retrieval & Reasoning Pipeline
**Goal:** build the RAG-grounded agent pipeline that turns a flagged payment into a decision.
- ✅ RAG pipeline (ingestion, embedding, retrieval) over policy docs, using Chroma
- ✅ Triage Agent (cause classification + citation)
- ✅ Compliance Agent (Clear/Block/Escalate decision + citation + reasoning trace)
- ✅ Audit Agent + report generation
**Validation:** running the pipeline against a synthetic flagged payment produces a report with citations traceable to specific source documents at every step.

### Phase 3 — Guardrails, Evaluation & Trust
**Goal:** prove the system is safe and measurably accurate, not just functional.
- ✅ PII masking guardrail + red-team-style test proving it
- ✅ Escalate-by-default enforcement above the configured risk threshold
- ✅ Eval harness (RAGAS or custom) with published retrieval/accuracy numbers
**Validation:** guardrail test suite passes visibly; eval numbers are published in the README, not just claimed.

### Phase 4 — SDLC Integration & Packaging
**Goal:** demonstrate agentic code generation and a production-shaped, zero-cost deployment.
- ✅ Dev-Tooling Agent generating tests for new/changed functions
- ✅ GitHub Actions CI running those tests on every PR
- ✅ Dockerize with Docker Compose (local); optional free-tier cloud deployment if time allows
- ✅ Architecture diagram, README, recorded walkthrough video
**Validation:** a real PR against the repo triggers CI, the Dev-Tooling Agent's generated tests run and report coverage, and the whole system starts from a single `docker compose up`.

---

## 12. Future Considerations

- Point the model-agnostic LLM layer at a hosted model (e.g., Claude) as a first-class supported mode, not just a demo-only recording, once cost is no longer a hard constraint.
- Extend the RAG knowledge base to additional ISO 20022 message types beyond `pain.001` (e.g., `pacs.008`) to widen the range of payment scenarios the Copilot can reason about.
- **Lightweight dashboard/API**, post-MVP: the architecture diagram (Section 6.1) shows `report.md / dashboard` as an eventual output. If pursued, a minimal API would expose `POST /payments/{payment_id}/process` (run the pipeline), `GET /payments/{payment_id}/report` (fetch the generated report + citations), and `GET /payments/{payment_id}/decision-log` (fetch the raw audit trail) — letting the pipeline be triggered and reports browsed interactively rather than run as a script. Not part of MVP scope; no milestone currently calls for it.
- Explore multi-turn analyst interaction — letting a human compliance analyst ask follow-up questions against the same retrieved context and decision log, rather than only consuming a static report.
- Expand the Dev-Tooling Agent beyond unit-test generation (e.g., flagging risky changes to guardrail or escalation logic specifically, given how safety-critical that code path is).
- Optional always-on free-tier cloud deployment, if a stable free-tier target is identified, to give reviewers a live link rather than only a local/video demo.

---

## 13. Risks & Mitigations

1. **Risk: Scope creep.** This project touches many JD bullets (agentic orchestration, RAG, guardrails, eval, CI/CD, containerization) and could expand indefinitely.
   - **Mitigation:** timebox each phase (Section 11) and treat Phase 4's optional cloud deployment as genuinely optional — the local Docker Compose demo is sufficient to prove the required skills.

2. **Risk: Synthetic data realism.** Data needs to be detailed enough to be credible without implying access to real customer/production data.
   - **Mitigation:** base synthetic documents on real public standards (ISO 20022 schemas) for structural realism, while clearly watermarking sanctions/policy content as fictional.

3. **Risk: Overclaiming regulatory rigor.** A well-built demo could be mistaken for (or implied to be) a production-grade compliance tool.
   - **Mitigation:** explicit README disclosure that this is a portfolio simulation, not a production compliance system, stated up front rather than buried.

4. **Risk: Local LLM quality ceiling.** A local open-weight model (Llama 3.1 8B / Mistral 7B) may produce weaker triage/compliance reasoning than a frontier hosted model, affecting eval numbers.
   - **Mitigation:** the model-agnostic LLM layer allows swapping in a hosted model for comparison without rewriting agent logic; publish eval numbers against whichever model is actually used, and disclose the trade-off in the README rather than hiding it.

5. **Risk: Unattributed or fabricated citations.** An LLM agent could produce a plausible-sounding citation that doesn't actually match retrieved content ("hallucinated grounding").
   - **Mitigation:** structurally require the citation to be a retrieved chunk ID/reference the system can verify against the vector store, not free-text the model invents; the RAGAS faithfulness metric in Phase 3 is specifically chosen to catch this.

---

## 14. Appendix

### Related Documents
- ISO 20022 `pain.001` public schema documentation (external reference for the message generator and field-spec RAG corpus).
- `docs/Gate_List_API_Spec_Balance.pdf`-style internal spec documents are **not** part of this project — they belong to the author's separate production Smart Routing system and are referenced here only as background context (Section 1), not as a dependency.

### Key Dependencies
- [LangChain](https://python.langchain.com/) or [CrewAI](https://www.crewai.com/) — agent orchestration
- [Ollama](https://ollama.com/) — local LLM runtime
- [Chroma](https://www.trychroma.com/) — local vector store
- [RAGAS](https://docs.ragas.io/) — RAG evaluation
- Docker / Docker Compose, GitHub Actions

### Mapping to Target JD Requirements

| JD Requirement | Project Component |
|---|---|
| Agentic AI development, multi-agent orchestration | Triage → Compliance → Audit pipeline |
| Agentic code generation, CI/CD integration | Dev-Tooling Agent + GitHub Actions |
| RAG, context management | Chroma knowledge base over policy/ISO 20022 docs |
| Full SDLC AI integration | Test generation, eval automation |
| Fintech domain, compliance | ISO 20022, mock AML/sanctions checks |
| Production AI systems, guardrails, observability | PII masking guardrail test, decision logging, eval metrics |
| Cloud/containers | Docker Compose (local) + optional free-tier cloud deployment |

---

*Assumptions made in this draft: no prior conversation history was available beyond the existing informal draft found in this repository, which this PRD restructures into the standard template while preserving all substantive requirements. The original informal draft is preserved at `docs/PRD_Payment_Compliance_Exception_Copilot_original.md`. The dashboard/API idea (Section 6.1's diagram, Section 12) is a future consideration only, not confirmed MVP scope. The `.claude/context/` files describing the author's production SmartRouting engine were intentionally excluded from this PRD's technical content — that system is explicitly Non-Goal background context (Section 1), not a component of this project.*
