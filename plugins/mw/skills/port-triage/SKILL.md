---
name: port-triage
description: Re-examine one reference-game subsystem part by part before any of it is rebuilt on the engine, and write the record the service stone builds to. Use as step 1 of a stone that rebuilds a reference subsystem, as the whole of a triage docs stone, or when asked to "triage the port of X".
---

# Port triage

The port of Iteration Zero is the plan, subsystem by subsystem, and never a blind copy: the owner ruled it on 2026-10-11 with the phase-1-plan stone's plan (pull request 147), and `documents/decisions/founding-decisions.md` records it under "Ruled 2026-10-11", with a dated note on its "Not doing, and why" entry. A subsystem is rebuilt only after a record says, part by part, why the reference did it that way, whether a Godot constraint forced it, what the engine does instead, and which of its tests carry over. The record is where the polish, the bug catching and the refactoring happen, and it is the reason a reviewer six months on does not ask why the engine differs from the reference. The main session on Fable writes it (`documents/process/model-choice.md`: a judgment call nothing checks afterwards); a subagent may sweep files and list line ranges, and the four rules below go into its prompt.

The reference game at `c:/projects/iteration-zero` is read-only. Untracked scratch files at a repository root are the owner's notebook, not a source. Any `.md` written follows AGENTS.md "Doc Prose". The clones under `c:/projects/engine-refs/` are read-only and are never built or run.

## When it runs

- As step 1 of a service stone that rebuilds a reference subsystem (the phase plan names which), before the stone's second step; the owner approves the record before any code.
- As the whole of a triage docs stone, when the record decides how later stones split (the UI in phase 1).
- Never mid-step: a part the record missed is a dated comment on the stone's pull request and a new row, and a part that changes the stone's scope is a replan (`start-stone` skill).

## Read, in this order

1. The subsystem's scripts in the reference game, named by the phase plan's stone entry, and its decision doc under `documents/decisions/` there when one exists.
2. Its test files under the reference's unit-test folder, every `func test_` counted.
3. The engine's founding decisions and the prior-art findings the stone entry cites, so the engine's answer is the one already ruled where a ruling exists.
4. The reference game's `documents/findings/tech-review/` entries that touch the subsystem, which say what the reference's own review found wrong with it.

## The record

One findings doc under `documents/findings/`, dated in the file name, listed in `documents/README.md`. Its line 1 is the frozen-record line, "Frozen record of <date>: it describes the repository at that date; a later fact is a dated note at the end, never an edit above it.", with the file name's date, and the invariant test fails any other. Then the title, then what the subsystem does in the reference in one paragraph and its size (scripts, lines, tests). Then one table, one row per part. A part is a thing the subsystem does that a test or a decision names: the atomic write, the migration ladder, the focus restore, the pitch variance on a one-shot.

| Part | What the reference does | Why: constraint or choice | The engine's answer | Evidence of use | Tests |
|---|---|---|---|---|---|

- **What the reference does.** One or two sentences, with the script and the line range.
- **Why.** One of three, named: a Godot constraint (a Resource class, a signal, the scene tree, the autoload order, `ConfigFile`), a design choice the reference's decision doc records, or a choice with no recorded reason. A rule the reference's review later called a mistake is marked so, with the tech-review file.
- **The engine's answer.** What the engine does instead, in one or two sentences, citing the founding decision or the findings section that rules it; "the same" is an answer when the reason survives; "dropped" is an answer when the part served a Godot constraint only. A part that needs a choice no ruling covers is marked for the `prior-art` skill and the stone's plan carries the question.
- **Evidence of use.** What shows that a player or the owner relies on the part: a screen or a flow that reaches it, a report, a release note, the owner's own play. A part with none gets "None:" and what was looked at, such as "None: no screen reaches it, and no report names it". The column keeps a part nobody uses from being rebuilt only because the reference has it, and a "None" row is a candidate to drop or to defer. The owner ruled the column on 2026-10-13, at Stone 11's close, for every record from Stone 12's on.
- **Tests.** The reference test functions the part has, each marked carry over, rewrite or drop with a one-line reason, in the `start-stone` skill's three senses: behaviour an engine system must have carries over; a test of the GDScript implementation is rewritten as behaviour through the public interface; a test of a game rule or a tuned value is dropped, or kept as a choice the owner rules. The stone's plan carries the `start-stone` triage table, one row per reference test, and the owner approves it with the plan (ruled 2026-10-09); this column extends that table and never replaces it: it lists each test by name with the verdict the plan gave, grouped under the part the test exercises. A verdict the record would change is a dated comment on the stone's pull request for the owner, never an edit to the record alone. A reviewer measures a step's tests against the plan's table and its code against the record's part rows. For a triage docs stone, the column is the table the next stones' plans copy into their own `start-stone` tables.

Below the table: the tests the engine needs that the reference lacks (determinism, no allocation in the tick, the reset contract, the tick budget where the part runs inside the tick), and what the record leaves to a later stone or to phase 2, each with a reason.

## What the stone does with it

- When the record is step 1 of a service stone, the stone's plan names the subsystem, the parts it expects and the data layout it proposes, and the owner approves the record before step 2; from step 2 on each step names the rows it implements, and a row the record adds that changes the stone's scope, exit test, data layout or interface is a replan (`start-stone` skill). When the record is a triage docs stone of its own, the next stones' plans build to it.
- A step that touches a ported part cites the part's row in its pull request body, so the reviewer measures the code against the record and not against the reference. Check 8 of the review tool's prompt (`${CLAUDE_PLUGIN_ROOT}/tools/review_pr.py`) measures such code against the row, and reports a rebuilt part with no row under Unresearched choices; the author settles that bullet as a part the record missed, by "When it runs" above, and not by pre-ruling 8, which covers the prompt's item 7.
- The closing summary of a game stone that rebuilds a subsystem records the port's cost (steps, lines, minutes from the stone's opening to its merge), which the full port's go or no-go reads.
- A row whose engine answer turned out wrong during the build is corrected in the record in the same step, with a dated note, never silently.
