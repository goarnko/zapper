"""M3U playlist parsing.

Hand-rolled on purpose: the format is two lines per entry and pulling in a
dependency for it would break the zero-dependency rule.

    #EXTINF:-1 tvg-id="La1.TV" tvg-logo="..." group-title="Generalistas",La 1
    https://example.invalid/la1.m3u8
"""

import re

from .models import Channel

_ATTR = re.compile(r'([\w-]+)="([^"]*)"')

DEFAULT_GROUP = "Otros"


def _parse_extinf(line: str) -> tuple[dict[str, str], str]:
    """Split an #EXTINF line into its attributes and its display name.

    Attribute values routinely contain commas (logo URLs carry `w_200,h_200`),
    so the name cannot be found by splitting the raw line on ","; the
    attributes are stripped out first and the name taken from what remains.
    """
    body = line.split(":", 1)[1] if ":" in line else line
    attrs = {k.lower(): v for k, v in _ATTR.findall(body)}
    remainder = _ATTR.sub("", body)
    name = remainder.split(",", 1)[1].strip() if "," in remainder else ""
    return attrs, name


def parse(text: str) -> list[Channel]:
    """Parse playlist text into channels, merging each channel's mirrors.

    Entries are keyed by (name, group) because tvg-id is absent from most of
    the playlist and shared across unrelated variants where it is present.
    """
    channels: dict[tuple[str, str], Channel] = {}
    pending: tuple[dict[str, str], str] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#EXTINF"):
            pending = _parse_extinf(line)
            continue

        if line.startswith("#"):
            continue

        if pending is None:
            # A URL with no preceding #EXTINF; nothing to name it with.
            continue

        attrs, name = pending
        pending = None
        if not name:
            continue

        group = attrs.get("group-title") or DEFAULT_GROUP
        channel = channels.get((name, group))
        if channel is None:
            channel = Channel(
                name=name,
                group=group,
                logo=attrs.get("tvg-logo") or None,
                tvg_id=attrs.get("tvg-id") or None,
            )
            channels[(name, group)] = channel

        if line not in channel.streams:
            channel.streams.append(line)

    return [c for c in channels.values() if c.streams]


def load(path) -> list[Channel]:
    return parse(path.read_text(encoding="utf-8", errors="replace"))
