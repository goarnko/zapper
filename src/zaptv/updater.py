"""Playlist download and cache freshness.

The app never ships channels: the playlist is always fetched from
TDTChannels and cached under ~/.local/share/zaptv/, refreshed when stale.
"""

import os
import time
import urllib.request
from pathlib import Path

PLAYLIST_URL = "https://www.tdtchannels.com/lists/tv.m3u8"
EPG_URL = "https://www.tdtchannels.com/epg/TV.xml.gz"


def cache_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "zaptv"


CACHE_DIR = cache_dir()
PLAYLIST_PATH = CACHE_DIR / "playlist.m3u"
EPG_PATH = CACHE_DIR / "epg.xml.gz"

MAX_AGE_SECONDS = 24 * 60 * 60
_TIMEOUT = 30
_USER_AGENT = "zaptv/0.1 (+https://github.com/goarnko/zapper)"


def is_stale(path: Path = PLAYLIST_PATH, max_age: int = MAX_AGE_SECONDS) -> bool:
    if not path.exists():
        return True
    return (time.time() - path.stat().st_mtime) > max_age


def download(path: Path = PLAYLIST_PATH, url: str = PLAYLIST_URL) -> Path:
    """Fetch a resource, replacing the cache only once the body is in hand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        body = response.read()

    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(body)
    tmp.replace(path)
    return path


def ensure(
    path: Path = PLAYLIST_PATH,
    max_age: int = MAX_AGE_SECONDS,
    url: str = PLAYLIST_URL,
) -> Path:
    """Return a usable cache path, downloading only when needed.

    A refresh failure on an existing cache is not fatal — yesterday's channel
    list is far better than no channel list.
    """
    if not is_stale(path, max_age):
        return path

    try:
        return download(path, url)
    except OSError:
        if path.exists():
            return path
        raise


def download_epg(path: Path = EPG_PATH) -> Path:
    return download(path, EPG_URL)


def ensure_epg(path: Path = EPG_PATH, max_age: int = MAX_AGE_SECONDS) -> Path | None:
    """Return the cached guide path, or None if there is nothing usable.

    Unlike the playlist, a missing guide is survivable: the app still lists
    and plays channels, it just cannot show what is on.
    """
    try:
        return ensure(path, max_age, EPG_URL)
    except OSError:
        return None
