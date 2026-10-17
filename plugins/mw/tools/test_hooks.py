"""Checks for the plugin's four hooks under hooks/, the hooks.json that wires them, and the repository-side hook template.

Usage:
    python tools/test_hooks.py [PROJECT]

PROJECT is the repository the checks run against: the folder given, else
CLAUDE_PROJECT_DIR, else the current folder. tools/run_checks.py passes it.

Each hook runs as Claude Code runs it: a separate process, a JSON payload on
stdin, CLAUDE_PROJECT_DIR in the environment. The project directory is a
temporary folder, so no check touches a checkout. The known issues of
2026-10-08 and 2026-10-09, resolved in the Millwright engine's
documents/known-issues.md, are asserted fixed: the guard hook denies a guard
file inside a worktree, the emoji hook passes the text stars and quotation
dingbats, and the scratch hook keeps the file name's case. The guard hook and
the scratch hook read their lists from the data file, .claude/mw.json: each
temporary repository gets one, a copy of the fixture tools/fixture/.claude/mw.json
(the engine's lists at v0.1.0) unless a check writes its own, and the data-file
checks give two repositories different lists and break the file in each way the
loader refuses. PROJECT's own data file must load, and a temporary repository
holding a copy of it must deny each file, folder and scratch pattern it lists.
The session-start hook writes its two markers and its context line under a
temporary folder that stands in for the system's, and the template
templates/require_plugin.py denies an edit without a marker. Prints
`[test_hooks] N checks, M failures` and exits 1 when M is not zero.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
HOOKS = PLUGIN / "hooks"
DATA = json.loads((PLUGIN / "tools" / "fixture" / ".claude" / "mw.json").read_text(encoding="utf-8"))
PROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
VERSION = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]

checks = 0
failures = []


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def run_hook(hook, project, file_path, extra_env=None, session_id=None, script=None):
    """(exit code, stdout, stderr) of one hook run on a payload naming file_path and, when given, a session id.

    The child never inherits CLAUDE_PID, so a check that wants one passes it in extra_env."""
    env = {k: v for k, v in os.environ.items() if k not in ("MW_ALLOW_GUARD_EDIT", "CLAUDE_PID")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(extra_env or {})
    payload = {"tool_input": {"file_path": str(file_path)}}
    if session_id is not None:
        payload["session_id"] = session_id
    proc = subprocess.run([sys.executable, str(script or HOOKS / hook)], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", env=env, cwd=project, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


def temp_env(folder, pid=None):
    """The environment that points tempfile.gettempdir() at folder, with CLAUDE_PID when given."""
    env = {"TMPDIR": str(folder), "TEMP": str(folder), "TMP": str(folder)}
    if pid is not None:
        env["CLAUDE_PID"] = pid
    return env


def passes(result):
    """A hook lets the call through when it exits 0 and prints nothing."""
    code, out, _ = result
    return code == 0 and out == ""


def denied(stdout):
    try:
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError, TypeError):
        return False


def write_data(root, data=None):
    """root/.claude/mw.json holding data, or this checkout's data file."""
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "mw.json").write_text(json.dumps(DATA if data is None else data), encoding="utf-8")


def with_lists(files, folders, patterns):
    """This checkout's data file with its own guard lists and scratch patterns."""
    data = json.loads(json.dumps(DATA))
    data["guard"] = {"files": files, "folders": folders}
    data["scratch_patterns"] = patterns
    return data


def refuses(result, reason):
    """A hook refuses a broken data file: exit 2, no decision on stdout, the reason on stderr."""
    code, out, err = result
    return code == 2 and out == "" and reason in err


def write_override(root):
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.local.json").write_text('{"mwAllowGuardEdit": true}', encoding="utf-8")


with tempfile.TemporaryDirectory() as scratch:
    base = Path(scratch)
    project, worktree = base / "project", base / "worktrees" / "1-core"
    (project / ".git").mkdir(parents=True)
    worktree.mkdir(parents=True)
    # A worktree's .git is a file naming its folder inside the main checkout's .git.
    (project / ".git" / "worktrees" / "1-core").mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {project / '.git' / 'worktrees' / '1-core'}\n", encoding="utf-8")
    stranger = base / "other-repo"
    (stranger / ".git" / "worktrees" / "w").mkdir(parents=True)
    stranger_worktree = base / "other-worktree"
    stranger_worktree.mkdir()
    (stranger_worktree / ".git").write_text(f"gitdir: {stranger / '.git' / 'worktrees' / 'w'}\n", encoding="utf-8")
    for folder in (project, worktree):
        write_data(folder)

    guard = "deny_guard_config.py"
    # The data file's lists, in the project and in its worktree, and the data file itself, which it does not list.
    for name in DATA["guard"]["files"] + [f"{folder}x.txt" for folder in DATA["guard"]["folders"]] + [".claude/mw.json"]:
        check(f"guard: denies the listed {name}", denied(run_hook(guard, project, project / name)[1]), True)
        check(f"guard: denies the listed {name} in a worktree", denied(run_hook(guard, project, worktree / name)[1]), True)
    check("guard: the data file does not list itself", ".claude/mw.json" in DATA["guard"]["files"], False)
    check("guard: passes a lookalike of the data file", passes(run_hook(guard, project, project / ".claude" / "mw.json.bak")),
          True)
    check("guard: passes the data file's name in a subfolder",
          passes(run_hook(guard, project, project / "src" / ".claude" / "mw.json")), True)
    check("guard: denies the presets", denied(run_hook(guard, project, project / "CMakePresets.json")[1]), True)
    check("guard: denies a hook", denied(run_hook(guard, project, project / ".claude" / "hooks" / "x.py")[1]), True)
    check("guard: denies the workflow", denied(run_hook(guard, project, project / ".github" / "workflows" / "t.yml")[1]), True)
    check("guard: ignores case", denied(run_hook(guard, project, project / "cmakepresets.JSON")[1]), True)
    check("guard: passes a source file", passes(run_hook(guard, project, project / "src" / "core" / "arena.cpp")), True)
    check("guard: passes a lookalike name", passes(run_hook(guard, project, project / "cmake" / "module.cmake")), True)
    check("guard: the environment override passes",
          passes(run_hook(guard, project, project / ".clang-tidy", {"MW_ALLOW_GUARD_EDIT": "1"})), True)
    check("guard: denies a guard file in a worktree", denied(run_hook(guard, project, worktree / ".clang-tidy")[1]), True)
    check("guard: passes a guard-named file in another repository", passes(run_hook(guard, project, stranger / ".clang-tidy")), True)
    check("guard: passes a guard-named file in another repository's worktree",
          passes(run_hook(guard, project, stranger_worktree / ".clang-tidy")), True)
    check("guard: a session in a worktree still guards the main checkout",
          denied(run_hook(guard, worktree, project / ".clang-format")[1]), True)
    sibling = base / "worktrees" / "2-clock"
    sibling.mkdir(parents=True)
    write_data(sibling)
    (project / ".git" / "worktrees" / "2-clock").mkdir(parents=True)
    (sibling / ".git").write_text(f"gitdir: {project / '.git' / 'worktrees' / '2-clock'}\n", encoding="utf-8")
    check("guard: a session in a worktree guards a sibling worktree",
          denied(run_hook(guard, worktree, sibling / ".clang-tidy")[1]), True)
    for name in ("cmake/warnings.cmake", ".clang-format", ".claude/settings.json", ".claude/settings.local.json",
                 "git-hooks/pre-commit"):
        check(f"guard: denies {name}", denied(run_hook(guard, project, project / name)[1]), True)
    check("guard: passes a source file in a worktree", passes(run_hook(guard, project, worktree / "src" / "x.cpp")), True)
    write_override(worktree)
    check("guard: the worktree's own override passes", passes(run_hook(guard, project, worktree / ".clang-tidy")), True)
    check("guard: the worktree's override does not cover the project",
          denied(run_hook(guard, project, project / ".clang-tidy")[1]), True)
    write_override(project)
    check("guard: the project's override passes", passes(run_hook(guard, project, project / ".clang-tidy")), True)

    scratch_hook = "deny_scratch_read.py"
    code, out, _ = run_hook(scratch_hook, project, project / "Untitled-3.txt")
    check("scratch: denies a scratch file at the root", denied(out), True)
    check("scratch: keeps the name's case", "Untitled-3.txt is an untracked" in out, True)
    check("scratch: denies a notebook at the root", denied(run_hook(scratch_hook, project, project / "x.ipynb")[1]), True)
    check("scratch: passes the name in a subfolder", passes(run_hook(scratch_hook, project, project / "docs" / "Untitled-3.txt")), True)
    check("scratch: passes an ordinary file", passes(run_hook(scratch_hook, project, project / "README.md")), True)

    emoji_hook = "no_emoji_md.py"
    samples = {
        "rocket.md": ("line one\nlaunch \U0001F680\n", 2),
        "check.md": ("done ✓ and ✔\n", 0),
        "stars.md": ("rated ★☆ ❛ quoted ❞\n", 0),
        "arrows.md": ("a → b, box ─\n", 0),
    }
    for name, (text, want) in samples.items():
        (project / name).write_text(text, encoding="utf-8")
        code, _, err = run_hook(emoji_hook, project, project / name)
        check(f"emoji: {name} exits {want}", code, want)
        if want:
            check("emoji: names the line", f"{name}:2: U+1F680" in err, True)
    (project / "notes.txt").write_text("\U0001F680\n", encoding="utf-8")
    check("emoji: passes a file that is not .md", run_hook(emoji_hook, project, project / "notes.txt")[0], 0)
    outside = base / "outside.md"
    outside.write_text("\U0001F680\n", encoding="utf-8")
    check("emoji: passes a file outside the project", run_hook(emoji_hook, project, outside)[0], 0)

    session = "session_start.py"
    for has_hooks in (True, False):
        repo = base / f"repo_{has_hooks}"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        if has_hooks:
            (repo / "git-hooks").mkdir()
        write_data(repo)
        run_hook(session, repo, repo, temp_env(base / f"tmp_{has_hooks}"))
        value = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
        check(f"session start: hooksPath with git-hooks {has_hooks}", value, "git-hooks" if has_hooks else "")

    # The markers: one per session id, one per Claude Code process id, each naming the plugin's root and version,
    # under the system's temporary folder, which a test folder stands in for.
    repo, tmp = base / "repo_True", base / "tmp_markers"
    markers = tmp / "mw-plugin"
    markers.mkdir(parents=True)
    stale, fresh = markers / "old-session", markers / "ppid-1"
    stale.write_text("{}", encoding="utf-8")
    fresh.write_text("{}", encoding="utf-8")
    two_days_ago = time.time() - 2 * 86400
    os.utime(stale, (two_days_ago, two_days_ago))
    code, out, err = run_hook(session, repo, repo, temp_env(tmp, "424242"), session_id="session-one")
    check("session start: exits 0", (code, err), (0, ""))
    for name in ("session-one", "ppid-424242"):
        try:
            body = json.loads((markers / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            body = None
        check(f"session start: the marker {name} names the plugin's root and version", body,
              {"root": str(PLUGIN), "version": VERSION})
    check("session start: prunes a marker older than a day", stale.exists(), False)
    check("session start: keeps a fresh marker", fresh.exists(), True)
    lines = out.splitlines()
    check("session start: prints one context line", len(lines), 1)
    check("session start: the line names the version, the root and the worktree folder",
          [f"mw {VERSION}" in out, str(PLUGIN) in out, DATA["worktrees"] in out], [True, True, True])
    run_hook(session, repo, repo, temp_env(tmp), session_id="session-two")
    check("session start: without CLAUDE_PID the parent's id names a marker",
          len([p for p in markers.iterdir() if p.name.startswith("ppid-")]), 3)
    run_hook(session, repo, repo, temp_env(tmp, "7"), session_id="../escaped")
    check("session start: a session id with a path in it writes no file", [(tmp / "escaped").exists(),
          (markers / "ppid-7").exists()], [False, True])
    refused = base / "repo_refused"
    (refused / ".git").mkdir(parents=True)
    code, out, _ = run_hook(session, refused, refused, temp_env(tmp, "8"), session_id="session-three")
    check("session start: a missing data file is named on the line, and the hook exits 0",
          (code, "its data file is refused: .claude/mw.json is missing" in out, (markers / "session-three").exists()),
          (0, True, True))

    # The repository-side hook template: it denies an edit when neither marker exists, and passes with either.
    template = PLUGIN / "templates" / "require_plugin.py"
    pinned = base / "pinned"
    (pinned / ".claude").mkdir(parents=True)
    (pinned / ".claude" / "settings.json").write_text(json.dumps({"extraKnownMarketplaces": {"millwright": {"source": {
        "source": "github", "repo": "nygus20/millwright-workflow", "ref": "v9.9.9"}}}}), encoding="utf-8")
    empty = base / "tmp_empty"
    empty.mkdir()
    code, out, _ = run_hook(None, pinned, pinned / "a.txt", temp_env(empty, "99"), session_id="nobody", script=template)
    check("require: denies with no marker", (code, denied(out)), (0, True))
    check("require: the reason names the plugin, the pin and what installs it",
          ["mw@millwright" in out, "nygus20/millwright-workflow at v9.9.9" in out, "trust dialog" in out], [True] * 3)
    check("require: passes with the session marker",
          passes(run_hook(None, pinned, pinned / "a.txt", temp_env(tmp, "99"), session_id="session-one", script=template)),
          True)
    check("require: passes with the process marker",
          passes(run_hook(None, pinned, pinned / "a.txt", temp_env(tmp, "424242"), session_id="other", script=template)),
          True)
    check("require: a session id with a path in it is no marker",
          denied(run_hook(None, pinned, pinned / "a.txt", temp_env(tmp, "99"), session_id="../mw-plugin/session-one",
                          script=template)[1]), True)
    code, out, _ = run_hook(None, base / "repo_False", base / "a.txt", temp_env(empty, "99"), script=template)
    check("require: denies without a pin, naming where the pin goes", (denied(out), ".claude/settings.json" in out),
          (True, True))

    # Two repositories with different lists: each denies its own set and passes the other's, so the lists come
    # from each repository's data file and not from the hook.
    alpha, beta = base / "alpha", base / "beta"
    lists = {alpha: (["alpha.cfg"], ["guard-a/"], ["alpha-*.txt"]), beta: (["beta.cfg"], ["guard-b/"], ["beta-*.txt"])}
    for repo, (files, folders, patterns) in lists.items():
        (repo / ".git").mkdir(parents=True)
        write_data(repo, with_lists(files, folders, patterns))
    for repo, other in ((alpha, beta), (beta, alpha)):
        mine, theirs = lists[repo], lists[other]
        for name in (mine[0][0], mine[1][0] + "x.txt", ".claude/mw.json"):
            check(f"data: {repo.name} denies {name}", denied(run_hook(guard, repo, repo / name)[1]), True)
        for name in (theirs[0][0], theirs[1][0] + "x.txt", "CMakePresets.json"):
            check(f"data: {repo.name} passes {name}", passes(run_hook(guard, repo, repo / name)), True)
        own_scratch, other_scratch = mine[2][0].replace("*", "1"), theirs[2][0].replace("*", "1")
        check(f"data: the scratch hook in {repo.name} denies {own_scratch}",
              denied(run_hook(scratch_hook, repo, repo / own_scratch)[1]), True)
        check(f"data: the scratch hook in {repo.name} passes {other_scratch}",
              passes(run_hook(scratch_hook, repo, repo / other_scratch)), True)
        check(f"data: the scratch hook in {repo.name} passes the engine's Untitled-3.txt",
              passes(run_hook(scratch_hook, repo, repo / "Untitled-3.txt")), True)

    # PROJECT's data file: it loads, and a temporary repository holding a copy denies each entry it lists.
    sys.path.insert(0, str(PLUGIN))
    import mw_data  # noqa: E402  (the loader sits at the plugin's root, off the import path until now)
    try:
        project_data = mw_data.load(PROJECT)
        project_error = ""
    except mw_data.DataFileError as error:
        project_data, project_error = None, str(error)
    check(f"project: {PROJECT}'s data file loads", project_error, "")
    if project_data is not None:
        copy = base / "project-copy"
        (copy / ".git").mkdir(parents=True)
        (copy / ".claude").mkdir()
        (copy / ".claude" / "mw.json").write_bytes((PROJECT / ".claude" / "mw.json").read_bytes())
        for name in project_data["guard"]["files"] + [f"{d}x.txt" for d in project_data["guard"]["folders"]] + \
                [".claude/mw.json"]:
            check(f"project: denies its listed {name}", denied(run_hook(guard, copy, copy / name)[1]), True)
        for pattern in project_data["scratch_patterns"]:
            if "[" in pattern:
                continue  # a character class has no one spelling to try
            name = pattern.replace("*", "x1").replace("?", "x")
            check(f"project: the scratch hook denies {name}", denied(run_hook(scratch_hook, copy, copy / name)[1]), True)
        check("project: passes a file it does not list",
              passes(run_hook(guard, copy, copy / "a-file-no-repository-guards.txt")), True)

    # A data file the loader refuses: each hook exits 2 with the reason, so the call stops and the agent reads why.
    broken = base / "broken"
    (broken / ".git").mkdir(parents=True)
    for hook, target in ((guard, "CMakePresets.json"), (scratch_hook, "Untitled-3.txt")):
        check(f"data: {hook} refuses a missing data file",
              refuses(run_hook(hook, broken, broken / target), ".claude/mw.json is missing"), True)
    cases = [("an unknown version", {**DATA, "version": 2}, "has version 2")]
    for key in ("repository", "worktrees", "guard", "scratch_patterns", "review"):
        cases.append((f"no {key}", {k: v for k, v in DATA.items() if k != key}, f"required key {key}"))
    for parent, key in (("guard", "files"), ("guard", "folders"), ("review", "costly_paths")):
        trimmed = json.loads(json.dumps(DATA))
        del trimmed[parent][key]
        cases.append((f"no {parent}.{key}", trimmed, f"required key {parent}.{key}"))
    cases.append(("guard files as one string", with_lists("CMakePresets.json", [], []), "guard.files must be a list"))
    rowless = json.loads(json.dumps(DATA))
    rowless["review"]["costly_paths"] = [{"pattern": "src/"}]
    cases.append(("a costly path with no reason", rowless, "review.costly_paths must be a list of objects"))
    for what, data, reason in cases:
        write_data(broken, data)
        check(f"data: {guard} refuses {what}", refuses(run_hook(guard, broken, broken / "CMakePresets.json"), reason), True)
        check(f"data: {scratch_hook} refuses {what}",
              refuses(run_hook(scratch_hook, broken, broken / "Untitled-3.txt"), reason), True)
    (broken / ".claude" / "mw.json").write_text('{"version": 1,', encoding="utf-8")
    check("data: the guard hook refuses a file that is not JSON",
          refuses(run_hook(guard, broken, broken / "CMakePresets.json"), "is not valid JSON"), True)
    check("data: the environment override passes before the data file is read",
          passes(run_hook(guard, broken, broken / "CMakePresets.json", {"MW_ALLOW_GUARD_EDIT": "1"})), True)

    # The loader fills the review section's defaults, and keeps the values a data file sets.
    minimal = json.loads(json.dumps(DATA))
    minimal["review"] = {"costly_paths": []}
    write_data(broken, minimal)
    review = mw_data.load(broken)["review"]
    check("data: the loader fills the review defaults", {k: review[k] for k in mw_data.REVIEW_DEFAULTS},
          mw_data.REVIEW_DEFAULTS)
    minimal["review"]["findings_folder"] = "notes/findings/"
    write_data(broken, minimal)
    check("data: the loader keeps a value the file sets", mw_data.load(broken)["review"]["findings_folder"],
          "notes/findings/")

wiring = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
check("hooks.json: one top-level hooks key", list(wiring), ["hooks"])
entries = [(event, entry["matcher"], hook) for event, items in wiring["hooks"].items() for entry in items
           for hook in entry["hooks"]]
wired = {(event, matcher, Path(hook["command"].split('"')[-2]).name) for event, matcher, hook in entries}
check("hooks.json: the four hooks and their matchers", wired, {
    ("PreToolUse", "Edit|Write|MultiEdit", "deny_guard_config.py"),
    ("PreToolUse", "Read", "deny_scratch_read.py"),
    ("PostToolUse", "Edit|Write|MultiEdit", "no_emoji_md.py"),
    ("SessionStart", "startup|resume|clear|compact|fork", "session_start.py"),
})
check("hooks.json: every wired hook exists", all((HOOKS / name).is_file() for _, _, name in wired), True)
check("hooks.json: every command runs from the plugin's root",
      all('"${CLAUDE_PLUGIN_ROOT}/hooks/' in hook["command"] for _, _, hook in entries), True)
check("hooks.json: the two PreToolUse hooks block when they fail",
      sorted((matcher, hook.get("onFailure")) for event, matcher, hook in entries if event == "PreToolUse"),
      [("Edit|Write|MultiEdit", "block"), ("Read", "block")])
manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
check("plugin.json: the name and a version", (manifest.get("name"), bool(manifest.get("version"))), ("mw", True))
style = (PLUGIN / "output-styles" / "millwright.md").read_text(encoding="utf-8")
check("output style: forced whenever the plugin is enabled", "\nforce-for-plugin: true\n" in style.split("---", 2)[1],
      True)

for line in failures:
    print(f"FAIL {line}")
print(f"[test_hooks] {checks} checks, {len(failures)} failures")
sys.exit(1 if failures else 0)
