"""Guide cache handling across several XMLTV sources.

Nothing here touches the network: `download` is replaced so the tests
describe the caching and failure rules rather than the feeds.
"""

import gzip

import pytest

from zaptv import updater

XML = b"<?xml version='1.0'?><tv></tv>"


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Point every cache path at a temporary directory."""
    monkeypatch.setattr(updater, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(updater, "EPG_PATH", tmp_path / "epg.xml.gz")
    monkeypatch.setattr(
        updater,
        "EPG_SOURCES",
        [("first", "https://first.invalid/e.gz"), ("second", "https://second.invalid/e.gz")],
    )
    return tmp_path


def _fake_download(monkeypatch, failing=()):
    """Write a file per source, raising for any URL named in `failing`."""
    calls = []

    def download(path, url=updater.PLAYLIST_URL):
        calls.append(url)
        if url in failing:
            raise OSError("unreachable")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(XML))
        return path

    monkeypatch.setattr(updater, "download", download)
    return calls


def test_each_source_caches_to_its_own_file(cache, monkeypatch):
    _fake_download(monkeypatch)
    paths = updater.download_epgs()
    assert [p.name for p in paths] == ["epg-first.xml.gz", "epg-second.xml.gz"]
    assert all(p.exists() for p in paths)


def test_one_unreachable_source_does_not_cost_the_others(cache, monkeypatch):
    _fake_download(monkeypatch, failing={"https://first.invalid/e.gz"})
    paths = updater.download_epgs()
    assert [p.name for p in paths] == ["epg-second.xml.gz"]


def test_a_failed_refresh_keeps_the_stale_cache(cache, monkeypatch):
    _fake_download(monkeypatch)
    updater.download_epgs()

    # Now the first source goes down; yesterday's data is better than none.
    _fake_download(monkeypatch, failing={"https://first.invalid/e.gz"})
    paths = updater.download_epgs()
    assert [p.name for p in paths] == ["epg-first.xml.gz", "epg-second.xml.gz"]


def test_every_source_failing_yields_no_paths(cache, monkeypatch):
    _fake_download(
        monkeypatch,
        failing={"https://first.invalid/e.gz", "https://second.invalid/e.gz"},
    )
    assert updater.download_epgs() == []


def test_ensure_skips_a_source_it_cannot_fetch(cache, monkeypatch):
    _fake_download(monkeypatch, failing={"https://second.invalid/e.gz"})
    paths = updater.ensure_epgs()
    assert [p.name for p in paths] == ["epg-first.xml.gz"]


def test_a_fresh_cache_is_not_downloaded_again(cache, monkeypatch):
    _fake_download(monkeypatch)
    updater.ensure_epgs()
    calls = _fake_download(monkeypatch)
    updater.ensure_epgs()
    assert calls == [], "a cache inside its max age must not be refetched"


# -- migrating the single-source cache ----------------------------------


def test_the_old_single_cache_becomes_the_primary_source(cache):
    """Upgrading must not force a re-download of a file already present."""
    legacy = updater.EPG_PATH
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(gzip.compress(XML))

    updater.migrate_legacy_epg()

    assert not legacy.exists()
    assert updater.epg_path("first").read_bytes() == gzip.compress(XML)


def test_migration_does_not_clobber_an_existing_primary_cache(cache):
    legacy = updater.EPG_PATH
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"old")
    updater.epg_path("first").write_bytes(b"current")

    updater.migrate_legacy_epg()

    assert updater.epg_path("first").read_bytes() == b"current"


def test_migration_without_a_legacy_cache_is_a_no_op(cache):
    updater.migrate_legacy_epg()
    assert not updater.epg_path("first").exists()
