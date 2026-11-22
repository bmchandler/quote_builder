# Quote Builder

NiceGUI desktop app (native window, Linux) for building quotes, managed
with uv (Python 3.13), storing data in SQLite. REQUIREMENTS.md is the
source of truth for scope and rules; keep it updated in the same change
whenever a rule changes.

Setup, running, and tests are in DEVELOPMENT.md, imported here:

@DEVELOPMENT.md

## Working norms (portable)

Norms the user has settled across projects, not specific to this one.
When starting a new project, or asked to bring over the working norms
from an earlier one, copy this whole section into its CLAUDE.md as
is. They live in each project's CLAUDE.md, not in `~/.claude/CLAUDE.md`:
that file is intentionally not being used "due to administrative
overhead." For example, `~/.claude` isn't git-synced, so a VM rebuild
would lose it. Norms live in CLAUDE.md only; don't keep a memory copy
of one: a second copy drifts, and can mask a problem in this file.

### Working style

- Hands-off by default: once the approach is clear, Claude takes a
  step all the way to the end (code, tests, docs, a staged diff with a
  drafted message), then still pauses before committing. The user
  designs (wording, layout, where things live, flow) from concrete
  options, previews, and trade-offs Claude offers, rather than Claude
  deciding design questions for them. Hands-off doesn't mean assume:
  ask early, before building much, whenever unsure about anything.
- When handing over a step, anything to do before running the app
  (deleting a database after a schema change, say) goes first in the
  summary, as a command: the user often starts the app before
  reading the rest, and would otherwise meet an error first.
- Screenshots in the chat are full size or close to it (a 0.6
  scale reads fine; 0.2 is too small to see when opened): the user
  reads them. To find where to click, use `find`/`read_page` rather
  than a tiny screenshot.

### Commits and pushes

- Never `git commit` without the user's explicit go-ahead for that
  commit. First: stage what makes sense, write the full drafted
  message (subject, body, trailer) in a code block in the chat itself
  (the app's next-step box shows only a short recap), and pause so the
  user can review the diff and message and hand-test the app. The
  go-ahead can be any natural phrasing ("Proceed", "Go ahead and
  commit").
- These are not a go-ahead: a plan or answer that mentions committing
  ("then stage and commit 1"), approval of an earlier commit, or
  approval given before the work was re-cut or changed. When in
  doubt, show the message and ask.
- Never `git push` unless the user asks for that push. A go-ahead to
  commit is not one to push.
- Exceptions only when the user names them, case by case; one never
  carries over to later commits or pushes.
- Iterate a step until it's fully baked, then commit it: reworking
  staged work before then (re-cutting it, removing fields) is normal.
  A bug caught after a commit gets a standard bugfix commit, never an
  amend. Committing a mistake as it was and its fix separately is an
  edge case, for a complex situation where holding the commit seems
  risky: raise it, don't assume it.
- Commit messages: short subject line, a body with details when useful,
  then the Co-Authored-By trailer. The first commit in a repo is always
  `Initial Commit`.
- Push targets: the private gitserver (`origin`) by default. A public
  mirror (GitHub) only when what's going out is probably safe to
  publish (it can't be taken back): if unsure, push to the gitserver
  only and vet the public push with the user first.
- Branches, in uv projects unless noted otherwise: work and commit on
  `dev`, never on `main`; `main` only ever points at the newest
  release's tag, moved only by the release step. A plain install
  then gets the newest release, a good pattern for users.

### Steps

- Build in small "horizontal" steps: only what the current request
  needs, and whatever a step adds comes with what uses it, so the
  user can try it by hand end to end (a setting with the behavior it
  changes; a field with where it shows). Several simple fields can
  share a step; an involved one gets its own, with its dependents.
  No extra behavior bundled unannounced: its own commit, or ask.
  Describe planned steps by what the user can try after each.
- Don't scaffold ahead or add functions before a step uses them. The
  exception, raised and agreed first: groundwork for something
  certain to come that's cheap now and costly to change later (say, a
  table shaped for several of something before more than one can be
  added). When less sure, pay the redo cost in the step that needs
  it: the feature may be dropped before then.
- REQUIREMENTS.md is the source of truth for scope and rules, updated
  in the same change whenever a rule changes; its "Status and plan"
  section says what's built and what's next, updated when a planned
  item lands.
- No repo polish (linters, pre-commit, CI) unless the user asks.

### Tests

- Add or update tests alongside each change: a unit test for a rule
  and an app-level test proving it's wired in, even where they check
  the same thing (a rule dropped from the app's wiring passes every
  unit test). Never propose cutting coverage for speed; run the full
  suite by default.
- Hand-test data only when the user asks, a few records that show off
  the whole feature. Text in it saying how a record came about is
  marked when that didn't literally happen (`Simulated hand-added`),
  so it can't be taken for the real thing.

### Questions and answers

- When a request is ambiguous (about UI behavior or anything else),
  ask instead of guessing.
- "Can we ...?" / "Could we ...?" is a literal question, not a go-ahead
  to edit. Answer it (doable out of the box with the framework? the
  trade-offs? would it override stock behavior?), then wait for a clear
  instruction. Avoid overriding framework defaults unless the user
  decides to.
- Keep questions tightly targeted at the current work. A question
  that doesn't have to be settled now goes in REQUIREMENTS.md (or the
  like), to settle when that part gets built, unless it heavily should
  be nailed down now. UI/UX targets whoever the app is for at this
  stage: a question about a later audience waits for that part.
- When reporting a change, call out as "Code Point: " any code
  trade-off or design choice with real impact that may cost us later,
  and any trap met, briefly and on its own so it stands out when
  skimming. Skip it when there's none. The general rule: pay a cost
  at implementation rather than let it compound down the road, so
  raise these while they're still cheap to change.

### Wording and docs

- On-screen wording the user dictates is used word for word (moving
  line breaks to fit is fine). For a case it doesn't cover, write
  wording that fits, showing it when it's part of a design question.
  Don't ask for sign-off on new wording or list it as open: no comment
  means the user is rolling with it. They'll ask for a change after
  some use, or for a list of the messages in a polish phase, to size
  them up for cohesiveness at one go. Wording changed from what was
  already on screen is different: say so when handing over, old and
  new. Keep set phrases the same across related cases: consistent
  beats precise-but-varying.
- In docs, a reference to a section or file is a link to it:
  `[Your data](#your-data)`, `[DEVELOPMENT.md](DEVELOPMENT.md)`. Not
  needed for a file already linked earlier in the same paragraph.
- What a third party does is stated as fact only from its own
  documentation; otherwise worded as uncertain ("appears to", "it's
  likely"), with the evidence where known. Never the word "hedge".
- Public docs (README) are terse and matter-of-fact, never name a
  third party as a bug's cause, and are for users only: developer
  material goes in developer docs, which the README doesn't mention.
- No email addresses in anything published: code, docs, package
  metadata, request headers. Contact is the repo's issues; a client
  identifies itself by the repo URL.

### Files

- In Accept Edits mode (the user's usual one), make file changes with
  the Edit/Write tools, not inline scripts (`python3 - <<'EOF'`,
  `sed -i`), to keep approval dialogs down: edits go through and show
  in Changes, while a script is opaque and asks for approval. Use the
  shell to run things (tests, git, servers).
- Wrap Markdown prose at about 70 columns: the user reads files with
  `cat` in a third of the screen.

## How we work (this project)

- Branches: the `dev`/`main` pattern (see portable norms above) is set
  up (2026-11-19). Work and commit on `dev`, never on `main`; `main`
  only ever moves forward to the newest release's tag, by the release
  step (`tag_new_version.py`; see RELEASING.md). The branch guard's
  hooks enforce this — install them once per clone with `uv run
  branch_guard.py install` (see DEVELOPMENT.md). `main` now carries the
  newest release's tag, moved there by the release step; push `dev` and
  releases freely, but the hooks refuse pushing `main` to a non-release.
  See REQUIREMENTS.md, Versioning and Path to first release.
- Frozen dependencies: `[project.dependencies]` pins the whole runtime
  closure to exact `==` versions from `uv.lock`, because `uv tool
  install`/`upgrade` from git ignores the lock and re-resolves from
  those specifiers (so a bare `>=` would let transitive deps float). The
  two native bindings (`pygobject`, `pycairo`) keep a `>=` floor instead
  (they compile against the system's GTK/cairo). `regen_release_deps.py`
  (beside `tag_new_version.py`, which imports `pins_match` from it)
  generates the pins; the release script refuses when they're out of
  sync with the lock. After `uv lock --upgrade`: test, run it, commit
  (see REQUIREMENTS.md, Versioning; RELEASING.md, Frozen dependencies).
- Only a change a user would notice earns a release. Developer-doc-only
  changes (REQUIREMENTS.md, DEVELOPMENT.md, CLAUDE.md), tests, and
  release tooling ride `dev` to both remotes with no version bump and no
  changelog line: the changelog is user-facing, with no honest line for
  them (see REQUIREMENTS.md, Versioning).
- UI/UX targets the business user for now, not the customer: what a
  customer sees is settled when building the parts they see.
- Check screen changes in the browser pane before handing over: a
  scratch script (outside the repo) that seeds a scratch database with
  made-up quotes and runs `ui.run(quote_page(conn), port=..., show=False,
  reload=False)`, viewed at 1000×750, the native window's size. The
  user hand-tests in the native window. The dev VM has no working 3D
  (software rendering), so the window feels slow there but not on real
  hardware. To try a layout change (a width, say), change it in the
  code: styling the page by hand in the pane can mislead. A click
  there can take seconds to draw (first use of a component loads its
  JavaScript): wait ~5 s before calling it lost. Run the server as a
  background task and stop it with TaskStop: `pkill -f`/`pgrep -f` on
  its path also match the shell running them, and kill that.
- Wording on screen: dates on a quote are `11/18/2026`, in the list
  `Nov 18, 2026`; a quote's last day is "Valid through" (REQUIREMENTS.md
  explains why); search places say "Line Item 3", not "Line 3";
  "customer", never "client".
- The first release has shipped (2026.11.20), so a schema change now goes
  through a migration (REQUIREMENTS.md, [Storage](#storage); storage.py,
  `_MIGRATIONS`). In dev you can still delete `data/` to start an
  unreleased database over rather than migrate it mid-change; keep
  existing `data/` only when the user says they're keeping hand-test data.

## Code notes

- Layers: quotes.py (dataclasses: `Quote`, `LineItem`, `Status`,
  `QuoteSummary`, `LineTotals`, `QuoteTotals`, `Extension`),
  business.py (`Business`: a business's settings; `TaxRate`,
  `TaxPart`), customers.py (`Customer`), catalog.py (`CatalogItem`),
  money.py and dates.py (text in and out: `parse_*` raise ValueError with a
  message for the user, `format_*`), totals.py (all money math),
  search.py (search matches: escaped HTML with `<mark>`, excerpts),
  printout.py (a quote as a standalone HTML page for the browser;
  `render_quote_html`, a pure function), storage.py + schema.sql (all
  SQL), app.py (NiceGUI only; calls the others). Never float for money: text goes straight to
  `Decimal`, cents are `int`; no `ui.number`.
- storage.py: `connect` sets `PRAGMA foreign_keys = ON` while in
  autocommit (it's a no-op inside a transaction), runs schema.sql, then
  sets `autocommit = False` so `with conn:` is one transaction. Tables
  are STRICT. Always parameters (`?` / `:name`), never values in SQL
  text; `IN (...)` gets one `?` per value. Escape `%`, `_`, `\` in a
  LIKE search (`ESCAPE '\'`). `ORDER BY` whenever order matters (SQLite
  may return index order). Load lines for many quotes in one query
  (`_line_items_of`), not one per quote. Timestamps: UTC,
  `isoformat(timespec="seconds")`, so the text sorts by time.
  `save_new_quote`/`save_draft` take `now` and `draw_number` for tests.
  A quote is a number plus revision (0, then R1, R2: `version_name`);
  `load_quote(conn, number)` gives the newest version, and the list
  shows only the newest per number. Check-and-change in one UPDATE
  (status, or the old date, in the WHERE clause) rather than reading
  first.
- Totals are computed from lines whenever shown, never stored, until
  `mark_quoted` freezes them (`frozen` on `Quote` and `LineItem`;
  REQUIREMENTS.md, Data). Show figures with `shown_line_totals` /
  `shown_quote_totals`, which prefer the frozen ones. `mark_quoted`
  also freezes the business's details for the printout
  (`printed_business` on `Quote`, a `PrintedBusiness`; `None` on a
  draft), stored in the quote's `frozen_business_*` columns and guarded
  by one CHECK on the name (the snapshot is written as a unit).
- app.py: `quote_page(conn, today=date.today)` returns the root
  function for `ui.run(root)`; tests pass a temp database and a fixed
  `today`. In `root`, handlers are defined before the layout that
  calls them. `show(quote, new_revision=False)` swaps the right side
  (`landing`, `quote_editor`, `quote_view`) and refreshes the list;
  `new_revision` marks a revision draft not stored yet (saved with
  `save_revision`, or `mark_quoted(..., new_revision=True)`).
  `quote_editor` and `business_settings` (shown by `show_settings`)
  return an `Editor`: `name` (for the discard question),
  `has_unsaved_changes` (form state compared with what it opened
  with), and `search_changed` (tints matching fields; a form is
  never redrawn for a search, which would drop its edits). The side
  panel is
  `ui.left_drawer` with `behavior=desktop` (Quasar's default turns it
  into a pop-over below 1024 pixels; the window is 1000), 350 wide.
  To try another width, change the prop: restyling the drawer in the
  page by hand leaves Quasar's page padding at the old width.
- NiceGUI quirks met: `props("active=True")` passes the text "True"
  (use `props("active")`); a handler that takes a parameter is passed
  the event's arguments (wrap it: `lambda: add_line()`);
  `refreshable.refresh()` runs in the background unless awaited.
  `.tooltip()` adds a sibling aimed by `target`, so in a slot it's one
  of the slot's children; an input's `html_id` is on its `<input>`, so
  a tooltip can aim at the text alone. A button in a field's `append`
  slot is in the Tab order unless given `tabindex="-1"`.
  A select's typing filter (`with_input`) matches the choices'
  labels in the browser; Add from catalog packs description and price
  into each label, on two lines, and draws them with slot templates.
  `ui.html` cleans its HTML with DOMPurify (`sanitize=True`, the
  default), which keeps `<mark>` and `class`; escape user text first
  anyway (search.py does).

## Testing notes

- Screen tests (tests/test_app.py) use `user_simulation(root=...)`
  directly, not NiceGUI's pytest plugin; `asyncio_mode = "auto"`.
- Elements tests touch have markers (`.mark(...)`): `description-1`,
  `quote-<number>`, `heading`, `foot-total`, and so on; line markers
  count lines ever added to that form, from 1.
- Async click handlers and `refresh()` finish in the background: wait
  with `user.should_see(...)`, `eventually(...)`, or `new_quote(user)`
  (waits for the "New Quote" heading) before checking or typing.
- `user.find("Discard")` also matches labels containing the word; use
  `find(kind=ui.button, content=...)` when it's ambiguous.
- Check a new test fails without the change it covers (break the code
  briefly) when the test is about async UI behavior.
- The `user` fixture's page has a fixed `TODAY` (10/19/2026), so dated
  quotes don't expire as real time passes; seed quoted ones with
  `mark_quoted` (the database refuses a non-draft without frozen
  totals), and revisions with `revision_draft` + `save_revision`.
- `user.find(...)` raises when nothing matches, so it can't be polled
  with `eventually`; wait with `should_see` / `should_not_see` (they
  take `marker=` and `kind=` too). `find(...).elements` is a set: to
  check order, compare element ids, which follow drawing order.
- The simulated user can't type in a select, and `find` doesn't look
  in an element's slots (a select's choices); tests send the event
  instead (`send` in test_app.py). Listeners are stored under
  camelCase names: `input-value` is `inputValue`.
- `should_see` also matches notifications: to check what a quote
  shows, read its marked element (e.g. `marker="dates"`), not any text.

## Privacy

- No email addresses in tracked files or package metadata.
- Real customer data stays in `data/` (ignored); tests and examples use
  made-up names and businesses.
