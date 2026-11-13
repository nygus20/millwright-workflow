# mw, the Millwright workflow plugin

This plugin holds the way of working that the Millwright engine and the repositories built on it share. Each repository pins one tag of the marketplace, and a tracked data file in each repository, `.claude/mw.json`, holds what differs between them.

## What it holds

| Path | What it does |
|---|---|
| `.claude-plugin/plugin.json` | Names the plugin `mw` and carries its version. |
| `agents/step-builder.md` | Defines the agent `mw:step-builder`, which builds one step of a stone. Its frontmatter fixes the model `claude-opus-5-5` and the effort `high`, and its body holds the standing brief every step obeys. The `mw:coordinate-stone` skill starts it once per step and passes no `model` and no `effort`, because a value in the call overrides the definition's. From 0.1.15 on, the step's pull request body states what the step does, the record rows it implements and each reversible choice, with no test count and no changed-line count, and a code comment may cite a call as `pull request <n>, call <m>`. |
| `skills/` | Holds seven skills: `start-stone`, `coordinate-stone`, `close-stone`, `adversarial-review`, `changelog-entry`, `prior-art` and `port-triage`. A session invokes each as `/mw:<skill>`. Each skill names the plugin's tools through `${CLAUDE_PLUGIN_ROOT}`, which Claude Code replaces with the plugin's folder when the skill loads. From 0.1.14 on, a step runs the repository's quick check before its push, and CI's run on the pull request's head is the step's one full gate; a step is planned under 1,200 changed lines, and CI fails one over 1,600; the close runs the suite with `--long`, records the test costs with `--record-costs`, cites the suite's weight line, and fixes the step rounds' Records bullets together in the closing step. From 0.1.15 on, the planning session reads the "Builds on" summaries in place of the closed stones' plans; the first step writes no record that marks the stone open, and the close writes the row and the registry entry once; the closing summary ends with a "For the next stone" section; the close writes no gotcha-history entry, and its item 1 no longer asks for a quiet machine; the triage record keeps five columns, carries the port-triage line and corrects a row in place; and a plan with no prior-art question says so in one line with the reason. From 0.1.16 on, a findings doc gets no row in a docs map, so the close no longer checks for one, and its docs-weight line sets only the active phase plan against a cap; the close settles a known issue as that doc's format line says. A consumer's plan carries an "Engine asks" section, and the planning session files each ask as a `from-game` issue before the hand-over. A consumer's session may open pull requests into the marketplace and into the engine's `main` under the two exceptions the start-stone skill states, and the coordinator merges such a pull request into the engine by hand after its one round. |
| `hooks/hooks.json` | Wires the five hooks. The three PreToolUse hooks carry `"onFailure": "block"`, so a hook that fails to run stops the tool call. |
| `hooks/deny_guard_config.py` | Denies an edit to a file or folder that the data file's `guard` key lists, and to the data file itself. |
| `hooks/deny_scratch_read.py` | Denies a read of a file at the repository's root that matches the data file's `scratch_patterns`. |
| `hooks/deny_kill_by_name.py` | Denies a `Bash` or `PowerShell` command that stops a process by its name, such as `taskkill /IM`, `Stop-Process -Name` or `pkill`, because a name matches every session's copy of the program. Its reason names the stop by PID. |
| `hooks/no_emoji_md.py` | Reports an emoji written into a `.md` file, so the agent removes it. |
| `hooks/session_start.py` | Sets `core.hooksPath` when the repository holds `git-hooks/`, writes the session's two markers, and prints one context line naming the plugin's version, its folder and the repository's worktree folder. |
| `mw_data.py` | Loads `.claude/mw.json`. It refuses a missing file, an unknown version, a missing required key and an optional `stone_registry` key that lacks its `file` or `rewrite` string, and it fills the review section's defaults. From 0.1.14 on, the default `stone` and `costly` profiles name `claude-fable-5-2` at high effort, and `step` keeps `claude-opus-5-5`. |
| `output-styles/millwright.md` | Sets the reply style. Its `force-for-plugin: true` applies it whenever the plugin is enabled. |
| `tools/review_pr.py` | Runs the adversarial review of a pull request in a fresh `claude -p` session, which loads this plugin through `--plugin-dir`, and reads CI's suite result for the reviewed commit in place of running the suite, waiting up to thirty minutes for it from 0.1.14 on. From 0.1.13 on, it splits a diff past the review section's `slice_bytes` into slices by path and reviews them at once. From 0.1.14 on, `--stone` reads the stone's section from the stone branch when the reviewed commit lacks it, and the prompt names the ref. Also from 0.1.14 on, a step round, on a pull request into a stone or a step branch, blocks on a narrower rule, and its reply carries a fourth heading, `Records`, whose bullets stop no merge. A stone round, into `main`, keeps the rule and the three headings it had. From 0.1.15 on, a step round's full review holds at most three one-sentence bullets under `Verified`, or one line when nothing blocks, while a step round's fix check and a stone round keep five bullets; the prompt also carries the plan's tables, the stone pull request's comments that open with `<!-- mw-plan-tables -->`, after the plan's body. |
| `tools/merge_step.py` | Merges a step's pull request into its stone branch once CI is green, then posts the step's brief. From 0.1.10 on, it reads the head's check runs when GitHub lists no run, and it waits ten minutes for a first run. From 0.1.14 on, it takes a lock per stone under the repository's common git folder, so a second run on the same stone waits and names the run that holds it, and a run that died holding it is taken over. From 0.1.15 on, it stops with exit 2, before any `gh` call, when the brief's `Ambiguities` item holds more than 600 bytes. |
| `tools/test_hooks.py`, `tools/test_review_pr.py`, `tools/test_merge_step.py` | Test the hooks, the review tool and the merge tool. Each takes the repository to check as its argument. |
| `tools/test_agents.py` | Tests the step builder's definition: its fixed fields, no field Claude Code ignores, the standing items of its body, no full local suite run in that body, the coordinate-stone skill's call, no skill or agent that names a repository's worktree folder, and the clauses the start-stone, close-stone and coordinate-stone skills hold for the plan's hand-overs, the stone registry, the gotchas and the worktree. From 0.1.16 on, it also checks the start-stone skill's engine asks and a consumer's pull requests into the engine, and that no findings skill asks for a docs-map row and the close sets no findings cap. It accepts the repository as its argument and reads only the plugin's files. |
| `tools/run_checks.py` | Runs the four tests against one repository and prints one summary line per test. |
| `tools/fixture/.claude/mw.json` | Gives the tests a fixed data file: the engine's lists of `v0.1.0`, with the review profiles of 0.1.14's defaults and, from 0.1.15 on, the four check scripts' grants under `tools/tests/`. |
| `templates/mw.json` | Gives a new repository its first data file. |
| `templates/require_plugin.py` | Gives a new repository its repository-side hook, which denies an edit when the plugin is not loaded or, from 0.1.6 on, when the loaded version differs from the pinned tag. |

## How a repository enables it

1. Copy `templates/mw.json` to `.claude/mw.json` and fill in the repository's name, its worktree folder, its guarded files and folders, its scratch patterns and its costly paths. A repository that keeps a stone registry also adds the optional `stone_registry` key, whose `file` names the registry and whose `rewrite` names the command that writes the files built from the registry; the `mw:close-stone` skill then writes the stone's entry and runs the rewrite once, in the closing step.
2. Copy `templates/require_plugin.py` to `.claude/hooks/require_plugin.py` without changing a byte.
3. Add three keys to `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "millwright": {"source": {"source": "github", "repo": "nygus20/millwright-workflow", "ref": "v0.1.16"}}
  },
  "enabledPlugins": {"mw@millwright": true},
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{"type": "command", "onFailure": "block",
                   "command": "sh -c 'if command -v python3 >/dev/null 2>&1; then exec python3 \"$0\"; else exec python \"$0\"; fi' \"$CLAUDE_PROJECT_DIR/.claude/hooks/require_plugin.py\""}]
      }
    ]
  }
}
```

4. Start Claude Code in the repository's folder and accept the trust dialog. Claude Code then adds the marketplace and loads the plugin from its clone under `~/.claude/plugins/marketplaces/millwright/`.
5. Run `python <plugin folder>/tools/run_checks.py <repository>` in the repository's CI, so a runner that loads no plugins still runs the hooks' tests against the repository's data file.

A session that did not load the plugin writes no marker, and `require_plugin.py` then denies its first edit with a reason that names the pin. A session that only reads goes on.

From 0.1.6 on, `require_plugin.py` also compares versions. When the pin's `ref` is a version tag, `v<version>`, the hook reads the session marker, or the process marker when the session marker is missing, and denies an edit when the marker records another version or none. Its reason names both versions and the fix: run `claude plugin update mw@millwright --scope project` in the repository's main checkout, or `claude plugin install mw@millwright --scope local` inside a worktree, then restart the session. Claude Code's installed-plugins record, `~/.claude/plugins/installed_plugins.json`, keeps the old version after a pin moves until that command runs, and `/reload-plugins` alone reloads the recorded version. The record holds one entry per folder, and the update command run inside a worktree rewrites the main checkout's entry, so a worktree takes the install command. A pin with no `ref`, or a `ref` that is not a version tag, keeps the loaded check alone. `onFailure` needs Claude Code 2.1.295 or later; an older version ignores the field.

## The review section's slice keys

The data file's `review` section takes two optional keys that set how the review tool splits a large diff. `mw_data.py` fills each default and refuses a value that is not a positive integer.

- `slice_bytes`, 800000 by default, is the most diff text one slice holds, in bytes; `--slice-bytes N` overrides it for one run.
- `max_slices`, 8 by default, is the most slices one round runs; a diff that needs more exits 2 before the CI wait.

## The session markers

`hooks/session_start.py` writes two files under the system's temporary folder, in `mw-plugin/`. One is named by the session id. The other is named `ppid-<id>` by the process id of Claude Code, which Claude Code sets as `CLAUDE_PID` in a hook's environment from v2.1.214 on (https://code.claude.com/docs/en/env-vars). Without `CLAUDE_PID`, the hook writes no second marker, and only the session marker counts. Each holds the plugin's folder and version as JSON, and the hook reads the version from `.claude-plugin/plugin.json` when it runs. The second marker covers a tool call whose session id differs from the one the session started with, such as a subagent's. The hook deletes markers older than a day. A process id that the system reuses within that day lets a session without the plugin through, and the hook's header records that gap.

## How a change is released

1. Open a pull request into `main`. CI runs `python plugins/mw/tools/run_checks.py --template`.
2. Review it with the review tool from a checkout of this repository: `python plugins/mw/tools/review_pr.py <pr> --post`. The repository's own `.claude/mw.json` gives the review its costly paths and its invariants.
3. Raise `version` in `.claude-plugin/plugin.json` and the example pin above, in the pull request or in a commit on `main` after the merge, then push an annotated tag `v<version>` on `main`. Claude Code compares versions to find an update, so a tag without a version change leaves every user on the cached copy.
4. Each repository that pins the plugin moves its `ref` to the new tag in one step. The two repositories move on the same day, because Claude Code fetches a marketplace again whenever two projects declare different sources for it. Each repository's main checkout then takes the new version through `claude plugin update mw@millwright --scope project`, each of its worktrees through `claude plugin install mw@millwright --scope local`, and each session restarts, because `/reload-plugins` alone reloads the version the installed-plugins record holds.
