"""Where the app keeps its database."""

from pathlib import Path

# src/quote_builder/data_folder.py -> the clone's top folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_folder() -> Path:
    """`data/` in a clone; `~/.local/share/quote-builder` once installed."""
    if (PROJECT_ROOT / "pyproject.toml").is_file():
        return PROJECT_ROOT / "data"
    return Path.home() / ".local" / "share" / "quote-builder"
