"""Startup: the window opens on the caches, the CLI still refreshes first.

On 2026-10-10 the playlist host was unreachable and ZapTV showed no window
at all: main() downloaded before building it, and each of the host's four
addresses cost a full connection timeout. These tests pin that the GUI path
never touches the network, while --list keeps its refresh-then-print
behaviour.

main() writes the web-channel seeds and providers.json as a side effect, and
conftest isolates neither, so every path is redirected here. ui.run is
replaced, so no window is ever built.
"""

import pytest

from zaptv import main as main_module
from zaptv import providers, updater, webchannels

PLAYLIST = """#EXTM3U
#EXTINF:-1 group-title="Generalistas",La 1
https://x.invalid/la1.m3u8
"""


@pytest.fixture
def startup(tmp_path, monkeypatch):
    config = tmp_path / "config"
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setattr(providers, "PROVIDERS_PATH", config / "zaptv" / "providers.json")
    monkeypatch.setattr(updater, "CACHE_DIR", cache)
    monkeypatch.setattr(updater, "PLAYLIST_PATH", cache / "playlist.m3u")
    monkeypatch.setattr(updater, "EPG_PATH", cache / "epg.xml.gz")

    fetched: list[str] = []

    def fetch(url, timeout=updater._TIMEOUT):
        fetched.append(url)
        if url == updater.PLAYLIST_URL:
            return PLAYLIST.encode()
        raise OSError(f"unreachable: {url}")

    monkeypatch.setattr(updater, "fetch", fetch)

    from zaptv import ui

    shown: list[list[str]] = []
    monkeypatch.setattr(
        ui, "run", lambda channels, *args, **kwargs: shown.append([c.name for c in channels])
    )
    return cache / "playlists" / "tdtchannels.m3u", fetched, shown


def test_the_window_opens_on_the_cache_without_touching_the_network(startup):
    cached, fetched, shown = startup
    cached.parent.mkdir(parents=True)
    cached.write_text(PLAYLIST, encoding="utf-8")
    # Older than a day: before, this alone made startup download first.
    old = 1_000_000_000
    import os

    os.utime(cached, (old, old))

    assert main_module.main([]) == 0
    assert fetched == []
    assert len(shown) == 1 and "La 1" in shown[0]


def test_with_no_cache_the_window_still_opens(startup):
    """First launch, or a wiped cache: an empty window that says it is
    loading, not an exit with a message menu users never see."""
    _cached, fetched, shown = startup

    assert main_module.main([]) == 0
    assert fetched == []
    assert len(shown) == 1


def test_list_still_refreshes_before_printing(startup, capsys):
    _cached, fetched, shown = startup

    assert main_module.main(["--list"]) == 0
    assert updater.PLAYLIST_URL in fetched
    assert "La 1" in capsys.readouterr().out
    assert shown == []


def test_list_with_nothing_anywhere_is_still_an_error(startup, monkeypatch):
    _cached, _fetched, _shown = startup

    def unreachable(url, timeout=updater._TIMEOUT):
        raise OSError("unreachable")

    monkeypatch.setattr(updater, "fetch", unreachable)
    # The seeded web-channel lists are local files, so switch them off to
    # leave the CLI with genuinely nothing.
    sources = providers.ProviderList.load()
    webchannels.install(sources)
    webchannels.install_regional(sources)
    for provider in list(sources):
        sources.set_enabled(provider.name, False)
    sources.set_enabled(providers.TDTCHANNELS_NAME, True)

    assert main_module.main(["--list"]) == 1


def test_the_connection_timeout_is_short():
    """Nothing waits on it any more; it only decides how soon the status
    bar can say a source is unavailable."""
    assert updater._TIMEOUT == 10
