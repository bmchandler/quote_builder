"""The version the app reports (shown in About)."""

from quote_builder.app_version import installed_commit, is_dev, reported_version

# A 40-hex-digit commit, and a PEP 610 direct_url.json carrying it.
COMMIT = "5f820a58" + "0" * 32
DIRECT_URL = '{"url": "git+https://x", "vcs_info": {"vcs": "git", "commit_id": "%s"}}'


def test_is_dev_reads_the_dev_mark():
    assert is_dev("2026.10.12+dev")
    assert not is_dev("2026.10.12")


def test_a_release_is_reported_as_written():
    assert reported_version("2026.10.12", None) == "2026.10.12"
    # Even with a commit to hand, a release doesn't append one.
    assert reported_version("2026.10.12", DIRECT_URL % COMMIT) == "2026.10.12"


def test_a_dev_build_appends_its_short_commit():
    assert (
        reported_version("2026.10.12+dev", DIRECT_URL % COMMIT)
        == "2026.10.12+dev.5f820a58"
    )


def test_a_dev_version_without_a_commit_is_reported_as_written():
    assert reported_version("2026.10.12+dev", None) == "2026.10.12+dev"


def test_installed_commit_ignores_missing_or_malformed():
    assert installed_commit(None) is None
    assert installed_commit("{}") is None
    assert installed_commit("not json") is None
    assert installed_commit('{"vcs_info": {"commit_id": "not-hex"}}') is None
    assert installed_commit(DIRECT_URL % COMMIT) == COMMIT
