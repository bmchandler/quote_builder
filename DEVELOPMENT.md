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

## Branches

- `main` only ever points at the newest release's tag, so an install
  from git without a branch or tag gets it. It's never committed to:
  `tag_new_version.py` moves it forward at each release (see
  [RELEASING.md](RELEASING.md)). Until the first dated release, `main`
  carries no release tag yet.
- `dev` is where work goes, and releases are made. Between releases its
  version is the last release's plus `+dev` (`2026.10.12+dev`), set by
  the release script; a build installed from git adds its commit
  (`2026.10.12+dev.5f820a58`), read when the app runs (`app_version.py`).
- Tags are for releases only. Testers install a development build by
  branch or commit instead (see [Development builds](#development-builds)).

If you'll commit, install the branch guard's git hooks once per clone.
They refuse a commit on `main` and a push that would set the remote's
`main` to anything but a release:

```bash
uv run branch_guard.py install
```

## Development builds

To test what's being worked on (which may not be ready for use),
install the newest development build from the gitserver:

```bash
uv tool install "git+ssh://git@gitserver/~/quote_builder.git@dev"
```

and update it with `uv tool upgrade quote-builder`. Or install one
commit, which `uv tool upgrade` doesn't move:

```bash
uv tool install "git+ssh://git@gitserver/~/quote_builder.git@<commit>"
```

Once the GitHub mirror is up (see REQUIREMENTS.md, Path to first
release), its URL works the same way, with `@dev` or `@<commit>`. In an
`ssh://` URL the path starts at the server's root, so `/~/` stands for
the user's home. Leave off `@dev` for the newest release.

A development build keeps its files in
`~/.local/share/quote-builder-dev/`, apart from a release's, so testing
it never touches your real quotes (uninstalling leaves it, too). Only
one `quote-builder` can be installed at a time: to switch between a
release and a development build, run the other's install command. To
try a development build without replacing an installed release:

```bash
uvx --from "git+ssh://git@gitserver/~/quote_builder.git@dev" quote-builder
```

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

The main open-source libraries it builds on, with their license and
project page (license links go to opensource.org):

| Library | License | Project |
| --- | --- | --- |
| NiceGUI | [MIT](https://opensource.org/license/mit) | [nicegui.io](https://nicegui.io) |
| pywebview | [BSD-3-Clause](https://opensource.org/license/bsd-3-clause) | [pywebview.flowrl.com](https://pywebview.flowrl.com) |
| WebKitGTK | [LGPL-2.1](https://opensource.org/license/lgpl-2-1) (with [BSD-2-Clause](https://opensource.org/license/bsd-2-clause) parts) | [webkitgtk.org](https://webkitgtk.org) |
| GTK | [LGPL-2.1](https://opensource.org/license/lgpl-2-1) | [gtk.org](https://www.gtk.org) |
| PyGObject | [LGPL-2.1](https://opensource.org/license/lgpl-2-1) | [pygobject.gnome.org](https://pygobject.gnome.org) |
| cairo / pycairo | [LGPL-2.1](https://opensource.org/license/lgpl-2-1) | [cairographics.org](https://www.cairographics.org) |

License identifiers here are each project's own stated license; confirm
against their sources before relying on them for a release.

