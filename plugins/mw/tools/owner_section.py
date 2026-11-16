"""Check the section "For the owner" that opens a stone's plan or its closing summary.

Usage:
    python "${CLAUDE_PLUGIN_ROOT}/tools/owner_section.py" plan FILE [--root FOLDER]
    python "${CLAUDE_PLUGIN_ROOT}/tools/owner_section.py" summary FILE [--root FOLDER]

FILE holds the plan or the summary as Markdown. The tool only reads, so a session in plan mode may
run it. The owner reads this one section and may skip the rest of the text, so the tool refuses a
text whose section a cold reader could not use. The `mw:start-stone` skill gives the section's
rules, and the `mw:close-stone` skill the summary's two differences. The checks:
1. A heading "For the owner", of level 2 or 3, exists. Only the text's title, other headings, blank
   lines and HTML comments, such as a record's marker, stand above it.
2. The section ends with the line "Everything below this line is for the agents.", and no heading
   stands between the section's heading and that line.
3. Each part opens a line with its label in bold, in order. A plan holds "What changes.", "The
   decisions." and "The impact."; a summary holds "What changed.", "The decisions.", "Against the
   plan." and "The impact.". No part is empty.
4. The impact part holds one line `- <name>: <text>` per name under `owner_section.impact` in the
   repository's .claude/mw.json. A repository without the key gets three to five lines of the
   author's own choosing.
5. The section holds at most 300 words.
6. The section holds no backtick, no file name with a source or data extension, no identifier
   joined by underscores and no call form such as `name()`. A link's address is not read.

The tool cannot judge whether a sentence is clear, whether a term is explained or whether a stone is
named by its title. Those rules stay the author's.

FOLDER is the repository whose data file gives the impact names: the folder given, else the git
top level of the caller's folder, else the caller's folder.

Exit code: 0 the section passes, with one line giving its word count; 1 the section breaks a check,
with one line per problem; 2 the file or the data file could not be read.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))
import mw_data  # noqa: E402  (it sits at the plugin's root)

HEADING = re.compile(r"^#{2,3} For the owner\s*$")
ANY_HEADING = re.compile(r"^#{1,6} ")
COMMENT = re.compile(r"^<!--.*-->$")
END_LINE = "Everything below this line is for the agents."
IMPACT_LABEL = "The impact."
PARTS = {"plan": ("What changes.", "The decisions.", IMPACT_LABEL),
         "summary": ("What changed.", "The decisions.", "Against the plan.", IMPACT_LABEL)}
# The cap in words. The game's results-screen stone, sketched in this form with three decisions and five
# impact lines, came to about 200 words; the room above that is for a stone with more decisions.
WORD_CAP = 300
OWN_LINES = (3, 5)  # the impact lines of a repository whose data file names none
WORD = re.compile(r"\S*\w\S*")
URL = re.compile(r"https?://\S+")
CODE_NAME = re.compile(r"\b[\w-]+\.(?:c|cc|cpp|h|hpp|py|toml|json|md|bat|sh|yml|yaml|cmake|txt|js|ts|gd)\b"
                       r"|\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b|\b\w+\(\)")


def problems(text, kind, impact):
    """The problems of the section in text, each one sentence; kind is "plan" or "summary", and impact
    lists the names the impact part must hold, or is empty when the repository names none."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
    if start is None:
        return ['the text has no heading "For the owner"']
    found = []
    above = next((i for i in range(start) if lines[i].strip() and not ANY_HEADING.match(lines[i])
                  and not COMMENT.match(lines[i].strip())), None)
    if above is not None:
        found.append(f"line {above + 1} stands above the section, which opens the text under its title")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == END_LINE), None)
    if end is None:
        return found + [f'the section lacks its end line, "{END_LINE}"']
    body = lines[start + 1:end]
    inner = next((line for line in body if ANY_HEADING.match(line)), None)
    if inner is not None:
        return found + [f'the heading "{inner.strip()}" stands inside the section, above its end line']

    labels = PARTS[kind]
    at = {label: next((i for i, line in enumerate(body) if line.startswith(f"**{label}**")), None) for label in labels}
    found += [f'the section lacks the part "{label}"' for label in labels if at[label] is None]
    present = [label for label in labels if at[label] is not None]
    if [at[label] for label in present] != sorted(at[label] for label in present):
        found.append("the parts stand out of order: " + ", ".join(sorted(present, key=at.get)))
    bounds = sorted(at[label] for label in present) + [len(body)]
    part = {}
    for label in present:
        stop = bounds[bounds.index(at[label]) + 1]
        part[label] = [body[at[label]][len(label) + 4:]] + body[at[label] + 1:stop]
        if not WORD.search(" ".join(part[label])):
            found.append(f'the part "{label}" is empty')

    bullets = [line for line in part.get(IMPACT_LABEL, []) if line.startswith("- ")]
    if IMPACT_LABEL in part and impact:
        found += [f'the impact part lacks the line "- {name}: ..."' for name in impact
                  if not any(re.match(rf"- {re.escape(name)}: .*\w", line) for line in bullets)]
    elif IMPACT_LABEL in part and not impact and not OWN_LINES[0] <= len(bullets) <= OWN_LINES[1]:
        found.append(f"the impact part holds {len(bullets)} lines, not {OWN_LINES[0]} to {OWN_LINES[1]}")

    words = sum(len(WORD.findall(line)) for line in body)
    if words > WORD_CAP:
        found.append(f"the section holds {words} words, over the cap of {WORD_CAP}")
    for number, line in enumerate(body, start + 2):
        if "`" in line:
            found.append(f"line {number} holds code formatting")
        name = CODE_NAME.search(URL.sub("", line.replace("`", " ")))
        if name:
            found.append(f'line {number} names "{name.group(0)}", which reads as a file or an identifier')
    return found


def word_count(text):
    """The words of the section in text, or 0 when the section does not parse."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
    end = next((i for i in range((start or 0) + 1, len(lines)) if lines[i].strip() == END_LINE), None)
    if start is None or end is None:
        return 0
    return sum(len(WORD.findall(line)) for line in lines[start + 1:end])


def repository(folder):
    """The git top level of folder, or folder itself outside a repository."""
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=folder)
    except OSError:
        return Path(folder)
    return Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else Path(folder)


def main(argv):
    parser = argparse.ArgumentParser(prog="owner_section.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", choices=sorted(PARTS))
    parser.add_argument("file")
    parser.add_argument("--root")
    args = parser.parse_args(argv[1:])
    try:
        text = Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"[owner_section] {args.file} could not be read: {error}")
        return 2
    root = Path(args.root) if args.root else repository(Path.cwd())
    impact = mw_data.load_or_exit(root).get("owner_section", {}).get("impact", [])
    found = problems(text, args.kind, impact)
    for line in found:
        print(f"[owner_section] {line}")
    if found:
        print(f"[owner_section] the {args.kind}'s section is refused for the lines above")
        return 1
    print(f"[owner_section] the {args.kind}'s section passes: {word_count(text)} words of {WORD_CAP}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
