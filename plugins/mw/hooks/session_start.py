"""SessionStart hook: point git at the repository's hooks, leave the session's markers, name the plugin.

Claude Code runs this when a session starts, resumes, clears, compacts or forks.
It does three things, and none of them can stop the session: a SessionStart
hook has no decision control, and its exit code 2 only shows stderr to the user.

1. When the project holds git-hooks/, `git config core.hooksPath git-hooks`
   makes the pre-commit hook there run. A once-per-clone instruction is the
   kind an agent forgets, so the session sets it every time; the call is
   idempotent and silent.
2. It writes two marker files under <temp>/mw-plugin/, where <temp> is
   tempfile.gettempdir(): one named by the session id from the hook's input,
   and, when CLAUDE_PID is set, one named ppid-<CLAUDE_PID> by the id of the
   Claude Code process that runs the hooks. Each holds the plugin's root and
   version as JSON. The repository-side hook templates/require_plugin.py denies an edit when neither marker exists,
   so a session that lacks the plugin stops loudly at its first edit. The
   second marker covers a tool call whose session id differs from the start's,
   such as a subagent's. It prunes markers older than MARKER_DAYS.
3. It prints one context line naming the plugin's version, its root and the
   repository's worktree folder from .claude/mw.json. A data file the loader
   refuses is named on that line instead; the guard hook refuses it at the
   first edit.

The process id. Claude Code sets CLAUDE_PID to its own process id in the hook
commands it spawns, from v2.1.214 on (https://code.claude.com/docs/en/env-vars).
The hook's own parent is a shell or a launcher, a different process for each
hook, so it never names Claude Code: without CLAUDE_PID the hook writes no
process marker, by the owner's ruling of 2026-10-17. require_plugin.py reads
the id the same way.

Known gap: a process id the system reuses within MARKER_DAYS lets a later
session with that id through without the plugin, when its own session marker is
missing. The session marker is the main check, and pruning keeps the window to
a day.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)
import mw_data  # noqa: E402  (it sits at the plugin's root, one folder above this hook)

MARKER_FOLDER = "mw-plugin"
MARKER_DAYS = 1  # a day covers a working session; a longer window widens the reused-process-id gap


def plugin_version():
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("version", "unknown")
    except (OSError, ValueError, AttributeError):
        return "unknown"


def claude_pid():
    """The id of the Claude Code process that runs the hooks, from CLAUDE_PID, or None when it is unset."""
    return os.environ.get("CLAUDE_PID") or None


def marker_folder():
    return os.path.join(tempfile.gettempdir(), MARKER_FOLDER)


def write_markers(session_id, version):
    """Writes the session's two markers and prunes old ones; a marker that cannot be written is skipped."""
    folder = marker_folder()
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return
    cutoff = time.time() - MARKER_DAYS * 86400
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass  # another session pruned it first
    body = json.dumps({"root": PLUGIN_ROOT, "version": version})
    pid = claude_pid()
    names = ([f"ppid-{pid}"] if pid else []) + ([session_id] if session_id else [])
    for name in names:
        if "/" in name or "\\" in name or name in (".", ".."):
            continue  # a session id is a UUID; anything else never names a path
        try:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(body)
        except OSError:
            pass


def set_hooks_path(root):
    if not os.path.isdir(os.path.join(root, "git-hooks")):
        return
    try:
        subprocess.run(["git", "config", "core.hooksPath", "git-hooks"], cwd=root, capture_output=True, check=False)
    except OSError:
        return  # no git on PATH: nothing to set


def main() -> None:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    version = plugin_version()
    set_hooks_path(root)
    write_markers(session_id if isinstance(session_id, str) else None, version)
    try:
        where = f"its worktrees sit under {mw_data.load(root)['worktrees']}"
    except mw_data.DataFileError as error:
        where = f"its data file is refused: {error}"
    print(f"[mw] The workflow plugin mw {version} is loaded from {PLUGIN_ROOT}; this repository is {root}, and {where}.")


if __name__ == "__main__":
    main()
