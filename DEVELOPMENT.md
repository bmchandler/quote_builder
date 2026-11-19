# Development

## Setup

Linux only. The native window uses GTK's WebKitGTK through PyGObject,
which uv builds from source, so it needs these stock Debian packages
first (once):

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev pkgconf python3-dev
```

The window itself also needs WebKitGTK (`gir1.2-webkit2-4.1`), already
on most GNOME and Cinnamon desktops.

## Running

```bash
uv run quote-builder
```

From a clone, the database is `data/quotes.db`. Until close to the
first release, its tables can change at any time: delete it to start
over.

## Tests

```bash
uv run pytest
```

Screen tests (tests/test_app.py) use NiceGUI's simulated user, so they
need no window or browser.

The suite runs in parallel across cores (pytest-xdist, `-n auto` in
`pyproject.toml`), since each test gets its own temp database and
in-process user. To debug one failure with ordered output, turn that
off with `uv run pytest -n0`.

## Code layout

All in `src/quote_builder/`:

- `app.py`: the window (NiceGUI), and `main`, the `quote-builder`
  command.
- `quotes.py`: quotes and line items as dataclasses.
- `business.py`: a business and its settings, and its tax rates.
- `customers.py`: a business's saved customers, and a quote's copy of
  a customer's details.
- `catalog.py`: a business's catalog of services and parts.
- `money.py`: reading and showing amounts, quantities, percents, and
  discounts.
- `dates.py`: reading and showing dates, and valid-through dates.
- `totals.py`: what a line and a quote add up to.
- `search.py`: showing where a search matched (highlights, excerpts).
- `printout.py`: a quote as a standalone HTML page for the browser.
- `quote_numbers.py`: new quote numbers.
- `storage.py`, `schema.sql`: the SQLite database.
- `data_folder.py`: where the database lives.

Tests in `tests/` mirror these files.

## Licensing

Quote Builder is under the MIT License ([LICENSE.md](LICENSE.md)). The
native-window stack it depends on is compatible with that, so the app's
own code stays MIT with no added obligation:

- The runtime graphics stack is weak-copyleft, not strong: WebKitGTK is
  LGPL-2.1+ with some BSD-2-Clause parts, and GTK, PyGObject, cairo, and
  pycairo are LGPL (pycairo LGPL-2.1 / MPL dual). Nothing in the runtime
  path is GPL, so nothing pulls the app under GPL.
- The Python dependencies are permissive: NiceGUI (MIT), pywebview
  (BSD-3-Clause), and the FastAPI/Starlette/uvicorn tree (MIT/BSD).
- LGPL's obligations attach to the LGPL library's own code, not to code
  that merely uses it. They bite only on modifying the library or
  bundling it so a user can't relink their own copy. We do neither: the
  app ships only its own source (installed with uv from git), and the
  LGPL libraries are the user's own system packages (see
  [Setup](#setup)), dynamically loaded. So dynamic use of an unmodified
  system library is the clean case, and the app's source stays MIT.
- Caveat for later: this stays clean only while we don't ship a combined
  binary. Bundling WebKitGTK into one distributable (an AppImage, a
  PyInstaller/Nuitka build) would trigger LGPL's relink provision (keep
  it dynamically linked, or provide a way to swap it). Such packaging is
  out of scope for now (REQUIREMENTS.md, Scope), so there's nothing to
  do until that changes.

License identifiers above are each project's own stated license; confirm
against their sources before relying on them for a release.

