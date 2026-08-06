"""Channel logo fetching and caching.

Logos are the one place ZapTV needs a third-party library. Nearly every logo
the playlist points at is JPEG (graph.facebook.com alone serves most of them)
and Tk's PhotoImage decodes only PNG and GIF, so Pillow does the decoding and
downscaling once, on the way into the cache. What lands on disk is a small PNG
that Tk can read directly.

Downloads run on worker threads because there are several hundred of them.
Only the main thread may touch Tk, so workers write files and the UI collects
finished ones by polling `drain()`.
"""

import hashlib
import queue
import threading
from pathlib import Path
from typing import Protocol

from PIL import Image

from . import updater

#: Row height in the channel list; logos are square and fit within it.
SIZE = 24

WORKERS = 6
_FETCH_TIMEOUT = 15


def cache_dir() -> Path:
    return updater.CACHE_DIR / "logos"


def cache_path(url: str, size: int = SIZE) -> Path:
    """Stable filename for a logo URL.

    Hashed because the URLs carry query strings and characters that do not
    survive a filesystem; the size is included so changing it re-renders
    rather than silently reusing the wrong scale.
    """
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir() / f"{digest}-{size}.png"


def convert(data: bytes, path: Path, size: int = SIZE) -> Path:
    """Decode any supported image and write a downscaled PNG."""
    from io import BytesIO

    with Image.open(BytesIO(data)) as image:
        image = image.convert("RGBA")
        image.thumbnail((size, size), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".png.part")
        image.save(tmp, "PNG")
        tmp.replace(path)
    return path


def prepare(url: str, size: int = SIZE) -> Path | None:
    """Return a cached PNG for a logo URL, downloading it if needed.

    Returns None on any failure: a missing logo is cosmetic and must never
    interrupt browsing.
    """
    path = cache_path(url, size)
    if path.exists():
        return path
    try:
        return convert(updater.fetch(url, timeout=_FETCH_TIMEOUT), path, size)
    except Exception:
        # Network error, redirect to HTML, truncated file, unsupported
        # format — all equally uninteresting, all equally "no logo".
        return None


class LogoSource(Protocol):
    """What the UI needs from a logo store.

    Narrower than LogoStore on purpose: the UI only asks for a path and
    collects finished downloads, so a test double needs nothing more.
    """

    def path_for(self, url: str | None) -> Path | None: ...

    def drain(self) -> list[str]: ...


class LogoStore:
    """Cached logos, fetched in the background.

    `get` answers immediately from memory or disk and otherwise queues a
    download. The UI calls `drain` periodically to learn which logos have
    since arrived, and only then builds Tk images — on the main thread.
    """

    def __init__(self, size: int = SIZE, workers: int = WORKERS):
        self.size = size
        self._paths: dict[str, Path | None] = {}
        self._queued: set[str] = set()
        self._work: queue.Queue[str | None] = queue.Queue()
        self._done: queue.Queue[tuple[str, Path]] = queue.Queue()
        self._lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._worker, daemon=True) for _ in range(workers)
        ]
        for thread in self._threads:
            thread.start()

    def _worker(self) -> None:
        while True:
            url = self._work.get()
            if url is None:
                return
            path = prepare(url, self.size)
            if path is not None:
                self._done.put((url, path))
            else:
                with self._lock:
                    self._paths[url] = None

    def path_for(self, url: str | None) -> Path | None:
        """Cached path for a logo, queueing a download the first time it misses."""
        if not url:
            return None
        with self._lock:
            if url in self._paths:
                return self._paths[url]

        path = cache_path(url, self.size)
        if path.exists():
            with self._lock:
                self._paths[url] = path
            return path

        with self._lock:
            if url not in self._queued:
                self._queued.add(url)
                self._work.put(url)
        return None

    def drain(self) -> list[str]:
        """URLs whose logos finished downloading since the last call."""
        ready = []
        while True:
            try:
                url, path = self._done.get_nowait()
            except queue.Empty:
                break
            with self._lock:
                self._paths[url] = path
            ready.append(url)
        return ready

    def stop(self) -> None:
        for _ in self._threads:
            self._work.put(None)
