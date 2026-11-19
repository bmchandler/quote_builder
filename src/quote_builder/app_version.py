"""The version the app reports (shown in the About view).

A release reports its date (`2026.10.12`). On the dev branch,
pyproject.toml's version ends `+dev` (`2026.10.12+dev`: the release it
follows), and a build installed from git adds the commit it was built
from (`2026.10.12+dev.5f820a58`), which the installer records in
`direct_url.json` (PEP 610). A clone run (`uv run`) or an install from a
package index records no commit, so its version is reported as written.
"""

import json
import re
from functools import cache
from importlib.metadata import distribution

# The app's package name, and how it names itself.
PROGRAM_ID = "quote-builder"
DEV_MARK = "+dev"
SHORT_COMMIT = 8


def is_dev(version: str) -> bool:
    """Whether a version is the dev branch's, not a release's."""
    return DEV_MARK in version


def installed_commit(direct_url: str | None) -> str | None:
    """The commit in a `direct_url.json`'s text, or None without one."""
    try:
        commit = json.loads(direct_url or "{}").get("vcs_info", {}).get("commit_id")
    except (ValueError, AttributeError):
        return None
    if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return commit
    return None


def reported_version(version: str, direct_url: str | None) -> str:
    """`version`, with the short commit added to a dev version that has one."""
    commit = installed_commit(direct_url) if is_dev(version) else None
    return f"{version}.{commit[:SHORT_COMMIT]}" if commit else version


def package_version() -> str:
    """The version in pyproject.toml, as installed."""
    return distribution(PROGRAM_ID).version


def package_summary() -> str:
    """The app's one-line description, from the package metadata."""
    return distribution(PROGRAM_ID).metadata["Summary"]


@cache
def app_version() -> str:
    package = distribution(PROGRAM_ID)
    return reported_version(package.version, package.read_text("direct_url.json"))
