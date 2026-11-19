from pathlib import Path

from quote_builder import data_folder as module
from quote_builder.data_folder import data_folder


def test_clone_keeps_data_beside_pyproject():
    assert data_folder() == module.PROJECT_ROOT / "data"


def test_installed_release_uses_local_share(tmp_path):
    # Installed, the package's folder has no pyproject.toml above it.
    assert data_folder(tmp_path, {}, "2026.10.12") == Path.home() / ".local/share/quote-builder"


def test_installed_release_honors_xdg_data_home(tmp_path):
    assert data_folder(tmp_path, {"XDG_DATA_HOME": "/xdg"}, "2026.10.12") == Path(
        "/xdg/quote-builder"
    )


def test_a_dev_install_keeps_its_data_apart_from_a_releases(tmp_path):
    dev = "2026.10.12+dev"
    assert data_folder(tmp_path, {}, dev) == Path.home() / ".local/share/quote-builder-dev"
    assert data_folder(tmp_path, {"XDG_DATA_HOME": "/xdg"}, dev) == Path("/xdg/quote-builder-dev")


def test_a_dev_clone_keeps_its_data_in_the_projects_data_folder():
    # from_source wins: a clone uses data/ whatever the version says.
    assert data_folder(module.PROJECT_ROOT, {}, "2026.10.12+dev") == module.PROJECT_ROOT / "data"
