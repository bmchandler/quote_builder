# Quote Builder

NiceGUI desktop app (native window, Linux) for building quotes, managed
with uv (Python 3.13), storing data in SQLite. REQUIREMENTS.md is the
source of truth for scope and rules; keep it updated in the same change
whenever a rule changes.

Setup, running, and tests are in DEVELOPMENT.md, imported here:

@DEVELOPMENT.md

## How we work

- Build in small "horizontal" steps: only what the current request needs.
  Don't scaffold ahead or add functions before a step uses them.
- Add or update tests alongside each change.
- After changes are done, stage what makes sense, draft a commit
  message, and pause there. Don't run `git commit` until the user reviews
  the diff/stage/message and app behavior and gives a clear go-ahead to
  commit, in whatever natural phrasing ("Proceed", "Go ahead and
  commit", etc.).
- Don't `git push` unasked. The user pushes by hand, or asks for a push.
- Commit messages: short subject line, a body with details when useful,
  then the Co-Authored-By trailer. The first commit in a repo is always
  `Initial Commit`.
- When a request is ambiguous (especially about UI behavior), ask instead
  of guessing.
- "Can we ...?" / "Could we ...?" is a literal question, not a go-ahead
  to edit. Answer it (doable out of the box with the framework? the
  trade-offs? would it override stock behavior?), then wait for a clear
  instruction.
- REQUIREMENTS.md's "Status and plan" section says what's built and
  what's next; update it when a planned item lands.
- No repo polish (linters, pre-commit, CI) unless the user asks.
- Until close to the first release, the database schema and data files
  can change freely: no migrations, and no need to keep existing data
  in `data/`, unless the user says they're keeping hand-test data.

## Privacy

- No email addresses in tracked files or package metadata.
- Real client data stays in `data/` (ignored); tests and examples use
  made-up names and businesses.
