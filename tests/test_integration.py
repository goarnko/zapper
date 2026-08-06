"""Integration tests against the live TDTChannels feeds.

Off by default: they need the network, they are slow, and a broadcaster
having a bad afternoon should not fail an unrelated pull request. Run them
deliberately, and when upstream changes shape:

    ZAPTV_INTEGRATION=1 pytest tests/test_integration.py -q

What they are for is the class of bug unit tests structurally cannot catch:
the feed changing format under us. Every assertion is therefore a loose
bound on real data, not an exact value that would break on any edit
upstream.
"""

import os
import urllib.error
import urllib.request

from zaptv import epg, playlist, updater, webchannels

ENABLED = os.environ.get("ZAPTV_INTEGRATION") == "1"

#: The real list carried 471 channels when this was written. A drop far
#: below that means a parser or feed change, not a quiet edit upstream.
MIN_CHANNELS = 250
MIN_PROGRAMMES = 1000


def _fetch_status(url: str, timeout: int = 20) -> int:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_playlist_downloads_and_parses():
    if not ENABLED:
        return
    body = updater.fetch(updater.PLAYLIST_URL).decode("utf-8", "replace")
    channels = playlist.parse(body, "TDTChannels")

    assert len(channels) >= MIN_CHANNELS
    assert all(c.streams for c in channels)
    assert all(c.name for c in channels)
    # Mirrors still collapse: fewer channels than #EXTINF entries.
    assert len(channels) < body.count("#EXTINF")


def test_playlist_still_carries_the_attributes_we_read():
    if not ENABLED:
        return
    body = updater.fetch(updater.PLAYLIST_URL).decode("utf-8", "replace")
    channels = playlist.parse(body)

    assert any(c.logo for c in channels), "tvg-logo disappeared from the feed"
    assert any(c.tvg_id for c in channels), "tvg-id disappeared from the feed"
    assert len({c.group for c in channels}) > 5


def test_guide_downloads_and_parses(tmp_path):
    if not ENABLED:
        return
    path = tmp_path / "epg.xml.gz"
    path.write_bytes(updater.fetch(updater.EPG_URL))
    guide = epg.load(path)

    assert len(guide) >= MIN_PROGRAMMES
    assert guide.channels


def test_guide_and_playlist_still_overlap():
    if not ENABLED:
        return
    body = updater.fetch(updater.PLAYLIST_URL).decode("utf-8", "replace")
    channels = playlist.parse(body)
    path = updater.EPG_PATH
    if not path.exists():
        return
    guide = epg.load(path)

    matched = [c for c in channels if guide.has(c.tvg_id)]
    # Coverage was ~27% when written; near zero would mean the join key broke.
    assert len(matched) > 20, "playlist and guide no longer share tvg-ids"


def test_web_channel_pages_are_reachable():
    if not ENABLED:
        return
    unreachable = [
        name
        for name, url, _tvg in webchannels.SEED_CHANNELS
        if _fetch_status(url) >= 400
    ]
    assert not unreachable, f"broadcaster pages moved: {unreachable}"
