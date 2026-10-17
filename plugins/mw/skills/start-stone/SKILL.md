---
name: start-stone
description: Start or replan a stone from scratch in plan mode, get the owner's approval before the first edit, then open the stone and hand it to a fresh coordinating session. Use when the owner says "continue Stone N", "start Stone N" or "replan Stone N", or when a stone's plan changes materially mid-way.
---

# Start a stone

A stone starts with a fresh plan, every time, even when an earlier session planned it (AGENTS.md "Working Units and Sessions"). No edit happens before the owner approves.

## Read, in this order

1. The stone's entry in the active phase plan, which `ROADMAP.md` names (`documents/plans/phase-2-target.md` from phase 1's close, "Stones"): its workstream, what it builds on, what it unblocks, its bullets and its exit test.
2. Its workstream's page in `documents/plans/workstreams.md`: what the workstream owns and guards, and the table of its stones.
3. That workstream's closed stones: open each row's pull request to `main` and read the approved plan in the body and the closing summary in the last comment.
4. `documents/decisions/founding-decisions.md` for every decision the stone touches.
5. The reference game's test files the stone names. They are the starting specification, not the specification: each test is triaged in the plan, as the next section says.
6. Every line in the active phase plan's "Inbound" and every open entry in `documents/known-issues.md` that names the stone or its workstream. The plan answers each one: a named step settles it, or a named later stone takes it, with the reason.

## Write the plan

First run the `prior-art` skill over the stone's hard-to-reverse choices; the questions it drafts and their answers go into the plan the owner approves, cuts or adds to, and into no tracked file until the first step. Then enter plan mode. The plan names: the data layout and the files; the tests, including the reference assertions they carry over; the steps the work splits into, each planned under 400 changed lines (CI fails a step over 500, and the room between is for review fixes, never for planning; a game-side step that builds widgets measured about twice its estimate in Stones 17 and 18); for each step, whether its pull request stacks on the step below while that one is in review, opens against the stone branch, or waits for a named step to merge (`adversarial-review` skill, "In the background, stacked"): a step waits when the step below's output is its input, such as a recorded baseline or a measurement, when it needs a merged result from another chain of steps, or when the step below is attended; what the owner checks, if the stone is owner-checked; the model and effort that build the steps, naming the pattern the `coordinate-stone` skill gives, and which steps touch a costly path and so get their one review round, which steps get none, and the reviewer each gets (`documents/process/model-choice.md`); for a stone that adds a module under `src/`, whether the module joins the review tool's costly paths, for the owner to rule; and a "Pre-rulings" section with one line per call `documents/process/agent-rulings.md` lists, numbered as there from item 0 (whether the stone runs unattended), each keeping the doc's default or giving the stone's own answer. Ask the owner only what the reading left open.

For each reference test file the stone names, the plan carries a triage table with one row per test, marking it carry over, rewrite or drop, with a one-line reason. A test of behaviour an engine system must have is carried over. A test of the GDScript implementation, such as an assertion on a private field or on a signal being emitted, is rewritten as behaviour through the public interface. A test of a game rule or a tuned value is dropped, or kept only as a choice the owner rules for this stone. Below the tables the plan lists the tests the engine needs that the reference lacks; the reference tests never check determinism, allocation in the tick or the tick budget. The owner approves the tables with the plan (ruled 2026-10-09).

## After approval

1. Cut the branch `stone/<n>-<slug>` (or `stone/<slug>` for a stone outside the phase numbering) from `main` in a worktree of its own, outside the repository: `git fetch origin`, then `git worktree add c:/projects/millwright-worktrees/<slug> -b <branch> origin/main`, and work only in that folder from here on (AGENTS.md "Working Units and Sessions"). `claude --worktree` is the wrong tool here: it puts the worktree under `.claude/worktrees/` on a branch named `worktree-<name>` (Claude Code's worktree page, https://code.claude.com/docs/en/worktrees, read 2026-10-09). In the new folder, add one empty commit (`git commit --allow-empty -m "chore: open Stone N"`) so the branch differs from `main`, and push it. GitHub refuses a pull request whose head and base are identical.
2. Open the pull request from it to `main` as a draft (`gh pr create --draft`), with the approved plan as the body, the same day the owner approves it. It stays open, and a draft, for the stone's life: CI builds nothing on a draft, because the steps are built and tested one by one (Stone 0, step 4c). The `close-stone` skill marks it ready.
3. Hand over. The planning session starts no step: it ends its turn with one line telling the owner to run /clear and then /mw:coordinate-stone, and the fresh session that skill starts builds the stone from its pull request (ruled by the owner on 2026-10-13, at Stone 11's close).

4. Before a step that edits a hook, a workflow or a preset, which the guard hook denies, ask the owner to lift it: `"mwAllowGuardEdit": true` in `.claude/settings.local.json`, in the stone's worktree or the main checkout, or the session started with `MW_ALLOW_GUARD_EDIT=1`. A step that lands or changes a hook needs it first, because hooks load the moment `.claude/settings.json` changes. The owner deletes the file when the stone merges (`close-stone` skill).

## Building the steps

The `coordinate-stone` skill builds the steps, one fresh subagent per step, and holds the briefs, the rulings, the merges and the replan rule.
