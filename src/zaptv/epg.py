"""XMLTV guide parsing.

Stdlib only, per STACK.md: gzip plus xml.etree.ElementTree.

Guide data covers far fewer channels than the playlist carries — roughly a
quarter of them, because most playlist entries have no tvg-id to match on.
Every lookup here therefore returns None rather than raising, and callers are
expected to render "no guide" as a normal state, not an error.
"""

import gzip
import xml.etree.ElementTree as ET
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, cast

from .models import Programme

_GZIP_MAGIC = b"\x1f\x8b"


def _open(path: Path) -> IO[bytes]:
    """Open the guide whether or not it is gzipped.

    The cache file is .gz, but a hand-supplied plain XML file should work too.
    """
    with open(path, "rb") as probe:
        gzipped = probe.read(2) == _GZIP_MAGIC
    # Returning an open handle is the point: callers close it with `with`.
    handle = gzip.open(path, "rb") if gzipped else open(path, "rb")  # noqa: SIM115
    # GzipFile implements the binary IO protocol; typeshed just does not
    # declare it as IO[bytes].
    return cast(IO[bytes], handle)


def parse_timestamp(value: str) -> datetime | None:
    """Parse an XMLTV timestamp, e.g. "20260806050000 +0000".

    The offset is optional in XMLTV; when absent the time is treated as UTC.
    Returns None for anything unparseable so one bad entry cannot take down
    the whole guide.
    """
    if not value:
        return None
    parts = value.strip().split()
    stamp = parts[0]
    # XMLTV allows truncated stamps (YYYYMMDD, YYYYMMDDHH, ...); pad to full
    # seconds so the shorter forms still parse.
    if not stamp.isdigit() or not 4 <= len(stamp) <= 14:
        return None
    stamp = stamp.ljust(14, "0")
    try:
        naive = datetime.strptime(stamp, "%Y%m%d%H%M%S")
    except ValueError:
        return None

    if len(parts) < 2:
        return naive.replace(tzinfo=timezone.utc)
    try:
        offset = datetime.strptime(parts[1], "%z").tzinfo
    except ValueError:
        return naive.replace(tzinfo=timezone.utc)
    return naive.replace(tzinfo=offset)


def _text(element: ET.Element, tag: str) -> str:
    found = element.find(tag)
    return (found.text or "").strip() if found is not None else ""


class Guide:
    """Programmes indexed by XMLTV channel id, each list ordered by start."""

    def __init__(self, programmes: dict[str, list[Programme]] | None = None):
        self._by_channel: dict[str, list[Programme]] = {}
        for channel, items in (programmes or {}).items():
            self._by_channel[channel] = sorted(items, key=lambda p: p.start)
        self._starts = {
            channel: [p.start for p in items] for channel, items in self._by_channel.items()
        }

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_channel.values())

    @property
    def channels(self) -> set[str]:
        return set(self._by_channel)

    def has(self, channel: str | None) -> bool:
        return bool(channel) and channel in self._by_channel

    def now_and_next(
        self, channel: str | None, at: datetime | None = None
    ) -> tuple[Programme | None, Programme | None]:
        """Current and following programme for a channel.

        Returns (None, None) for an unknown channel, which is the common case:
        most playlist channels carry no tvg-id at all.
        """
        if not self.has(channel):
            return None, None
        assert channel is not None

        at = at or datetime.now(timezone.utc)
        items = self._by_channel[channel]
        # Index of the last programme that had already started at `at`.
        index = bisect_right(self._starts[channel], at) - 1

        current = items[index] if index >= 0 and items[index].is_live(at) else None
        following = items[index + 1] if index + 1 < len(items) else None
        return current, following

    def between(self, channel: str | None, start: datetime, end: datetime) -> list[Programme]:
        """Programmes overlapping [start, end), ordered by start.

        A programme that began before `start` but is still running is
        included: on the grid it occupies the left edge rather than being
        missing, which is why this steps back one from the bisect rather than
        taking everything at or after `start`.
        """
        if not self.has(channel):
            return []
        assert channel is not None

        items = self._by_channel[channel]
        starts = self._starts[channel]
        first = max(bisect_right(starts, start) - 1, 0)

        found: list[Programme] = []
        for index in range(first, len(items)):
            programme = items[index]
            if programme.start >= end:
                break
            stop = programme.end
            if stop is None:
                # No stop time: runs until the next programme, or off the end.
                stop = items[index + 1].start if index + 1 < len(items) else end
            if stop > start:
                found.append(programme)
        return found

    def upcoming(
        self, channel: str | None, at: datetime | None = None, limit: int = 5
    ) -> list[Programme]:
        """Programmes starting after `at`, soonest first."""
        if not self.has(channel):
            return []
        assert channel is not None
        at = at or datetime.now(timezone.utc)
        index = bisect_right(self._starts[channel], at)
        return self._by_channel[channel][index : index + limit]


def parse(source: IO[bytes] | IO[str] | str | Path) -> Guide:
    """Build a Guide from an XMLTV file object or path.

    Programmes missing a channel, title or start time are skipped: they cannot
    be placed on a timeline or shown to anyone.
    """
    root = ET.parse(source).getroot()
    programmes: dict[str, list[Programme]] = {}

    for element in root.iter("programme"):
        channel = element.get("channel")
        start = parse_timestamp(element.get("start", ""))
        title = _text(element, "title")
        if not channel or start is None or not title:
            continue

        programmes.setdefault(channel, []).append(
            Programme(
                channel=channel,
                title=title,
                start=start,
                end=parse_timestamp(element.get("stop", "")),
                description=_text(element, "desc"),
                category=_text(element, "category"),
            )
        )

    return Guide(programmes)


def load(path: Path) -> Guide:
    """Parse the cached guide, returning an empty Guide if it is unusable.

    A corrupt or half-downloaded guide must not stop the user watching TV.
    """
    try:
        with _open(path) as handle:
            return parse(handle)
    except (OSError, ET.ParseError, EOFError):
        return Guide()
