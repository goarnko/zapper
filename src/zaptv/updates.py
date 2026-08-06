"""Check whether a newer ZapTV has been released.

This *checks*, it does not update. A .deb is updated through apt and an
AppImage by replacing the file, so silently overwriting either would be both
wrong and surprising. All this does is notice a newer tag and say so.

The result is cached so launching the app is not a request to GitHub every
time, and every failure is silent: a version check is the least important
thing the app does, and it must never delay or interrupt watching TV.
"""

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import updater

LATEST_URL = "https://api.github.com/repos/goarnko/zapper/releases/latest"
RELEASES_URL = "https://github.com/goarnko/zapper/releases"

#: Ask GitHub at most this often, however many times the app is started.
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_TIMEOUT = 10


def state_path() -> Path:
    return updater.CACHE_DIR / "update-check.json"


@dataclass(frozen=True)
class Release:
    version: str
    url: str


def parse_version(text: str) -> tuple[int, ...]:
    """Turn "v0.2.1" into (0, 2, 1).

    Anything non-numeric is dropped, so a pre-release like "0.2.0-rc1"
    compares equal to "0.2.0" rather than crashing; `is_newer` then treats
    it as not newer, which is the safe direction for a suggestion.
    """
    cleaned = text.strip().lstrip("vV").split("+")[0].split("-")[0]
    parts = []
    for chunk in cleaned.split("."):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts)


def is_newer(candidate: str, current: str) -> bool:
    """True when `candidate` is a strictly higher version than `current`."""
    left, right = parse_version(candidate), parse_version(current)
    if not left:
        return False
    # Compare on equal length so (0, 2) and (0, 2, 0) are the same version.
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left > right


def _read_state(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, checked_at: float, version: str, url: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(
            json.dumps({"checked_at": checked_at, "version": version, "url": url}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        # A cache we cannot write just means we ask again next time.
        pass


def fetch_latest(url: str = LATEST_URL) -> Release | None:
    """Ask GitHub for the newest release, or None if that fails."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "zaptv-update-check",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        return None
    link = payload.get("html_url")
    return Release(version=tag, url=link if isinstance(link, str) and link else RELEASES_URL)


def check(
    current: str,
    path: Path | None = None,
    interval: int = CHECK_INTERVAL_SECONDS,
    now: float | None = None,
) -> Release | None:
    """The newer release if there is one, else None.

    Uses the cached answer while it is fresh, so repeated launches do not
    repeatedly ask GitHub.
    """
    path = path or state_path()
    now = time.time() if now is None else now
    state = _read_state(path)

    checked_at = state.get("checked_at")
    fresh = isinstance(checked_at, int | float) and (now - float(checked_at)) < interval
    if fresh:
        cached = state.get("version")
        if isinstance(cached, str) and is_newer(cached, current):
            url = state.get("url")
            return Release(cached, url if isinstance(url, str) else RELEASES_URL)
        return None

    latest = fetch_latest()
    if latest is None:
        return None

    _write_state(path, now, latest.version, latest.url)
    return latest if is_newer(latest.version, current) else None


def check_async(current: str) -> queue.Queue[Release | None]:
    """Run `check` on a daemon thread; the result lands on the queue.

    Startup must not wait on GitHub, and the app must still quit promptly if
    the request hangs — hence a daemon thread rather than a joined one.
    """
    results: queue.Queue[Release | None] = queue.Queue()

    def run() -> None:
        try:
            results.put(check(current))
        except Exception:
            results.put(None)

    threading.Thread(target=run, daemon=True).start()
    return results
