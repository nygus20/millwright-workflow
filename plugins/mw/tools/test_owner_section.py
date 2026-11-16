"""Checks for tools/owner_section.py: no gh, no network, and git only to find a repository's top level.

Usage:
    python tools/test_owner_section.py [PROJECT]

PROJECT is the repository the checks run against: the folder given, else
CLAUDE_PROJECT_DIR, else the current folder. tools/run_checks.py passes it.
A section built from PROJECT's own impact names, or from none when its data
file has no `owner_section` key, must pass.

The function `problems` runs on literal texts: a plan and a summary that pass,
then one planted break per check, each of which must give exactly its one
problem, so no check passes by default. The whole command runs as a separate
process against a temporary repository, once per exit code. Prints
`[test_owner_section] N checks, M failures` and exits 1 when M is not zero.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
TOOL = PLUGIN / "tools" / "owner_section.py"
PROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
DATA = json.loads((PLUGIN / "tools" / "fixture" / ".claude" / "mw.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("owner_section", TOOL)
section = importlib.util.module_from_spec(spec)
spec.loader.exec_module(section)

checks = 0
failures = []


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


IMPACT = ["The player", "Saves and content", "Speed on the devices", "Other stones", "Waiting for you"]
END = section.END_LINE


def build(kind, impact, title="# Plan: Stone 7, the results screen"):
    """A text of the given kind that passes, with one impact line per name."""
    first = "What changes." if kind == "plan" else "What changed."
    against = ["**Against the plan.** As planned.", ""] if kind == "summary" else []
    names = impact or ["The player", "The schedule", "Waiting for you"]
    return "\n".join([
        title, "", "## For the owner", "",
        f"**{first}** A run now ends on a full results screen. The game keeps one record of each run.", "",
        "**The decisions.**",
        "- The stone was split in two, and a later stone takes the network parts. A later stone can undo it. "
        "The owner decided.",
        "- The score matches the leaderboard server, a small program that ranks the runs. The agent decided.", "",
        *against,
        "**The impact.**", *[f"- {name}: none." for name in names], "",
        END, "", "## Context", "", "The plan's own text names `src/death.cpp` and `run_score()` freely.", ""])


PLAN = build("plan", IMPACT)
SUMMARY = build("summary", IMPACT, "<!-- mw-closing-summary -->\n## Stone 7 closing summary, 2026-11-16")
check("a plan passes", section.problems(PLAN, "plan", IMPACT), [])
check("a summary under its marker and its heading passes", section.problems(SUMMARY, "summary", IMPACT), [])
check("a heading of level 3 passes", section.problems(PLAN.replace("## For the owner", "### For the owner"), "plan",
                                                     IMPACT), [])
check("a repository with no names passes three lines of its own", section.problems(build("plan", []), "plan", []), [])
check("a link's address is not read", section.problems(PLAN.replace(
    "The agent decided.", "The agent decided, see https://example.com/a_b/run_score.py for it."), "plan", IMPACT), [])
check("the words are counted", section.word_count(PLAN) > 60, True)
check("a text without the section counts no words", section.word_count("# Plan\n\nText.\n"), 0)

FILLER = " ".join(["word"] * section.WORD_CAP)
planted = [
    ("no heading", PLAN.replace("## For the owner", "## For the reader"), ['the text has no heading "For the owner"']),
    ("a paragraph above the section", PLAN.replace("## For the owner", "Workstream screens.\n\n## For the owner"),
     ["line 3 stands above the section, which opens the text under its title"]),
    ("no end line", PLAN.replace(END, "The rest follows."), [f'the section lacks its end line, "{END}"']),
    ("the end line below another section", PLAN.replace(END + "\n\n## Context", "## Context\n\n" + END),
     ['the heading "## Context" stands inside the section, above its end line']),
    ("no first part", PLAN.replace("**What changes.**", "**In short.**"), ['the section lacks the part "What changes."']),
    ("no decisions", PLAN.replace("**The decisions.**", "The decisions:"), ['the section lacks the part "The decisions."']),
    ("the decisions with no text", "\n".join(line for line in PLAN.splitlines()
                                             if not line.startswith("- The s")), ['the part "The decisions." is empty']),
    ("the parts out of order", PLAN.replace("**What changes.**", "**X.**").replace("**The decisions.**", "**What changes.**")
     .replace("**X.**", "**The decisions.**"), ["the parts stand out of order: The decisions., What changes., The impact."]),
    ("an impact line gone", PLAN.replace("- Other stones: none.\n", ""), ['the impact part lacks the line "- Other stones: ..."']),
    ("an impact line with no text", PLAN.replace("- Other stones: none.", "- Other stones: "),
     ['the impact part lacks the line "- Other stones: ..."']),
    ("over the cap", PLAN.replace("The owner decided.", "The owner decided. " + FILLER),
     [f"the section holds {section.word_count(PLAN) + section.WORD_CAP} words, over the cap of {section.WORD_CAP}"]),
    ("code formatting", PLAN.replace("one record of each run", "one `record` of each run"), ["line 5 holds code formatting"]),
    ("a file name", PLAN.replace("one record of each run", "one record of each run in death.cpp"),
     ['line 5 names "death.cpp", which reads as a file or an identifier']),
    ("an identifier", PLAN.replace("one record of each run", "one record of each run in run_score"),
     ['line 5 names "run_score", which reads as a file or an identifier']),
    ("a constant", PLAN.replace("one record of each run", "one record of each run under HOST_FADE"),
     ['line 5 names "HOST_FADE", which reads as a file or an identifier']),
    ("a call form", PLAN.replace("one record of each run", "one record of each run through recompute()"),
     ['line 5 names "recompute()", which reads as a file or an identifier']),
]
for name, text, want in planted:
    check(f"planted, {name}", section.problems(text, "plan", IMPACT), want)
check("planted, a plan read as a summary", section.problems(PLAN, "summary", IMPACT),
      ['the section lacks the part "What changed."', 'the section lacks the part "Against the plan."'])
check("planted, a summary with no word on the plan", section.problems(
    SUMMARY.replace("**Against the plan.** As planned.", "**Against the plan.**"), "summary", IMPACT),
    ['the part "Against the plan." is empty'])
two = build("plan", ["The player", "The schedule"]).replace("- The schedule: none.\n", "")
check("planted, one line of its own in a repository with no names", section.problems(two, "plan", []),
      ["the impact part holds 1 lines, not 3 to 5"])
six = build("plan", ["A", "B", "C", "D", "E", "F"])
check("planted, six lines of its own in a repository with no names", section.problems(six, "plan", []),
      ["the impact part holds 6 lines, not 3 to 5"])
check("the text below the end line is not read", "run_score()" in PLAN and section.problems(PLAN, "plan", IMPACT) == [], True)


def run(base, kind, text, data=None, root=True):
    """(the exit code, the output) of the command over text, in a temporary repository whose data file is data."""
    repo = Path(tempfile.mkdtemp(prefix="repo-", dir=base))
    (repo / ".claude").mkdir()
    if data is not None:
        (repo / ".claude" / "mw.json").write_text(json.dumps(data), encoding="utf-8")
    file = repo / "plan.md"
    if text is not None:
        file.write_text(text, encoding="utf-8", newline="\n")
    proc = subprocess.run([sys.executable, str(TOOL), kind, str(file)] + (["--root", str(repo)] if root else []),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=repo)
    return proc.returncode, proc.stdout + proc.stderr


base = tempfile.mkdtemp(prefix="mw-owner-section-")
try:
    named = {**DATA, "owner_section": {"impact": IMPACT}}
    code, out = run(base, "plan", PLAN, named)
    check("command: a plan that passes exits 0", (code, "the plan's section passes" in out, " words of 300" in out),
          (0, True, True))
    code, out = run(base, "summary", SUMMARY, named)
    check("command: a summary that passes exits 0", (code, "the summary's section passes" in out), (0, True))
    code, out = run(base, "plan", PLAN.replace("- Other stones: none.\n", ""), named)
    check("command: a missing impact line exits 1 and names it",
          (code, '[owner_section] the impact part lacks the line "- Other stones: ..."' in out, "section is refused" in out),
          (1, True, True))
    code, out = run(base, "plan", PLAN, DATA)
    check("command: a data file with no names takes five lines of the author's own", code, 0)
    code, out = run(base, "plan", build("plan", ["The player"]), {**DATA, "owner_section": {"impact": ["The player"]}})
    check("command: the names come from the data file", code, 0)
    code, out = run(base, "plan", None, named)
    check("command: a missing file exits 2", (code, "could not be read" in out), (2, True))
    code, out = run(base, "plan", PLAN, None)
    check("command: a missing data file exits 2", (code, ".claude/mw.json is missing" in out), (2, True))
    code, out = run(base, "plan", PLAN, {**DATA, "owner_section": {"impact": []}})
    check("command: a data file the loader refuses exits 2", (code, "owner_section.impact" in out), (2, True))
    code, out = run(base, "essay", PLAN, named)
    check("command: an unknown kind exits 2", code, 2)

    # PROJECT's own names: a section built from them passes, so a repository's list cannot name a line no text can hold.
    sys.path.insert(0, str(PLUGIN))
    import mw_data  # noqa: E402  (the loader sits at the plugin's root)
    try:
        project_impact = mw_data.load(PROJECT).get("owner_section", {}).get("impact", [])
    except mw_data.DataFileError:
        project_impact = None  # tools/test_hooks.py reports a data file that does not load
    if project_impact is not None:
        for kind in ("plan", "summary"):
            check(f"project: a {kind} built from {PROJECT.name}'s names passes",
                  section.problems(build(kind, project_impact), kind, project_impact), [])
finally:
    shutil.rmtree(base, ignore_errors=True)

for line in failures:
    print(f"FAIL {line}")
print(f"[test_owner_section] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
