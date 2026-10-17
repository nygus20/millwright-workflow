"""PreToolUse hook: deny reads of the owner's scratch files at the repo root.

Untracked scratch files at the root are the owner's private notebook, not a
work source (CLAUDE.md "Workflow Rules"). The patterns come from the
scratch_patterns key of the repository's data file, .claude/mw.json, read
through mw_data.py at the plugin's root, and match the last section of .gitignore.
Only the repository root is checked; the same names elsewhere are ordinary
files. A missing data file, an unknown version or a missing required key exits
2 with the reason on stderr, which stops the read and tells the agent why.

Known gap: the matcher covers Read. Grep, Glob and a shell `cat` are not
intercepted. The prose rule and the delegation brief cover that path.
"""

import fnmatch
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the plugin's root
import mw_data  # noqa: E402  (it sits at the plugin's root, one folder above this hook)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    patterns = mw_data.load_or_exit(project)["scratch_patterns"]
    root = os.path.normcase(os.path.abspath(project))
    full = os.path.normcase(os.path.abspath(path))
    if os.path.dirname(full) != root:
        return
    if not any(fnmatch.fnmatch(os.path.basename(full), os.path.normcase(pat)) for pat in patterns):
        return
    name = os.path.basename(path)  # as the caller typed it: normcase lower-cases it on Windows
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{name} is an untracked scratch file at the repo root: the owner's "
                        "private notebook, not a work source (CLAUDE.md Workflow Rules)."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
