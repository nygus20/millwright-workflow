"""Checks for the pure functions of tools/review_pr.py: no gh, no claude, no network.

Usage:
    python tools/test_review_pr.py [PROJECT]

PROJECT is the repository the checks run against: the folder given, else
CLAUDE_PROJECT_DIR, else the current folder. tools/run_checks.py passes it.
The tool's behaviour is checked against the fixture tools/fixture/.claude/mw.json,
the engine's lists at v0.1.0. PROJECT's own data file must load, its costly
paths must compile, its grants must join the base list, and the prompt must name
it; when PROJECT holds documents/process/model-choice.md, its costly-path table
must match its data file row for row, and otherwise that check prints a skipped
line.

Each check records a failure instead of raising, then the script prints one line,
`[test_review_pr] N checks, M failures`, and exits 1 when M is not zero.
run_tests.bat runs it. The context-path checks build a prompt over a
temporary worktree, so they touch no checkout and call no gh. The tool's lists
come from the fixture's .claude/mw.json; the data-file checks swap in a
temporary repository's file and put the fixture back.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("review_pr", Path(__file__).resolve().parent / "review_pr.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
PLUGIN = Path(__file__).resolve().parent.parent
ENGINE_DATA = rp.mw_data.load(PLUGIN / "tools" / "fixture")
rp.DATA = ENGINE_DATA
PROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
skipped_checks = []

checks = 0
failures = []


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# vendored_summary: upstream files under third_party/<library>/ become counts; glue directly
# in third_party/ is not counted, because it is diffed like any other file.
status = "A\tthird_party/SDL3/src/a.c\nA\tthird_party/SDL3/include/b.h\nM\tthird_party/sokol/sokol_gfx.h\nD\tthird_party/sokol/sokol_glue.h\nM\tthird_party/CMakeLists.txt\nM\tsrc/x.cpp\nR100\tthird_party/stb/old.h\tthird_party/stb/new.h\n"
summary = rp.vendored_summary(status)
check("vendored SDL3 line", "- third_party/SDL3/: 2 added, 0 changed, 0 removed, 0 renamed" in summary, True)
check("vendored sokol line", "- third_party/sokol/: 0 added, 1 changed, 1 removed, 0 renamed" in summary, True)
check("vendored rename line", "- third_party/stb/: 0 added, 0 changed, 0 removed, 1 renamed" in summary, True)
check("vendored glue not counted", "CMakeLists" in summary, False)
check("vendored change named", "  - M third_party/sokol/sokol_gfx.h" in summary, True)
check("vendored removal named", "  - D third_party/sokol/sokol_glue.h" in summary, True)
check("vendored rename named", "  - R third_party/stb/new.h" in summary, True)
check("vendored addition not named", "third_party/SDL3/src/a.c" in summary, False)
many = "".join(f"M\tthird_party/big/f{i}.c\n" for i in range(rp.VENDORED_NAMES_SHOWN + 3))
check("vendored names capped", "  - and 3 more changed, removed or renamed files" in rp.vendored_summary(many), True)
check("vendored none", rp.vendored_summary("M\tsrc/x.cpp\nM\tthird_party/CMakeLists.txt\n"), "")

HEAD = "b" * 40
OLD = "a" * 40
STEP = ("step", "claude-opus-5-5", "high")

# blocking_count: only an exact "none" is clean; a malformed review blocks.
check("blocking none", rp.blocking_count("## Blocking\n- none\n\n## Unresearched choices\n- x"), 0)
check("blocking none with period", rp.blocking_count("## Blocking\n- None.\n"), 0)
check("blocking two bullets", rp.blocking_count("## Blocking\n- a\n- b\n## Unresearched choices\n- none"), 2)
check("blocking heading missing", rp.blocking_count("no headings at all"), 1)
check("blocking section empty", rp.blocking_count("## Blocking\n\n## Unresearched choices\n- none"), 1)

# review_kind: main is a stone review, a costly path is a costly review, anything else is a step review.
check("kind stone", rp.review_kind("main", ["tools/review_pr.py"]), "stone")
check("kind docs are a step", rp.review_kind("stone/x", ["AGENTS.md", "documents/plans/a.md"]), "step")
check("kind core is costly", rp.review_kind("stone/x", ["AGENTS.md", "src/core/arena.cpp"]), "costly")
check("kind sim is costly", rp.review_kind("stone/x", ["src/sim/tick.cpp"]), "costly")
check("kind public header is costly", rp.review_kind("stone/x", ["src/render/render.h"]), "costly")
check("kind private header is a step", rp.review_kind("stone/x", ["src/render/batch.h"]), "step")
check("kind render source is a step", rp.review_kind("stone/x", ["src/render/render.cpp"]), "step")
check("kind guard stack is costly", rp.review_kind("stone/x", [".github/workflows/tests.yml"]), "costly")
check("kind presets are costly", rp.review_kind("stone/x", ["CMakePresets.json"]), "costly")
for path in ["src/save/ladder.cpp", "src/content/content.cpp", "src/game/stats.cpp", "src/game/host/host.cpp",
             "tests/invariants/invariants.py", "cmake/warnings.cmake",
             ".claude/hooks/deny_guard_config.py", "git-hooks/pre-commit", ".clang-tidy", ".clang-format", ".claude/settings.json"]:
    check(f"kind {path} is costly", rp.review_kind("stone/x", [path]), "costly")
check("a costly prefix mid-path is a step", rp.review_kind("stone/x", ["third_party/x/cmake/y.cmake"]), "step")
check("the untracked local settings stay costly too", rp.review_kind("stone/x", [".claude/settings.local.json"]), "costly")
check("kind the reviewer is costly", rp.review_kind("stone/x", ["tools/review_pr.py"]), "costly")
check("kind other tools are a step", rp.review_kind("stone/x", ["tools/test_review_pr.py"]), "step")
check("kind no files", rp.review_kind("stone/x", []), "step")
check("kind the build's other CMake files stay costly", rp.review_kind("stone/x", ["cmake/module.cmake"]), "costly")

# PROJECT's data file: it loads, its patterns compile, its grants join the base list, and the prompt names it.
try:
    PROJECT_DATA = rp.mw_data.load(PROJECT)
    project_error = ""
except rp.mw_data.DataFileError as error:
    PROJECT_DATA, project_error = None, str(error)
check(f"project: {PROJECT}'s data file loads", project_error, "")
if PROJECT_DATA is not None:
    rp.DATA = PROJECT_DATA
    for row in PROJECT_DATA["review"]["costly_paths"]:
        try:
            re.compile(row["pattern"])
            compiled = True
        except re.error:
            compiled = False
        check(f"project: the costly path {row['pattern']} compiles", compiled, True)
    check("project: each profile names a model and an effort",
          all(len(PROJECT_DATA["review"]["profiles"].get(kind, [])) == 2 for kind in ("stone", "costly", "step")), True)
    project_grants = rp.allowed_tools().split(",")
    check("project: the grants start with the base list", project_grants[:len(rp.BASE_TOOLS)], rp.BASE_TOOLS)
    check("project: the grants hold each addition",
          all(tool in project_grants for tool in PROJECT_DATA["review"]["allowed_tools"]), True)
    check("project: the prompt names the repository and fills every slot",
          (f"in the {PROJECT_DATA['repository']} repository" in rp.instructions(None),
           "<repository>" in rp.instructions(None), "<path sources>" in rp.instructions(None)), (True, False, False))

    # PROJECT's costly paths against documents/process/model-choice.md's costly-path table, which repeats them row for
    # row: each path the table names is costly, and each alternative of each pattern is in the table, spelled as the
    # table spells it (escapes and $ dropped, [^/]* as *; the public-header pattern by the one hand-written pair below).
    choice_file = PROJECT / "documents" / "process" / "model-choice.md"
    if choice_file.is_file():
        choice = choice_file.read_text(encoding="utf-8")
        table = [path for line in choice.split("## Costly paths", 1)[-1].split("\n## ", 1)[0].splitlines()
                 if line.startswith("| `") for path in re.findall(r"`([^`]+)`", line.split(" | ")[0])]
        check("the costly-path table names paths", len(table) > 0, True)
        for path in table:
            check(f"the table's {path} is costly",
                  rp.review_kind("stone/x", [path.replace("<module>", "render").replace("*", "")]), "costly")
        PUBLIC_HEADER = (r"src/([^/]+)/\1\.h$", "src/<module>/<module>.h")
        for row in PROJECT_DATA["review"]["costly_paths"]:
            for part in row["pattern"].split("|"):
                spelled = PUBLIC_HEADER[1] if part == PUBLIC_HEADER[0] else \
                    part.replace("[^/]*", "*").replace("\\.", ".").rstrip("$")
                check(f"the data file's {spelled} is in the table", spelled in table, True)
    else:
        skipped_checks.append(f"the costly-path table checks: {PROJECT} holds no documents/process/model-choice.md")
    rp.DATA = ENGINE_DATA

# review_profile: Fable 5.1 for a costly step and every stone round, Opus 5.5 otherwise, never Sonnet;
# full model ids, because the alias `opus` reached an older Opus (ruled 2026-10-12).
check("costly round 1 on fable", rp.review_profile("costly", 1), ("claude-fable-5-1", "high"))
check("costly round 2 on opus", rp.review_profile("costly", 2), ("claude-opus-5-5", "high"))
check("stone round 2 stays on fable", rp.review_profile("stone", 2), ("claude-fable-5-1", "high"))
check("step on opus", rp.review_profile("step", 1), ("claude-opus-5-5", "high"))
check("no sonnet anywhere", any("sonnet" in model for model, _ in ENGINE_DATA["review"]["profiles"].values()), False)
check("every profile names a full model id",
      all(model.startswith("claude-") for model, _ in ENGINE_DATA["review"]["profiles"].values()), True)

# The grants: the tool's base list, then the data file's additions. The engine's file adds its build and its suite.
grants = rp.allowed_tools().split(",")
check("grants: the base list comes first", grants[:len(rp.BASE_TOOLS)], rp.BASE_TOOLS)
check("grants: the engine's additions follow", grants[len(rp.BASE_TOOLS):], ENGINE_DATA["review"]["allowed_tools"])
check("grants: the engine's suite is granted", "Bash(./run_tests.bat:*)" in grants, True)
check("grants: the base list holds no engine command", any("run_tests" in g or "cmake" in g for g in rp.BASE_TOOLS), False)

# The reviewer's command: the engine's copy runs it as before; the plugin's copy loads itself and installs first.
check("plugin: the flag is on in the plugin's copy", rp.FROM_PLUGIN, True)
saved_sync = os.environ.pop("CLAUDE_CODE_SYNC_PLUGIN_INSTALL", None)
try:
    rp.FROM_PLUGIN = False
    engine_cmd, engine_env = rp.reviewer_call(STEP, 60)
    rp.FROM_PLUGIN = True
    plugin_cmd, plugin_env = rp.reviewer_call(STEP, 60)
finally:
    rp.FROM_PLUGIN = True
    if saved_sync is not None:
        os.environ["CLAUDE_CODE_SYNC_PLUGIN_INSTALL"] = saved_sync
check("engine: the reviewer's command is unchanged", engine_cmd, [
    "claude", "-p", "--output-format", "text", "--max-turns", "60", "--model", "claude-opus-5-5", "--effort", "high",
    "--allowedTools", rp.allowed_tools(), "--disallowedTools", "PowerShell"])
check("engine: no plugin install wait", "CLAUDE_CODE_SYNC_PLUGIN_INSTALL" in engine_env, False)
check("plugin: the reviewer loads the plugin's own root", plugin_cmd, engine_cmd + ["--plugin-dir", str(rp.HOME)])
check("plugin: the reviewer waits for the install", plugin_env.get("CLAUDE_CODE_SYNC_PLUGIN_INSTALL"), "1")
check("the loader sits at the plugin's root", rp.loader_path(), PLUGIN / "mw_data.py")
check("plugin: the reviewer's plugin folder is the plugin's root", rp.HOME, PLUGIN)
# review_in runs the command reviewer_call gives: a stubbed claude records it and fails, so nothing is posted.
ran = []
saved_run = rp.subprocess.run
rp.subprocess.run = lambda cmd, **kw: ran.append((cmd, kw["env"])) or rp.subprocess.CompletedProcess(cmd, 1, "", "")
rp.FROM_PLUGIN = True
try:
    with contextlib.redirect_stderr(io.StringIO()):
        stubbed = rp.review_in(Path("."), "prompt", {}, None, (1, "full", "", STEP, 60, "c", None, None, None))
finally:
    rp.subprocess.run, rp.FROM_PLUGIN = saved_run, True
check("review_in: a failed reviewer exits 2", stubbed, 2)
check("review_in: the plugin's copy passes --plugin-dir and the wait",
      (ran[0][0][-2:], ran[0][1].get("CLAUDE_CODE_SYNC_PLUGIN_INSTALL")), (["--plugin-dir", str(rp.HOME)], "1"))

# skips_review: a step outside the costly paths merges on green CI; --force-review asks for a round.
check("skip: a step without the flag", rp.skips_review("step", False), True)
check("skip: a step with the flag is reviewed", rp.skips_review("step", True), False)
check("skip: a costly step is reviewed", rp.skips_review("costly", False), False)
check("skip: a stone is reviewed", rp.skips_review("stone", False), False)
check("--force-review parses", rp.arg_parser().parse_args(["83", "--force-review"]).force_review, True)
check("no --force-review by default", rp.arg_parser().parse_args(["83"]).force_review, False)

# one_round_note: a step gets one round; only the owner grants another; the stone review keeps its rounds.
check("one round: a first round runs", rp.one_round_note("costly", None, None), None)
one_round = rp.one_round_note("costly", (OLD, 1, 1, None), None)
check("one round: a step's second round refuses", one_round is not None and "--extra-round owner" in one_round, True)
check("one round: a clean round refuses a second too", rp.one_round_note("costly", (OLD, 1, 0, None), None) is not None, True)
check("one round: a forced step's second round refuses", rp.one_round_note("step", (OLD, 1, 1, None), None) is not None, True)
check("one round: the author's grant does not reach a step", rp.one_round_note("costly", (OLD, 1, 1, None), "agent") is not None, True)
check("one round: the owner's grant runs", rp.one_round_note("costly", (OLD, 1, 1, None), "owner"), None)
check("one round: the stone review keeps its fix round", rp.one_round_note("stone", (OLD, 1, 1, None), None), None)

# fetch_ref retries a failed fetch once, after a pause, and returns the second result.
fetches = []
saved_fetch = (rp.run, rp.time.sleep)
rp.run = lambda cmd, **kw: fetches.append(cmd) or rp.subprocess.CompletedProcess(cmd, 1 if len(fetches) == 1 else 0, "", "race")
rp.time.sleep = lambda seconds: fetches.append(seconds)
try:
    retried = rp.fetch_ref("stone/x")
finally:
    rp.run, rp.time.sleep = saved_fetch
check("fetch: a failure retries once after the pause", (retried.returncode, len(fetches), fetches[1]), (0, 3, rp.FETCH_RETRY_SECONDS))
check("fetch: the retry fetches the same ref", fetches[0] == fetches[2] == ["git", "fetch", "origin", "stone/x"], True)

# parse_marks and comment_body round-trip; a comment from before the marks is round 1.
pr = {"headRefOid": HEAD, "headRefName": "step/x/1-y", "baseRefName": "stone/x"}
review = "## Blocking\n- p:1 bad.\n\n## Unresearched choices\n- none\n\n## Verified\n- ok"
body = rp.comment_body(review, 1, pr, 2, "fix check", "", STEP, "aaaaaaa..bbbbbbb", 1)
check("marks round-trip", rp.parse_marks(body), (HEAD, 2, 3, None))
check("marks absent", rp.parse_marks("<!-- mw-review -->\n## Adversarial review (fresh session)\n\n## Blocking\n- none"), None)
check("marks without the exit mark", rp.parse_marks(f"<!-- mw-review -->\n<!-- mw-review-head: {OLD} -->\n<!-- mw-review-round: 1 -->"), (OLD, 1, None, None))
check("spent line after a blocking round", "Fix round spent" in body, True)
check("no spent line at round 1", "Fix round spent" in rp.comment_body("## Blocking\n- a", 1, pr, 1, "full", "", STEP, "c"), False)
check("no spent line after a clean round", "Fix round spent" in rp.comment_body("## Blocking\n- a", 1, pr, 2, "fix check", "", STEP, "c", 0), False)
check("footer names the kind", "A step review: model claude-opus-5-5" in body, True)

# earlier_findings keeps the three sections and drops the markers and the footer.
findings = rp.earlier_findings(body)
check("findings start", findings.startswith("## Blocking"), True)
check("findings drop markers", "<!--" in findings, False)
check("findings drop footer", "blocking finding(s)" in findings, False)
check("findings keep a bullet", "- p:1 bad." in findings, True)
noted = rp.comment_body("## Blocking\n- a\n```\n__init__ runs twice\n```\n\n## Verified\n- x", 1, pr, 2, "full", "a full review, forced with --full", STEP, "c")
check("note line written", "_Note: a full review, forced with --full._" in noted, True)
check("findings drop the note", "_Note:" in rp.earlier_findings(noted), False)
check("findings drop the spent line", "Fix round spent" in rp.earlier_findings(body), False)
check("findings keep the reviewer's underscore lines", "__init__ runs twice" in rp.earlier_findings(noted), True)
check("findings without a Blocking heading keep the text", rp.earlier_findings("plain text\n_3 blocking finding(s). x_"), "plain text")

# plan_round: first review, fix check, forced full, rebased, nothing new, the limit after an exit 3.
check("first review", rp.plan_round(None, HEAD, False, False, None), (1, "full", ""))
check("fix check", rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None), (2, "fix check", ""))
check("forced full", rp.plan_round((OLD, 1, 1, None), HEAD, True, True, None)[:2], (2, "full"))
check("rebased goes full", rp.plan_round((OLD, 1, 1, None), HEAD, False, False, None)[:2], (2, "full"))
check("unrecorded commit goes full", rp.plan_round((None, 1, None, None), HEAD, False, False, None)[:2], (2, "full"))
M1, M2 = "c" * 40, "d" * 40
check("an unclean merge of the base goes full", rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None, ([], [], M1))[:2], (2, "full"))
check("the full round names the unclean merge", "cccccc" in rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None, ([], [], M1))[2], True)
one_range = ([(OLD, HEAD)], [], None)
check("a walk of plain commits is a fix check", rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None, one_range), (2, "fix check", ""))
skipped = rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None, ([(OLD, M1), (M2, HEAD)], [M2], None))
check("a clean merge between fixes is a fix check", skipped[:2], (2, "fix check"))
check("the note counts the clean merges left out", "1 clean merge(s) of the base left out (ddddddd)" in skipped[2], True)
check("only clean merges after a clean round review nothing", rp.plan_round((OLD, 1, 0, None), HEAD, False, True, None, ([], [M1], None))[:2], (2, "nothing"))
check("only clean merges after a blocking round refuse", rp.plan_round((OLD, 1, 1, None), HEAD, False, True, None, ([], [M1], None))[:2], (2, None))
check("--full still reviews after only clean merges", rp.plan_round((OLD, 1, 0, None), HEAD, True, True, None, ([], [M1], None))[:2], (2, "full"))
check("the limit holds against only clean merges", rp.plan_round((OLD, 2, 3, None), HEAD, False, True, None, ([], [M1], None))[:2], (3, None))

# stone_branch: a stacked step's base names its stone, so its reviewer reads the stone's plan.
check("a stone base is its own stone", rp.stone_branch("stone/stacked-steps"), "stone/stacked-steps")
check("a step base maps to its stone", rp.stone_branch("step/stacked-steps/2-tool"), "stone/stacked-steps")
check("main has no stone", rp.stone_branch("main"), None)
check("a bare step prefix has no stone", rp.stone_branch("step/x"), None)
check("no new commits refuses", rp.plan_round((HEAD, 1, 1, None), HEAD, False, True, None)[1], None)
check("after exit 3 refuses", rp.plan_round((OLD, 2, 3, None), HEAD, False, True, None)[:2], (3, None))
refusal = rp.plan_round((OLD, 2, 3, None), HEAD, False, True, None)[2]
check("the refusal names both grants", "--extra-round agent" in refusal and "--extra-round owner" in refusal, True)
check("the limit holds against --full", rp.plan_round((OLD, 2, 3, None), HEAD, True, True, None)[:2], (3, None))
check("after exit 3 with the owner's round", rp.plan_round((OLD, 2, 3, None), HEAD, False, True, "owner")[:2], (3, "fix check"))
check("after a clean round a new one runs", rp.plan_round((OLD, 2, 0, None), HEAD, False, True, None)[:2], (3, "fix check"))

# The extra round: the author's runs only while none has run on the pull request, the owner's has no
# limit, and the first one's mark is carried in the one comment.
AGENT3, OWNER3 = ("agent", 3), ("owner", 3)
check("the author's round runs once", rp.plan_round((OLD, 2, 3, None), HEAD, False, True, "agent")[:2], (3, "fix check"))
spent = rp.plan_round((OLD, 4, 3, AGENT3), HEAD, False, True, "agent")
check("a second author's round refuses", spent[:2], (5, None))
check("the refusal names the spent round and the owner", "the author granted the extra round 3" in spent[2] and "--extra-round owner" in spent[2], True)
after_owner = rp.plan_round((OLD, 4, 3, OWNER3), HEAD, False, True, "agent")
check("the author's round refuses after the owner's", after_owner[:2], (5, None))
check("that refusal names the owner's round", "the owner granted the extra round 3" in after_owner[2], True)
check("the owner's round runs after the author's", rp.plan_round((OLD, 4, 3, AGENT3), HEAD, False, True, "owner")[:2], (5, "fix check"))
check("--full does not pass a spent extra round", rp.plan_round((OLD, 4, 3, AGENT3), HEAD, True, True, "agent")[:2], (5, None))
no_flag = rp.plan_round((OLD, 4, 3, AGENT3), HEAD, False, True, None)
check("after a spent extra round the refusal names only the owner", "--extra-round owner" in no_flag[2] and "--extra-round agent" not in no_flag[2], True)
check("no extra mark on a first review", rp.carried_extra(None, 1, "agent"), None)
check("the author's grant marks this round", rp.carried_extra((OLD, 2, 3, None), 3, "agent"), ("agent", 3))
check("the owner's grant marks this round", rp.carried_extra((OLD, 2, 3, None), 3, "owner"), ("owner", 3))
check("the flag without an exit 3 writes no mark", rp.carried_extra((OLD, 1, 1, None), 2, "agent"), None)
check("the mark carries forward without the flag", rp.carried_extra((OLD, 3, 0, AGENT3), 4, None), AGENT3)
check("the first mark carries past a later owner's round", rp.carried_extra((OLD, 4, 3, AGENT3), 5, "owner"), AGENT3)
granted = rp.comment_body(review, 1, pr, 3, "fix check", "", STEP, "c", 3, AGENT3)
check("the agent mark round-trips", rp.parse_marks(granted), (HEAD, 3, 3, AGENT3))
owned = rp.comment_body(review, 1, pr, 3, "fix check", "", STEP, "c", 3, OWNER3)
check("the owner mark round-trips", rp.parse_marks(owned), (HEAD, 3, 3, OWNER3))
clean = rp.comment_body("## Blocking\n- none", 0, pr, 4, "fix check", "", STEP, "c", 3, AGENT3)
check("the mark carries into a clean round", rp.parse_marks(clean)[3], AGENT3)
check("spent line before any extra round", "the author rules once" in body, True)
check("spent line after the author's round", "_Fix round spent: the owner decides._" in granted and "author rules" not in granted, True)
check("spent line after the owner's round", "author rules" in owned, False)
both = rp.earlier_findings(granted) + rp.earlier_findings(body)
check("findings drop the extra mark and both spent lines", "mw-review-extra" in both or "Fix round spent" in both, False)

# The flag: bare means the owner's grant; the author's grant needs --post.
parse = rp.arg_parser().parse_args
check("bare --extra-round is the owner's", parse(["83", "--extra-round"]).extra_round, "owner")
check("--extra-round agent", parse(["83", "--extra-round", "agent"]).extra_round, "agent")
check("no flag", parse(["83"]).extra_round, None)
check("the author's round without --post refuses", rp.flag_error(parse(["83", "--extra-round", "agent"])) is not None, True)
check("the author's round with --post runs", rp.flag_error(parse(["83", "--post", "--extra-round", "agent"])), None)
check("the owner's round without --post runs", rp.flag_error(parse(["83", "--extra-round"])), None)
# main refuses an unposted author's round before its first gh or git call.
calls = []
saved = (sys.argv, rp.gh_json, rp.run)
sys.argv = ["review_pr.py", "83", "--extra-round", "agent"]
rp.gh_json = lambda *a, **k: calls.append("gh")
rp.run = lambda *a, **k: calls.append("run")
try:
    with contextlib.redirect_stderr(io.StringIO()):
        refused_code = rp.main()
finally:
    sys.argv, rp.gh_json, rp.run = saved  # a raise in main must not leave the stubs or the argv in place
check("main exits 2 on an unposted author's round", refused_code, 2)
check("main calls neither gh nor git first", calls, [])

# exit_code: clean is 0; blocking gets one fix round; blocking after a blocking round is 3.
check("exit clean", rp.exit_code(0, 1), 0)
check("exit round 1", rp.exit_code(2, None), 1)
check("exit after a clean round", rp.exit_code(1, 0), 1)
check("exit after a blocking round", rp.exit_code(1, 1), 3)
check("exit after an extra round", rp.exit_code(1, 3), 3)

# Both prompts carry the blocking rule; the budget line and the heading check.
check("fix check has the blocking rule", rp.BLOCKING_RULE in rp.FIX_CHECK_INSTRUCTIONS, True)
check("full review has the blocking rule", rp.BLOCKING_RULE in rp.INSTRUCTIONS, True)
# Stone 1 step 8: the invariant test checks emoji and the instruction files' paths, so the prompt leaves them.
check("the prompt leaves emoji to the invariant test", "an emoji" in rp.INSTRUCTIONS, False)
check("the prompt names the files whose paths the test checks",
      "other than CLAUDE.md, AGENTS.md, documents/README.md and the skills." in rp.instructions(None), True)
check("the prompt names the repository", "in the Millwright Engine repository" in rp.instructions(None)
      and "in the Millwright Engine repository" in rp.instructions((1, "a", "- x", "a..b")), True)
check("the full review measures a ported part against its triage row", "against that part's row in the record, never against the reference game" in rp.INSTRUCTIONS, True)
check("a ported part with no triage row is an unresearched choice", "has no row in the record goes under Unresearched choices" in rp.INSTRUCTIONS and "ported part with no row that check 8 finds" in rp.OUTPUT_FORMAT, True)
check("budget has a floor", "turn 1," in rp.turn_budget(3), True)
check("budget names the turns", "You have 30 turns" in rp.turn_budget(30) and "turn 25" in rp.turn_budget(30), True)
check("wait: a reply that waits on its build", rp.announces_wait(
    "I started the suite as a background task.\n\nI will report once it finishes."), True)
check("wait: a review that mentions the background in a finding", rp.announces_wait(
    "## Blocking\n- a.py:1 runs in the background\n\n## Unresearched choices\n- none\n\n## Verified\n- ran the suite"), False)
check("wait: an empty reply", rp.announces_wait(""), False)
check("wait: a run named in several words", rp.announces_wait("I will post the review when the test run finishes."), True)
check("wait: waiting for the run", rp.announces_wait("Let me wait for the build to finish."), True)

check("extra note: none without the flag", rp.extra_round_note((OLD, 1, 1, None), None), None)
check("extra note: none after an exit 3", rp.extra_round_note((OLD, 2, 3, None), "agent"), None)
check("extra note: the flag after an exit 1 says it is unused",
      (rp.extra_round_note((OLD, 1, 1, None), "agent") or "").startswith("--extra-round agent has no effect"), True)
check("extra note: the flag on a first review says it is unused", rp.extra_round_note(None, "owner") is not None, True)

THIRD = "diff --git a/src/x.cpp b/src/x.cpp\n"
check("join: no vendored file, the diffs in order", rp.join_ranges([("one\n", ""), ("two\n", "")]), "one\ntwo\n")
joined = rp.join_ranges([(THIRD, "A\tthird_party/lib/a.h"), ("", "M\tthird_party/lib/a.h\nM\tthird_party/lib/b.h")])
check("join: a file two ranges touch counts once, by its first letter",
      "- third_party/lib/: 1 added, 1 changed, 0 removed, 0 renamed" in joined, True)
check("join: the diff follows the summary", joined.endswith(THIRD), True)
check("join: no range, no text", rp.join_ranges([]), "")

check("well formed", rp.well_formed("## Blocking\n- none\n\n## Unresearched choices\n- none\n\n## Verified\n- x"), True)
check("the old non-blocking headings are not well formed",
      rp.well_formed("## Blocking\n- none\n\n## Non-blocking\n- none\n\n## Verified\n- x"), False)
# Blocking findings only (ruled 2026-10-12): neither prompt asks for a non-blocking finding.
check("the full review asks for no non-blocking finding", "Non-blocking" in rp.INSTRUCTIONS, False)
check("the fix check asks for no non-blocking finding", "non-blocking" in rp.FIX_CHECK_INSTRUCTIONS.lower(), False)
check("the format names the unresearched choices", "## Unresearched choices" in rp.OUTPUT_FORMAT, True)
check("cut off after Blocking", rp.well_formed("## Blocking\n- p:1 half a sente"), False)

# build_prompt's context-path rule (documents/known-issues.md, 2026-10-09): a relative --context path is
# read at the reviewed commit when it exists there and stays inside the worktree, otherwise as typed from
# the caller's directory; a file found nowhere, a missing CLAUDE.md or a missing exit test exits 2.
# The worktree is a temporary folder, and stone_plan is replaced so no gh call runs.
rp.stone_plan = lambda base_ref: None
PROMPT_PR = {"number": 7, "title": "t", "body": "b", "baseRefName": "stone/x", "headRefOid": HEAD}


def exits_2(*args):
    """True when build_prompt stops with exit code 2, its refusal."""
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            rp.build_prompt(*args)
    except SystemExit as stop:
        return stop.code == 2
    return False


with tempfile.TemporaryDirectory() as scratch:
    base = Path(scratch)
    worktree, caller = base / "worktree", base / "caller" / "inside"
    (worktree / "documents" / "plans").mkdir(parents=True)
    caller.mkdir(parents=True)
    (worktree / "CLAUDE.md").write_text("## Load-Bearing Invariants\n1. a rule\n", encoding="utf-8")
    (worktree / "documents" / "plans" / "phase-1-target.md").write_text("### Stone 1 — x\nexit test here\n", encoding="utf-8")
    (worktree / "ROADMAP.md").write_text("Its plan is `documents/plans/phase-1-target.md`, and more.\n", encoding="utf-8")
    (worktree / "notes.md").write_text("from the reviewed commit", encoding="utf-8")
    (base / "outside.md").write_text("beside the worktree", encoding="utf-8")
    (base / "caller" / "outside.md").write_text("from the caller", encoding="utf-8")
    absolute = base / "absolute.md"
    absolute.write_text("read as given", encoding="utf-8")
    previous = os.getcwd()
    os.chdir(caller)
    try:
        prompt = rp.build_prompt(PROMPT_PR, "diff", 1, ["notes.md", "../outside.md", str(absolute)], worktree)
        check("context: a path at the reviewed commit is read there", "from the reviewed commit" in prompt, True)
        check("context: a .. path never reaches beside the worktree", "beside the worktree" in prompt, False)
        check("context: a .. path is read from the caller's directory", "from the caller" in prompt, True)
        check("context: an absolute path is read as given", "read as given" in prompt, True)
        check("context: the exit test is the stone's section", "exit test here" in prompt, True)
        check("context: the plan is the one ROADMAP.md names", rp.phase_plan(worktree), Path("documents/plans/phase-1-target.md"))
        check("prompt: a full review forbids background tasks", rp.FOREGROUND in prompt, True)
        check("prompt: a fix check forbids background tasks",
              rp.FOREGROUND in rp.build_prompt(PROMPT_PR, "d", None, [], worktree, (1, "abc", "- x", "a..b")), True)
        check("context: a file found nowhere exits 2", exits_2(PROMPT_PR, "d", None, ["no_such.md"], worktree), True)
        check("context: a missing stone section exits 2", exits_2(PROMPT_PR, "d", 9, [], worktree), True)
        (worktree / "documents" / "plans" / "phase-1-target.md").unlink()
        check("context: a missing phase plan exits 2", exits_2(PROMPT_PR, "d", 1, [], worktree), True)
        (worktree / "ROADMAP.md").write_text("No plan named here.\n", encoding="utf-8")
        check("context: a roadmap that names no plan exits 2", exits_2(PROMPT_PR, "d", 1, [], worktree), True)
        check("context: no plan named reads as None", rp.phase_plan(worktree), None)
        (worktree / "CLAUDE.md").unlink()
        check("context: a missing CLAUDE.md exits 2", exits_2(PROMPT_PR, "d", None, [], worktree), True)
    finally:
        os.chdir(previous)

# walk_since over a real repository in a temporary folder: a clean merge of the base is left out, an
# unclean one (a conflict resolved by hand, an edit folded in) names itself, and a merge of a branch the
# base does not carry is reviewed like any commit. The identity and signing settings are the test's own.
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
       "-c", "init.defaultBranch=base", "-c", "core.autocrlf=false"]


with tempfile.TemporaryDirectory() as scratch:
    repo = Path(scratch)

    def git(*args):
        proc = rp.subprocess.run(GIT + list(args), cwd=repo, text=True, capture_output=True, encoding="utf-8")
        if proc.returncode != 0 and args[0] != "merge":
            raise RuntimeError(f"git {' '.join(args)}: {proc.stderr}")
        return proc.stdout.strip()

    def commit(name, text, message):
        (repo / name).write_text(text, encoding="utf-8")
        git("add", name)
        git("commit", "-q", "-m", message)
        return git("rev-parse", "HEAD")

    def walk(a, b):
        return rp.walk_since(a, b, "base", cwd=repo)

    git("init", "-q")
    commit("shared.txt", "one\ntwo\n", "root")
    git("checkout", "-q", "-b", "step")
    reviewed = commit("step.txt", "step\n", "the step")
    fix = commit("step.txt", "step fixed\n", "a fix")
    check("walk: one fix commit is one range", walk(reviewed, fix), ([(reviewed, fix)], [], None))
    git("checkout", "-q", "base")
    commit("base.txt", "base\n", "a sibling step merged into the base")
    git("checkout", "-q", "step")
    git("merge", "-q", "--no-ff", "-m", "merge the base", "base")
    clean_merge = git("rev-parse", "HEAD")
    check("walk: only a clean merge of the base is no range", walk(fix, clean_merge), ([], [clean_merge], None))
    later = commit("step.txt", "step fixed twice\n", "a later fix")
    check("walk: the ranges skip the clean merge", walk(reviewed, later), ([(reviewed, fix), (clean_merge, later)], [clean_merge], None))
    git("checkout", "-q", "base")
    commit("base.txt", "base again\n", "another sibling")
    git("checkout", "-q", "step")
    git("merge", "-q", "--no-ff", "--no-commit", "base")
    (repo / "step.txt").write_text("edited inside the merge\n", encoding="utf-8")
    git("add", "step.txt")
    git("commit", "-q", "-m", "merge the base with an edit folded in")
    folded = git("rev-parse", "HEAD")
    check("walk: an edit folded into a merge of the base names it", walk(later, folded)[2], folded)
    git("checkout", "-q", "base")
    commit("shared.txt", "one\ntwo from the base\n", "a sibling edits the shared line")
    git("checkout", "-q", "step")
    commit("shared.txt", "one\ntwo from the step\n", "the step edits the same line")
    git("merge", "-q", "--no-ff", "base")  # conflicts; resolved by hand below
    (repo / "shared.txt").write_text("one\ntwo from both\n", encoding="utf-8")
    git("add", "shared.txt")
    git("commit", "-q", "-m", "merge the base, resolving the conflict")
    resolved = git("rev-parse", "HEAD")
    check("walk: a conflict resolved by hand names the merge", walk(folded, resolved)[2], resolved)
    git("checkout", "-q", "-b", "elsewhere", git("rev-list", "--max-parents=0", "HEAD"))
    commit("other.txt", "other\n", "a branch the base does not carry")
    git("checkout", "-q", "step")
    git("merge", "-q", "--no-ff", "-m", "merge another branch", "elsewhere")
    foreign = git("rev-parse", "HEAD")
    check("walk: a merge of a branch off the base is reviewed", walk(resolved, foreign), ([(resolved, foreign)], [], None))
    with contextlib.redirect_stderr(io.StringIO()):
        check("walk: a bad range is a git failure", walk("nosuchref", foreign), None)
    # main passes origin/<base>: a remote-tracking ref behaves as the local branch does.
    git("checkout", "-q", "base")
    commit("base.txt", "base a third time\n", "a third sibling")
    git("update-ref", "refs/remotes/origin/base", "base")
    git("checkout", "-q", "step")
    git("merge", "-q", "--no-ff", "-m", "merge the base once more", "base")
    remote_merge = git("rev-parse", "HEAD")
    check("walk: a remote-tracking base finds the clean merge", rp.walk_since(foreign, remote_merge, "origin/base", cwd=repo), ([], [remote_merge], None))
    # An octopus merge has no clean form to compare against, so it names itself.
    root = git("rev-list", "--max-parents=0", "HEAD")
    for name in ("left", "right"):
        git("checkout", "-q", "-b", name, root)
        commit(f"{name}.txt", name + "\n", f"the {name} branch")
    git("checkout", "-q", "step")
    git("merge", "-q", "--no-ff", "-m", "an octopus", "left", "right")
    octopus = git("rev-parse", "HEAD")
    check("walk: an octopus merge names itself", walk(remote_merge, octopus)[2], octopus)
    # A merge made the other way round: the base checked out, the step merged into it, and the result
    # pushed to the step. The reviewed commit is then on the second parent's line, not the first's.
    off_line = commit("step.txt", "step reviewed off the line\n", "a step commit, reviewed")
    git("checkout", "-q", "base")
    git("merge", "-q", "--no-ff", "-m", "the step merged into the base", "step")
    turned = git("rev-parse", "HEAD")
    check("walk: a reviewed commit off the first-parent line names itself", walk(off_line, turned), ([], [], off_line))
    mode, note = rp.plan_round((off_line, 1, 0, None), turned, False, True, None, walk(off_line, turned))[1:]
    check("walk: off the line is a full review", mode, "full")
    check("walk: off the line says why", "first-parent line" in note, True)

# A second repository's data file: the tool reads its root from the caller's folder and its lists from that root's
# .claude/mw.json, not from this repository's.
OTHER = {"version": 1, "repository": "Second Repo", "worktrees": "c:/w", "guard": {"files": ["a"], "folders": ["b/"]},
         "scratch_patterns": ["*.tmp"],
         "review": {"costly_paths": [{"pattern": "lib/", "reason": "the library"}],
                    "profiles": {"stone": ["claude-x", "max"], "costly": ["claude-y", "low"], "step": ["claude-z", "medium"]},
                    "allowed_tools": ["Bash(make test:*)", "Read"], "roadmap": "PLAN.md",
                    "plan_sentence": r"Next: `(plans/[\w.-]+\.md)`", "invariants": {"file": "RULES.md", "heading": "Our Rules"},
                    "path_sources": ["README.md"]}}


def quiet():
    """stderr into a buffer that main can reconfigure, as it does the console."""
    return contextlib.redirect_stderr(io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))


with tempfile.TemporaryDirectory() as scratch:
    other = Path(scratch).resolve() / "other"
    (other / ".claude").mkdir(parents=True)
    (other / "deep" / "er").mkdir(parents=True)
    rp.subprocess.run(GIT + ["init", "-q"], cwd=other, check=True, capture_output=True)
    (other / ".claude" / "mw.json").write_text(json.dumps(OTHER), encoding="utf-8")
    check("root: a subfolder resolves to its git top level", rp.repo_root(other / "deep" / "er").resolve(), other)
    check("root: not the tool's own checkout", rp.repo_root(other / "deep").resolve() == rp.HOME, False)
    outside = Path(scratch).resolve() / "outside"
    outside.mkdir()
    saved_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
    os.environ["GIT_CEILING_DIRECTORIES"] = str(Path(scratch).resolve())
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            rp.repo_root(outside)
        outside_code = None
    except SystemExit as stop:
        outside_code = stop.code
    finally:
        if saved_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES")
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = saved_ceiling
    check("root: a folder outside any repository exits 2", outside_code, 2)
    # main resolves the root from the caller's folder and loads that root's data file before its first gh call.
    seen = []
    saved = (sys.argv, rp.gh_json, rp.ROOT, rp.DATA)
    sys.argv = ["review_pr.py", "83"]
    rp.gh_json = lambda *a, **k: seen.append((rp.ROOT, rp.DATA["repository"])) or sys.exit(2)
    previous = os.getcwd()
    os.chdir(other / "deep")
    try:
        with quiet():
            rp.main()
    except SystemExit:
        pass
    finally:
        os.chdir(previous)
        sys.argv, rp.gh_json = saved[:2]
    check("main: the root is the caller's git top level", seen and seen[0][0].resolve(), other)
    check("main: the data file is that root's", seen and seen[0][1], "Second Repo")
    other_data = rp.mw_data.load(other)
    (other / ".claude" / "mw.json").write_text(json.dumps({**OTHER, "version": 9}), encoding="utf-8")
    sys.argv = ["review_pr.py", "83"]
    os.chdir(other)
    try:
        with quiet():
            rp.main()
        refused_data = None
    except SystemExit as stop:
        refused_data = stop.code
    finally:
        os.chdir(previous)
        sys.argv, rp.gh_json, rp.ROOT, rp.DATA = saved
    check("main: a data file the loader refuses exits 2", refused_data, 2)
    rp.DATA = other_data
    check("kind: the data file's costly path", rp.review_kind("stone/x", ["lib/a.c"]), "costly")
    check("kind: the engine's costly path is not that repository's", rp.review_kind("stone/x", ["src/core/a.cpp"]), "step")
    check("profile: the data file's costly profile", rp.review_profile("costly", 1), ("claude-y", "low"))
    check("profile: the data file's later round", rp.review_profile("costly", 2), ("claude-z", "medium"))
    check("profile: the data file's stone profile", rp.review_profile("stone", 1), ("claude-x", "max"))
    grants = rp.allowed_tools().split(",")
    check("grants: the base list joins the data file's addition", grants, rp.BASE_TOOLS + ["Bash(make test:*)"])
    worktree = Path(scratch).resolve() / "reviewed"
    (worktree / "plans").mkdir(parents=True)
    (worktree / "RULES.md").write_text("## Other\nnot this\n## Our Rules\n1. a second repository's rule\n", encoding="utf-8")
    (worktree / "CLAUDE.md").write_text("## Load-Bearing Invariants\n1. the engine's rule\n", encoding="utf-8")
    (worktree / "PLAN.md").write_text("Next: `plans/p.md`\n", encoding="utf-8")
    (worktree / "plans" / "p.md").write_text("### Stone 2 x\nits exit test\n", encoding="utf-8")
    prompt = rp.build_prompt(PROMPT_PR, "diff", 2, [], worktree)
    check("prompt: names the data file's repository", "in the Second Repo repository" in prompt and "Millwright" not in prompt, True)
    check("prompt: the invariants come from the configured file and heading",
          ("a second repository's rule" in prompt, "not this" in prompt, "the engine's rule" in prompt), (True, False, False))
    check("prompt: the invariants' header names the file", "# Repository invariants (RULES.md)" in prompt, True)
    check("prompt: the roadmap and plan sentence are the data file's", "its exit test" in prompt, True)
    check("prompt: the path sources are the data file's", "other than README.md. The invariant test" in prompt, True)
    (worktree / "RULES.md").unlink()
    check("prompt: a missing configured invariants file exits 2", exits_2(PROMPT_PR, "d", None, [], worktree), True)
    rp.DATA = ENGINE_DATA

for line in failures:
    print(f"FAIL {line}")
for line in skipped_checks:
    print(f"[test_review_pr] skipped {line}")
print(f"[test_review_pr] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
