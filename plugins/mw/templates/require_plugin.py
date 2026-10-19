"""PreToolUse hook: deny an edit in a session that has not loaded the workflow plugin mw at the pinned version.

A repository that uses the plugin copies this file to .claude/hooks/require_plugin.py
unchanged and wires it in .claude/settings.json on Edit|Write|MultiEdit|NotebookEdit
with "onFailure": "block". The plugin's SessionStart hook writes two markers under
<temp>/mw-plugin/: one named by the session id, one named ppid-<CLAUDE_PID>. Claude Code
sets CLAUDE_PID to its own process id in hook commands (https://code.claude.com/docs/en/env-vars);
without it only the session marker counts. With neither present, the plugin did not
start in this session, and this hook denies the edit with
a reason naming the plugin, the pin and what installs it. A read-only session goes on.

The version check. Each marker holds the loaded plugin's version, which the SessionStart hook
reads from the plugin's manifest. When the pin's ref in .claude/settings.json is a version tag,
v<version>, the hook reads the session marker, or the process marker when the session marker is
missing, and denies the edit when the marker's version differs from the tag's. A marker without a
version counts as a mismatch. Claude Code's installed-plugins record keeps the old version after
the pin moves, and /reload-plugins reloads the recorded one, so the reason names
`claude plugin update mw@millwright --scope project` and a restart. A pin with no ref, or a ref
that is not a version tag, keeps the loaded check alone.
Known gap: a process id reused within a day passes; the plugin's session_start.py says why.
"""

import json
import os
import re
import sys
import tempfile

VERSION_TAG = re.compile(r"v(\d+\.\d+\.\d+)")  # the plugin's tags are v<version> (its README, "Rules")


def pin():
    """(the pin's text for a reason, the pinned version or None) from .claude/settings.json."""
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        with open(os.path.join(project, ".claude", "settings.json"), encoding="utf-8") as f:
            source = json.load(f)["extraKnownMarketplaces"]["millwright"]["source"]
        ref = source.get("ref")
        text = f"{source['repo']} at {ref}" if ref else f"{source['repo']} with no ref"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "the ref .claude/settings.json names", None
    tag = VERSION_TAG.fullmatch(ref) if isinstance(ref, str) else None
    return text, tag.group(1) if tag else None


def marker_version(path):
    """The version a marker holds, or None when it holds none or cannot be read."""
    try:
        with open(path, encoding="utf-8") as f:
            version = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and version else None


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    session = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
    folder = os.path.join(tempfile.gettempdir(), "mw-plugin")
    pid = os.environ.get("CLAUDE_PID")
    names = ([session] if session and not set(session) & set("/\\.") else []) + ([f"ppid-{pid}"] if pid else [])
    found = [os.path.join(folder, name) for name in names if os.path.isfile(os.path.join(folder, name))]
    pinned_text, pinned = pin()
    if not found:
        deny(f"The workflow plugin mw@millwright is not loaded in this session, and this repository pins it "
             f"({pinned_text}, in .claude/settings.json). Start Claude Code in this repository's folder and accept the "
             "folder's trust dialog, so Claude Code adds the millwright marketplace and loads the plugin, then "
             "restart the session or run /reload-plugins.")
        return
    if pinned is None:
        return
    loaded = marker_version(found[0])
    if loaded == pinned:
        return
    loaded_text = f"mw {loaded}" if loaded else "an mw whose marker records no version"
    deny(f"This session loaded {loaded_text} and this repository pins mw {pinned} ({pinned_text}, in "
         ".claude/settings.json). Claude Code's installed-plugins record keeps the old version after a pin moves, "
         "and /reload-plugins reloads the recorded version. Run `claude plugin update mw@millwright --scope project` "
         "in this repository's folder, then restart the session.")


if __name__ == "__main__":
    main()
