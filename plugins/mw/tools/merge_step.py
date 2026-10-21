"""Merge a step's pull request into its stone branch once CI is green, then post the step's brief.

Usage:
    python "${CLAUDE_PLUGIN_ROOT}/tools/merge_step.py" <pr-number> --brief FILE

One command does a step's merge mechanics (the owner's ruling of 2026-10-13). In order:
1. It refuses a brief that breaks the form of documents/process/agent-rulings.md, "The
   records", before any gh call; a pull request that is closed, a draft, or not a step
   (head `step/<slug>/<step>`, base `stone/<slug>` or a step of it); a stone with no open
   pull request to main; and a repository that deletes head branches on merge, because
   GitHub closes a pull request whose base branch is deleted.
2. A stacked step's step below must have merged. The tool retargets the step to `stone/<slug>`.
3. For every step, stacked or not, it computes the merge of `origin/stone/<slug>` into the head
   with `git merge-tree --write-tree`, with no worktree and no push. A conflict stops it here
   with the files named, before any push or CI wait. When the merge's tree equals the head's
   tree and `git merge-base --all` names one base, it pushes nothing: the stone branch brings
   nothing the head lacks, so the tree CI judged on the head is the tree that merges, and a
   green run already there merges at once (the fast path, the owner's ruling of 2026-10-14).
   Otherwise it pushes the merge commit and waits for CI on it, so CI judges the step together
   with every sibling that merged meanwhile. An unchanged tree with two or more bases still
   pushes: a step that merged the stone branch in while its step below was open keeps two bases
   after that step lands, and CI's three-dot diff reads the older one and counts the step
   below's lines as the step's (documents/gotcha-history.md, "a stacked step's size check
   counted the step below"). The pushed merge leaves one base. The fetch and the push run again,
   up to three tries, when git names a ref lock, because every worktree shares one .git.
4. It waits for CI on the head. Only runs whose head SHA is the head count. The newest green
   run that wrote the result summary decides, as a build or a "no code path changed" run does
   and a label or body edit's run does not, and a run still going after it does not block. A
   red run blocks unless a newer run is still going or wrote the summary green, or it was
   cancelled and any newer run followed it. The signal is the build job's `mw-tests` comment,
   which names the commit and the run it summarised: with that run ended `success`, the
   summary was written. GitHub posts it as the run ends, where the job step list lagged up to
   25 minutes in Stone 12, so the step list decides only a run the comment does not name. A gh
   error or an empty step list reads as unknown and polls with backoff up to the overall
   limit, never as "no run built". It stops on a red run, on a run queued past ten minutes
   (documents/process/ci-runner.md, "When a run stays queued"), on no run after three
   minutes, and on green runs that all show no summary.
5. It merges with a merge commit, only at the head CI passed (`--match-head-commit`).
6. It posts the brief on the stone's pull request and prints it. It never squashes, deletes
   a branch or force-pushes, so a step stacked on the merged one keeps its base.

The repository is the git top level of the caller's folder, not the folder this tool sits in, so
the plugin's copy merges the repository it is run from. A folder outside a repository stops it.

Exit code: 0 merged and the brief posted; 1 a run on the head is red, nothing merged;
2 stopped before the merge, with a line saying why; 3 merged, but the brief did not post.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = None  # the repository: main sets it to the git top level of the caller's folder
STEP_BRANCH = re.compile(r"^step/([^/]+)/[^/]+$")
BRIEF_MARK = re.compile(r"^<!-- mw-step-brief: (\S+) -->$")
BRIEF_ITEMS = ("- Merged:", "- Rulings:", "- Ambiguities:", "- Deferred:", "- For the owner:")
GREEN = ("success", "skipped")
# The step of the workflow's build job that writes the comment: it runs on a build, a docs-only run and a
# run that says no code path changed, and skips on a label or body edit, which checks only the size.
SUMMARY_STEP = "Write the result summary"
# The comment the build job's next step posts under the same condition, and the line naming its commit and run.
TESTS_MARK = "<!-- mw-tests -->"
TESTS_LINE = re.compile(r"^Commit ([0-9a-f]{8}), \[run (\d+)\]", re.M)
POLL_SECONDS = 20
MAX_POLL_SECONDS = 160  # the backoff's ceiling while GitHub's reply is unknown
NO_RUN_SECONDS = 180  # GitHub lists a pull request's run within seconds of the push
QUEUED_SECONDS = 600  # documents/process/ci-runner.md: a run queued past ten minutes gets the runner check
WAIT_SECONDS = 3600  # twice the build job's 30-minute limit, so a queued start still fits
# Every worktree of a repository shares one .git, so two fetches, or a fetch and a push, race on one ref file.
REF_LOCK = re.compile(r"cannot lock ref|Unable to create .*\.lock|unable to update local ref", re.IGNORECASE)
GIT_LOCK_TRIES = 3
GIT_LOCK_SECONDS = (2, 5)  # the pauses before the second and the third try: another session's fetch takes seconds


def run(cmd, cwd=None):
    return subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd or ROOT)


sleep = time.sleep
now = time.time


def git_retrying(cmd):
    """Run a git command, rerunning it while its stderr names a ref lock, up to GIT_LOCK_TRIES tries in all.

    Any other failure, and the last locked try, returns at once. A push that landed on the remote and failed only its
    local ref update succeeds on the rerun, which pushes nothing."""
    for attempt in range(GIT_LOCK_TRIES):
        proc = run(cmd)
        if proc.returncode == 0 or not REF_LOCK.search(proc.stderr or "") or attempt == GIT_LOCK_TRIES - 1:
            return proc
        pause = GIT_LOCK_SECONDS[min(attempt, len(GIT_LOCK_SECONDS) - 1)]
        print(f"[merge_step] {' '.join(cmd[:2])} met a ref lock; try {attempt + 2} of {GIT_LOCK_TRIES} in {pause} s")
        sleep(pause)
    return proc


class Stop(Exception):
    """Stop(code, line): the exit code and the line that says why."""


def repo_root(cwd=None):
    """The git top level of cwd, the caller's folder by default; a folder outside a repository raises Stop."""
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True, capture_output=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise Stop(2, f"{Path(cwd or '.').resolve()} is in no git repository: {proc.stderr.strip()}")
    return Path(proc.stdout.strip())


def gh(args, what):
    proc = run(["gh"] + args)
    if proc.returncode != 0:
        raise Stop(2, f"could not {what}: {proc.stderr.strip()}")
    return proc.stdout


def gh_json(args, what):
    try:
        return json.loads(gh(args, what))
    except json.JSONDecodeError:
        raise Stop(2, f"could not {what}: the reply is not JSON") from None


def gh_try(args):
    """The JSON reply of a gh call, or None when gh fails or the reply is not JSON: unknown, never absent."""
    proc = run(["gh"] + args)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def check_brief(text, pr):
    """The step named by a brief in the form of documents/process/agent-rulings.md, else a Stop."""
    lines = text.splitlines()
    mark = BRIEF_MARK.match(lines[0]) if lines else None
    if not mark:
        raise Stop(2, "the brief's first line is not `<!-- mw-step-brief: N -->`")
    step = mark.group(1)
    if len(lines) < 2 or not lines[1].startswith(f"## Step {step} brief, "):
        raise Stop(2, f"the brief's second line is not `## Step {step} brief, <date>`")
    for item in BRIEF_ITEMS:
        if not any(line.startswith(item) for line in lines):
            raise Stop(2, f"the brief has no `{item}` line")
    if not re.search(rf"^- Merged: pull request {pr}\b", text, re.M):
        raise Stop(2, f"the brief's Merged line does not name pull request {pr}")
    return step


def stone_of(head, base):
    """The stone branch a step's pull request merges into, else a Stop."""
    found = STEP_BRANCH.match(head)
    if not found:
        raise Stop(2, f"the head branch {head} is not a step branch, step/<slug>/<step>")
    stone = f"stone/{found.group(1)}"
    if base != stone and not base.startswith(f"step/{found.group(1)}/"):
        raise Stop(2, f"the base branch {base} is neither {stone} nor a step of it")
    return stone


def ci_verdict(runs):
    """("none"|"red"|"green"|"pending"|"unknown"|"unbuilt", the run ids that decide it) for one head's runs.

    A green run's "summary" key is True when it wrote the result summary, False when it did not, and
    absent or None while unknown."""
    if not runs:
        return "none", []
    runs = sorted(runs, key=lambda r: r["databaseId"])
    done = [r for r in runs if r["status"] == "completed"]
    good = [r["databaseId"] for r in done if r["conclusion"] in GREEN and r.get("summary") is True]

    def superseded(r):
        later = [x for x in runs if x["databaseId"] > r["databaseId"]]
        return (r["conclusion"] == "cancelled" and bool(later)) or any(
            x["status"] != "completed" or x["databaseId"] in good for x in later)

    red = [r["databaseId"] for r in done if r["conclusion"] not in GREEN and not superseded(r)]
    if red:
        return "red", red
    if good:
        return "green", good[-1:]
    pending = [r["databaseId"] for r in runs if r["status"] != "completed"]
    if pending:
        return "pending", pending
    unknown = [r["databaseId"] for r in done if r["conclusion"] in GREEN and r.get("summary") is None]
    return ("unknown", unknown) if unknown else ("unbuilt", [r["databaseId"] for r in done])


def queued_too_long(runs, at):
    """The ids of the runs still queued QUEUED_SECONDS after GitHub created them."""
    return [r["databaseId"] for r in runs if r["status"] in ("queued", "waiting", "pending", "requested")
            and at - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")).timestamp() > QUEUED_SECONDS]


def wrote_summary(jobs):
    """True when a step list shows the summary written; None while a finished job's step list is empty."""
    if any(s.get("name") == SUMMARY_STEP and s.get("conclusion") == "success" for j in jobs for s in j.get("steps", [])):
        return True
    if not jobs or any(not j.get("steps") and j.get("conclusion") in ("success", "failure") for j in jobs):
        return None
    return False


def commented_run(comments, head):
    """The run id the build job's `mw-tests` comment names for the head, else None."""
    for comment in comments:
        body = comment.get("body") or ""
        found = TESTS_LINE.search(body) if body.startswith(TESTS_MARK) else None
        if found and head.startswith(found.group(1)):
            return int(found.group(2))
    return None


def ci_state(pr, head):
    """(verdict, run ids, runs) for the runs whose head SHA is the head; "unknown" when gh fails."""
    runs = gh_try(["run", "list", "--commit", head, "--json", "databaseId,headSha,status,conclusion,createdAt"])
    if not isinstance(runs, list):
        return "unknown", [], []
    runs = [r for r in runs if r.get("headSha") == head]
    green = sorted((r for r in runs if r["status"] == "completed" and r["conclusion"] in GREEN),
                   key=lambda r: -r["databaseId"])
    if green:
        reply = gh_try(["pr", "view", str(pr), "--json", "comments"])
        commented = commented_run(reply.get("comments", []) if isinstance(reply, dict) else [], head)
        for r in green:  # newest first, up to the first that wrote the summary
            if r["databaseId"] == commented or r["conclusion"] == "skipped":
                r["summary"] = r["conclusion"] != "skipped"
            else:
                jobs = gh_try(["run", "view", str(r["databaseId"]), "--json", "jobs"])
                r["summary"] = wrote_summary(jobs.get("jobs", [])) if isinstance(jobs, dict) else None
            if r["summary"]:
                break
    return *ci_verdict(runs), runs


def merge_stone_in(branch, sha, stone):
    """Merge origin/<stone> into the head with no worktree, pushing a merge that changes the tree or leaves one base."""
    fetched = git_retrying(["git", "fetch", "origin", branch, stone])
    if fetched.returncode != 0:
        raise Stop(2, f"could not fetch {branch} and {stone}: {fetched.stderr.strip()}")
    merged = run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", sha, f"origin/{stone}"])
    lines = merged.stdout.splitlines()
    if merged.returncode == 1:
        raise Stop(2, f"merging {stone} into {branch} conflicts in {', '.join(lines[1:])}; "
                      "merge it by hand, push, and run the tool again")
    if merged.returncode != 0 or not lines:
        raise Stop(2, f"could not compute the merge of {stone} into {branch}: {merged.stderr.strip()}")
    if lines[0] == run(["git", "rev-parse", f"{sha}^{{tree}}"]).stdout.strip():
        bases = run(["git", "merge-base", "--all", sha, f"origin/{stone}"])
        if bases.returncode != 0:
            raise Stop(2, f"could not find the merge bases of {branch} and {stone}: {bases.stderr.strip()}")
        count = len(bases.stdout.split())
        if count <= 1:
            print(f"[merge_step] {stone} brings nothing {sha[:8]} lacks: no push, CI on {sha[:8]} judged the tree that merges")
            return sha
        print(f"[merge_step] {stone} brings nothing {sha[:8]} lacks, but they share {count} merge bases: "
              "pushing the merge so CI's diff reads one base")
    made = run(["git", "commit-tree", lines[0], "-p", sha, "-p", f"origin/{stone}", "-m", f"Merge branch '{stone}' into {branch}"])
    if made.returncode != 0:
        raise Stop(2, f"could not write the merge commit: {made.stderr.strip()}")
    commit = made.stdout.strip()
    pushed = git_retrying(["git", "push", "origin", f"{commit}:refs/heads/{branch}"])
    if pushed.returncode != 0:
        raise Stop(2, f"could not push {branch}: {pushed.stderr.strip()}")
    print(f"[merge_step] merged {stone} into {branch} and pushed {commit[:8]}")
    return commit


def wait_for_ci(pr, head):
    """Wait until a green run on the head that wrote the summary decides; it returns at once when one already has."""
    start, delay = now(), POLL_SECONDS
    while True:
        verdict, ids, runs = ci_state(pr, head)
        if verdict == "green":
            print(f"[merge_step] CI green on {head[:8]}: run {ids[0]} wrote the summary")
            return
        if verdict == "red":
            raise Stop(1, f"run {', '.join(map(str, ids))} on {head[:8]} is red; nothing merged")
        if verdict == "unbuilt":
            raise Stop(2, f"no run on {head[:8]} built or said that no code path changed; push a commit to start one")
        late = queued_too_long(runs, now())
        if late:
            raise Stop(2, f"run {', '.join(map(str, late))} queued over ten minutes; check the runner "
                          "(documents/process/ci-runner.md, \"When a run stays queued\")")
        if verdict == "none" and now() - start > NO_RUN_SECONDS:
            raise Stop(2, f"no run on {head[:8]} after {NO_RUN_SECONDS} seconds; push a commit to start one")
        if now() - start > WAIT_SECONDS:
            raise Stop(2, f"CI on {head[:8]} not done after {WAIT_SECONDS // 60} minutes")
        delay = min(delay * 2, MAX_POLL_SECONDS) if verdict == "unknown" else POLL_SECONDS
        sleep(delay)


def merge_step(pr, brief_path):
    try:
        brief = Path(brief_path).read_text(encoding="utf-8")
    except OSError as error:
        raise Stop(2, f"could not read the brief: {error}") from None
    check_brief(brief, pr)
    if gh(["api", "repos/{owner}/{repo}", "--jq", ".delete_branch_on_merge"], "read the repository").strip() != "false":
        raise Stop(2, "the repository deletes head branches on merge, which would close every step stacked on this one")
    info = gh_json(["pr", "view", str(pr), "--json", "state,isDraft,baseRefName,headRefName,headRefOid"], f"read #{pr}")
    if info["state"] != "OPEN" or info["isDraft"]:
        raise Stop(2, f"#{pr} is {'a draft' if info['isDraft'] else info['state'].lower()}")
    head, base = info["headRefName"], info["baseRefName"]
    stone = stone_of(head, base)
    stone_prs = gh_json(["pr", "list", "--base", "main", "--head", stone, "--state", "open", "--json", "number"],
                        f"find the pull request of {stone}")
    if not stone_prs:
        raise Stop(2, f"{stone} has no open pull request to main")
    if base != stone:
        below = gh_json(["pr", "list", "--head", base, "--base", stone, "--state", "merged", "--json", "number"],
                        f"find the pull request of {base}")
        if not below:
            raise Stop(2, f"the step below, {base}, has not merged into {stone}; merge it first")
        gh(["pr", "edit", str(pr), "--base", stone], f"retarget #{pr} to {stone}")
        print(f"[merge_step] retargeted #{pr} from {base} to {stone}")
    sha = merge_stone_in(head, info["headRefOid"], stone)
    wait_for_ci(pr, sha)
    current = gh_json(["pr", "view", str(pr), "--json", "headRefOid,baseRefName"], f"read #{pr}")
    if current["headRefOid"] != sha or current["baseRefName"] != stone:
        raise Stop(2, f"#{pr} moved while CI ran; run the tool again")
    gh(["pr", "merge", str(pr), "--merge", "--match-head-commit", sha], f"merge #{pr}")
    if gh_json(["pr", "view", str(pr), "--json", "state"], f"read #{pr}")["state"] != "MERGED":
        raise Stop(2, f"#{pr} did not merge")
    print(f"[merge_step] merged #{pr} into {stone} with a merge commit")
    stone_pr = stone_prs[0]["number"]
    posted = run(["gh", "pr", "comment", str(stone_pr), "--body-file", str(brief_path)])
    if posted.returncode != 0:
        raise Stop(3, f"merged, but the brief did not post on #{stone_pr}: {posted.stderr.strip()}")
    print(f"[merge_step] posted the brief on #{stone_pr}; the same text for the owner:\n{brief}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", type=int)
    ap.add_argument("--brief", required=True, help="the step's brief, in the form documents/process/agent-rulings.md gives")
    args = ap.parse_args(argv)
    global ROOT
    try:
        ROOT = repo_root()
        merge_step(args.pr, args.brief)
    except Stop as stop:
        code, line = stop.args
        print(f"[merge_step] #{args.pr}: {line}", file=sys.stderr)
        return code
    return 0


if __name__ == "__main__":
    # A brief carries characters the Windows console code page cannot encode.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
