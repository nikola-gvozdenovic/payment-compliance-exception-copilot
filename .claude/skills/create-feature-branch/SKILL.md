---
name: create-feature-branch
description: Creates a new feature branch off main (or the repo's detected default branch), ready for a ticket's implementation. Use at the start of a ticket, before any code is written, so work happens on its own branch instead of directly on main.
argument-hint: "[ticket-id-or-description] [--base <branch>] (default base: auto-detected)"
---

# Create Feature Branch: Start a Ticket on Its Own Branch

This is the **setup** step before implementation: get off `main` and onto a dedicated branch so the ticket's
work stays isolated and reviewable.

## Phase 0 — Detect the base branch

Don't hardcode `main`. Resolve it:
1. If `$ARGUMENTS` contains `--base <branch>`, use that.
2. Else: `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'`
3. Fallback: `git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{print $NF}'`
4. Last resort: `main`. Store as `{base}`.

## Phase 1 — Validate git state

```bash
git status --short
git branch --show-current
```

| State | Action |
|-------|--------|
| Uncommitted changes | STOP: "Commit or stash before switching branches." |
| Already on a non-`{base}` feature branch with no upstream tracking issue | Ask whether to branch from here or from `{base}` — default to `{base}`. |
| Clean, on `{base}` or willing to branch from `{base}` | PROCEED |

## Phase 2 — Sync the base branch

```bash
git fetch origin {base}
git checkout {base}
git pull origin {base}
```

Skip the pull if there's no remote tracking (`STOP` messages aside, don't fail the whole skill over a missing
remote — just branch from local `{base}` and note it in the output).

## Phase 3 — Derive the branch name

Use `$ARGUMENTS` (a ticket id like `ACC-123` and/or a short description) to build a
`<type>/<ticket-id>-<kebab-description>` name, e.g. `feat/acc-123-payment-retry-limit`.

- `{type}` = `feat` / `fix` / `chore` / `refactor` / … inferred from the ticket or description; default `feat`.
- If no ticket id is given, omit it: `feat/kebab-description`.
- If nothing is given at all, ask the user for a one-line description of the work before naming the branch.

## Phase 4 — Create and switch

```bash
git checkout -b "{branch-name}" {base}
```

If a branch with that name already exists locally, STOP and ask whether to check it out instead of creating a
duplicate.

## Output

```bash
git branch --show-current
```

Report the new branch name, the base it was cut from, and **"Ready for implementation."** Do not push or open a
PR here — that's `piv-create-pr`'s job once the work is committed.

## Notes

- One branch per ticket keeps `piv-create-pr` and worktree-based parallel work (`new-worktrees`) clean.
- This skill never commits or pushes — it only positions the working tree on a fresh branch.
