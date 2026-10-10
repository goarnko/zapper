"""Downloading playlists and guides off the Tk main thread.

Startup used to download before the window existed, and Ctrl+R downloaded on
the main thread. When a host does not answer, each of its addresses costs a
full connection timeout, so either way ZapTV sat frozen for minutes. Here
the downloading and parsing run on a daemon thread and the result lands on a
queue the UI polls: the same shape as updates.check_async.

Nothing here touches Tk, and nothing here touches Pillow, so neither Tk's
single-thread rule nor the lazy-plugin race noted in logos.py applies.
"""

import queue
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from . import epg, updater
from .models import Channel
from .providers import Provider, load_from


@dataclass(frozen=True)
class Refreshed:
    #: Merged channels; empty when every source failed.
    channels: list[Channel]
    #: Names of providers that yielded nothing.
    failed: list[str]
    #: None when no guide source has usable data, fresh or cached.
    guide: epg.Guide | None
    #: (provider name, cache mtime) for sources whose download failed but
    #: whose old list loaded: not failed, but not up to date either.
    outdated: list[tuple[str, float]] = field(default_factory=list)


def refresh(
    providers: Sequence[Provider], extra: Sequence[tuple[str, str]], force: bool
) -> Refreshed:
    """Bring playlists and guides up to date and parse them.

    `force` downloads everything, as Ctrl+R asks; otherwise only caches
    older than a day are fetched. Either way a failed download falls back to
    the cache, so a dropped network costs freshness, not channels.
    """
    max_age = 0 if force else updater.MAX_AGE_SECONDS
    outdated: list[tuple[str, float]] = []
    channels, failed = load_from(providers, max_age, outdated=outdated)
    if force:
        paths = updater.download_epgs(extra=extra)
    else:
        paths = updater.ensure_epgs(max_age, extra=extra)
    guide = epg.load_all(paths) if paths else None
    return Refreshed(channels, failed, guide, outdated)


def refresh_async(
    providers: Iterable[Provider], extra: Sequence[tuple[str, str]], force: bool
) -> queue.Queue[Refreshed]:
    """Run `refresh` on a daemon thread; the result lands on the queue.

    The providers are copied here, on the caller's thread, before the worker
    starts: the playlists window can add, remove or toggle them meanwhile.
    Any unexpected error still produces a result, so the UI never waits
    forever for one.
    """
    snapshot = [replace(provider) for provider in providers]
    wanted = list(extra)
    results: queue.Queue[Refreshed] = queue.Queue()

    def run() -> None:
        try:
            results.put(refresh(snapshot, wanted, force))
        except Exception:
            results.put(Refreshed([], [p.name for p in snapshot], None))

    threading.Thread(target=run, daemon=True).start()
    return results
