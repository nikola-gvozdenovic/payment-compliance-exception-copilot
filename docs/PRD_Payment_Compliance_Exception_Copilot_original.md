# Product Requirements Document
## Payment Compliance & Exception Copilot

**Author:** [Your Name]
**Status:** Draft v1.0
**Purpose:** Personal portfolio project targeting AI Engineer roles in fintech/payment processing (built with Sokin's AI Engineer JD in mind)

---

## 1. Background & Motivation

I currently work on **Smart & Live Routing** at a payment processing company — using Gradient Boosting for offline policy learning and Thompson Sampling for online exploration to select the optimal payment gate/processor per transaction. That system is deliberately deterministic and statistical: it optimizes a numeric objective (approval rate, cost) and must be fast, auditable in the logging sense, and reproducible.

This project addresses a **different, complementary problem**: the parts of payment processing that involve judgment, unstructured reasoning, and explanation rather than a scoring function — investigating why a payment is stuck or flagged, checking it against compliance rules, and producing a human-readable explanation for auditors, compliance officers, or merchants.

The goal is not to replace deterministic systems (like my routing work) with LLMs, but to demonstrate where **agentic AI genuinely adds value** in a regulated payments environment: exception handling, compliance reasoning, and auditability.

---

## 2. Problem Statement

When a cross-border payment is delayed, flagged, or blocked, a human compliance analyst currently has to:
1. Manually inspect the payment message and its metadata
2. Cross-reference internal policy documents, sanctions lists, and rail-specific rules
3. Decide whether to clear, block, or escalate the payment
4. Write up a clear explanation for audit/regulatory purposes

This process is manual, slow, inconsistent across analysts, and hard to scale as transaction volume grows — especially for a multi-currency, multi-rail business.

---

## 3. Goals

- Build a multi-agent AI system that triages, checks compliance, and explains flagged/stuck cross-border payments
- Ground every agent decision in retrieved source documents (RAG), not model memory — for auditability
- Produce a clear, human-readable audit trail for every decision
- Demonstrate production-mindset practices: guardrails, evaluation metrics, CI/CD integration, containerized deployment
- Model the domain accurately using real-world standards (ISO 20022 messaging) and Sokin's actual business shape (multi-currency, cross-border, SWIFT/local rails, treasury/AP/AR)

## 3.1 Constraint: Zero-Cost Build

This project must be buildable and demoable **entirely for free** — no paid cloud services, no paid API usage beyond free tiers, no infrastructure costs. This constraint is intentional, not just budget-driven: it also proves I can build a credible, production-shaped system using open-source and free-tier tooling, which is itself a useful signal (resourcefulness, not dependency on a company card).

Every technology choice below is selected specifically because it has a genuinely free option, not just a "free trial."

## 4. Non-Goals

- This project does **not** perform live payment routing/gate selection (covered separately by my production Smart Routing work — GBM + Thompson Sampling)
- This project does **not** connect to real banking rails, real sanctions databases, or real customer/PII data — all data is synthetic
- This is not a claims-of-accuracy production compliance tool; it's a portfolio demonstration of architecture and engineering practice

---

## 5. Target "User" (for this portfolio's purposes)

- Primary: hiring managers/engineers evaluating this as a portfolio artifact
- Simulated end user within the product: a payments compliance analyst who reviews flagged transactions

---

## 6. Scope & System Overview

The system ingests a simulated flagged/stuck payment (modeled as an ISO 20022 `pain.001`-style message) and runs it through a pipeline of agents that hand off work, culminating in a compliance decision and a written report.

### 6.1 Agents

**1. Triage Agent**
- Input: a flagged/stuck payment + its processing log
- Task: classify the likely cause (missing/malformed field, compliance hold, corridor/currency issue, timeout, duplicate)
- Method: retrieves relevant internal policy/spec docs via RAG before classifying, rather than guessing from parametric knowledge
- Output: cause classification + confidence + supporting citation from retrieved docs

**2. Compliance Agent**
- Input: payment + triage output
- Task: check the payment against a mock sanctions list, AML rule set, and jurisdiction-specific policy docs; decide **Clear / Block / Escalate**
- Method: RAG over policy documents; must cite the specific rule/document used for its decision — no unattributed decisions allowed
- Output: decision + cited rule(s) + reasoning trace

**3. Audit / Report Agent**
- Input: outputs from Triage + Compliance agents
- Task: synthesize into a clear, structured, plain-English report suitable for a compliance officer or auditor
- Output: a Markdown/PDF-style report per payment

**4. Dev-Tooling Agent (separate track, same repo)**
- Not part of the payment reasoning pipeline — this operates on the **codebase itself**
- Task: automatically generates unit tests for new/changed functions in the agent codebase, runs in CI on every PR, flags missing coverage
- Purpose: demonstrates "agentic code generation" and AI-assisted SDLC integration, distinct from the payments-reasoning agents above

### 6.2 RAG Knowledge Base

Synthetic but realistic documents, chunked and embedded:
- ISO 20022 `pain.001` field specifications (real public schema docs)
- Mock internal routing/compliance policy documents (written by me, styled like real policy docs)
- Mock sanctions/watchlist entries (synthetic names/entities — clearly labeled as fake)
- Mock jurisdiction-specific rules (e.g., "EUR→GBP corridor requires X")

Vector store: **Chroma**, run locally and file-based — chosen explicitly (not left abstract) and free, with no server or hosting cost.

### 6.3 Guardrails

- No raw account numbers, names, or other PII ever enter an LLM prompt — all identifiers are tokenized/masked before agents see them
- A test suite proves this: a red-team style test feeds a payment with embedded PII and asserts the LLM never receives or outputs it
- Compliance Agent decisions above a risk threshold are never auto-executed — always routed to "Escalate" for human review (no autonomous blocking of real funds, even in the simulation's own logic)

### 6.4 Evaluation

- RAGAS or a custom eval harness measuring:
  - Retrieval precision/faithfulness for Triage and Compliance agents
  - Compliance Agent accuracy against a hand-labeled synthetic test set (e.g., "20/20 correctly blocks known sanctioned test entities")
- Results published in the README with actual numbers, not just claimed capability

---

## 7. Technical Architecture

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

### 7.1 Tech Stack (all free-tier or open-source)

| Layer | Choice | Why it's free |
|---|---|---|
| Orchestration | LangChain or CrewAI | Open-source, no license cost |
| LLM | **Ollama running a local open-weight model** (e.g., Llama 3.1 8B or Mistral 7B) as the default | Runs entirely on your own machine, zero API cost, no usage limits. Code is written model-agnostically (via LangChain's LLM abstraction) so it can be pointed at a hosted API later if desired — but the default path costs nothing |
| Vector DB | **Chroma** (local, file-based) | Runs in-process, no server, no hosting cost — simpler than pgvector for a local-only setup |
| Backend | Python | Free |
| Containerization | Docker + Docker Compose | Docker is free to use locally |
| CI/CD | GitHub Actions | Free/unlimited minutes on public repositories |
| "Cloud deployment" | **Skip real cloud, or use a free tier only** (e.g., Render/Railway free web-service tier, or AWS/GCP always-free tier resources) — entirely optional, not required to demonstrate containerization | Avoids any recurring cost; Docker Compose running locally already proves the containerization skill for the JD |
| Eval | RAGAS | Open-source Python library, free |
| Data format | ISO 20022 XML (`pain.001`) | Public schema, free to use |

**Note on the LLM choice:** Anthropic's Claude API is not free beyond a small initial trial credit, so it is not the default here. If you want the *demo/walkthrough video* to show Claude specifically (since you're applying to a Claude-centric role at Sokin — noting the JD mentions "Claude Code" as an example tool), you can record one short segment using Claude's free trial credit or a very small number of calls, and disclose in the README that the system runs fully free using local models via Ollama, with optional hosted-model support.

---

## 8. Data Model (Synthetic)

- **Payment record**: payment ID, source/destination currency, corridor, amount, timestamp, ISO 20022 XML payload, status, flag reason (if any)
- **Policy document store**: versioned markdown/text docs representing internal policy
- **Sanctions mock list**: synthetic entity names, clearly watermarked as fictional
- **Agent decision log**: append-only log of every agent's input, retrieved context, decision, and reasoning — this is the audit trail

---

## 9. Milestones

| Phase | Deliverable |
|---|---|
| 1 | Data model + synthetic payment/policy dataset + ISO 20022 message generator |
| 2 | RAG pipeline (ingestion, embedding, retrieval) over policy docs |
| 3 | Triage Agent + Compliance Agent (core reasoning pipeline) |
| 4 | Audit Agent + report generation |
| 5 | Guardrail tests (PII masking) + eval harness (RAGAS) with published results |
| 6 | Dev-Tooling Agent + GitHub Actions CI integration |
| 7 | Dockerize with Docker Compose (local); optional free-tier cloud deployment (e.g., Render/Railway free tier) if time allows |
| 8 | Architecture diagram, README, recorded walkthrough video |

---

## 10. Success Criteria (for the portfolio's purposes)

- End-to-end demo: a flagged synthetic payment goes in, a full audit report comes out, with visible retrieval citations at each step
- Guardrail test passes and is shown explicitly (PII never reaches the LLM)
- At least one real evaluation metric with numbers, not just a claim
- CI pipeline visibly runs on a real PR with generated tests
- README clearly explains the "why" — the reasoning about where agentic AI belongs vs. deterministic systems (tying to my Smart Routing experience)

---

## 11. Risks / Open Questions

- Scope creep: this touches many JD bullets; must timebox each phase to avoid never finishing
- Synthetic data realism: needs to be detailed enough to be credible without implying access to real customer/production data
- Should clearly disclose in the README that this is a portfolio simulation, not a production compliance system, to avoid any implication of overclaiming regulatory rigor

---

## 12. Appendix: Mapping to Sokin JD Requirements

| JD Requirement | Project Component |
|---|---|
| Agentic AI development, multi-agent orchestration | Triage → Compliance → Audit pipeline |
| Agentic code generation, CI/CD integration | Dev-Tooling Agent + GitHub Actions |
| RAG, context management | pgvector knowledge base over policy/ISO 20022 docs |
| Full SDLC AI integration | Test generation, eval automation |
| Fintech domain, compliance | ISO 20022, mock AML/sanctions checks |
| Production AI systems, guardrails, observability | PII masking guardrail test, decision logging, eval metrics |
| Cloud/containers | Docker Compose (local, free) + optional free-tier cloud deployment |
