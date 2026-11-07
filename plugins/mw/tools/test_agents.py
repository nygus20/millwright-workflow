"""Checks for the plugin's agent definition agents/step-builder.md and the skills that start it.

Usage:
    python tools/test_agents.py [PROJECT]

PROJECT is accepted as tools/run_checks.py passes it, and unused: every check
reads the plugin's own files. The checks: the definition's frontmatter fences
parse; `name`, `model` and `effort` hold their fixed values; no field Claude Code
ignores for a plugin agent, and no `tools` line, is present; the body names each
standing item of the brief; the coordinate-stone skill starts `mw:step-builder`
and passes no `model`; no skill and no agent names a repository's worktree folder,
which the data file's `worktrees` key holds. Each check runs once on the real files,
which must pass, and once on a planted copy that breaks it, which must fail, so no
check passes by default. Prints `[test_agents] N checks, M failures` and exits 1
when M is not zero.
"""

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
FOLDER_NAME = "millwright-worktrees"


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
    found += ["the coordinate-stone skill does not name mw:step-builder"] if "`mw:step-builder`" not in coordinate else []
    found += ["the coordinate-stone skill does not say the call passes no model"] if "no `model`" not in coordinate else []
    found += [f"{name} names {FOLDER_NAME}" for name, text in others.items() if FOLDER_NAME in text]
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
         for path in sorted((PLUGIN / "skills").glob("*/SKILL.md")) + sorted((PLUGIN / "agents").glob("*.md"))}
check("the real files pass", problems(agent_text, coordinate_text, texts), [])
check("the skills and the agent are read", len(texts) >= 8, True)

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
    ("no step builder", agent_text, coordinate_text.replace("`mw:step-builder`", "`general-purpose`"), {},
     "the coordinate-stone skill does not name mw:step-builder"),
    ("a model passed", agent_text, coordinate_text.replace("no `model`", "`model` set to opus"), {},
     "the coordinate-stone skill does not say the call passes no model"),
    ("a folder named", agent_text, coordinate_text, {"skills/x/SKILL.md": "c:/projects/millwright-worktrees/<slug>"},
     "skills/x/SKILL.md names millwright-worktrees"),
]
for name, agent, coordinate, others, want in planted:
    check(f"planted, {name}", problems(agent, coordinate, others), [want])
for what, text in STANDING.items():
    check(f"planted, the body without {what}", f"the body does not name {what}" in problems(
        agent_text.replace(text, ""), coordinate_text, {}), True)

for line in failures:
    print(f"FAIL {line}")
print(f"[test_agents] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
