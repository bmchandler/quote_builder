"""Where the app keeps its database.

Run from a clone (`uv run quote-builder`), it's the clone's `data/`, for
development (git-ignored). Installed (`uv tool install`), it's
`~/.local/share/quote-builder/`, outside the install, which an upgrade
or uninstall replaces or removes. A dev build installed (its version
ends `+dev`, app_version.py) uses `~/.local/share/quote-builder-dev/`
instead, so testing one never touches a release's quotes.
"""

import os
from pathlib import Path

from quote_builder.app_version import is_dev, package_version

# src/quote_builder/data_folder.py -> the clone's top folder.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_FOLDER = "quote-builder"
DEV_APP_FOLDER = "quote-builder-dev"


def from_source(root: Path = PROJECT_ROOT) -> bool:
    """Whether the app runs from a clone, not an install."""
    return (root / "pyproject.toml").is_file()


def user_data_home(environ=os.environ) -> Path:
    """`$XDG_DATA_HOME` when set to an absolute path, else ~/.local/share."""
    base = Path(environ.get("XDG_DATA_HOME", ""))
    return base if base.is_absolute() else Path.home() / ".local" / "share"


def data_folder(
    root: Path = PROJECT_ROOT, environ=os.environ, version: str | None = None
) -> Path:
    """`data/` in a clone; `~/.local/share/quote-builder` once installed,
    or `quote-builder-dev` for an installed development build."""
    if from_source(root):
        return root / "data"
    folder = DEV_APP_FOLDER if is_dev(version or package_version()) else APP_FOLDER
    return user_data_home(environ) / folder
