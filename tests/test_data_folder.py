from quote_builder import data_folder as module
from quote_builder.data_folder import data_folder


def test_clone_keeps_data_beside_pyproject():
    assert data_folder() == module.PROJECT_ROOT / "data"


def test_installed_copy_uses_local_share(tmp_path, monkeypatch):
    # Installed, the package's folder has no pyproject.toml above it.
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path / "home")
    assert data_folder() == tmp_path / "home" / ".local" / "share" / "quote-builder"
