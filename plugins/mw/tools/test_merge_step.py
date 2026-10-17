"""Checks for tools/merge_step.py: no gh, no network, and git only to find a repository's top level.

Usage:
    python tools/test_merge_step.py [PROJECT]

PROJECT is the repository the checks run against: the folder given, else
CLAUDE_PROJECT_DIR, else the current folder. tools/run_checks.py passes it.
When PROJECT holds .github/workflows/tests.yml, the two checks that the workflow
writes the summary step and the comment the tool reads run against it; otherwise
they print a skipped line.

The pure functions run on literal data. The whole command runs against a fake that answers each
gh and git call from a scenario and records it, so a check can require that a red run, a size-only
run or a moved head never reaches `gh pr merge`. Prints `[test_merge_step] N checks, M failures`
and exits 1 when M is not zero.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("merge_step", PLUGIN / "tools" / "merge_step.py")
PROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
WORKFLOW = PROJECT / ".github" / "workflows" / "tests.yml"
skipped_checks = []
# The scenarios run main, which finds its repository from the current folder. They run inside a temporary
# repository, so the result does not depend on the folder the test starts in.
SCENARIO_REPO = tempfile.mkdtemp(prefix="mw-merge-test-")
subprocess.run(["git", "init", "-q"], cwd=SCENARIO_REPO, check=True, capture_output=True)
os.chdir(SCENARIO_REPO)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)

checks = 0
failures = []


def check(name, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def stop_code(fn, *args):
    try:
        fn(*args)
    except ms.Stop as stop:
        return stop.args[0]
    return None


BRIEF = ("<!-- mw-step-brief: 0b -->\n## Step 0b brief, 2026-10-13\n- Merged: pull request 42; review: none.\n"
         "- Rulings: none.\n- Ambiguities: none.\n- Deferred: none.\n- For the owner: none.\n")
check("brief: the step it names", ms.check_brief(BRIEF, 42), "0b")
for name, text in (("another pull request", BRIEF.replace("42", "43")), ("no marker", BRIEF.split("\n", 1)[1]),
                   ("a heading for another step", BRIEF.replace("## Step 0b", "## Step 1")),
                   ("an item missing", BRIEF.replace("- Deferred: none.\n", "")), ("empty", "")):
    check(f"brief: {name}", stop_code(ms.check_brief, text, 42), 2)

check("stone: a step on the stone", ms.stone_of("step/12-save/0b-x", "stone/12-save"), "stone/12-save")
check("stone: a stacked step", ms.stone_of("step/12-save/2-y", "step/12-save/1-x"), "stone/12-save")
check("stone: the stone's own pull request", stop_code(ms.stone_of, "stone/12-save", "main"), 2)
check("stone: a step into main", stop_code(ms.stone_of, "step/12-save/1-x", "main"), 2)
check("stone: a base of another stone", stop_code(ms.stone_of, "step/12-save/1-x", "stone/11-stat"), 2)


def runs(*items):
    """Runs from (id, status, conclusion) or (id, status, conclusion, summary); the fake fills each head SHA."""
    return [{"databaseId": i[0], "status": i[1], "conclusion": i[2], "createdAt": "2026-10-13T10:00:00Z",
             **({"summary": i[3]} if len(i) > 3 else {})} for i in items]


check("verdict: none", ms.ci_verdict([])[0], "none")
check("verdict: red beside pending", ms.ci_verdict(runs((1, "in_progress", ""), (2, "completed", "failure"))), ("red", [2]))
check("verdict: cancelled is red", ms.ci_verdict(runs((1, "completed", "cancelled")))[0], "red")
check("verdict: pending", ms.ci_verdict(runs((1, "completed", "success"), (2, "queued", ""))), ("pending", [2]))
check("verdict: green names the newest summarised run",
      ms.ci_verdict(runs((1, "completed", "success", True), (2, "completed", "skipped", False))), ("green", [1]))
check("verdict: a red run before a summarised green no longer counts",
      ms.ci_verdict(runs((1, "completed", "failure"), (2, "completed", "success", True))), ("green", [2]))
check("verdict: a red run with a newer run still going waits",
      ms.ci_verdict(runs((1, "completed", "failure"), (2, "in_progress", ""))), ("pending", [2]))
check("verdict: a red run after the summarised green blocks",
      ms.ci_verdict(runs((1, "completed", "success", True), (2, "completed", "failure"), (3, "completed", "success", False))),
      ("red", [2]))
check("verdict: a cancelled run a newer run followed no longer counts",
      ms.ci_verdict(runs((1, "completed", "success", True), (2, "completed", "cancelled"), (3, "completed", "success", False))),
      ("green", [1]))
check("verdict: a run still going after the summarised green does not block",
      ms.ci_verdict(runs((1, "completed", "success", True), (2, "in_progress", ""))), ("green", [1]))
check("verdict: unknown summary", ms.ci_verdict(runs((1, "completed", "success", None))), ("unknown", [1]))
check("verdict: no summary", ms.ci_verdict(runs((1, "completed", "success", False))), ("unbuilt", [1]))
created = ms.datetime.fromisoformat("2026-10-13T10:00:00+00:00").timestamp()
check("queued: ten minutes is the line", [ms.queued_too_long(runs((1, "queued", "")), created + t) for t in (590, 610)], [[], [1]])
check("queued: in progress is not queued", ms.queued_too_long(runs((1, "in_progress", "")), created + 610), [])
SUMMARY = [{"conclusion": "success", "steps": [{"name": ms.SUMMARY_STEP, "conclusion": "success"}]}]
SIZE_ONLY = [{"conclusion": "success", "steps": [{"name": ms.SUMMARY_STEP, "conclusion": "skipped"}]},
             {"conclusion": "skipped", "steps": []}]
EMPTY = [{"conclusion": "success", "steps": []}]
check("summary: written", ms.wrote_summary(SUMMARY), True)
check("summary: skipped on a body edit, beside a skipped job", ms.wrote_summary(SIZE_ONLY), False)
check("summary: an empty step list is unknown", [ms.wrote_summary(EMPTY), ms.wrote_summary([])], [None, None])
if WORKFLOW.is_file():
    check("summary: the workflow still names the step", f"name: {ms.SUMMARY_STEP}" in WORKFLOW.read_text(encoding="utf-8"),
          True)
    check("comment: the workflow still writes the marker and the line",
          [s in WORKFLOW.read_text(encoding="utf-8")
           for s in (f"const marker = '{ms.TESTS_MARK}'", "Commit ${context.payload.pull_request.head.sha.slice(0, 8)}, [run ")],
          [True, True])
else:
    skipped_checks.append(f"the workflow checks: {PROJECT} holds no .github/workflows/tests.yml")


def tests_comment(sha, run_id):
    return {"body": f"{ms.TESTS_MARK}\n## Lint and test suite\n\nCommit {sha[:8]}, [run {run_id}](https://x/runs/{run_id})."}


check("comment: names the head's run", ms.commented_run([tests_comment("a" * 40, 5)], "a" * 40), 5)
check("comment: another commit, or a quote of the marker",
      [ms.commented_run([tests_comment("c" * 40, 5)], "a" * 40),
       ms.commented_run([{"body": "> " + tests_comment("a" * 40, 5)["body"]}], "a" * 40)], [None, None])

ERROR = "error"  # a run list or step list gh fails to read


class Fake:
    """Answers gh and git from a scenario, records every call, and moves a clock instead of sleeping.

    tree is the merge-tree outcome: "same" as the head's tree, "differs", or "conflict"; bases is how many
    merge bases `git merge-base --all` names for the head and the stone branch, or ERROR when the call fails."""

    def __init__(self, run_lists, base="stone/12-save", jobs=SUMMARY, deletes="false", below=True, moved=False,
                 tree="same", comments=(), bases=1):
        self.calls, self.clock, self.merged, self.sleeps = [], created + 60, False, []
        self.run_lists, self.base, self.deletes, self.below, self.moved = run_lists, base, deletes, below, moved
        self.jobs = jobs if isinstance(jobs, tuple) else (jobs,)
        self.tree, self.comments, self.bases = tree, list(comments), bases

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        reply = self.answer(" ".join(cmd))
        code, reply = reply if isinstance(reply, tuple) else (0, reply)
        return subprocess.CompletedProcess(cmd, code, reply if isinstance(reply, str) else json.dumps(reply), "")

    def head(self):  # a pushed merge of the stone makes a new head
        return "b" * 40 if any(c[:2] == ["git", "commit-tree"] for c in self.calls) else "a" * 40

    def answer(self, line):
        if line.startswith("gh api"):
            return self.deletes
        if line.startswith("gh pr view") and "isDraft" in line:
            return {"state": "OPEN", "isDraft": False, "baseRefName": self.base, "headRefName": "step/12-save/2-y",
                    "headRefOid": "a" * 40}
        if line.startswith("gh pr view") and "comments" in line:
            return {"comments": self.comments}
        if line.startswith("gh pr view"):
            return {"headRefOid": "f" * 40 if self.moved else self.head(), "baseRefName": "stone/12-save",
                    "state": "MERGED" if self.merged else "OPEN"}
        if line.startswith("gh pr list"):
            return [{"number": 306}] if "--base main" in line else [{"number": 7}] if "merged" in line and self.below else []
        if line.startswith("gh run list"):
            listed = self.run_lists.pop(0) if len(self.run_lists) > 1 else self.run_lists[0]
            commit = line.split("--commit ")[1].split()[0]
            return (1, "HTTP 502") if listed == ERROR else [{"headSha": commit, **r} for r in listed]
        if line.startswith("gh run view"):
            jobs = self.jobs[0] if len(self.jobs) == 1 else self.jobs[sum(c[:3] == ["gh", "run", "view"] for c in self.calls) - 1]
            return (1, "HTTP 502") if jobs == ERROR else {"jobs": jobs}
        if line.startswith("git merge-tree"):
            return {"same": "t" * 40, "differs": "d" * 40, "conflict": (1, "e" * 40 + "\nsrc/a.cpp\nsrc/b.cpp\n")}[self.tree]
        if line.startswith("git merge-base"):
            if self.bases == ERROR:
                return 1, ""
            return "".join(f"{n}" * 40 + "\n" for n in range(1, self.bases + 1))
        if line.startswith("git rev-parse"):
            return "t" * 40
        if line.startswith("git commit-tree"):
            return "b" * 40
        self.merged = self.merged or line.startswith("gh pr merge")
        return ""


def scenario(fake, brief=BRIEF):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "brief.md"
        path.write_text(brief, encoding="utf-8")
        ms.run, ms.now = fake, lambda: fake.clock

        def sleep(seconds):
            fake.sleeps.append(seconds)
            fake.clock += seconds
        ms.sleep = sleep
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ms.main(["42", "--brief", str(path)])
    return code, [c for c in fake.calls if c[:3] == ["gh", "pr", "merge"]], out.getvalue()


def pushes(fake):
    return [c for c in fake.calls if c[:2] in (["git", "push"], ["git", "commit-tree"])]


GREEN = runs((1, "completed", "success"))
fake = Fake([[], runs((1, "in_progress", "")), GREEN])
code, merges, _ = scenario(fake)
check("green: exit after waiting", code, 0)
check("green: one merge commit at the head CI passed", merges, [["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "a" * 40]])
posts = [i for i, c in enumerate(fake.calls) if c[:3] == ["gh", "pr", "comment"]]
check("green: the brief goes to the stone's pull request, after the merge",
      [fake.calls[i][3] for i in posts if i > fake.calls.index(merges[0])], ["306"])
check("never squash, rebase, delete or force", [c for c in fake.calls if set(c) & {
      "--squash", "--rebase", "--delete-branch", "-d", "--force", "-f"}], [])
code, merges, said = scenario(Fake([runs((1, "completed", "success"), (2, "completed", "failure"))]))
check("red: exit, no merge, the run named", (code, merges, "run 2" in said), (1, [], True))
check("size only: no merge", scenario(Fake([GREEN], jobs=SIZE_ONLY))[:2], (2, []))
check("queued: no merge", scenario(Fake([runs((1, "queued", ""))]))[:2], (2, []))
check("no run: no merge", scenario(Fake([[]]))[:2], (2, []))
check("moved head: no merge", scenario(Fake([GREEN], moved=True))[:2], (2, []))
check("deletes on merge: no merge", scenario(Fake([GREEN], deletes="true"))[:2], (2, []))
fake = Fake([GREEN])
check("bad brief: stops before any call", (scenario(fake, BRIEF.replace("42", "41"))[0], fake.calls), (2, []))

fake = Fake([GREEN], base="step/12-save/1-x", below=False)
check("stacked, below open: no retarget", (scenario(fake)[0], [c for c in fake.calls if c[:3] == ["gh", "pr", "edit"]]), (2, []))
fake = Fake([GREEN], base="step/12-save/1-x", tree="differs")
code, merges, _ = scenario(fake)
check("stacked: exit", code, 0)
check("stacked: retarget, merge the stone in, push the step branch, merge the new head", [
    c for c in fake.calls if c[:3] in (["gh", "pr", "edit"], ["git", "push", "origin"]) or c[:2] == ["git", "commit-tree"]
    or c[:3] == ["gh", "pr", "merge"]], [
    ["gh", "pr", "edit", "42", "--base", "stone/12-save"],
    ["git", "commit-tree", "d" * 40, "-p", "a" * 40, "-p", "origin/stone/12-save", "-m",
     "Merge branch 'stone/12-save' into step/12-save/2-y"],
    ["git", "push", "origin", "b" * 40 + ":refs/heads/step/12-save/2-y"],
    ["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "b" * 40]])
check("stacked: waits on the new head", ["gh", "run", "list", "--commit", "b" * 40] in [c[:5] for c in fake.calls], True)

# The fast path: the stone brings nothing the head lacks, and the comment names a green run on the head.
fake = Fake([runs((1, "completed", "success"), (2, "in_progress", ""))], base="step/12-save/1-x",
            jobs=ERROR, comments=[tests_comment("a" * 40, 1)])
code, merges, said = scenario(fake)
check("fast path: merged at once at the head, nothing pushed, no wait, no step list read",
      (code, merges, pushes(fake), fake.sleeps, [c for c in fake.calls if c[:3] == ["gh", "run", "view"]]),
      (0, [["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "a" * 40]], [], [], []))
fake = Fake([GREEN], tree="differs")
code, merges, _ = scenario(fake)
check("fast path refused, a differing tree: a step that is not stacked gets the merge pushed and waits on it",
      (code, len(pushes(fake)), merges[0][-1]), (0, 2, "b" * 40))
fake = Fake([runs((1, "in_progress", "")), GREEN])
code, merges, _ = scenario(fake)
check("fast path refused, no green run on the head: waits, pushes nothing",
      (code, merges[0][-1], pushes(fake), len(fake.sleeps)), (0, "a" * 40, [], 1))
# Two merge bases: the step merged the stone branch in while its step below was open.
fake = Fake([GREEN], base="step/12-save/1-x", bases=2, comments=[tests_comment("a" * 40, 1)])
code, merges, said = scenario(fake)
check("two bases, an unchanged tree: the merge is pushed, CI on the new head waited for, the new head merged",
      (code, pushes(fake), ["gh", "run", "list", "--commit", "b" * 40] in [c[:5] for c in fake.calls], merges,
       "2 merge bases" in said),
      (0, [["git", "commit-tree", "t" * 40, "-p", "a" * 40, "-p", "origin/stone/12-save", "-m",
            "Merge branch 'stone/12-save' into step/12-save/2-y"],
           ["git", "push", "origin", "b" * 40 + ":refs/heads/step/12-save/2-y"]],
       True, [["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "b" * 40]], True))
fake = Fake([GREEN], base="step/12-save/1-x", comments=[tests_comment("a" * 40, 1)])
code, merges, said = scenario(fake)
check("one base, an unchanged tree: the bases are read, nothing is pushed, the head CI passed merges",
      (code, [c[:3] for c in fake.calls if c[:2] == ["git", "merge-base"]], pushes(fake), merges),
      (0, [["git", "merge-base", "--all"]], [], [["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "a" * 40]]))
fake = Fake([GREEN], base="step/12-save/1-x", bases=ERROR, comments=[tests_comment("a" * 40, 1)])
code, merges, said = scenario(fake)
check("a failed merge-base call, an unchanged tree: exit 2, nothing pushed, nothing merged, the call named",
      (code, pushes(fake), merges, "could not find the merge bases" in said), (2, [], [], True))
fake = Fake([GREEN], tree="conflict")
code, merges, said = scenario(fake)
check("conflict: stops before any push or wait, the files named",
      (code, merges, pushes(fake), [c for c in fake.calls if c[:3] == ["gh", "run", "list"]], "src/a.cpp, src/b.cpp" in said),
      (2, [], [], [], True))
fake = Fake([[*runs((2, "completed", "success")), {"headSha": "c" * 40, **runs((3, "completed", "failure"))[0]}]])
check("a red run on a superseded head does not block", scenario(fake)[:2],
      (0, [["gh", "pr", "merge", "42", "--merge", "--match-head-commit", "a" * 40]]))
fake = Fake([ERROR, ERROR, GREEN])
check("a gh error polls with backoff as unknown", (scenario(fake)[0], fake.sleeps), (0, [40, 80]))
fake = Fake([GREEN], jobs=(EMPTY, EMPTY, SUMMARY))
check("an empty step list polls as unknown, not as no run built", (scenario(fake)[0], fake.sleeps), (0, [40, 80]))
code, merges, said = scenario(Fake([ERROR]))
check("a gh error to the overall limit: no merge, never no run built", (code, merges, "not done" in said), (2, [], True))

# The root is the git top level of the caller's folder, not the tool's checkout. Outside a repository main stops
# before any gh or git call reaches the fake.
with tempfile.TemporaryDirectory() as folder:
    repo = Path(folder).resolve() / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    check("root: a subfolder resolves to its git top level", ms.repo_root(repo / "sub").resolve(), repo)
    outside = Path(folder).resolve() / "outside"
    outside.mkdir()
    previous, saved_ceiling = os.getcwd(), os.environ.get("GIT_CEILING_DIRECTORIES")
    try:
        os.chdir(repo / "sub")
        code = scenario(Fake([GREEN]))[0]
        check("root: main works in the caller's repository", (code, ms.ROOT.resolve()), (0, repo))
        os.environ["GIT_CEILING_DIRECTORIES"] = str(Path(folder).resolve())
        os.chdir(outside)
        fake = Fake([GREEN])
        code, merges, said = scenario(fake)
        check("root: outside any repository main stops before any call",
              (code, fake.calls, "is in no git repository" in said), (2, [], True))
    finally:
        os.chdir(previous)
        if saved_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = saved_ceiling

for line in failures:
    print(f"FAIL {line}")
for line in skipped_checks:
    print(f"[test_merge_step] skipped {line}")
print(f"[test_merge_step] {checks} checks, {len(failures)} failures")
os.chdir(PLUGIN)
shutil.rmtree(SCENARIO_REPO, ignore_errors=True)
sys.exit(1 if failures else 0)
