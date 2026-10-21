"""PreToolUse hook: deny a shell command that stops a process by its name.

Claude Code runs this before Bash and PowerShell. Several sessions share one
machine's process table, so a name matches every session's copy of a program:
on 2026-10-20 one session ran `taskkill /F /IM mw_tests.exe` to end its own
stray run and ended another session's suite, which died with no summary line
(the Millwright engine's documents/gotcha-history.md, 2026-10-20). A prose rule
in the run-tests skill had not stopped it, so this hook makes the rule hold.

Denied, ignoring case: taskkill with /IM or -IM; Stop-Process, spps or kill
with -Name or -ProcessName; Get-Process or gps piped into Stop-Process, spps or
kill; pkill; killall; wmic process where. Passing: a stop by PID
(taskkill /PID, Stop-Process -Id, kill <pid>) and a listing alone
(Get-Process <name>, pgrep <name>). An unreadable payload, or a command field
that is not a string, passes.

Known gap: the hook reads the command's text, so a form it does not list
passes, and a quoted string that only mentions a denied form, such as a commit
message given with -m, is denied too; write such text through a file.
"""

import json
import re
import sys

KILL_BY_NAME = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\btaskkill\b[^\n;&|]*(?<!\S)[/-]im\b",
        r"\b(?:stop-process|spps|kill)\b[^\n;&|]*(?<!\S)-(?:process)?name\b",
        r"\b(?:get-process|gps)\b[^\n;&]*\|\s*(?:stop-process|spps|kill)\b",
        r"\bpkill\b",
        r"\bkillall\b",
        r"\bwmic\s+process\s+where\b",
    )
]

REASON = (
    "This command stops a process by its name, and a name matches every session's copy of that program on this "
    "machine: a kill by image name once ended another session's test suite. Stop only the PID your own command "
    "started: `taskkill /F /PID <pid>`, `Stop-Process -Id <pid>` or `kill <pid>`. `Get-Process <name>` or "
    "`pgrep <name>` alone lists the PIDs."
)


def stops_by_name(command: str) -> bool:
    return any(pattern.search(command) for pattern in KILL_BY_NAME)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not stops_by_name(command):
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": REASON,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
