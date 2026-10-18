"""Adversarial review of a pull request by a fresh Claude Code session.

Usage:
    python "${CLAUDE_PLUGIN_ROOT}/tools/review_pr.py" <pr-number> [--stone N] [--context FILE]... [--post]
                                                      [--full] [--extra-round [agent|owner]] [--force-review]
                                                      [--model NAME] [--effort LEVEL] [--max-turns N]

What it does. It fetches the pull request's title and body with `gh` and its
diff with git, from the merge base (GitHub refuses a pull-request diff over 300
files; upstream files under third_party/<library>/ arrive as names and counts),
builds a prompt that asks a reviewer to refute the change against the stone's
exit test and the repository's invariants, and runs that prompt in a separate
`claude -p` process. The reviewer is not the session that wrote the code: it
starts with an empty conversation, sees only what this script gives it plus
the repository itself, and may read files and run the suite to check claims.
It works in a detached git worktree at the pull request's head commit, so what
it reads is what the pull request contains, not the author's checkout.
With --post the findings go to the pull request as one comment; without it
they print to stdout.

Exit code: 0 when the review has no blocking finding, or when no review is
due; 1 when it has one; 2 on a tool error (an off-format or cut-short review
included, which spends no round and posts nothing) or a round that must not
start; 3 when a round after a blocking round still blocks, because an
earlier finding was not fixed or the fix broke something: the fix round is
spent, the author rules once (documents/process/agent-rulings.md), and then
the owner decides. The author session merges a step on 0, and on 1 once it
has fixed the finding and posted a ruling that names the fix commit.

Which pull requests get a review, ruled by the owner 2026-10-12. A step that
touches a costly path gets one round, and only the owner grants it
another, with --extra-round owner. A step that touches none gets no review:
the tool prints so and exits 0, unless --force-review, the owner's call, asks
for one. A pull request into main, the stone review, keeps the rounds below.
The reviewer reports blocking findings only.

Rounds. The posted comment records the reviewed commit and the round number.
The next run reads them back: when new commits sit on top of the reviewed one,
it runs a fix check, which sees the earlier findings and only the diff since
that commit and asks whether each finding is fixed and whether the fix broke
something. A clean merge of the pull request's base since the reviewed commit
is left out of that diff: it brings only commits the base already carries,
each reviewed through its own pull request, and no edit of its own. When the
commits since the reviewed one are only such merges and the round before was
clean, nothing is reviewed and the tool exits 0 without posting. A rebased
branch, a merge of the base that is not clean (a conflict resolved by hand, an
edit folded in), a reviewed commit that is not on the head's first-parent line
(as after a merge made the other way round), or --full gets a full review
instead. The comment also records the round's exit code: a clean round
spends nothing, so every blocking round gets one fix round, and a round
after an exit 3 refuses to start without --extra-round. `--extra-round agent`
is the author's grant, allowed only while no extra round has run on the pull
request; `--extra-round owner`, or the bare flag, is the owner's, without a
limit. The comment records the first extra round and who granted it, and
carries that mark into every later rewrite, so the cap holds across rounds. A run without --post records nothing, so it never counts
as a round, and `--extra-round agent` refuses to run without it.

Model. The kind of change picks the reviewer's model and effort from the
profiles: a pull request into main is a stone review, a step that
touches a costly path is a costly review, anything else is a step
review, run only under --force-review. A costly review's later rounds, which
only the owner grants, run on the step profile. --model and --effort override
the profile.

The repository's data. The repository is the git top level of the caller's
folder, not the folder this tool sits in. Its .claude/mw.json, read through the
loader mw_data.py, gives the costly paths, the profiles, the grants it adds to
the reviewer's, the roadmap and its plan sentence, the invariants' file and
heading, the repository's name and the path sources the prompt names. A data
file the loader refuses prints the reason and exits 2.

Context. --stone N copies the "Stone N" section of the active phase plan into
the prompt as the exit test; the active plan is the one the data file's plan sentence first matches in
the roadmap at the reviewed commit. For a step (a pull request into a stone branch,
or into a step branch of that stone while the step below is open) the body of
the stone's open pull request to main, which holds the approved plan, is
appended through one `gh pr list` call. --context FILE appends a file verbatim, for a
documents-only step whose exit test is a plan file. A relative path is read at
the pull request head when it exists there and its resolved path stays inside
the worktree; otherwise it is read as typed, relative to the caller's directory,
so a scratch file outside the repository still works. A context file that exists
in neither place, a roadmap that names no plan, a missing phase plan or a
missing invariants file at the reviewed commit each print a named message and exit 2.

Foreground. Both prompts tell the reviewer to run every command in the
foreground with a timeout and never end its turn to wait for a task. A reply
without the three headings whose last paragraph announces such a wait exits 2
with a line saying so; a well-formed review whose last paragraph does is posted,
with a printed warning that its Verified section may rest on a run nobody read. The invariant list comes
from the data file's invariants heading. The reviewer starts in the reviewed
worktree, so its own system prompt carries that repository's CLAUDE.md.

From the plugin. The plugin's copy of this tool sets FROM_PLUGIN, and then the
reviewer loads that copy of the plugin with --plugin-dir and waits for its
plugins to install before its first turn. The engine's copy leaves the
reviewer's command as it was.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# The plugin's copy sets FROM_PLUGIN to True; the engine's copy leaves it False. It decides where the loader sits
# and whether the reviewer loads the plugin (documents/findings/stone-19-workflow-plugin-2026-10-17.md, question 2).
FROM_PLUGIN = True
HOME = Path(__file__).resolve().parent.parent  # the engine's checkout, or in the plugin the plugin's root


def loader_path():
    """The data file's loader: beside the hooks in the engine, at the plugin's root in the plugin."""
    return HOME / "mw_data.py" if FROM_PLUGIN else HOME / ".claude" / "hooks" / "mw_data.py"


_spec = importlib.util.spec_from_file_location("mw_data", loader_path())
mw_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw_data)

ROOT = None  # the repository under review: main sets it to the git top level of the caller's folder
DATA = None  # that repository's data file, as the loader returns it; main sets it
FOREGROUND = (
    "Run every command in the foreground with a timeout. Never start a background task, and never end your "
    "turn to wait for one: your reply ends the session, and nothing reads a later report."
)
# A reply whose last paragraph says it waits on something it started: the known issue of 2026-10-11, where
# three rounds ended on a background build and exited 2 with no review.
WAIT_ANNOUNCED = re.compile(
    r"\b(in the background|background (task|build|job)|(will|I'll) (report|check back|follow up)"
    r"|(once|when) (it|the [\w ]+?) (finishes|completes|is done)|wait(ing)? (for|on) (it|the))\b",
    re.I,
)
MARKER = "<!-- mw-review -->"
HEAD_MARK = re.compile(r"<!-- mw-review-head: ([0-9a-f]{7,40}) -->")
ROUND_MARK = re.compile(r"<!-- mw-review-round: (\d+) -->")
EXIT_MARK = re.compile(r"<!-- mw-review-exit: (\d) -->")
EXTRA_MARK = re.compile(r"<!-- mw-review-extra: (agent|owner), round (\d+) -->")  # the first extra round, and who granted it
TOOL_LINE = re.compile(r"^_(Note: |\d+ blocking finding|Round limit reached|Fix round spent)")  # what comment_body adds around the review

# The reviewer's model and effort per kind of change ("profiles") and the paths whose mistakes are costly and hard
# to see ("costly_paths", each with its reason) sit in the data file's review section. A change to either needs the
# owner's word; documents/process/model-choice.md holds the reasoning and says when the lists are revisited.

# Upstream code under third_party/<library>/ never reaches the reviewer as text: GitHub
# refuses a pull-request diff over 300 files, and SDL3 alone holds about 1,560. Our own
# glue (CMake, implementation units) sits directly in third_party/ and is diffed like any
# other file; the reviewer gets a file count per library for the rest.
VENDORED_EXCLUDE = ":(glob,exclude)third_party/*/**"
# Changed, removed and renamed upstream files are listed by name up to this many per
# library, so a local edit to upstream code is visible; a version bump lists the rest
# as a count.
VENDORED_NAMES_SHOWN = 40

# `claude -p` stops dead at the turn limit and its findings are lost, so the prompt states the
# budget. Set by the owner 2026-10-09 after Sonnet ran out of 40 turns on a 659-line pull
# request and Opus ran out of 15 on a fix check.
FULL_TURNS = 60
FIX_CHECK_TURNS = 30  # a fix check reads the earlier findings and the fix commits only
FETCH_RETRY_SECONDS = 5  # long enough for a concurrent fetch in the same checkout to finish

BLOCKING_RULE = """What blocks. A finding goes under Blocking only if it shows one of these:
- the step's own claim or the stone's exit test is not met;
- a repository invariant is broken;
- two tracked docs contradict each other, or a doc states a false fact;
- a path, heading or command the change names does not exist;
- a tool can lose data or leak a secret.
A gap in a later stone's plan never blocks, because every stone is replanned from scratch when it starts. Being cheap to fix does not make a finding blocking. Report nothing else: leave out every finding that does not meet this rule, a gap in a later stone's plan included."""

OUTPUT_FORMAT = """Write the result as Markdown with exactly these three headings, in this order:

## Blocking
One bullet per finding that meets the rule above. Each bullet starts with `path:line` where it applies, then one sentence stating the defect and one sentence stating the concrete failure. Write `- none` if there is none.

## Unresearched choices
One bullet per hard-to-reverse design choice that check 7 finds, and per ported part with no row that check 8 finds, same format. `- none` if none. Nothing else goes here.

## Verified
At most five bullets, each a claim you checked and found true, with how you checked it.

Be specific and terse. No preamble, no summary paragraph, no praise.
"""

FIX_CHECK_INSTRUCTIONS = f"""You are checking the fixes to one pull request in the <repository> repository. An earlier review of this pull request is below, and the diff below holds only the commits made since that review. Do two things:
1. For each finding under the earlier review's Blocking heading, decide whether the new commits fix it. An unfixed one goes under Blocking again.
2. Check the new commits for anything they break.
Do not review code the new commits leave untouched; the earlier round did that. You did not write the fixes and must not assume they work: read the repository at the pull request head, and compile a Python tool with `python -m py_compile` when a fix touches one. {FOREGROUND} Do not comment on style; the lint owns that.

{BLOCKING_RULE}

{OUTPUT_FORMAT}
Under Verified, give one bullet per earlier blocking finding that is fixed, with how you checked it."""

INSTRUCTIONS = """You are reviewing one pull request in the <repository> repository. Your job is to refute it: find every way the change fails its exit test, breaks a repository rule, or would misbehave. You did not write this code and you must not assume it works. Verify claims by reading the repository, by running the suite when the change touches C++, and by compiling a Python tool with `python -m py_compile` when the change touches one. """ + FOREGROUND + """ Do not comment on style; the lint owns that.

Check, in this order:
1. Correctness against the exit test and bullets below. Does the change do what the step claims, completely?
2. Repository invariants (listed below). Any violation, even in a test or a tool, is a finding.
3. Determinism risks: wall-clock reads, platform randomness, hash-map iteration, float contraction, iteration-order dependence.
4. Allocation inside the tick, pointers to pooled entities, missing module headers.
5. Missing or weak tests: an assertion the exit test implies that no test makes.
6. For documents: a stated fact that is false or contradicts another tracked doc, a heading that does not exist, and a path that does not exist<path sources>, and every tracked .md for prose rules.
7. Did this step make a hard-to-reverse design choice (a data layout, a file format, a public interface, a memory-ownership rule) that neither the stone's plan (below, when a stone pull request is open) nor a findings doc researched? A yes goes under Unresearched choices; a choice that breaks a repository invariant blocks under the rule below.
8. Ported parts. When the stone's plan names a port-triage record under documents/findings/, measure code that rebuilds a part of the reference game's subsystem against that part's row in the record, never against the reference game: the rows the pull request body cites, and any other row the code rebuilds. Code that departs from its row's engine answer fails the step's own claim and goes under Blocking. A part the code rebuilds that has no row in the record goes under Unresearched choices.

""" + BLOCKING_RULE + "\n\n" + OUTPUT_FORMAT

# Read-and-verify only. The reviewer may inspect history, build and run the
# suite, and run the tools scripts; it may not merge, close, commit or edit.
# This is the base list; allowed_tools() joins the repository's additions from the data file.
BASE_TOOLS = [
        "Read",
        "Grep",
        "Glob",
        "Bash(git diff:*)",
        "Bash(git log:*)",
        "Bash(git show:*)",
        "Bash(gh pr diff:*)",
        "Bash(gh pr view:*)",
        "Bash(gh pr checks:*)",
        "Bash(git ls-files:*)",
        "Bash(git grep:*)",
        "Bash(wc:*)",
        # The hooks, so a reviewer can feed them JSON by hand. No blanket
        # "python tools/*": it would let the reviewer run this very script and
        # post from inside a review. Name tool scripts here one by one as they land.
        "Bash(python .claude/hooks/*)",
        "Bash(python3 .claude/hooks/*)",
        # The syntax check a tool step's exit test names; py_compile runs nothing.
        "Bash(python -m py_compile:*)",
        "Bash(python3 -m py_compile:*)",
        # The tool's own checks: pure functions only, no gh, no claude, no posting.
        "Bash(python tools/test_review_pr.py:*)",
        "Bash(python3 tools/test_review_pr.py:*)",
        "Bash(python tools\\test_review_pr.py:*)",
        "Bash(python tools/test_hooks.py:*)",
        "Bash(python3 tools/test_hooks.py:*)",
        "Bash(python tools\\test_hooks.py:*)",
]


def allowed_tools():
    """The reviewer's grants: the base list, then each addition of the data file that the base list lacks."""
    return ",".join(BASE_TOOLS + [tool for tool in DATA["review"]["allowed_tools"] if tool not in BASE_TOOLS])


def repo_root(cwd=None):
    """The git top level of cwd, the caller's folder by default; a folder outside a repository exits 2."""
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True, capture_output=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(f"[review_pr] {Path(cwd or '.').resolve()} is in no git repository: {proc.stderr.strip()}\n")
        sys.exit(2)
    return Path(proc.stdout.strip())


def instructions(fix_check):
    """The prompt's opening for this repository: its name, and the files whose paths the invariant test checks."""
    sources = DATA["review"]["path_sources"]
    named = ", ".join(sources[:-1]) + " and " + sources[-1] if len(sources) > 1 else "".join(sources)
    where = f" in any doc other than {named}. The invariant test checks those for paths" if sources else ""
    text = FIX_CHECK_INSTRUCTIONS if fix_check else INSTRUCTIONS
    return text.replace("<repository>", DATA["repository"]).replace("<path sources>", where)


def run(cmd, **kw):
    # A diff can hold bytes that are not UTF-8, such as a fuzz input; they show as replacement characters.
    kw.setdefault("cwd", ROOT)  # gh and git both need the repository, wherever the caller sits
    return subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace", **kw)


def fetch_ref(ref):
    """`git fetch origin <ref>` in the checkout, retried once after a pause.

    Two runs fetching at once raced on one remote-tracking ref and ended a round with no review
    (documents/known-issues.md, 2026-10-12); the second try comes after the first has finished.
    """
    proc = run(["git", "fetch", "origin", ref], cwd=ROOT)
    if proc.returncode != 0:
        time.sleep(FETCH_RETRY_SECONDS)
        proc = run(["git", "fetch", "origin", ref], cwd=ROOT)
    return proc


def gh_json(args):
    proc = run(["gh"] + args)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(2)
    return json.loads(proc.stdout)


def phase_plan(root):
    """The active phase plan the roadmap names at the reviewed commit, as a path relative to the root, or None.

    The plan sentence's first match wins: the engine's ROADMAP.md names the open phase's plan first."""
    roadmap = root / DATA["review"]["roadmap"]
    if not roadmap.is_file():
        return None
    match = re.search(DATA["review"]["plan_sentence"], roadmap.read_text(encoding="utf-8"))
    return Path(match.group(1)) if match else None


def stone_section(number, root):
    """The stone's section of the phase plan at the reviewed commit, or None when the heading is missing."""
    relative = phase_plan(root)
    if relative is None:
        sys.stderr.write(f"[review_pr] {DATA['review']['roadmap']} names no phase plan at the reviewed commit (no match for "
                         f"{DATA['review']['plan_sentence']!r}); refusing to review without an exit test\n")
        sys.exit(2)
    plan = root / relative
    if not plan.is_file():
        sys.stderr.write(f"[review_pr] {relative.as_posix()} is absent at the reviewed commit; refusing to review without an exit test\n")
        sys.exit(2)
    text = plan.read_text(encoding="utf-8")
    pattern = re.compile(rf"^### Stone {number}\b.*?(?=^### |^## |\Z)", re.S | re.M)
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def strip_preamble(review):
    """Drop any narration the reviewer wrote before its first heading."""
    index = review.find("## Blocking")
    return review[index:] if index > 0 else review


def invariants(root):
    """The section the data file names, read at the reviewed commit."""
    name, heading = DATA["review"]["invariants"]["file"], DATA["review"]["invariants"]["heading"]
    source = root / name
    if not source.is_file():
        sys.stderr.write(f"[review_pr] {name} is absent at the reviewed commit; refusing to review without the invariant list\n")
        sys.exit(2)
    text = source.read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1).strip() if match else f"({name} has no {heading} section)"


def stone_branch(base_ref):
    """The stone branch a step's base belongs to: the base itself, or stone/<slug> for a stacked step's
    base step/<slug>/<n>-<name>; None for main or any other base."""
    if base_ref.startswith("stone/"):
        return base_ref
    parts = base_ref.split("/")
    if len(parts) >= 3 and parts[0] == "step" and parts[1]:
        return f"stone/{parts[1]}"
    return None


def stone_plan(base_ref):
    """The body of the open pull request whose head is the stone branch, so the reviewer sees what the plan researched.

    A step's base is its stone branch, or the step below it while that one is open; the stone's own pull
    request to main carries the approved plan. Returns None for a pull request into main or when no such
    pull request is open.
    """
    stone = stone_branch(base_ref)
    if stone is None:
        return None
    proc = run(["gh", "pr", "list", "--head", stone, "--state", "open", "--json", "body", "--limit", "1"])
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError:
        return None  # a review without the plan beats a traceback
    return rows[0]["body"] if rows and rows[0].get("body") else None


def build_prompt(pr, diff, stone, context_files, root, fix_check=None, turns=FULL_TURNS):
    """root is the worktree at the pull request head, so the exit test and the invariants are the reviewed text.

    fix_check is None for a full review. For a fix check it is (earlier round, reviewed commit, earlier
    findings, commits), and diff holds only the commits since the reviewed one, without the clean merges
    of the base; commits names the ranges the diff covers.
    """
    parts = [instructions(fix_check), turn_budget(turns)]
    body = pr.get("body") or "(no body)"
    parts.append(f"# Pull request #{pr['number']}: {pr['title']}\n\nTarget branch: {pr['baseRefName']}\n\n{body}")
    if stone is not None:
        section = stone_section(stone, root)
        if section is None:
            sys.stderr.write(f"[review_pr] Stone {stone} has no section in {phase_plan(root).as_posix()}; refusing to review without an exit test\n")
            sys.exit(2)
        parts.append("# Exit test and bullets\n\n" + section)
    for path in context_files:
        source = Path(path)
        if not source.is_absolute():
            # A tracked file is read at the pull request head, like the stone
            # section. The resolved path must stay under the worktree, so a
            # `..` segment cannot reach a file beside it.
            in_worktree = (root / source).resolve()
            if in_worktree.is_file() and root.resolve() in in_worktree.parents:
                source = in_worktree
        # Any other path, absolute or relative to the caller's directory, is read
        # as given: the stone context file lives outside the repository on purpose.
        if not source.is_file():
            looked = f"at {source}" if source.is_absolute() else f"at the reviewed commit or at {source.resolve()}"
            sys.stderr.write(f"[review_pr] --context {path}: no such file {looked}\n")
            sys.exit(2)
        parts.append(f"# Context: {path} (read from {source})\n\n" + source.read_text(encoding="utf-8"))
    plan = stone_plan(pr["baseRefName"])
    if plan:
        parts.append("# The stone's approved plan (the body of the stone's pull request to main)\n\n" + plan)
    parts.append(f"# Repository invariants ({DATA['review']['invariants']['file']})\n\n" + invariants(root))
    if fix_check:
        number, commit, findings, commits = fix_check
        parts.append(f"# The earlier review (round {number}, commit {commit[:7]})\n\n{findings}")
        parts.append(f"# Diff since the reviewed commit ({commits})\n\n```diff\n{diff}\n```")
    else:
        parts.append("# Diff\n\n```diff\n" + diff + "\n```")
    return "\n\n".join(parts)


def turn_budget(turns):
    """The budget section: the session ends without output at the limit, so the result must come first."""
    return (
        f"# Your budget\n\nYou have {turns} turns, and the session ends without output when they run out. "
        "Batch independent reads into one turn. Write the three headings no later than "
        f"turn {max(1, turns - 5)}, with what you have verified by then."
    )


def vendored_summary(name_status):
    """`git diff --name-status` output as one line per library under third_party/<library>/."""
    counts = {}
    named = {}  # every file that is not a plain addition, so an edit to upstream code shows by name
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        segments = parts[-1].split("/")
        if len(segments) < 3 or segments[0] != "third_party":
            continue
        letter = parts[0][:1]
        tally = counts.setdefault(segments[1], {"A": 0, "M": 0, "D": 0, "R": 0})
        tally[letter if letter in tally else "M"] += 1
        if letter != "A":
            named.setdefault(segments[1], []).append(f"{letter} {parts[-1]}")
    if not counts:
        return ""
    lines = ["Upstream files under third_party/<library>/ are not shown as a diff. Per library in this change:"]
    for library in sorted(counts):
        t = counts[library]
        lines.append(f"- third_party/{library}/: {t['A']} added, {t['M']} changed, {t['D']} removed, {t['R']} renamed")
        lines.extend(f"  - {entry}" for entry in named.get(library, [])[:VENDORED_NAMES_SHOWN])
        hidden = len(named.get(library, [])) - VENDORED_NAMES_SHOWN
        if hidden > 0:
            lines.append(f"  - and {hidden} more changed, removed or renamed files")
    lines.append("Their content is upstream's. Check the licence row in documents/third-party-licenses.md and the "
                 "CMake wiring in third_party/, and read any vendored file you need in the worktree.")
    return "\n".join(lines) + "\n\n"


def review_kind(base_ref, paths):
    """stone for a pull request into main, costly when a path matches the data file's costly paths, step otherwise."""
    if base_ref == "main":
        return "stone"
    if any(re.match(row["pattern"], p) for p in paths for row in DATA["review"]["costly_paths"]):
        return "costly"
    return "step"


def review_profile(kind, round_number):
    """The model and effort for this round: a costly step's later rounds check fixes, so they run on the step profile."""
    return tuple(DATA["review"]["profiles"]["step" if kind == "costly" and round_number > 1 else kind])


def skips_review(kind, force):
    """True for a step that touches no costly path: it merges on green CI unless --force-review asks for a round."""
    return kind == "step" and not force


def one_round_note(kind, earlier, extra_round):
    """The refusal for a step's second round, or None when this round may run.

    A step gets one round, ruled by the owner 2026-10-12: the author fixes a blocking finding, records the fix
    and merges, and the stone review rereads it. Only the owner grants a step another round; the stone review
    keeps its fix round and the author's extra round.
    """
    if kind == "stone" or earlier is None or extra_round == "owner":
        return None
    return (
        f"a step gets one review round (ruled 2026-10-12), and round {earlier[1]} has run: fix a blocking finding, "
        "record the fix and merge once CI is green; only the owner grants another round, with --extra-round owner"
    )


def parse_marks(body):
    """(reviewed commit, round, exit code, extra) from an earlier comment of this tool, or None for a comment from before the marks.

    A comment without marks was written before rounds existed, so the next run is round 1 and edits it in
    place. A comment without the exit mark predates it; its exit code reads as None, which spends no fix round.
    extra is (grantor, round) for the first extra round on the pull request, "agent" or "owner", or None before one runs.
    """
    head = HEAD_MARK.search(body)
    number = ROUND_MARK.search(body)
    if not number:
        return None
    code = EXIT_MARK.search(body)
    extra = EXTRA_MARK.search(body)
    return (
        head.group(1) if head else None,
        int(number.group(1)),
        int(code.group(1)) if code else None,
        (extra.group(1), int(extra.group(2))) if extra else None,
    )


def earlier_findings(body):
    """The earlier comment's three sections, without the markers and the footer."""
    start = body.find("## Blocking")
    text = body[start:] if start >= 0 else body
    lines = [line for line in text.splitlines() if not line.startswith("<!--") and not TOOL_LINE.match(line)]
    return "\n".join(lines).strip()


def plan_round(earlier, head, full, ancestor, extra_round, walk=None):
    """This run's round, its mode and a note, from the earlier comment's marks.

    earlier is (reviewed commit, round, exit code, extra), or None on a first review; extra_round is
    None, "agent" or "owner"; ancestor says whether the reviewed commit is an ancestor of head; walk is
    walk_since's (segments, clean merges, unclean merge) for the commits between them, or None when it
    was not taken. A merge of the base that is not clean would show the base's changes as the fix, so it
    forces a full review. The mode is "full", "fix check", "nothing" when only clean merges of the base
    follow a clean round, or None when the run must not start, and then the note says why.
    """
    if earlier is None:
        return 1, "full", ""
    commit, number, code, extra = earlier
    this = number + 1
    if code == 3 and not extra_round:
        if extra is not None:
            return this, None, f"round {number} exited 3 after the extra round {extra[1]}, so round {this} needs --extra-round owner"
        return this, None, (
            f"round {number} exited 3, so round {this} needs --extra-round agent, the author's one ruling "
            "(documents/process/agent-rulings.md), or --extra-round owner"
        )
    if code == 3 and extra_round == "agent" and extra is not None:
        who = "the author" if extra[0] == "agent" else "the owner"
        return this, None, (
            f"{who} granted the extra round {extra[1]} on this pull request; "
            "only the owner grants another, with --extra-round owner"
        )
    if full:
        return this, "full", "a full review, forced with --full"
    if commit is None or not ancestor:
        shown = commit[:7] if commit else "(not recorded)"
        return this, "full", f"the reviewed commit {shown} is not an ancestor of {head[:7]}, so this round reviews the whole diff"
    if head.startswith(commit) or commit.startswith(head):
        return this, None, f"no commits since round {number} reviewed {commit[:7]}; push the fixes first, or pass --full"
    if walk is None:
        return this, "fix check", ""
    segments, clean, unclean = walk
    if unclean and unclean.startswith(commit):
        return this, "full", (
            f"the reviewed commit {commit[:7]} is not on {head[:7]}'s first-parent line, as after a merge made the "
            "other way round, so this round reviews the whole diff"
        )
    if unclean:
        return this, "full", (
            f"the commits since {commit[:7]} include the merge {unclean[:7]} of the base, which is not clean, "
            "so this round reviews the whole diff"
        )
    skipped = f"{len(clean)} clean merge(s) of the base left out ({', '.join(c[:7] for c in clean)})" if clean else ""
    if not segments:
        if code in (0, None):
            return this, "nothing", f"nothing to review since round {number}: the commits since {commit[:7]} are clean merges of the base"
        return this, None, (
            f"the commits since round {number} reviewed {commit[:7]} are clean merges of the base only, "
            "and that round blocked; push the fixes first, or pass --full"
        )
    return this, "fix check", skipped


def walk_since(reviewed, head, base_ref, cwd=None):
    """(segments, clean, unclean) for the first-parent commits from reviewed to head, or None on a git failure.

    A merge whose second parent the base already carries is a merge of the base. It is clean when its
    tree is git's own merge of its two parents (`git merge-tree --write-tree`, git 2.38 or later): it
    brings only reviewed commits and no edit of its own, so it is left out of the fix check and listed in
    clean. A merge of the base with any other tree is unclean, and its commit is returned so the round
    reviews the whole diff. Every other commit, a merge of some other branch included, is reviewed.
    segments are the (from, to) ranges between the clean merges, each diffed as one. A reviewed commit
    that is not on the head's first-parent line, as after a merge made the other way round (the base
    checked out, the step merged into it, the result pushed to the step), is returned as the unclean
    commit, so the round reviews the whole diff: the walk would read the base's own merges as the step's.
    """
    kw = {"cwd": cwd} if cwd else {}
    listed = run(["git", "rev-list", "--first-parent", "--reverse", "--parents", f"{reviewed}..{head}"], **kw)
    if listed.returncode != 0:
        sys.stderr.write(listed.stderr)
        return None
    full = run(["git", "rev-parse", "--verify", f"{reviewed}^{{commit}}"], **kw)
    line = run(["git", "rev-list", "--first-parent", head], **kw)
    if full.returncode != 0 or line.returncode != 0:
        sys.stderr.write(full.stderr + line.stderr)
        return None
    if full.stdout.strip() not in line.stdout.split():
        return [], [], full.stdout.strip()
    segments, clean = [], []
    start = prev = reviewed
    for line in listed.stdout.splitlines():
        commit, *parents = line.split()
        if len(parents) == 2 and run(["git", "merge-base", "--is-ancestor", parents[1], base_ref], **kw).returncode == 0:
            merged = run(["git", "merge-tree", "--write-tree", parents[0], parents[1]], **kw)
            tree = run(["git", "rev-parse", f"{commit}^{{tree}}"], **kw)
            if tree.returncode != 0:
                sys.stderr.write(tree.stderr)
                return None
            if merged.returncode not in (0, 1):  # 1 is a conflict; anything else is git failing, never a verdict
                sys.stderr.write(merged.stderr)
                return None
            if merged.returncode == 1 or merged.stdout.split()[:1] != tree.stdout.split():
                return segments, clean, commit  # a conflict resolved by hand, or an edit folded into the merge
            if start != prev:
                segments.append((start, prev))
            clean.append(commit)
            start = commit
        elif len(parents) > 2:
            return segments, clean, commit  # an octopus merge: no clean form to compare against
        prev = commit
    if start != prev:
        segments.append((start, prev))
    return segments, clean, None


def join_ranges(parts):
    """The diff text a round reads, from each range's (diff, third_party name-status) in walk order.

    A file two ranges touch under third_party/ counts once, by its first letter: added in one range
    and changed in a later one is an addition.
    """
    first = {}
    for _, name_status in parts:
        for line in name_status.splitlines():
            first.setdefault(line.split("\t")[-1], line)
    return vendored_summary("\n".join(first.values())) + "".join(diff for diff, _ in parts)


def extra_round_note(earlier, extra_round):
    """The line a run prints when --extra-round is given on a round that does not follow an exit 3, or None."""
    if not extra_round or (earlier is not None and earlier[2] == 3):
        return None
    return (f"--extra-round {extra_round} has no effect: the round before did not exit 3, "
            "so this round is not an extra round and spends none")


def announces_wait(review):
    """True when the reply's last paragraph says it waits on a task it started instead of reporting."""
    paragraphs = [p for p in re.split(r"\n\s*\n", review.strip()) if p.strip()]
    return bool(paragraphs) and bool(WAIT_ANNOUNCED.search(paragraphs[-1]))


def carried_extra(earlier, number, extra_round):
    """The extra mark this round's comment records: the earlier one, carried forward, or (grantor, this round).

    The tool edits one comment in place, so a mark lives only in the latest body; carrying it keeps the
    cap: the author's grant runs only while no extra round has run on the pull request, the owner's or
    its own. This round is an extra round only when it runs after an exit 3 under --extra-round; the
    flag on any other round has no effect and writes no mark.
    """
    if earlier is None:
        return None
    if earlier[3] is not None:
        return earlier[3]
    return (extra_round, number) if earlier[2] == 3 and extra_round else None


def exit_code(blocking, earlier_code):
    """0 clean; 1 blocking with a fix round to come; 3 when the fix round still blocks.

    earlier_code is the exit code of the round before, or None on round 1 and for a comment from
    before the exit mark. A clean round spends nothing, so every blocking round gets one fix round.
    A round after a blocking round that still blocks, on an unfixed finding or on a defect the fix
    brought in, goes to the author's one ruling and then to the owner: per-finding rounds would need
    the reviewer to tag each finding and could run without end.
    """
    if not blocking:
        return 0
    return 3 if earlier_code in (1, 3) else 1


def spent_line(extra):
    """The footer line and the closing print after an exit 3: the author's one ruling, or the owner once an extra round has run."""
    if extra is None:
        return "Fix round spent: the author rules once (documents/process/agent-rulings.md), then the owner decides."
    return "Fix round spent: the owner decides."


def comment_body(review, blocking, pr, number, mode, note, profile, commits, earlier_code=None, extra=None):
    """The posted comment: the markers the next round reads, the header, the review and the footer.

    profile is (kind, model, effort); extra is carried_extra's value for this round.
    """
    kind, model, effort = profile
    code = exit_code(blocking, earlier_code)
    lines = [MARKER, f"<!-- mw-review-head: {pr['headRefOid']} -->", f"<!-- mw-review-round: {number} -->"]
    lines.append(f"<!-- mw-review-exit: {code} -->")
    if extra is not None:
        lines.append(f"<!-- mw-review-extra: {extra[0]}, round {extra[1]} -->")
    lines += [f"## Adversarial review (fresh session), round {number}, {mode}", ""]
    if note:
        lines += [f"_Note: {note}._", ""]
    lines += [review, ""]
    lines.append(
        f"_{blocking} blocking finding(s). Branch {pr['headRefName']}, commits {commits}. "
        f"A {kind} review: model {model}, effort {effort}._"
    )
    if code == 3:
        lines.append(f"_{spent_line(extra)}_")
    return "\n".join(lines)


def well_formed(review):
    """True when the review carries all three headings; one cut off after Blocking lacks the last two."""
    return all(re.search(rf"^## {name}\s*$", review, re.M) for name in ("Blocking", "Unresearched choices", "Verified"))


def blocking_count(review):
    """Anything in the Blocking section other than exactly `- none` blocks."""
    match = re.search(r"^## Blocking\s*\n(.*?)(?=^## |\Z)", review, re.S | re.M)
    if not match:
        return 1  # a malformed review blocks until a human reads it
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    if not lines:
        return 1
    if len(lines) == 1 and lines[0].rstrip(".").lower() in ("- none", "* none", "none"):
        return 0
    bullets = [line for line in lines if re.match(r"^(-|\*|\d+\.)\s", line)]
    return max(1, len(bullets))


def find_review_comment(pr_number):
    """This tool's comment on the pull request as (id, body), or None when there is none.

    A failed listing exits 2: treating it as "no comment" would restart the rounds at 1
    and post a second comment.
    """
    # --slurp wraps the pages in one array; without it a second page breaks the JSON.
    listed = run(["gh", "api", f"repos/{{owner}}/{{repo}}/issues/{pr_number}/comments", "--paginate", "--slurp"])
    if listed.returncode != 0:
        sys.stderr.write(listed.stderr)
        sys.stderr.write(f"[review_pr] could not list the comments on #{pr_number}\n")
        sys.exit(2)
    try:
        pages = json.loads(listed.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"[review_pr] the comment listing for #{pr_number} is not JSON\n")
        sys.exit(2)
    found = None
    for page in pages:
        for comment in page:
            body = comment.get("body") or ""
            if body.startswith(MARKER):  # a reply that quotes the review starts with ">"
                found = (comment["id"], body)
    return found


def post_comment(pr_number, body, existing_id):
    """Update this tool's earlier comment on the pull request, or create one.

    One comment per pull request, edited in place as the CI comment is, so the
    thread shows the latest verdict and the comment's edit history holds the
    earlier ones.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        body_path = f.name
    try:
        if existing_id is not None:
            return run(["gh", "api", "--method", "PATCH", f"repos/{{owner}}/{{repo}}/issues/comments/{existing_id}", "-F", f"body=@{body_path}"])
        return run(["gh", "pr", "comment", str(pr_number), "--body-file", body_path])
    finally:
        os.unlink(body_path)


def arg_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", type=int)
    ap.add_argument("--stone", type=int)
    ap.add_argument("--context", action="append", default=[])
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--full", action="store_true", help="review the whole diff even when a fix check would do")
    ap.add_argument(
        "--extra-round",
        nargs="?",
        const="owner",
        choices=("agent", "owner"),
        help="start a round past the limit: agent on the author's ruling while no extra round has run "
        "(documents/process/agent-rulings.md), owner or bare on the owner's word; give it after the "
        "pull-request number, which it would otherwise take as its value",
    )
    ap.add_argument("--force-review", action="store_true",
                    help="review a step that touches no costly path; the owner's call (ruled 2026-10-12)")
    ap.add_argument("--model", help="override the model the kind of change picks")
    ap.add_argument("--effort", help="override the effort the kind of change picks")
    ap.add_argument("--max-turns", type=int, help=f"default {FULL_TURNS} for a full review, {FIX_CHECK_TURNS} for a fix check")
    return ap


def flag_error(args):
    """A message when the flags must not run together, else None.

    The author's extra round is capped by the mark the posted comment carries; a run without --post
    writes no mark, so it would leave the grant unspent.
    """
    if args.extra_round == "agent" and not args.post:
        return "--extra-round agent needs --post, because only a posted round records the author's grant"
    return None


def main():
    args = arg_parser().parse_args()
    refused = flag_error(args)
    if refused:
        sys.stderr.write(f"[review_pr] #{args.pr}: {refused}\n")
        return 2
    # A review carries characters the Windows console code page cannot encode, and a crash
    # while printing loses the whole run.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    global ROOT, DATA
    ROOT = repo_root()
    DATA = mw_data.load_or_exit(ROOT)

    pr = gh_json(["pr", "view", str(args.pr), "--json", "number,title,body,baseRefName,headRefName,headRefOid"])
    # The reviewer reads the pull request's head commit, not whatever the author
    # has checked out: a detached worktree at that commit, removed afterwards.
    # pull/<n>/head resolves for a fork's pull request too.
    fetch = fetch_ref(f"pull/{args.pr}/head")
    if fetch.returncode != 0:
        sys.stderr.write(fetch.stderr)
        return 2

    head = pr["headRefOid"]
    # The base is fetched first: the walk below asks whether a merge's second parent is on it.
    base = f"origin/{pr['baseRefName']}"
    base_fetch = fetch_ref(pr["baseRefName"])
    if base_fetch.returncode != 0:
        sys.stderr.write(base_fetch.stderr)
        return 2
    # The kind comes first, from every file of the pull request: a step outside the costly paths gets no
    # review at all, and a step gets one round.
    merge_base = run(["git", "merge-base", base, head])
    if merge_base.returncode != 0:
        sys.stderr.write(merge_base.stderr)
        return 2
    pr_base = merge_base.stdout.strip()
    names = run(["git", "diff", "--name-only", pr_base, head])
    if names.returncode != 0:
        sys.stderr.write(names.stderr)
        return 2
    kind = review_kind(pr["baseRefName"], names.stdout.splitlines())
    if skips_review(kind, args.force_review):
        print(f"[review_pr] #{args.pr}: no review: the step touches no costly path "
              f"(documents/process/model-choice.md); merge once CI is green on {head[:7]}")
        return 0
    found = find_review_comment(args.pr)
    earlier = parse_marks(found[1]) if found else None
    refusal = one_round_note(kind, earlier, args.extra_round)
    if refusal:
        sys.stderr.write(f"[review_pr] #{args.pr}: {refusal}\n")
        return 2
    ancestor, walk = False, None
    if earlier and earlier[0]:
        ancestor = run(["git", "merge-base", "--is-ancestor", earlier[0], head]).returncode == 0
        if ancestor and not head.startswith(earlier[0]):
            walk = walk_since(earlier[0], head, base)
            if walk is None:
                sys.stderr.write(f"[review_pr] could not walk the commits in {earlier[0][:7]}..{head[:7]}\n")
                return 2
    number, mode, note = plan_round(earlier, head, args.full, ancestor, args.extra_round, walk)
    if mode is None:
        sys.stderr.write(f"[review_pr] #{args.pr}: {note}\n")
        return 2
    unused = extra_round_note(earlier, args.extra_round)
    if unused:
        print(f"[review_pr] note: {unused}")
    if mode == "nothing":
        # No reviewer runs and the comment stays as it is, so the next run walks from the same commit.
        print(f"[review_pr] #{args.pr}: {note}; merge once CI is green on {head[:7]}")
        return 0
    extra = carried_extra(earlier, number, args.extra_round)

    # The diff comes from git, not from `gh pr diff`, which GitHub refuses past 300 files.
    # A full review diffs from the merge base, as GitHub's own pull-request diff does; a fix
    # check diffs each range between the clean merges of the base.
    if mode == "fix check":
        ranges = walk[0] if walk else [(earlier[0], head)]
        commits = ", ".join(f"{a[:7]}..{b[:7]}" for a, b in ranges)
        fix_check = (earlier[1], earlier[0], earlier_findings(found[1]), commits)
    else:
        ranges = [(pr_base, head)]
        commits = f"{pr['baseRefName']}..{head[:7]}"
        fix_check = None
    parts = []
    for diff_from, diff_to in ranges:
        diff_proc = run(["git", "diff", diff_from, diff_to, "--", ".", VENDORED_EXCLUDE])
        # core.quotePath off, so a path with non-ASCII characters is not quoted and still counted.
        vendored = run(["git", "-c", "core.quotePath=false", "diff", "--name-status", diff_from, diff_to, "--", "third_party"])
        for proc in (diff_proc, vendored):
            if proc.returncode != 0:
                sys.stderr.write(proc.stderr)
                return 2
        parts.append((diff_proc.stdout, vendored.stdout))
    diff_text = join_ranges(parts)
    model, effort = review_profile(kind, number)
    profile = (kind, args.model or model, args.effort or effort)
    turns = args.max_turns or (FIX_CHECK_TURNS if fix_check else FULL_TURNS)
    print(f"[review_pr] #{args.pr} round {number}, {mode}, {kind} review, model {profile[1]}, effort {profile[2]}, {turns} turns")
    if note:
        print(f"[review_pr] note: {note}")

    worktree = Path(tempfile.mkdtemp(prefix="mw_review_"))
    added = run(["git", "worktree", "add", "--detach", str(worktree), pr["headRefOid"]], cwd=ROOT)
    if added.returncode != 0:
        sys.stderr.write(added.stderr)
        return 2
    try:
        prompt = build_prompt(pr, diff_text, args.stone, args.context, worktree, fix_check, turns)
        earlier_code = earlier[2] if earlier else None
        review_round = (number, mode, note, profile, turns, commits, found[0] if found else None, earlier_code, extra)
        return review_in(worktree, prompt, pr, args, review_round)
    finally:
        removed = run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT)
        if removed.returncode != 0:
            sys.stderr.write(
                f"[review_pr] could not remove the review worktree at {worktree}: {removed.stderr.strip()}\n"
                "[review_pr] remove it by hand, then run `git worktree prune`.\n"
            )


def reviewer_call(profile, turns):
    """The reviewer's command and environment. From the plugin, the reviewer loads this copy of the plugin in place
    and waits for its plugins to install before its first turn; from the engine, neither."""
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "text",
        "--max-turns",
        str(turns),
        "--model",
        profile[1],
        "--effort",
        profile[2],
        "--allowedTools",
        allowed_tools(),
        # Every allowed entry is a Bash rule, and a refused PowerShell call cannot ask for
        # approval under -p, so the reviewer keeps to the shell the list covers.
        "--disallowedTools",
        "PowerShell",
    ]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # permit a nested session when run from inside Claude Code
    if FROM_PLUGIN:
        cmd += ["--plugin-dir", str(HOME)]
        env["CLAUDE_CODE_SYNC_PLUGIN_INSTALL"] = "1"
    return cmd, env


def review_in(worktree, prompt, pr, args, review_round):
    number, mode, note, profile, turns, commits, comment_id, earlier_code, extra = review_round
    cmd, env = reviewer_call(profile, turns)
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        cwd=worktree,
        env=env,
        shell=(os.name == "nt"),
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        # `claude -p` reports some failures, such as running out of turns, on stdout only.
        tail = "\n".join(proc.stdout.strip().splitlines()[-20:])
        if tail:
            sys.stderr.write(f"[review_pr] the last lines of the reviewer's output:\n{tail}\n")
        sys.stderr.write(f"\n[review_pr] claude exited {proc.returncode}\n")
        return 2
    review = strip_preamble(proc.stdout.strip())
    if not well_formed(review) and announces_wait(review):
        print(review)
        sys.stderr.write(f"[review_pr] the reviewer on #{args.pr} ended its turn waiting on a task it started, which its prompt "
                         "forbids (run every command in the foreground); nothing posted, rerun the same round\n")
        return 2
    if not well_formed(review):
        # Off format or cut short: a tool error, so the round is not spent and nothing is posted.
        print(review)
        sys.stderr.write(f"[review_pr] the reviewer's output on #{args.pr} lacks one of the three headings; nothing posted, rerun the same round\n")
        return 2
    if announces_wait(review):
        sys.stderr.write(f"[review_pr] warning: the review on #{args.pr} ends by announcing a wait on a task it started; "
                         "its Verified section may rest on a run nobody read\n")
    blocking = blocking_count(review)
    body = comment_body(review, blocking, pr, number, mode, note, profile, commits, earlier_code, extra)

    if args.post:
        post = post_comment(args.pr, body, comment_id)
        if post.returncode != 0:
            sys.stderr.write(post.stderr)
            return 2
        print(f"[review_pr] posted to #{args.pr}: round {number}, {blocking} blocking")
    else:
        print(body)
    code = exit_code(blocking, earlier_code)
    if code == 3:
        print(f"[review_pr] #{args.pr}: {spent_line(extra)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
