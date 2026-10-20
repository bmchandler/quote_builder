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
  commit", etc.). Always write the full drafted message (subject, body,
  trailer) in a code block in the chat itself: the app's next-step box
  shows only a short recap.
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
- The user is learning from the code: point out good practices (and
  traps met) when reporting a change, briefly.
- Check screen changes in the browser pane before handing over: a
  scratch script (outside the repo) that seeds a scratch database with
  made-up quotes and runs `ui.run(quote_page(conn), port=..., show=False,
  reload=False)`, viewed at 1000×750, the native window's size. The
  user hand-tests in the native window. The dev VM has no working 3D
  (software rendering), so the window feels slow there but not on real
  hardware.
- Until close to the first release, the database schema and data files
  can change freely: no migrations, and no need to keep existing data
  in `data/`, unless the user says they're keeping hand-test data.

## Code notes

- Layers: quotes.py (dataclasses: `Quote`, `LineItem`, `Status`,
  `QuoteSummary`, `LineTotals`, `QuoteTotals`, `Extension`), money.py
  and dates.py (text in and out: `parse_*` raise ValueError with a
  message for the user, `format_*`), totals.py (all money math),
  search.py (search matches: escaped HTML with `<mark>`, excerpts),
  storage.py + schema.sql (all SQL), app.py (NiceGUI only; calls the
  others). Never float for money: text goes straight to
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
  `shown_quote_totals`, which prefer the frozen ones.
- app.py: `quote_page(conn, today=date.today)` returns the root
  function for `ui.run(root)`; tests pass a temp database and a fixed
  `today`. In `root`, handlers are defined before the layout that
  calls them. `show(quote, new_revision=False)` swaps the right side
  (`landing`, `quote_editor`, `quote_view`) and refreshes the list;
  `new_revision` marks a revision draft not stored yet (saved with
  `save_revision`, or `mark_quoted(..., new_revision=True)`).
  `quote_editor` returns a has-unsaved-changes function (form state
  compared with what it opened with). The side panel is
  `ui.left_drawer` with `behavior=desktop` (Quasar's default turns it
  into a pop-over below 1024 pixels; the window is 1000), 350 wide.
  To try another width, change the prop: restyling the drawer in the
  page by hand leaves Quasar's page padding at the old width.
- NiceGUI quirks met: `props("active=True")` passes the text "True"
  (use `props("active")`); a handler that takes a parameter is passed
  the event's arguments (wrap it: `lambda: add_line()`);
  `refreshable.refresh()` runs in the background unless awaited.
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

## Privacy

- No email addresses in tracked files or package metadata.
- Real client data stays in `data/` (ignored); tests and examples use
  made-up names and businesses.
