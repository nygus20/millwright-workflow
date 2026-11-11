---
name: port-triage
description: Re-examine one reference-game subsystem part by part before any of it is rebuilt on the engine, and write the record the service stone builds to. Use as step 1 of a stone that rebuilds a reference subsystem, as the whole of a triage docs stone, or when asked to "triage the port of X".
---

# Port triage

The port of Iteration Zero is the plan, subsystem by subsystem, and never a blind copy: the owner ruled it on 2026-10-11 with the phase-1-plan stone's plan (pull request 147), and `documents/decisions/founding-decisions.md` records it under "Ruled 2026-10-11", with a dated note on its "Not doing, and why" entry. A subsystem is rebuilt only after a record says, part by part, what the reference does, what the engine does instead, whether a Godot constraint forced the reference's way, and which tests the part has. The record is where the polish, the bug catching and the refactoring happen, and it is the reason a reviewer six months on does not ask why the engine differs from the reference. The main session on Fable writes it (`documents/process/model-choice.md`: a judgment call nothing checks afterwards); a subagent may sweep files and list line ranges, and the four rules below go into its prompt.

The reference game at `c:/projects/iteration-zero` is read-only. Untracked scratch files at a repository root are the owner's notebook, not a source. Any `.md` written follows AGENTS.md "Doc Prose". The clones under `c:/projects/engine-refs/` are read-only and are never built or run.

## When it runs

- As step 1 of a service stone that rebuilds a reference subsystem (the phase plan names which), before the stone's second step; the owner approves the record before any code.
- As the whole of a triage docs stone, when the record decides how later stones split (the UI in phase 1).
- Never mid-step: a part the record missed is a dated comment on the stone's pull request and a new row, and a part that changes the stone's scope is a replan (`mw:start-stone` skill).

## Read, in this order

1. The subsystem's scripts in the reference game, named by the phase plan's stone entry, and its decision doc under `documents/decisions/` there when one exists.
2. Its test files under the reference's unit-test folder, every `func test_` counted.
3. The engine's founding decisions and the prior-art findings the stone entry cites, so the engine's answer is the one already ruled where a ruling exists.
4. The reference game's `documents/findings/tech-review/` entries that touch the subsystem, which say what the reference's own review found wrong with it.

## The record

One findings doc under `documents/findings/`, named `<stone>-<subsystem>-triage-<date>.md`, listed in `documents/README.md`. Its line 1 is the port-triage line, "Port-triage record of <date>: a row is corrected in place, and the correction carries its date in the row.", with the file name's date. The invariant test's `findings-frozen` rule accepts that line only for a file named `*-triage-<date>.md`, and such a file may carry either it or the frozen-record line every other findings doc carries, so the records written on the frozen-record line stay as they are. Then the title, then what the subsystem does in the reference in one paragraph and its size (scripts, lines, tests). At most one line then names the record's own file aliases, such as "Line ranges without a file name are in `content_registry.gd`." Then one table, one row per part. A part is a thing the subsystem does that a test or a decision names: the atomic write, the migration ladder, the focus restore, the pitch variance on a one-shot.

| Part | What the reference does | The engine's answer | Exception | Tests |
|---|---|---|---|---|

- **What the reference does.** One or two sentences, with the script and the line range.
- **The engine's answer.** What the engine does instead, in one or two sentences, citing the founding decision, the findings section or the call that rules it, a call as `pull request <n>, call <m>`; "the same" is an answer when the reason survives; "dropped" is an answer when the part served a Godot constraint only. A part that needs a choice no ruling covers is marked for the `mw:prior-art` skill and the stone's plan carries the question. The column keeps this name, because check 8 of the review tool's prompt reads it.
- **Exception.** Written only in three cases, and left empty otherwise: a Godot constraint, named (a Resource class, a signal, the scene tree, the autoload order, `ConfigFile`); a rule the reference's review called a mistake, with the tech-review file; or a part with no evidence of use, as "None:" and what was looked at, such as "None: no screen reaches it, and no report names it". A "None" row is a candidate to drop or to defer. The column narrows the owner's ruling of 2026-10-13 that gave evidence of use a column of its own, because most such cells held a stock answer (the engine's pull request 970, call 13).
- **Tests.** The reference test functions the part has, listed by name without verdicts. The stone's plan carries the `mw:start-stone` triage table, one row per reference test with its verdict, and the owner approves it with the plan (ruled 2026-10-09). A verdict the record would change is a dated comment on the stone's pull request for the owner. A reviewer measures a step's tests against the plan's table and its code against the record's part rows. For a triage docs stone, the next stones' plans copy the column into their own `mw:start-stone` tables and give each test its verdict there.

Below the table: the tests the engine needs that the reference lacks (determinism, no allocation in the tick, the reset contract, the tick budget where the part runs inside the tick), and what the record leaves to a later stone or to phase 2, each with a reason.

## What the stone does with it

- When the record is step 1 of a service stone, the stone's plan names the subsystem, the parts it expects and the data layout it proposes, and the owner approves the record before step 2; from step 2 on each step names the rows it implements, and a row the record adds that changes the stone's scope, exit test, data layout or interface is a replan (`mw:start-stone` skill). When the record is a triage docs stone of its own, the next stones' plans build to it.
- A step that touches a ported part cites the part's row in its pull request body, so the reviewer measures the code against the record and not against the reference. Check 8 of the review tool's prompt (`${CLAUDE_PLUGIN_ROOT}/tools/review_pr.py`) measures such code against the row, and reports a rebuilt part with no row under Unresearched choices; the author settles that bullet as a part the record missed, by "When it runs" above, and not by pre-ruling 8, which covers the prompt's item 7.
- The closing summary of a game stone that rebuilds a subsystem records the port's cost (steps, lines, minutes from the stone's opening to its merge), which the full port's go or no-go reads.
- A row whose engine answer turned out wrong during the build is corrected in place, in the same step: the cell changes, and the correction carries its date in the row. A record that opens with the frozen-record line keeps its dated notes at the end.

## Reading a record

This guide stands once, here, and a record repeats none of it.

- Each row is one part, and the columns read as "The record" above defines them.
- An empty Exception cell means the part has no Godot constraint, no mistake the reference's review named, and evidence of use.
- A call cited as `pull request <n>, call <m>` is call m of the approved plan in that pull request's body.
- The Tests column names each reference test the part has, and the stone's plan holds each test's verdict.
- A line range without a file name is in the file the record's alias line names.
- A date in a row marks a correction, which replaced the row's earlier text; git history keeps that text.
