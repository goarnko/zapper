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


def parse(text: str, provider: str = "") -> list[Channel]:
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
                provider=provider,
                # Non-standard, ours: lets a playlist say which player a
                # channel needs. Unknown to other M3U readers, which ignore
                # unrecognised attributes.
                player=attrs.get("zaptv-player", ""),
            )
            channels[(name, group)] = channel

        if line not in channel.streams:
            channel.streams.append(line)

    return [c for c in channels.values() if c.streams]


def load(path, provider: str = "") -> list[Channel]:
    return parse(path.read_text(encoding="utf-8", errors="replace"), provider)


def merge(sources: list[list[Channel]]) -> list[Channel]:
    """Combine channel lists from several providers into one.

    Channels are matched on (name, group), the same key used for mirrors
    within a single playlist, and their streams are pooled — a second source
    offering the same channel becomes another fallback rather than a
    duplicate row. The first provider to supply a channel owns its metadata,
    so ordering the sources orders the preference.
    """
    merged: dict[tuple[str, str], Channel] = {}
    for channels in sources:
        for channel in channels:
            key = (channel.name, channel.group)
            existing = merged.get(key)
            if existing is None:
                merged[key] = channel
                continue
            for stream in channel.streams:
                if stream not in existing.streams:
                    existing.streams.append(stream)
            # Fill gaps the earlier provider left, without overwriting it.
            existing.logo = existing.logo or channel.logo
            existing.tvg_id = existing.tvg_id or channel.tvg_id
    return list(merged.values())
