# mw, the Millwright workflow plugin

This plugin holds the way of working that the Millwright engine and the repositories built on it share. Each repository pins one tag of the marketplace, and a tracked data file in each repository, `.claude/mw.json`, holds what differs between them.

## What it holds

| Path | What it does |
|---|---|
| `.claude-plugin/plugin.json` | Names the plugin `mw` and carries its version. |
| `skills/` | Holds seven skills: `start-stone`, `coordinate-stone`, `close-stone`, `adversarial-review`, `changelog-entry`, `prior-art` and `port-triage`. A session invokes each as `/mw:<skill>`. Each skill names the plugin's tools through `${CLAUDE_PLUGIN_ROOT}`, which Claude Code replaces with the plugin's folder when the skill loads. |
| `hooks/hooks.json` | Wires the four hooks. The two PreToolUse hooks carry `"onFailure": "block"`, so a hook that fails to run stops the tool call. |
| `hooks/deny_guard_config.py` | Denies an edit to a file or folder that the data file's `guard` key lists, and to the data file itself. |
| `hooks/deny_scratch_read.py` | Denies a read of a file at the repository's root that matches the data file's `scratch_patterns`. |
| `hooks/no_emoji_md.py` | Reports an emoji written into a `.md` file, so the agent removes it. |
| `hooks/session_start.py` | Sets `core.hooksPath` when the repository holds `git-hooks/`, writes the session's two markers, and prints one context line naming the plugin's version, its folder and the repository's worktree folder. |
| `mw_data.py` | Loads `.claude/mw.json`. It refuses a missing file, an unknown version and a missing required key, and it fills the review section's defaults. |
| `output-styles/millwright.md` | Sets the reply style. Its `force-for-plugin: true` applies it whenever the plugin is enabled. |
| `tools/review_pr.py` | Runs the adversarial review of a pull request in a fresh `claude -p` session, which loads this plugin through `--plugin-dir`. |
| `tools/merge_step.py` | Merges a step's pull request into its stone branch once CI is green, then posts the step's brief. |
| `tools/test_hooks.py`, `tools/test_review_pr.py`, `tools/test_merge_step.py` | Test the hooks, the review tool and the merge tool. Each takes the repository to check as its argument. |
| `tools/run_checks.py` | Runs the three tests against one repository and prints one summary line per test. |
| `tools/fixture/.claude/mw.json` | Gives the tests a fixed data file, the engine's lists at `v0.1.0`. |
| `templates/mw.json` | Gives a new repository its first data file. |
| `templates/require_plugin.py` | Gives a new repository its repository-side hook. |

## How a repository enables it

1. Copy `templates/mw.json` to `.claude/mw.json` and fill in the repository's name, its worktree folder, its guarded files and folders, its scratch patterns and its costly paths.
2. Copy `templates/require_plugin.py` to `.claude/hooks/require_plugin.py` without changing a byte.
3. Add three keys to `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "millwright": {"source": {"source": "github", "repo": "nygus20/millwright-workflow", "ref": "v0.1.4"}}
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

A session that did not load the plugin writes no marker, and `require_plugin.py` then denies its first edit with a reason that names the pin. A session that only reads goes on. `onFailure` needs Claude Code 2.1.295 or later; an older version ignores the field.

## The session markers

`hooks/session_start.py` writes two files under the system's temporary folder, in `mw-plugin/`. One is named by the session id. The other is named `ppid-<id>` by the process id of Claude Code, which Claude Code sets as `CLAUDE_PID` in a hook's environment from v2.1.214 on (https://code.claude.com/docs/en/env-vars). Without `CLAUDE_PID`, the hook writes no second marker, and only the session marker counts. Each holds the plugin's folder and version as JSON. The second marker covers a tool call whose session id differs from the one the session started with, such as a subagent's. The hook deletes markers older than a day. A process id that the system reuses within that day lets a session without the plugin through, and the hook's header records that gap.

## How a change is released

1. Open a pull request into `main`. CI runs `python plugins/mw/tools/run_checks.py --template`.
2. Review it with the review tool from a checkout of this repository: `python plugins/mw/tools/review_pr.py <pr> --post`. The repository's own `.claude/mw.json` gives the review its costly paths and its invariants.
3. After the merge, raise `version` in `.claude-plugin/plugin.json`, commit, and push an annotated tag `v<version>`. Claude Code compares versions to find an update, so a tag without a version change leaves every user on the cached copy.
4. Each repository that pins the plugin moves its `ref` to the new tag in one step. The two repositories move on the same day, because Claude Code fetches a marketplace again whenever two projects declare different sources for it. A running session takes the new version at `/reload-plugins`.
