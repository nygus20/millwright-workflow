"""PreToolUse hook: deny an edit in a session that has not loaded the workflow plugin mw.

A repository that uses the plugin copies this file to .claude/hooks/require_plugin.py
unchanged and wires it in .claude/settings.json on Edit|Write|MultiEdit|NotebookEdit
with "onFailure": "block". The plugin's SessionStart hook writes two markers under
<temp>/mw-plugin/: one named by the session id, one named ppid-<id> by the Claude Code
process id, which Claude Code sets as CLAUDE_PID in a hook's environment. With neither
present, the plugin did not start in this session, and this hook denies the edit with
a reason naming the plugin, the pin and what installs it. A read-only session goes on.
Known gap: a process id reused within a day passes; the plugin's session_start.py says why.
"""

import json
import os
import sys
import tempfile


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    session = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
    folder = os.path.join(tempfile.gettempdir(), "mw-plugin")
    pid = os.environ.get("CLAUDE_PID") or str(os.getppid())
    names = [f"ppid-{pid}"] + ([session] if session and not set(session) & set("/\\.") else [])
    if any(os.path.isfile(os.path.join(folder, name)) for name in names):
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        with open(os.path.join(project, ".claude", "settings.json"), encoding="utf-8") as f:
            source = json.load(f)["extraKnownMarketplaces"]["millwright"]["source"]
        pin = f"{source['repo']} at {source['ref']}"
    except (OSError, ValueError, KeyError, TypeError):
        pin = "the ref .claude/settings.json names"
    reason = (f"The workflow plugin mw@millwright is not loaded in this session, and this repository pins it "
              f"({pin}, in .claude/settings.json). Start Claude Code in this repository's folder and accept the "
              "folder's trust dialog, so Claude Code adds the millwright marketplace and loads the plugin, then "
              "restart the session or run /reload-plugins.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
