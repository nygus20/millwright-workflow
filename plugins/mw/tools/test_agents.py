"""Checks for the plugin's agent definition agents/step-builder.md and the skills that start it.

Usage:
    python tools/test_agents.py [PROJECT]

PROJECT is accepted as tools/run_checks.py passes it, and unused: every check
reads the plugin's own files. The checks: the definition's frontmatter fences
parse; `name`, `model` and `effort` hold their fixed values; no field Claude Code
ignores for a plugin agent, and no `tools` line, is present; the body names each
standing item of the brief, and no full local suite run, because CI's run is a
step's one gate; the coordinate-stone skill starts `mw:step-builder`,
and the sentence of that call says it passes no `model`; no skill, agent or hook
names a concrete worktree folder, which only the data file's `worktrees` key holds;
the start-stone, close-stone and coordinate-stone skills hold the clauses each
stone needs (the plan's hand-overs, the "Builds on" reading, the stone registry and
the row written once at the close, where a gotcha lands, the summary's "For the
next stone" section, the worktree under `<worktrees>`, a consumer's engine asks and
its pull requests into the engine); the close-stone skill names no gotcha history
and no findings cap, the coordinate-stone skill sets no row to "open", and no
findings skill asks for a docs-map row; no skill names the retired "Common Gotchas"; and
each citation of a close-stone item from another plugin file names, in its sentence,
a topic the cited item holds, so a renumbering that leaves a citation behind fails.
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
            "the call citation": "`pull request <n>, call <m>`",
            "the plan file": "never a file under `documents/plans/`",
            "the body's three items": "what the step does, the record rows it implements, and each reversible "
                                      "choice the plan did not pre-rule",
            "no test count": "no test count", "the refusal test": "fails when the refusal breaks",
            "the scratchpad name": "carries the step's number in its name", "the quick check": "`quick_check.bat`",
            "CI's run": "CI's run on the pull request's head is the step's one full gate",
            "the background wait": "`gh pr checks <pr> --watch", "the base": "against the base the brief names",
            "no draft": "never as a draft", "the report": "200 words"}
# CI's run is a step's one full gate (the engine's issue 942), so the body names
# no full local suite run: the coordinator's brief names one for a step that changes a file CI does not build.
UNFILTERED = {"an unfiltered run": "unfiltered", "the suite wrapper": "run_tests.bat",
              "the lint skill": "`lint` skill", "the suite before the push": "suite and lint"}
CALL = "`mw:step-builder`"
# The clauses each stone skill holds: the plan's hand-overs (engine issue 831), the stone registry (engine
# issue 877), where a gotcha lands since the engine's AGENTS.md retired its gotcha section, the worktree, and the
# lighter start and close of the engine's issue 962: the planning reads the "Builds on" summaries, the summary
# ends with "For the next stone", and the close alone writes the row and the registry entry. The engine's issue
# 1012 adds a consumer's engine asks (item 4) and its pull requests into the engine's `main` (item 3).
CLAUSES = {
    "start-stone": {"the hand-overs section": "a \"Hand-overs\" section",
                    "the check against open stones": "`gh pr list --base main --state open",
                    "the \"Builds on\" reading": "the stones on the entry's \"Builds on\" line",
                    "the worktree": "git worktree add <worktrees>/<slug>",
                    "the engine asks": "an \"Engine asks\" section",
                    "the branch into the engine": "from a branch `game/<slug>`",
                    "the issue-only rest": "Everything else in the engine stays issue-only"},
    "close-stone": {"the registry": "holds a `stone_registry` key", "the rewrite": "the key's `rewrite` command",
                    "the row written once": "writes the stone's row once",
                    "where a gotcha lands": "where AGENTS.md \"Maintenance Rules\" says a gotcha lands",
                    "the summary's last section": "the fixed section \"For the next stone\"",
                    "the worktree removal": "git worktree remove <worktrees>/<slug>"},
    "coordinate-stone": {"no row and no registry entry": "writes no workstream row and no registry entry",
                         "the consumer's step in the engine": "a consumer stone's step in the engine's repository"},
}
# The texts a skill must not hold: no close writes the gotcha history (the engine's issue 962, ask 4), no first
# step marks a stone open in a record, no findings doc gets a docs-map row (the engine's issue 995), and the close
# sets the findings folder against no cap, which the owner dropped on 2026-11-12.
FORBIDDEN = {"close-stone": {"the gotcha history": "gotcha-history.md",
                             "the docs-map check": "lists the stone's findings doc",
                             "the findings cap": "those of `documents/findings/`"},
             "coordinate-stone": {"the row set to open": "to \"open\""},
             "prior-art": {"the docs-map row": "lists that doc in `documents/README.md`"},
             "port-triage": {"the docs-map row": "listed in `documents/README.md`"}}
RETIRED = "Common Gotchas"
# Each citation of a close-stone item from another plugin file, keyed by a text its sentence holds, with a text the
# cited item must hold. Pull request 22 dropped item 6 and left three citations one number high, which the review
# of pull request 23 found.
CLOSE = PLUGIN / "skills" / "close-stone" / "SKILL.md"
CLOSE_CITATION = re.compile(r"`mw:close-stone` skill, item (\d+)")
CLOSE_TOPICS = {"the full run": ("runs it once more", "`run_tests.bat --long`"),
                "the row written once": ("the registry entry once", "writes the stone's row once"),
                "the Records bullets": ("Records bullet", "The Records bullets"),
                "the fix check": ("fix check", "`gh pr ready <stone-pr>`")}
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
    found += [f"the body names {what}" for what, text in UNFILTERED.items() if text in body]
    calls = [s for s in re.split(r"(?<=\.)\s", coordinate) if CALL in s and "Agent tool" in s]
    if not calls:
        found.append("the coordinate-stone skill does not start mw:step-builder through the Agent tool")
    elif not any("no `model`" in sentence for sentence in calls):
        found.append("the coordinate-stone skill's call does not pass no model")
    found += [f"{name} names the worktree folder {folder}" for name, text in others.items()
              for folder in worktree_folders(text)]
    return found


def clause_problems(skills):
    """The clauses missing from the stone skills, the forbidden texts they hold, and each skill that names the
    retired section."""
    found = [f"{skill} does not name {what}" for skill, clauses in CLAUSES.items()
             for what, text in clauses.items() if text not in skills.get(skill, "")]
    found += [f"{skill} names {what}" for skill, texts in FORBIDDEN.items()
              for what, text in texts.items() if text in skills.get(skill, "")]
    return found + [f"{skill} names {RETIRED}" for skill, text in skills.items() if RETIRED in text]


def citation_problems(close, texts):
    """Each citation of a close-stone item whose sentence names no one known topic, or whose item does not hold
    the topic's text; close is the skill's text, texts maps a name to a citing text."""
    items = {}
    for line in close.splitlines():
        numbered = re.match(r"(\d+)\. ", line)
        if numbered:
            items.setdefault(int(numbered.group(1)), line)
    found = []
    for name, text in texts.items():
        for cited in CLOSE_CITATION.finditer(text):
            sentence, number = re.split(r"(?<=[.;])\s", text[:cited.start()])[-1], int(cited.group(1))
            topics = [what for what, (said, _) in CLOSE_TOPICS.items() if said in sentence]
            if len(topics) != 1:
                found.append(f"{name} cites close-stone item {number} for no one known topic")
            elif CLOSE_TOPICS[topics[0]][1] not in items.get(number, ""):
                found.append(f"{name} cites close-stone item {number} for {topics[0]}, which that item does not hold")
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
for what, text in UNFILTERED.items():
    check(f"planted, the body with {what}",
          problems(agent_text + f"\nRun the {text} before the push.\n", coordinate_text, {}), [f"the body names {what}"])

skills = {path.parent.name: path.read_text(encoding="utf-8") for path in sorted((PLUGIN / "skills").glob("*/SKILL.md"))}
check("the stone skills hold their clauses", clause_problems(skills), [])
for skill, clauses in CLAUSES.items():
    for what, text in clauses.items():
        check(f"planted, {skill} without {what}", clause_problems({**skills, skill: skills[skill].replace(text, "")}),
              [f"{skill} does not name {what}"])
for skill, texts in FORBIDDEN.items():
    for what, text in texts.items():
        check(f"planted, {skill} with {what}", clause_problems({**skills, skill: skills[skill] + f"\nSee {text}.\n"}),
              [f"{skill} names {what}"])
check("planted, the retired section", clause_problems({**skills, "x": f"AGENTS.md \"{RETIRED}\""}),
      [f"x names {RETIRED}"])

close_text = CLOSE.read_text(encoding="utf-8")
# This file is left out, because its planted texts below cite items on purpose.
citing = {path.relative_to(PLUGIN).as_posix(): path.read_text(encoding="utf-8")
          for path in [PLUGIN / "README.md"] + sorted((PLUGIN / "skills").glob("*/SKILL.md"))
          + sorted((PLUGIN / "agents").glob("*.md")) + sorted((PLUGIN / "hooks").glob("*.py"))
          + sorted((PLUGIN / "output-styles").glob("*.md")) + sorted((PLUGIN / "tools").glob("*.py"))
          if path not in (CLOSE, Path(__file__).resolve())}
check("each close-stone citation names its item", citation_problems(close_text, citing), [])
check("the close-stone citations are read",
      sum(len(CLOSE_CITATION.findall(text)) for text in citing.values()) >= 5, True)
CITE = "(`mw:close-stone` skill, item "
for name, text, want in [
        ("the fix check one item high", f"the next round is the fix check over them {CITE}10).",
         "x cites close-stone item 10 for the fix check, which that item does not hold"),
        ("the Records bullets at the fix check's item", f"each Records bullet is fixed {CITE}9).",
         "x cites close-stone item 9 for the Records bullets, which that item does not hold"),
        ("no known topic", f"Read the memory index {CITE}6).", "x cites close-stone item 6 for no one known topic")]:
    check(f"planted, {name}", citation_problems(close_text, {"x": text}), [want])
dropped = re.sub(r"^9\. ", "10. ", close_text, flags=re.M)
check("planted, the close's fix check renumbered", citation_problems(dropped, citing),
      ["skills/adversarial-review/SKILL.md cites close-stone item 9 for the fix check, which that item does not hold"] * 2)

for line in failures:
    print(f"FAIL {line}")
print(f"[test_agents] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
