"""Run the plugin's three tests against one repository and print one summary line per test.

Usage:
    python tools/run_checks.py [FOLDER]
    python tools/run_checks.py --template

FOLDER is the repository to check: the folder given, else CLAUDE_PROJECT_DIR,
else the current folder. --template checks a temporary folder that holds only
templates/mw.json as its .claude/mw.json, which is what the marketplace's CI runs.

It first loads the folder's .claude/mw.json through mw_data.py, and a data file
the loader refuses prints the reason and exits 1 before any test runs. Then it
runs tools/test_hooks.py, tools/test_review_pr.py and tools/test_merge_step.py
with this interpreter, each with the folder as its argument, and prints each
test's FAIL lines, its skipped lines and its summary line,
`[test_x] N checks, M failures`. A test that prints no summary line gets one
naming its exit code. The last line is `[run_checks] N tests, M failed against
<folder>`. Exit 0 when every test passed, 1 otherwise.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
TESTS = ["test_hooks.py", "test_review_pr.py", "test_merge_step.py"]
TIMEOUT_SECONDS = 600  # the hook test starts some two hundred processes; a slow Windows machine took about a minute

sys.path.insert(0, str(PLUGIN))
import mw_data  # noqa: E402  (it sits at the plugin's root)


def run_test(name, folder):
    """(passed, the lines to print) for one test run against folder."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(folder)}
    tag = f"[{name[:-3]}]"
    try:
        proc = subprocess.run([sys.executable, str(PLUGIN / "tools" / name), str(folder)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, cwd=folder, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, [f"{tag} hung past {TIMEOUT_SECONDS} s"]
    lines = [line for line in proc.stdout.splitlines() if line.startswith("FAIL ") or line.startswith(f"{tag} skipped")]
    summary = [line for line in proc.stdout.splitlines() if line.startswith(f"{tag} ") and " checks, " in line]
    if not summary:
        lines += [line for line in proc.stderr.splitlines()[-5:]]
        summary = [f"{tag} exited {proc.returncode} without a summary line"]
    return proc.returncode == 0, lines + summary[-1:]


def check(folder):
    try:
        mw_data.load(folder)
    except mw_data.DataFileError as error:
        print(f"[run_checks] {folder}: {error}")
        return 1
    failed = 0
    for name in TESTS:
        passed, lines = run_test(name, folder)
        failed += not passed
        for line in lines:
            print(line)
    print(f"[run_checks] {len(TESTS)} tests, {failed} failed against {folder}")
    return 1 if failed else 0


def main(argv):
    if argv[1:] == ["--template"]:
        folder = Path(tempfile.mkdtemp(prefix="mw-template-"))
        try:
            (folder / ".claude").mkdir()
            shutil.copyfile(PLUGIN / "templates" / "mw.json", folder / ".claude" / "mw.json")
            return check(folder)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    if len(argv) > 2 or (len(argv) == 2 and argv[1].startswith("-")):
        print(__doc__.split("\n\n")[1])
        return 2
    folder = Path(argv[1] if len(argv) == 2 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    return check(folder)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
