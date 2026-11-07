"""Checks for the plugin's agent definition agents/step-builder.md and the skills that start it.

Usage:
    python tools/test_agents.py [PROJECT]

PROJECT is accepted as tools/run_checks.py passes it, and unused: every check
reads the plugin's own files. The checks: the definition's frontmatter fences
parse; `name`, `model` and `effort` hold their fixed values; no field Claude Code
ignores for a plugin agent, and no `tools` line, is present; the body names each
standing item of the brief; the coordinate-stone skill starts `mw:step-builder`,
and the sentence of that call says it passes no `model`; no skill, agent or hook
names a concrete worktree folder, which only the data file's `worktrees` key holds.
A concrete folder is a `<word>-worktrees` name, or an absolute path from a drive
letter or a home folder that runs through a folder named `worktrees`; the
placeholder `<worktrees>` and the bare key stay allowed. Each check runs once on
the real files, which must pass, and once on a planted copy that breaks it, which
must fail, so no check passes by default. Prints `[test_agents] N checks, M failures`
and exits 1 when M is not zero.
"""

import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
AGENT = PLUGIN / "agents" / "step-builder.md"
COORDINATE = PLUGIN / "skills" / "coordinate-stone" / "SKILL.md"
FIXED = {"name": "step-builder", "model": "claude-opus-5-5", "effort": "high"}
# The sub-agents and plugin reference pages, read 2026-11-07: a plugin agent ignores these fields.
IGNORED = ("hooks", "mcpServers", "permissionMode", "initialPrompt")
STANDING = {"the rule files": ".claude/rules/", "the worktree line": "`git worktree add` line",
            "the plan citation": "never a plan", "the refusal test": "fails when the refusal breaks",
            "the scratchpad name": "carries the step's number in its name", "the suite": "`run-tests`",
            "the lint": "`lint` skills", "the base": "against the base the brief names",
            "no draft": "never as a draft", "the report": "200 words"}
CALL = "`mw:step-builder`"
# No repository's folder is a constant here: the data file's worktrees key holds it (the plugin's rule 5).
NAMED_FOLDER = re.compile(r"[\w.-]*\w-worktrees\b", re.I)
ABSOLUTE_PATH = re.compile(r"(?:(?<![\w])[A-Za-z]:[\\/]|~/|/home/|/Users/)[^\s`'\"()<>,;]*")


def worktree_folders(text):
    """Each concrete worktree folder the text names, once per mention."""
    found = NAMED_FOLDER.findall(text)
    for path in ABSOLUTE_PATH.findall(text):
        if not NAMED_FOLDER.search(path) and "worktrees" in re.split(r"[\\/]", path.lower()):
            found.append(path)
    return found


def problems(agent, coordinate, others):
    """The problems of one set of texts: agent and coordinate are file texts, others maps a name to a text."""
    lines = agent.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return ["the frontmatter fences do not parse"]
    end = lines.index("---", 1)
    fields = dict(line.split(":", 1) for line in lines[1:end] if ":" in line and not line.startswith(" "))
    fields = {key.strip(): value.strip() for key, value in fields.items()}
    body = "\n".join(lines[end + 1:])
    found = [f"{key} is {fields.get(key)!r}, not {want!r}" for key, want in FIXED.items() if fields.get(key) != want]
    found += [f"the ignored field {key} is present" for key in IGNORED if key in fields]
    found += ["a tools line narrows the inherited tools"] if "tools" in fields else []
    found += [f"the body does not name {what}" for what, text in STANDING.items() if text not in body]
    calls = [s for s in re.split(r"(?<=\.)\s", coordinate) if CALL in s and "Agent tool" in s]
    if not calls:
        found.append("the coordinate-stone skill does not start mw:step-builder through the Agent tool")
    elif not any("no `model`" in sentence for sentence in calls):
        found.append("the coordinate-stone skill's call does not pass no model")
    found += [f"{name} names the worktree folder {folder}" for name, text in others.items()
              for folder in worktree_folders(text)]
    return found


checks, failures = 0, []


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


agent_text = AGENT.read_text(encoding="utf-8")
coordinate_text = COORDINATE.read_text(encoding="utf-8")
texts = {str(path.relative_to(PLUGIN)): path.read_text(encoding="utf-8")
         for path in sorted((PLUGIN / "skills").glob("*/SKILL.md")) + sorted((PLUGIN / "agents").glob("*.md"))
         + sorted((PLUGIN / "hooks").glob("*.py"))}
check("the real files pass", problems(agent_text, coordinate_text, texts), [])
check("the skills, the agent and the hooks are read", len(texts) >= 13, True)
CALL_CLAUSE = ", and passes no `model` and no `effort`"
check("the call's clause sits in the skill once", coordinate_text.count(CALL_CLAUSE), 1)
without_clause = coordinate_text.replace(CALL_CLAUSE, "")
check("without the call's clause, the skill still says no `model` elsewhere", "no `model`" in without_clause, True)

planted = [
    ("no fences", agent_text.replace("---\n", "", 1), coordinate_text, {}, "the frontmatter fences do not parse"),
    ("another model", agent_text.replace("model: claude-opus-5-5", "model: opus"), coordinate_text, {},
     "model is 'opus', not 'claude-opus-5-5'"),
    ("another effort", agent_text.replace("effort: high", "effort: low"), coordinate_text, {},
     "effort is 'low', not 'high'"),
    ("an ignored field", agent_text.replace("effort: high", "effort: high\npermissionMode: auto"), coordinate_text, {},
     "the ignored field permissionMode is present"),
    ("a tools line", agent_text.replace("effort: high", "effort: high\ntools: Read"), coordinate_text, {},
     "a tools line narrows the inherited tools"),
    ("no 200 words", agent_text.replace("200 words", "300 words"), coordinate_text, {}, "the body does not name the report"),
    ("no step builder", agent_text, coordinate_text.replace(CALL, "`general-purpose`"), {},
     "the coordinate-stone skill does not start mw:step-builder through the Agent tool"),
    ("the call's clause gone, the other no-model sentence kept", agent_text, without_clause, {},
     "the coordinate-stone skill's call does not pass no model"),
    # Joined at run time, so this file itself does not name the engine's folder.
    ("the engine's folder", agent_text, coordinate_text, {"x": "under `millwright" + "-worktrees/<slug>`"},
     "x names the worktree folder millwright" + "-worktrees"),
    ("the marketplace's folder", agent_text, coordinate_text, {"x": "`c:/projects/millwright-workflow-worktrees/1`"},
     "x names the worktree folder millwright-workflow-worktrees"),
    ("a drive-letter path", agent_text, coordinate_text, {"x": "`D:\\work\\worktrees\\3-core`"},
     "x names the worktree folder D:\\work\\worktrees\\3-core"),
    ("a home path", agent_text, coordinate_text, {"x": "`~/worktrees/3-core`"},
     "x names the worktree folder ~/worktrees/3-core"),
]
for name, agent, coordinate, others, want in planted:
    check(f"planted, {name}", problems(agent, coordinate, others), [want])
allowed = {"x": "`<worktrees>/<slug>`, the `worktrees` key, `.git/worktrees/`, `c:/projects/iteration-zero`"}
check("the placeholder, the key, git's folder and another absolute path pass",
      problems(agent_text, coordinate_text, allowed), [])
for what, text in STANDING.items():
    check(f"planted, the body without {what}", f"the body does not name {what}" in problems(
        agent_text.replace(text, ""), coordinate_text, {}), True)

for line in failures:
    print(f"FAIL {line}")
print(f"[test_agents] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
