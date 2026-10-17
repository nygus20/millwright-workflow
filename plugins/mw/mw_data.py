"""The loader of a repository's workflow data file, .claude/mw.json.

The data file holds what differs between two repositories that share one way of
working: the guarded files and folders, the scratch patterns, the review tool's
costly paths and the rest of the review section. This loader is the one reader
of it. It sits at the plugin's root: the guard hook and the scratch hook under
hooks/ and the review tool under tools/ each load it from there. The move list in
the Millwright engine's documents/findings/stone-19-workflow-plugin-2026-10-17.md
records how it came from the engine's .claude/hooks/.

load(root) returns the file's object with the review section's defaults filled
in, or raises DataFileError naming what is wrong: a missing file, a file that is
not JSON, an unknown version, a missing required key or a value of the wrong
type. load_or_exit(root) is the form a hook or a tool calls: it prints the
reason on stderr and exits 2, which stops a hook's tool call and hands the
reason to the agent, and which a tool's caller reads as a refusal.

guard_lists(data) gives the guard hook's files, lower case because Windows
paths ignore case, and folders. The data file itself always joins the files,
whatever the file lists, so an edit to the data file cannot drop its own guard.
"""

import json
import sys
from pathlib import Path

DATA_FILE = ".claude/mw.json"
VERSION = 1

# The review section's defaults: the values a repository with the engine's layout would write.
REVIEW_DEFAULTS = {
    "profiles": {"stone": ["claude-fable-5-1", "high"], "costly": ["claude-fable-5-1", "high"],
                 "step": ["claude-opus-5-5", "high"]},
    "allowed_tools": [],
    "roadmap": "ROADMAP.md",
    "plan_sentence": "Its plan is `(documents/plans/[\\w.-]+\\.md)`",
    "invariants": {"file": "CLAUDE.md", "heading": "Load-Bearing Invariants"},
    "path_sources": ["CLAUDE.md", "AGENTS.md", "documents/README.md", "the skills"],
    "findings_folder": "documents/findings/",
}


class DataFileError(Exception):
    """What is wrong with a repository's data file, as one sentence the agent reads."""


def _require(obj, key, kind, where):
    if not isinstance(obj, dict) or key not in obj:
        raise DataFileError(f"{DATA_FILE} lacks the required key {where}{key}")
    value = obj[key]
    if kind is list and not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
        raise DataFileError(f"{DATA_FILE} key {where}{key} must be a list of strings")
    if kind is not list and not isinstance(value, kind):
        raise DataFileError(f"{DATA_FILE} key {where}{key} must be a {kind.__name__}")
    return value


def load(root):
    """The data file of the repository at root, with the review defaults filled in; raises DataFileError."""
    path = Path(root) / DATA_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise DataFileError(f"{DATA_FILE} is missing from {root}: the workflow reads its lists from it") from None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise DataFileError(f"{DATA_FILE} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise DataFileError(f"{DATA_FILE} must hold one JSON object")
    version = data.get("version")
    if type(version) is not int or version != VERSION:
        raise DataFileError(f"{DATA_FILE} has version {version!r}; this loader reads version {VERSION}")
    _require(data, "repository", str, "")
    _require(data, "worktrees", str, "")
    guard = _require(data, "guard", dict, "")
    _require(guard, "files", list, "guard.")
    _require(guard, "folders", list, "guard.")
    _require(data, "scratch_patterns", list, "")
    review = _require(data, "review", dict, "")
    rows = _require(review, "costly_paths", object, "review.")  # its rows are objects, checked below
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get("pattern"), str) and
                                             isinstance(row.get("reason"), str) for row in rows):
        raise DataFileError(f"{DATA_FILE} key review.costly_paths must be a list of objects with a pattern and a "
                            "reason")
    for key, default in REVIEW_DEFAULTS.items():
        review.setdefault(key, json.loads(json.dumps(default)))  # a copy, so no caller edits the defaults
    return data


def load_or_exit(root):
    """load(root), or the reason on stderr and exit 2."""
    try:
        return load(root)
    except DataFileError as error:
        sys.stderr.write(f"{error}\n")
        sys.exit(2)


def guard_lists(data):
    """(the guarded files in lower case, with the data file always among them; the guarded folders in lower case)."""
    files = {name.lower() for name in data["guard"]["files"]} | {DATA_FILE}
    folders = tuple(name.lower() for name in data["guard"]["folders"])
    return files, folders
