---
name: changelog-entry
description: Write a CHANGELOG.md entry in project style, or cut a release. Use when closing a stone or merging a step, when asked to "update the changelog", or when asked to "cut a release" / "tag v0.X.Y".
---

# CHANGELOG entries and releases

Two related tasks live here. Work out which one is being asked for; ask if it is ambiguous. This skill owns the CHANGELOG style; the `close-stone` skill and `documents/README.md` point here.

## The style

- Entries are **commit-message bullets**, not design docs or implementation narratives. The plan doc is the design record, the code is the implementation record, the changelog is a delta log.
- One line per entry under `### Added` / `### Changed` / `### Fixed` in the `[Unreleased]` section. Lead with the verb: "Added the arena allocator", "Fixed the flow field re-walking cleared cells".
- Include the plan-doc anchor in parens: `(phase 0, Stone 3)`. A step inside a stone names the stone and the step: `(founding review stone, step 1)`.
- Include the new passing-test count in parens when it changed: `(84 tests passing)`. Run the `run-tests` skill first to get the real number; do not guess it.
- Do **not** restate API signatures, rationale, test lists or out-of-scope notes that already live in the plan doc or the module header.
- Multiple unrelated changes landing together get multiple one-line bullets, not one dense paragraph.
- **Do not rewrite prior entries.** They are records, and Doc Prose's no-retrofit rule covers them.

## When an entry lands

At the latest when the stone closes; a step may add its own as it merges. For a stone whose exit test is an owner check, the close entry lands in the closing step before the owner's verdict, so the stone review reads it (`close-stone` skill, ruled by the owner on 2026-10-11); a feedback round adds its own lines in its step. Never a second "docs: close Stone N" pull request.

## Cutting a release

Only when explicitly asked to "cut a release" / "tag v0.X.Y".

1. Confirm every entry under `[Unreleased]` belongs to the release being cut.
2. Move them into a new version header: `## [0.X.Y] — Title — YYYY-MM-DD`.
3. Create the tag: `git tag v0.X.Y && git push --tags`. The tag name must match the header exactly.
4. The release procedure beyond the tag (exports, a store or itch.io step) lands as a skill of its own when a game on the engine first ships.
