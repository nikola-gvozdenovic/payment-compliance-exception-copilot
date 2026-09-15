---
name: nutshell
description: Generates a short, plain-language summary of the project — a simple schema of how it works plus jargon-free explanations — so anyone can grasp the project's goal at a glance. Use when someone needs to understand what the project is and why, not how it's built.
argument-hint: [optional audience, e.g. "for a recruiter" or "explain like I'm 5"]
---

# Nutshell: Explain the Project Simply

## Objective

Produce one short document that explains this project the way you'd explain it out
loud to a smart friend who has never worked in AI, payments, or software. Every
technical word gets a plain-English translation right next to it. No jargon left
unexplained, no implementation detail included just because it exists.

This is a "what and why," not a "how." Skip tech stack, milestones, timelines, file
structure — that's what the PRD and specs are for. If someone reads this and still
doesn't know what the project actually does, it has failed at its one job.

## Process

### 1. Find the source of truth

Read whatever document currently explains the project's goals and scope — usually the
PRD (e.g. `docs/PRD_*.md`), otherwise the top-level README or the most recent planning
doc. Look for: what problem it solves, who it's for, and what actually happens from
input to output.

If an audience was given as an argument (e.g. "for a recruiter", "explain like I'm 5"),
keep that reader specifically in mind for every sentence written in step 2 — the same
facts, but the vocabulary and examples shift for them.

### 2. Reduce it to the simplest true version

Boil the source material down to:

- **One sentence**: what is this, in plain words?
- **One sentence**: what problem does it solve? Use a concrete everyday example if one
  helps ("like a bank employee double-checking a wire transfer before it goes out").
- **A simple schema**: an actual diagram, not just a prose arrow-chain, and not a
  `mermaid` code fence — hand-author a real standalone SVG image (boxes, arrows with
  arrowhead markers, a decision diamond where the process branches) and embed it with
  Markdown image syntax, e.g. `![...](assets/nutshell-flow.svg)`. This renders
  identically everywhere (GitHub, an IDE preview, a plain browser) with no dependency
  on the viewer supporting mermaid. Use plain-word box labels only, four to six boxes
  max, real arrowheads (an SVG `<marker>`), literal hex colors (no CSS variables or
  `currentColor` — a standalone SVG has no host page to inherit a theme from; pick one
  legible, paper-toned palette with a small `<rect>` background card so it reads
  cleanly regardless of the surrounding page's theme), and a plain system font stack
  (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif` —
  never a Google Font link, which a plain `<img>` embed won't reliably load). Show a
  real branch/decision point as a diamond if the process has one (e.g. three different
  outcomes) rather than flattening it into a single line — that's usually the most
  informative part of the mechanism. Save each diagram under `docs/assets/`. Follow
  the image with one short prose line walking through it in words, for accessibility
  and for anyone who can't see the image. If the project has a second, unrelated
  process worth knowing about (e.g. a dev-tooling/CI side-track), give it its own
  small second diagram rather than folding it into the main one. If a browser tool is
  available, render the SVG once to check for text overflowing its box or elements
  crossing the viewBox edge before embedding it; if none is available, sanity-check by
  parsing it as XML and estimating text width against box width by hand.
- **A short glossary**: every technical term that appears in the project's own docs
  (e.g. RAG, agent, pipeline, decision log, corridor, ISO 20022) translated into one
  plain sentence each. Analogies are encouraged, as long as they're accurate, not just
  catchy.

### 3. Apply the simplicity test to everything you write

- If a sentence needs another sentence to explain it, rewrite it, don't add the second
  sentence.
- If you can't explain a term in one plain sentence, that's a signal to simplify your
  understanding of it first, not to write a longer explanation.
- Prefer concrete, physical comparisons over abstract ones.
- No acronym appears without being spelled out and explained the first time it's used.
- Cut anything that exists to sound impressive rather than to help understanding.

## Output

Write to `docs/PROJECT_IN_A_NUTSHELL.md` (overwrite if it already exists — this should
always reflect the current state of the project, not a historical snapshot), using
this structure:

```markdown
# <Project Name>, in a nutshell

## What is this?
<1-2 plain sentences>

## What problem does it solve?
<1-2 plain sentences, with a concrete everyday example if it helps>

## How it works (simple version)
![<alt text describing the flow in words>](assets/nutshell-flow.svg)
<one short prose line walking through the diagram in words>

(Add a decision diamond if the real process branches into different outcomes. Give
any second, unrelated process its own small diagram — e.g. `assets/nutshell-cicd.svg`
— rather than merging it in.)

## Plain-English glossary
- **<jargon term>** — <one simple, accurate sentence>
- **<jargon term>** — <one simple, accurate sentence>
```

## After creating

- State the file path.
- Read your own output back once and ask: would this make sense to someone with zero
  context on the project? If any sentence fails that test, fix it before reporting
  done.
- Offer to regenerate it for a different audience if the user wants a second version
  (e.g. a recruiter-facing version vs. an "explain like I'm 5" version) — these can
  coexist as separate files (e.g. `docs/PROJECT_IN_A_NUTSHELL_recruiter.md`) rather than
  overwriting the default one.
