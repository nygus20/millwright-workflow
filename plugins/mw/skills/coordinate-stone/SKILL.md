---
name: coordinate-stone
description: Coordinate an open stone's steps in a fresh session, one subagent per step, after the mw:start-stone skill opened the stone; resume a stopped or oversized coordinator from the stone's pull request alone. Use when the owner runs /mw:coordinate-stone, with or without a stone number, after /clear, or says "coordinate Stone N" or "resume Stone N".
argument-hint: "[stone number or slug]"
---

# Coordinate a stone

The planning session ends when the stone opens (`mw:start-stone` skill, "After approval"), and a fresh session runs this skill to build the stone. The planning's reading then stays out of the build: Stone 11's coordinator held 385K tokens of context at approval and 686K at its end, and re-read a median of 506K per turn (ruled by the owner on 2026-10-13, at Stone 11's close). The stone's pull request to `main` holds everything the coordinator needs. Its body holds the approved plan, and its comments hold the rulings and the step briefs. The owner looks nothing up and writes nothing for the hand-over.

## The first line

The session's first line names the model it runs on, as its system prompt states it. When that model is not Opus, the line warns the owner and says how to switch: run /model claude-opus-5-5, then /mw:coordinate-stone again. The skill cannot pin the session's model: Claude Code's skills page (https://code.claude.com/docs/en/skills, read 2026-10-13) says a skill's `model` field holds only for the rest of the turn that invokes the skill, and the session's model resumes at the next prompt. This skill therefore sets no `model` field, because a pin for one turn would make the first line name Opus while every later turn ran on the session's model; the first line's warning is the guard.

## Find the stone

1. List the open stones: `gh pr list --base main --state open --json number,title,headRefName,isDraft`, keeping each pull request whose head branch starts with `stone/`. Keep drafts and ready ones alike, because the `mw:close-stone` skill marks a stone's pull request ready before its review and fix rounds.
2. Pick one. With a stone number or a slug given (`$ARGUMENTS`), take the pull request whose branch is `stone/<n>-<slug>` or `stone/<slug>`, so a stone outside the phase numbering is found by its slug. With nothing given and one stone open, take it. With several open, as parallel stones allow, and nothing given, list each one's number, title and branch, ask the owner which, and stop.
3. With no stone open, open it first. Take the newest file under `$HOME/.claude/plans/` whose first line names a stone, such as "# Plan: Stone 12, save with migration, profiles and settings"; that folder also holds plans of other kinds. When no file names a stone, or the newest names another stone than the number given, ask the owner which plan and stop. Then run items 1 and 2 of the `mw:start-stone` skill's "After approval" with that file as the body. A plan over GitHub's body limit of 65,536 characters keeps its prose in the body and moves its tables to a first comment that opens with `<!-- mw-plan-tables -->`, as Stone 12's pull request 306 did.

## Read the stone

- **The body** is the approved plan: its steps, its pre-rulings, and the checklist "Step pull requests" at its end, where a ticked box marks a merged step.
- **The comments** come from `gh pr view <stone-pr> --json comments`, and each record opens with a marker (`documents/process/agent-rulings.md`, "The records"). A comment opening with `<!-- mw-plan-tables -->` is part of the approved plan. One opening with `<!-- mw-agent-ruling -->` is a ruling, and one opening with `<!-- mw-step-brief: N -->` is the brief of merged step N. One opening with `<!-- mw-owner-ruling -->` is a ruling the owner gave in a session and the agent relayed; it binds as the owner's own comment does, and a later reply from the owner corrects it. A comment without a marker is the owner's, and it binds as a ruling.
- **Nothing else from the planning.** The coordinator reads AGENTS.md, CLAUDE.md and the stone's pull request. It does not reread the closed stones, the reference game or the findings the plan cites, because the plan carries what they said; each step's subagent reads the files its own step needs.

## Find the worktree

Run `git worktree list` from the main checkout and take the line on the stone's branch. When none exists, recreate it: `git fetch origin`, then `git worktree add <worktrees>/<slug> <branch>`, which checks out the remote branch. `<worktrees>` is the folder the session's start line names, which the `worktrees` key of the repository's `.claude/mw.json` holds; the plugin names no repository's folder. Work only in that folder from here on, never in the main checkout (AGENTS.md "Working Units and Sessions"). The same list shows each step worktree a stopped coordinator left: one whose step merged is removed, and one whose pull request is open stays for that step.

## Where the stone stands

A session that starts after /clear, or after the context rule below ended its predecessor, rebuilds the state from the pull requests alone:

- the checklist in the body and the briefs in the comments name the merged steps;
- `gh pr list --state open --json number,title,headRefName,baseRefName` lists the open step pull requests, whose branches start with `step/<stone-slug>/`;
- `gh pr list --state merged` with the same fields finds a step that merged after its predecessor's last brief; that step gets its brief and its ticked box now;
- a step branch on the remote with no pull request is a subagent's unfinished work, which a fresh subagent continues from the branch.

An open step pull request continues where its comments leave it: no review round yet, a round with findings to rule on, or a ruling posted and the merge waiting on CI. The next steps to start are the unticked ones the plan lets start now.

## Building the steps

From Stone 11 on, one coordinating session holds the plan, runs the review tool and merges, and it starts one fresh subagent per step, on Opus at high, which builds the step and opens its pull request (ruled by the owner on 2026-10-13). From 0.1.12 on, that subagent is the plugin's step builder, the agent `mw:step-builder`, whose definition fixes its model and effort and holds the standing brief every step obeys. The reason is measured: building sessions that drove a whole stone themselves re-read 460K to 620K tokens of context per turn, 966K at the peak, and those cache reads made 77 to 87 percent of their cost. A fresh subagent starts empty and reads only its own step. From Stone 12 on, the coordinator is itself a fresh session, started by this skill.

The coordinator starts the step builder once per step, through the Agent tool with `subagent_type` set to `mw:step-builder`, and passes no `model` and no `effort`. A value in the call overrides the definition's (Claude Code's sub-agents page, https://code.claude.com/docs/en/sub-agents, read 2026-11-07), and the call's `model` takes only an alias. The brief carries only what varies:
- the step's part of the plan, with the rows of the record or the tables it implements and the rulings it touches;
- its branch `step/<stone-slug>/<n>-<slug>`, the branch it is cut from, and the base its pull request opens against;
- its worktree line, `git worktree add <worktrees>/<stone-slug>-<n> -b <branch> origin/<from>`, with `<worktrees>` written out as the session's start line names it;
- the quick check's command, when it differs from `quick_check.bat`;
- for a step that changes a file CI does not build, such as a Windows-only source, the unfiltered suite run (`run-tests` skill) and the lint before its push, because CI builds no Windows target;
- each gotcha an earlier step learned, until the tracked doc that owns its rule holds it.

The definition holds the rest, so the brief does not repeat it: the rule files of the checkout the step edits, the worktree rule, the three rules CLAUDE.md names for every delegation, the comment that cites a call and no plan file, the tested refusal, the scratchpad name, the quick check, CI's run as the step's one full gate with one background wait for it, the pull request against its base with a body that holds no count, and the report of about 200 words.

The coordinator keeps no report beyond the next decision; the pull request body and the brief keep the record. The stone's first step adds the stone's entry to the phase plan when the stone has none, and reads every open issue with the `from-game` label into the phase plan's "Inbound" as a dated line that links the issue, skipping an issue a line already links. It writes no workstream row and no registry entry, because no record marks a stone open: the open draft pull request into `main` is the sign, and the close writes the row and the registry entry once (`mw:close-stone` skill, item 5). The shared records thus change inside a reviewed step (AGENTS.md "Working Units and Sessions"). Before a step that edits a hook, a workflow or a preset, the owner lifts the guard hook as item 4 of the `mw:start-stone` skill's "After approval" says.

**A subagent names its model.** A subagent inherits its parent's model, so one started from a Fable session runs on Fable unless the call or its definition names another. The step builder's definition fixes its model and effort, so its call names neither. Every other subagent this skill starts names its model in the call: Opus for research, Haiku for a file search.

**Steps run side by side.** Steps the plan marks independent start at once, each subagent in the background in its own worktree. The limit on open step pull requests and the rules for a stacked step are the `mw:adversarial-review` skill's, "In the background, stacked".

**After a subagent reports**, the coordinator:
1. runs the review tool on the step's pull request with the flags the plan names, in the background, and acts on its exit code (`mw:adversarial-review` skill); a fix the round calls for goes back to the step's own builder through SendMessage, the Agent tool's continue-by-message, because that builder still holds the step's context and a fresh one would read the step again;
2. writes the step's brief (`documents/process/agent-rulings.md`, "The records") to a file in the scratchpad, with an `Ambiguities` line of one sentence per ambiguity, or "none", and no count and no version constant, then merges with `python "${CLAUDE_PLUGIN_ROOT}/tools/merge_step.py" <pr> --brief <file>` in the background, as that skill's exit 0 says; the tool retargets a stacked step first, stops on a conflict with the stone branch before any wait, and merges at once when the stone branch changes nothing and the head is already green; it stops with exit 2 before any merge when the brief's `Ambiguities` item runs over 600 bytes, and the coordinator then shortens the line to one sentence per ambiguity; the brief's Merged line starts `- Merged: pull request <N>` in plain text, because the tool refuses a linked number; a step in another repository whose pull request opens against that repository's `main` has no stone base for the tool: a marketplace step, or a consumer stone's step in the engine's repository under the exceptions the `mw:start-stone` skill states in "Each repository builds its own code", which always gets its one round; the coordinator merges it with `gh pr merge <pr> --merge` once its checks are green and its round has passed, then posts the brief on the stone's pull request by hand;
3. reads the tool's exit code: on 0 the brief is on the stone's pull request, and the coordinator gives the owner the same text; it runs items 4 and 5 only once the exit code reads 0 or `gh pr view <pr> --json state` reads `MERGED`, never chained behind the merge in one command, because a conflict stop on the gate-cost stone's step 10 left a ticked box and a removed worktree;
4. ticks the step's box in the body: `gh pr view <stone-pr> --json body --jq .body` into a file in the scratchpad, the tick made with the file tools, then `gh pr edit <stone-pr> --body-file <file>`;
5. removes the step's worktree from the main checkout, `git worktree remove <worktrees>/<stone-slug>-<n>`, after retargeting every step stacked on it; the branch stays until the stone's close (`mw:adversarial-review` skill);
6. carries a gotcha the step learned into the next brief, or into the tracked doc that owns its rule.

**The full Windows run.** CI builds Linux and the web only, so the coordinator runs the unfiltered suite (`run-tests` skill) on the stone branch after every fifth merged step, in the background, and the close runs it once more (`mw:close-stone` skill, item 1). The count is mechanical: at each merge the coordinator counts the step pull requests merged into the stone branch in the stone's own repository, `gh pr list --base stone/<slug> --state merged --limit 200 --json number --jq length`, and starts the run when the count is a multiple of five. It runs in the stone's worktree after `git pull`, and the next brief records its result with the commit it ran on. A red run is a defect on the stone branch, and a fix step repairs it, added to the checklist as a split step is.

## The context rule

After each merge the coordinator reads its own cache read: the `usage.cache_read_input_tokens` of the newest assistant entry in the session's transcript, the newest `.jsonl` under `$HOME/.claude/projects/<project-folder>/`. When it passes 400K tokens, the coordinator starts no new subagent, lets every running one report, finishes each merge in hand up to its brief and its ticked box, and ends the session (ruled with Stone 12's plan on 2026-10-13). Its last line tells the owner to run /clear and then /mw:coordinate-stone <n>, and the fresh session resumes from the pull request as "Where the stone stands" says.

## Rulings and replans

The owner's approval of the plan is the ruling on each of its pre-rulings. From the first step on, the coordinator decides the calls they cover and any call it can reverse inside the stone, and stops for the rest (`documents/process/agent-rulings.md`). Pre-ruling 0 names the steps where the stone waits for the owner anyway.

A plan that changes materially mid-way, as pre-ruling 5 of that doc defines the word, is replanned through the `mw:start-stone` skill. A smaller change, such as a split step, gets a dated comment on the stone's pull request and a new row in its checklist, never a silent change.

## Do not

- Do not build a step in the coordinating session. A step's code and docs come from its subagent, which starts empty.
- Do not paste a step's diff or a subagent's full transcript into the coordinator; read the pull request's changed lines and its CI result.
- Do not resume from a summary the owner did not write. The stone's pull request and its step pull requests are the state.
