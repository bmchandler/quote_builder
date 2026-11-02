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

## Code layout

All in `src/quote_builder/`:

- `app.py`: the window (NiceGUI), and `main`, the `quote-builder`
  command.
- `quotes.py`: quotes and line items as dataclasses.
- `business.py`: a business and its settings, and its tax rates.
- `customers.py`: a business's customers.
- `money.py`: reading and showing amounts, quantities, percents, and
  discounts.
- `dates.py`: reading and showing dates, and valid-through dates.
- `totals.py`: what a line and a quote add up to.
- `search.py`: showing where a search matched (highlights, excerpts).
- `quote_numbers.py`: new quote numbers.
- `storage.py`, `schema.sql`: the SQLite database.
- `data_folder.py`: where the database lives.

Tests in `tests/` mirror these files.

