---
name: prior-art
description: Research how shipped engines answer a hard-to-reverse design choice before the choice is made. Use when start-stone is about to write a plan, when a step meets a design choice the plan did not foresee (stop and research that one question before writing code, then take the answer to the owner), or when a phase plan is being written (one or two questions per drafted stone).
---

# Prior art

A stone's plan names its data layouts, file formats and interfaces. Each of those is expensive to reverse, and some catalog project has already paid for an answer. This skill turns such a choice into one question, answers it from at most three sources, and records the answer where the owner approves it with the plan. The agent drafts the questions; the owner approves, cuts or adds to them.

The catalog of repositories is `documents/process/prior-art.md`. The clones live under `c:/projects/engine-refs/`, outside this repository. They are read-only and are never built or run.

## The filter

A design choice becomes a question only when all three hold:

1. It is expensive to reverse: a data layout, a file format, a public interface, a memory-ownership rule. A function's internals are not.
2. No founding decision in `documents/decisions/founding-decisions.md` and no test in the reference game already answers it.
3. Some catalog project has shipped an answer under similar constraints.

A choice that fails any of the three is made in the plan without research.

## The template

Every question takes this form: "How does X handle Y, given our constraint Z, and what did it cost them?" X is a catalog project, Y is the choice, Z is the constraint from this engine (the 60 Hz tick, determinism, no allocation in the tick, the four targets, the web build).

## The limits

- At most three sources per question, named from the catalog.
- Read down to the data layout and the one function that does the work, then stop.
- Copy no code. The rule is the reference game's: take the pattern and the test, leave the code. The catalog marks two projects whose licences forbid close paraphrase as well.
- Time: a question is one subagent run. A question that needs more than that is too wide; split it or drop it.

## The output

One section per question. At a stone start the sections go into the plan text the owner approves, and no tracked file changes before approval; the stone's first step then copies them into the stone's findings doc under `documents/findings/`, dated in the file name, and lists that doc in `documents/README.md`. The doc opens with the frozen-record line every findings doc carries, with the file name's date (`documents/README.md`, "documents/findings/"), then its title. A question raised mid-step lands its section in that step; the author posts the question and its answer on the stone's pull request and stops for the owner's ruling (`documents/process/agent-rulings.md`, "Unforeseen calls"). Each section states the question, the answer in plain words, what it cost the source project, and the citation: the repository, the version or commit as the catalog lists it, and the file path inside the clone; for a recovered game from the catalog's second table, the game's version, the recovery's date and the file path under `recovered`. A later reader checks the claim against that commit or recovery.

When a phase plan is being written, the sections land in the findings doc of the step that writes the plan, and the plan cites them. In every case the plan says which choice each answer settles.

## The subagent prompt

Research runs in a subagent so the main session keeps its context. The call names the subagent's model, Opus, because a subagent inherits its parent's model and a Fable planning session would otherwise run the research on Fable (ruled by the owner on 2026-10-13; `documents/process/model-choice.md`). The prompt carries the question, the catalog rows for its sources, the three rules CLAUDE.md names for every delegation, and a fourth that this skill adds, because the subagent sees neither CLAUDE.md nor AGENTS.md:

1. The reference game at `c:/projects/iteration-zero` is read-only.
2. Untracked scratch files at the repository root are the owner's notebook, not a source.
3. Any `.md` the agent writes follows AGENTS.md "Doc Prose".
4. The clones under `c:/projects/engine-refs/` and the recovered games under `C:/Projects/_reference/` are read-only and are never built or run.

The subagent returns the section text. The main session checks every file path it cites against the clone before the section lands.
