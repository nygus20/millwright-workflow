"""PreToolUse hook: deny edits to the guard stack's configuration.

Claude Code runs this before Edit, Write and MultiEdit. The guarded files and
folders come from the guard key of the repository's data file, .claude/mw.json,
read through mw_data.py at the plugin's root: the guard stack's configuration, the
CI workflow, the git hooks, and the Claude Code hooks themselves with the
settings file that wires them; loosening one is an owner decision (CLAUDE.md
"Workflow Rules"). The data file itself is always guarded, whatever it lists.
The prose rule stays in CLAUDE.md; this hook makes it hold for the file tools.
Matching ignores case, because Windows does.

The data file is the one in the project directory the session started in. A
missing file, an unknown version or a missing required key exits 2 with the
reason on stderr, which stops the edit and tells the agent why.

A path is matched against two roots: the project directory the session started
in, and the checkout the file itself sits in, found by walking up to the
nearest `.git` entry, when that checkout is a worktree of the same repository.
A session whose project directory is itself a worktree also guards the main
checkout that worktree belongs to. The second root covers a stone's worktree under
c:/projects/millwright-worktrees/, which a session started in the main
checkout edits without changing its project directory (documents/known-issues.md,
2026-10-09).

To let an agent through after a discussion, the owner either sets
MW_ALLOW_GUARD_EDIT=1 in the environment for that session, or puts
"mwAllowGuardEdit": true in .claude/settings.local.json (gitignored,
per machine) of the checkout being edited, or of the project directory, and
removes it afterwards. The second form works from the editor, where an
environment variable is awkward to set.

Known gap: the matcher covers Edit, Write and MultiEdit. A shell redirect, a
`git checkout` of the file or a PowerShell `Set-Content` is not intercepted.
The prose rule and the adversarial review cover that path.
"""

import json
import os
import sys
from pathlib import PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the plugin's root
import mw_data  # noqa: E402  (it sits at the plugin's root, one folder above this hook)


def local_override(root: str) -> bool:
    try:
        with open(os.path.join(root, ".claude", "settings.local.json"), encoding="utf-8") as f:
            return json.load(f).get("mwAllowGuardEdit") is True
    except (OSError, ValueError, AttributeError):
        return False


def checkout_root(path: str):
    """The nearest folder above path that holds a .git entry: a directory in the main checkout, a file in a worktree."""
    folder = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def same_repository(checkout: str, project: str) -> bool:
    """True for the main checkout itself, or a worktree whose .git file points into its .git folder.

    project here is the main checkout, so a session started in one worktree also
    recognises a sibling worktree of the same repository.
    """
    if os.path.normcase(os.path.abspath(checkout)) == os.path.normcase(os.path.abspath(project)):
        return True
    git = os.path.join(checkout, ".git")
    if not os.path.isfile(git):
        return False  # another repository's main checkout
    try:
        with open(git, encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        return False
    if not first.startswith("gitdir:"):
        return False
    target = os.path.normcase(os.path.abspath(os.path.join(checkout, first[len("gitdir:"):].strip())))
    return target.startswith(os.path.normcase(os.path.abspath(os.path.join(project, ".git"))) + os.sep)


def main_checkout_of(project: str):
    """The main checkout a worktree belongs to, read from its .git file, or None for a main checkout."""
    git = os.path.join(project, ".git")
    if not os.path.isfile(git):
        return None
    try:
        with open(git, encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        return None
    if not first.startswith("gitdir:"):
        return None
    target = os.path.abspath(os.path.join(project, first[len("gitdir:"):].strip()))
    parts = target.replace("\\", "/").split("/")
    if len(parts) < 3 or parts[-3] != ".git" or parts[-2] != "worktrees":
        return None
    return os.path.dirname(os.path.dirname(os.path.dirname(target)))


def protected_relative(path: str, root: str, files, folders):
    """The path relative to root when it names one of files, or sits in one of folders, there, else None."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        return None  # another drive on Windows
    rel = PurePosixPath(rel.replace("\\", "/")).as_posix()
    if rel.startswith("../"):
        return None
    key = rel.lower()
    return rel if key in files or any(key.startswith(d) for d in folders) else None


def main() -> None:
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if os.environ.get("MW_ALLOW_GUARD_EDIT") == "1":
        return
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return
    # The off-switch, .claude/settings.local.json, belongs in the guard key: the owner writes it from the editor,
    # which the hook never sees, and an agent must not be able to create it with the file tools.
    files, folders = mw_data.guard_lists(mw_data.load_or_exit(project))
    roots = [project]
    main_checkout = main_checkout_of(project)
    if main_checkout:
        roots.append(main_checkout)  # a session started in a worktree still guards the main checkout
    checkout = checkout_root(path)
    if checkout and same_repository(checkout, main_checkout or project) and \
            os.path.normcase(os.path.abspath(checkout)) != os.path.normcase(os.path.abspath(project)):
        roots.append(checkout)
    hit = next(((root, rel) for root in roots if (rel := protected_relative(path, root, files, folders))), None)
    if hit is None or local_override(hit[0]) or local_override(project):
        return
    rel = hit[1]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{rel} is guard-stack configuration. Editing it is an owner "
                        "decision (CLAUDE.md Workflow Rules). Ask the owner; they can set "
                        "MW_ALLOW_GUARD_EDIT=1 for this session or mwAllowGuardEdit in "
                        ".claude/settings.local.json."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
