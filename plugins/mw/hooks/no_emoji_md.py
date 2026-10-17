"""PostToolUse hook: fail a write that puts an emoji into a tracked .md file.

Claude Code runs this after Edit, Write and MultiEdit. No emoji or emoticons
in .md files (CLAUDE.md "Workflow Rules"). Exit code 2 reports the message
back to the agent, which then removes the character. Code points checked: the
emoji and pictograph blocks (U+1F000 to U+1FAFF), the miscellaneous symbols
and dingbats blocks (U+2600 to U+27BF), the miscellaneous symbols and arrows
block (U+2B00 to U+2BFF), the clocks, media and geometric symbols that render
as emoji (U+2328, U+231A, U+231B, U+23CF, U+23E9 to U+23F3, U+23F8 to U+23FA,
U+25AA, U+25AB, U+25B6, U+25C0, U+25FD, U+25FE, U+2934, U+2935), the keycap
combiner U+20E3, the handful of emoji scattered elsewhere
(U+203C, U+2049, U+2139, U+24C2, U+3030, U+303D, U+3297, U+3299), and the
emoji variation selector U+FE0F. Text symbols inside those blocks that a
document may legitimately use pass: the check marks, crosses and ballot boxes
(U+2610 to U+2612, U+2713, U+2714, U+2717, U+2718), the card suits (U+2660
to U+2667), the stars (U+2605, U+2606) and the quotation dingbats (U+275B to
U+275E). Plain arrows, box drawing and typographic punctuation are outside
the ranges and pass. Text emoticons such as a colon and a bracket are not
checked; a regular expression for them has too many false positives in prose
about code.

Only files under the project directory are checked. A scratch file outside it
is not a tracked doc and no rule covers it.

Known gap: the matcher covers Edit, Write and MultiEdit. A shell redirect into
a .md file is not intercepted. The prose rule and the adversarial review cover
that path.
"""

import json
import os
import sys


SCATTERED = {0x203C, 0x2049, 0x2139, 0x24C2, 0x3030, 0x303D, 0x3297, 0x3299, 0xFE0F, 0x20E3}
SCATTERED |= {0x2328, 0x231A, 0x231B, 0x23CF, 0x25AA, 0x25AB, 0x25B6, 0x25C0, 0x25FD, 0x25FE, 0x2934, 0x2935}
SCATTERED |= set(range(0x23E9, 0x23F4)) | set(range(0x23F8, 0x23FB))
TEXT_SYMBOLS = {0x2610, 0x2611, 0x2612, 0x2713, 0x2714, 0x2717, 0x2718} | set(range(0x2660, 0x2668))
# The black and white stars and the quotation dingbats render as text (documents/known-issues.md, found 2026-10-08).
TEXT_SYMBOLS |= {0x2605, 0x2606} | set(range(0x275B, 0x275F))


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    if cp in TEXT_SYMBOLS:
        return False
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2B00 <= cp <= 0x2BFF
        or cp in SCATTERED
    )


def under_project(path: str) -> bool:
    root = os.path.normcase(os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    full = os.path.normcase(os.path.abspath(path))
    return full == root or full.startswith(root + os.sep)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.lower().endswith(".md") or not under_project(path):
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    hits = []
    for number, line in enumerate(lines, start=1):
        for ch in line:
            if is_emoji(ch):
                hits.append(f"{path}:{number}: U+{ord(ch):04X} {ch!r}")
                break
    if not hits:
        return
    sys.stderr.write(
        "No emoji in .md files (CLAUDE.md Workflow Rules). Remove these characters:\n"
        + "\n".join(hits)
        + "\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
