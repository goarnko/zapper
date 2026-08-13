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

#: XMLTV sources, in preference order: where two carry the same channel id
#: the first one wins. Each caches separately, so one being unreachable
#: never costs the others their data — the same rule providers.py applies
#: to playlists.
#:
#: TDTChannels is the primary and covers the terrestrial channels. The
#: second exists for one measured gap: Atresmedia (Antena 3, laSexta, Neox,
#: Nova, Mega, Atreseries) is absent from the TDTChannels guide entirely, so
#: those channels showed "No guide data" forever. Their id spaces do not
#: overlap at all — 0 ids in common out of 170 and 373 — so merging cannot
#: silently shadow one feed with the other.
EPG_SOURCES: list[tuple[str, str]] = [
    ("tdtchannels", EPG_URL),
    ("epgshare01", "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"),
]


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


def fetch(url: str, timeout: int = _TIMEOUT) -> bytes:
    """GET a URL and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: bytes = response.read()
    return body


def download(path: Path = PLAYLIST_PATH, url: str = PLAYLIST_URL) -> Path:
    """Fetch a resource, replacing the cache only once the body is in hand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = fetch(url)

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


def epg_path(slug: str) -> Path:
    return CACHE_DIR / f"epg-{slug}.xml.gz"


def migrate_legacy_epg() -> None:
    """Move the single-source cache to the primary source's own file.

    Before there were several guides the cache was one epg.xml.gz. Renaming
    it rather than ignoring it means upgrading does not force a fresh
    download of a file that is already there and current.
    """
    legacy = EPG_PATH
    target = epg_path(EPG_SOURCES[0][0])
    if legacy.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(target)


def ensure_epgs(max_age: int = MAX_AGE_SECONDS) -> list[Path]:
    """Cached paths for every guide source that has usable data.

    Sources are independent: one being unreachable costs only its own
    channels, so failures are skipped rather than raised. An empty list is a
    normal result — it means no guide, which the whole EPG path already
    treats as ordinary.
    """
    migrate_legacy_epg()
    paths = []
    for slug, url in EPG_SOURCES:
        try:
            paths.append(ensure(epg_path(slug), max_age, url))
        except OSError:
            continue
    return paths


def download_epgs() -> list[Path]:
    """Force a refresh of every guide source, keeping whatever succeeds."""
    migrate_legacy_epg()
    paths = []
    for slug, url in EPG_SOURCES:
        path = epg_path(slug)
        try:
            paths.append(download(path, url))
        except OSError:
            if path.exists():
                paths.append(path)
    return paths
