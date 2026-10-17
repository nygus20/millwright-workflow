# millwright-workflow

This repository is the Claude Code marketplace `millwright`. It lists one plugin, `mw`, under `plugins/mw/`, which holds the Millwright engine's process skills, four hooks, the output style, the review tool and the merge tool. `plugins/mw/README.md` says what the plugin holds, how a repository enables it and how a change is released.

## Layout

| Path | What it does |
|---|---|
| `.claude-plugin/marketplace.json` | Names the marketplace `millwright` and lists the plugin `mw` by the relative path `./plugins/mw`. |
| `plugins/mw/` | Holds the plugin. |
| `.claude/mw.json` | Gives the review tool this repository's costly paths, grants and invariants, so the tool reviews the plugin's own pull requests from a checkout of this repository. |
| `.github/workflows/checks.yml` | Runs `python plugins/mw/tools/run_checks.py --template` on every pull request and every push to `main`. |

A session in a checkout of this repository loads the plugin from the checkout with `claude --plugin-dir plugins/mw`.

## Rules

1. Every tag raises `version` in `plugins/mw/.claude-plugin/plugin.json`, and the tag is `v` followed by that version. Claude Code finds an update by comparing versions.
2. A tag never moves. A repository pins a tag, so a moved tag changes what a pinned session runs.
3. The plugin's Python runs on the standard library of Python 3.11 or later, with no package to install.
4. `plugins/mw/templates/require_plugin.py` stays byte for byte equal to each pinning repository's `.claude/hooks/require_plugin.py`, and each repository's own check compares them.
5. A hook, a skill or a tool reads nothing that is particular to one repository from its own code; the repository's `.claude/mw.json` holds it.
6. `python plugins/mw/tools/run_checks.py --template` passes before a pull request merges.
