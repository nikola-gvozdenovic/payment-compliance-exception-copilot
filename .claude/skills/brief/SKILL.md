---
name: brief
description: Explains one specific task or ticket in plain, jargon-free language before it's implemented — what it does, why it exists, and how it affects the whole project — with simple visual diagrams and real screenshots where something runnable already exists. Use before starting implementation on a ticket, so everyone understands the task's goal and its place in the bigger picture before code gets written.
argument-hint: [task description, ticket id, or path to a ticket/spec]
---

# Brief: Explain a Task Simply, In Context

## Objective

Before implementing something, produce one short, plain-language briefing on: what
this specific task is, why it exists, and how it fits into — and changes — the whole
project. This is not a technical implementation plan (that's `/plan-feature`'s job).
It's a "what and why, and what it touches" explainer that anyone could read and
understand, paired with simple diagrams of the task's own workflow and of where it
sits inside the bigger system.

This is scoped to **one task**, unlike `/nutshell`, which explains the whole project.
Assume the reader has already seen (or can see) `/nutshell`'s output — don't
re-explain the whole project's glossary from scratch. Only cover terms specific to
this task that weren't already covered there.

## Input

`$ARGUMENTS` is the task to explain, in any of these forms:

- A ticket ID that appears in `docs/specs/*.md` (e.g. `TICKET-3`) — look it up there
  for its scope, acceptance criteria, and dependencies.
- A path to a plan file (e.g. one under `.claude/plans/`).
- Free text describing the task directly.

If nothing is given, ask which task or ticket to explain before doing anything else.

## Process

### 1. Find the task, and find the whole picture it sits inside

- Load the task's own definition: the ticket's scope/acceptance criteria/dependencies
  from the spec, or the plan file, or the free text given.
- Load whatever already explains the whole project's big picture — the PRD, the
  spec's dependency graph, `docs/PROJECT_IN_A_NUTSHELL.md` if it exists, and any
  already-published architecture diagram. Use these as the source of truth for "the
  whole project" rather than reconstructing it from scratch.
- Work out: what does this task actually add or change? What existed before it? What
  other tasks does it feed into, or does it depend on (per the spec's dependency
  graph)? Which single piece of the whole-project picture does this task correspond
  to?

### 2. Reduce it to the simplest true version

- **One sentence**: what is this task, in plain words?
- **One sentence**: why does it exist — what's missing or broken without it?
- **One sentence**: what changes about the whole project once it's done?
- A short glossary, but **only** for terms specific to this task that `/nutshell`'s
  glossary doesn't already cover — don't repeat those entries.

### 3. Draw two diagrams

Same rules as `/nutshell`: hand-authored standalone SVG, not mermaid — real boxes and
arrows with arrowhead `<marker>`s, literal hex colors (no CSS variables — a standalone
SVG has no page to inherit a theme from), a plain system font stack
(`-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif`), a
small background card so it reads cleanly anywhere it's viewed. Save both under
`docs/assets/`, named `<task-slug>-flow.svg` and `<task-slug>-context.svg`.

1. **This task's own workflow** — the steps this task itself performs or produces, in
   plain words. For a data ticket: raw input → validated shape → stored result. For
   an agent/reasoning ticket: something comes in → it looks something up → it
   produces a decision or output. Four to six boxes max, a decision diamond only if
   the task itself actually branches.
2. **Where it sits in the whole project** — reuse the shape of the project's own
   big-picture diagram (mirror `/nutshell`'s main flow, or an existing architecture
   diagram) and highlight the **one piece** this task builds or changes with a
   distinct accent color/outline, keeping every other piece neutral/grey. The point is
   a reader sees, at a glance, "this one box, right here, is what's being built, and
   here's what it's connected to" — not a repeat of the whole diagram at equal weight.

If a browser tool is available, render each SVG once to check for overflowing text or
misplaced elements before embedding; otherwise sanity-check by parsing as XML and
estimating text width against box width by hand.

### 4. Screenshots, only when something real exists to screenshot

If the task touches something with an actual running UI, API, or observable CLI
output — not the case for an early foundational ticket in a project that's still
backend/data-only — use the `agent-browser` skill (or a direct CLI run) to capture
1-3 real before/after screenshots of the actual behavior, and embed those alongside
the diagrams with one-line captions.

If nothing runnable or visible exists yet, **do not fabricate a screenshot or a mockup
of one** — say plainly, in the output itself, that nothing runnable exists for this
task yet, and that the two diagrams above are the workflow view for now.

### 5. Apply the simplicity test

Same bar as `/nutshell`: rewrite a sentence that needs a second sentence to explain
it, rather than adding the second sentence; no unexplained acronym; concrete
comparisons over abstract ones; cut anything that exists to sound impressive rather
than to help understanding.

## Output

Write to `docs/tasks/<task-slug>.md` (create `docs/tasks/` if it doesn't exist yet),
structured as:

```markdown
# <Task name>, in plain words

## What is this task?
<1-2 plain sentences>

## Why does it exist?
<1-2 plain sentences>

## What changes because of it?
<1-2 plain sentences on its effect on the whole project>

## This task's own workflow
![<alt text in words>](../assets/<task-slug>-flow.svg)
<one prose line walking through it>

## Where it fits in the whole project
![<alt text in words>](../assets/<task-slug>-context.svg)
<one prose line naming which piece is highlighted and why it matters>

## Screenshots
<either real before/after images with one-line captions, or a plain sentence saying
nothing runnable exists yet for this task>

## New terms this task introduces
- **<term>** — <one simple, accurate sentence>
- (omit this section entirely if there are none beyond what `/nutshell` covers)
```

## After creating

- State the file path, and the path of any new SVGs (and screenshots, if any).
- Read the output back once against the simplicity test; fix anything that fails it
  before reporting done.
- Say explicitly whether real screenshots were included or skipped, and why — never
  leave that ambiguous.
