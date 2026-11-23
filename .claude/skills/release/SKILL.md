---
name: release
description: >
  Cut a Quote Builder release on `dev`: bump the version
  (`uv run tag_new_version.py`), commit, tag, move `main`, and stop
  before pushing. Use when the user asks to make, cut, or tag a release,
  or to bump/publish the version. NOT for ordinary commits, and NOT for
  changes nothing in a release would reflect (dev docs, tests, tooling),
  which ride `dev` with no version bump.
---
<!-- seeded from claude_templates/skills/release @ 2026-11-23; diverge freely -->

# Release

The triggerable checklist. The full step mechanics live in
[RELEASING.md](../../../RELEASING.md), and the reasoning in
REQUIREMENTS.md → Versioning; this skill does not restate them — it makes
the procedure fire at the right moment and holds the guard rails in one
place.

## Before you touch anything — preconditions

- **Does this change earn a release?** Only a change a user would notice
  does. Dev-doc / test / tooling changes ride `dev` to both remotes with
  no version bump and no changelog line.
- **Clean tree, on `dev`.** The release script refuses otherwise, and
  `branch_guard.py`'s hooks refuse a commit on `main`; check first so you
  fail fast rather than mid-run.
- **Get the user's explicit go-ahead before anything commits or tags.**

## Steps

1. If the dependencies changed since the last release (e.g. you ran
   `uv lock --upgrade`), freeze them once the tests pass:
   `uv run regen_release_deps.py`, committed on its own.
2. Record the release's changes in CHANGELOG.md, under `## Unreleased`,
   and commit everything for the release, on `dev`.
3. Run `uv run tag_new_version.py` (the only supported way to bump the
   version), or pass an explicit `YYYY.M.D[.N]`.
4. Verify the version it reports, then answer `y` when prompted.
5. Report the push command it prints and STOP. Don't push unless the
   user asks.

## Guard rails

- Never hand-edit the version in `pyproject.toml`, and never tag by
  hand; use `tag_new_version.py` only.
- Never commit on `main`; never push unasked.
- Scan the staged diff and the commit message for anything real that
  shouldn't be published — customer records live in `data/` (git-ignored),
  so watch for any that slipped into a change or a message.

## Why bump + commit + tag are atomic

A version a build embeds in its output must trace to exactly one commit.
A tag without the bump ships a stale version; a bump without the tag
names a release no commit answers to. Done together, in order, the
version the app shows in About points at exactly one tagged commit.
Full reasoning: REQUIREMENTS.md → Versioning.
