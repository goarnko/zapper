"""Background refresh of playlists and guides.

The network is a dict of URL -> body; a URL absent from it fails the way an
unreachable host does, with OSError. Every cache path is redirected into
tmp_path: conftest isolates config, not the download cache.
"""

import gzip
import queue
import threading

import pytest

from zaptv import refresh, updater
from zaptv.providers import Provider, ProviderList

PLAYLIST_URL = "https://lists.invalid/tv.m3u"
GUIDE_URL = "https://guide.invalid/tv.xml.gz"

PLAYLIST = b"""#EXTM3U
#EXTINF:-1 tvg-id="La1.TV" group-title="Generalistas",La 1
https://x.invalid/la1.m3u8
"""

GUIDE = gzip.compress(b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="La1.TV"><display-name>La 1</display-name></channel>
  <programme start="20261010120000 +0000" stop="20261010130000 +0000" channel="La1.TV">
    <title>Telediario</title>
  </programme>
</tv>
""")


@pytest.fixture
def network(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(updater, "CACHE_DIR", cache)
    monkeypatch.setattr(updater, "PLAYLIST_PATH", cache / "playlist.m3u")
    monkeypatch.setattr(updater, "EPG_PATH", cache / "epg.xml.gz")
    monkeypatch.setattr(updater, "EPG_SOURCES", [("main", GUIDE_URL)])

    served = {PLAYLIST_URL: PLAYLIST, GUIDE_URL: GUIDE}
    fetched: list[str] = []

    def fetch(url, timeout=updater._TIMEOUT):
        fetched.append(url)
        if url not in served:
            raise OSError(f"unreachable: {url}")
        return served[url]

    monkeypatch.setattr(updater, "fetch", fetch)
    return served, fetched


def _result(results: "queue.Queue[refresh.Refreshed]") -> refresh.Refreshed:
    return results.get(timeout=5)


def test_refresh_downloads_channels_and_guide(network):
    result = refresh.refresh([Provider("TDT", PLAYLIST_URL)], [], force=False)

    assert [c.name for c in result.channels] == ["La 1"]
    assert result.failed == []
    assert result.guide is not None and len(result.guide) == 1


def test_an_unreachable_source_is_named_and_does_not_sink_the_others(network):
    providers = [Provider("Down", "https://down.invalid/x.m3u"), Provider("TDT", PLAYLIST_URL)]

    result = refresh.refresh(providers, [], force=False)

    assert result.failed == ["Down"]
    assert [c.name for c in result.channels] == ["La 1"]


def test_nothing_reachable_and_nothing_cached(network):
    served, _ = network
    served.clear()

    result = refresh.refresh([Provider("TDT", PLAYLIST_URL)], [], force=False)

    assert result.channels == []
    assert result.failed == ["TDT"]
    assert result.guide is None


def test_fresh_caches_are_not_downloaded_again_unless_forced(network):
    _, fetched = network
    providers = [Provider("TDT", PLAYLIST_URL)]
    refresh.refresh(providers, [], force=False)
    fetched.clear()

    refresh.refresh(providers, [], force=False)
    assert fetched == []

    refresh.refresh(providers, [], force=True)
    assert sorted(fetched) == sorted([PLAYLIST_URL, GUIDE_URL])


def test_a_failed_forced_refresh_falls_back_to_the_cache(network):
    served, _ = network
    providers = [Provider("TDT", PLAYLIST_URL)]
    refresh.refresh(providers, [], force=False)
    served.clear()

    result = refresh.refresh(providers, [], force=True)

    assert [c.name for c in result.channels] == ["La 1"]
    assert result.guide is not None and len(result.guide) == 1


def test_extra_guide_feeds_are_fetched(network):
    served, fetched = network
    served["https://extra.invalid/uk.xml.gz"] = GUIDE

    refresh.refresh([], [("uk", "https://extra.invalid/uk.xml.gz")], force=False)

    assert "https://extra.invalid/uk.xml.gz" in fetched


def test_refresh_async_delivers_on_the_queue(network):
    results = refresh.refresh_async([Provider("TDT", PLAYLIST_URL)], [], force=False)

    assert [c.name for c in _result(results).channels] == ["La 1"]


def test_refresh_async_reports_every_source_failed_on_an_unexpected_error(
    network, monkeypatch
):
    def explode(*_args, **_kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(refresh, "refresh", explode)

    results = refresh.refresh_async([Provider("TDT", PLAYLIST_URL)], [], force=False)

    result = _result(results)
    assert result.channels == []
    assert result.failed == ["TDT"]
    assert result.guide is None


def test_refresh_async_works_on_a_snapshot(network, tmp_path, monkeypatch):
    """The playlists window can edit the list while the worker runs."""
    sources = ProviderList([Provider("TDT", PLAYLIST_URL)], tmp_path / "p.json")
    edited = threading.Event()

    def after_the_edits(providers, extra, force):
        edited.wait(5)
        seen = [f"{p.name}:{'on' if p.enabled else 'off'}" for p in providers]
        return refresh.Refreshed([], seen, None)

    monkeypatch.setattr(refresh, "refresh", after_the_edits)
    results = refresh.refresh_async(sources.enabled, [], force=False)
    sources.set_enabled("TDT", False)
    sources.add("Other", "https://other.invalid/x.m3u")
    edited.set()

    assert _result(results).failed == ["TDT:on"]


def test_provider_list_load_channels_still_merges_through_load_from(network, tmp_path):
    sources = ProviderList(
        [Provider("TDT", PLAYLIST_URL), Provider("Down", "https://down.invalid/x.m3u")],
        tmp_path / "p.json",
    )

    channels, failed = sources.load_channels()

    assert [c.name for c in channels] == ["La 1"]
    assert failed == ["Down"]


# A source that could not be refreshed but still has a cached list is not
# "failed" (its channels are there), but the user should know the list is old.


def _age(path, days):
    import os
    import time

    when = time.time() - days * 86400
    os.utime(path, (when, when))
    return when


def test_a_stale_cache_that_could_not_be_refreshed_is_reported(network):
    served, _ = network
    providers = [Provider("TDT", PLAYLIST_URL)]
    refresh.refresh(providers, [], force=False)
    when = _age(providers[0].cache_path, 3)
    served.clear()

    result = refresh.refresh(providers, [], force=False)

    assert [c.name for c in result.channels] == ["La 1"]
    assert result.failed == []
    [(name, mtime)] = result.outdated
    assert name == "TDT" and mtime == pytest.approx(when)


def test_a_forced_refresh_that_fails_reports_the_cache_as_outdated(network):
    served, _ = network
    providers = [Provider("TDT", PLAYLIST_URL)]
    refresh.refresh(providers, [], force=False)
    served.clear()

    assert [name for name, _ in refresh.refresh(providers, [], force=True).outdated] == ["TDT"]


def test_a_successful_or_unneeded_refresh_reports_nothing_outdated(network, tmp_path):
    providers = [Provider("TDT", PLAYLIST_URL)]
    assert refresh.refresh(providers, [], force=False).outdated == []  # downloaded
    assert refresh.refresh(providers, [], force=False).outdated == []  # still fresh
    _age(providers[0].cache_path, 3)
    assert refresh.refresh(providers, [], force=False).outdated == []  # re-downloaded

    local = tmp_path / "mine.m3u"
    local.write_bytes(PLAYLIST)
    _age(local, 30)
    assert refresh.refresh([Provider("Mine", str(local))], [], force=True).outdated == []
