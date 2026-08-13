"""Layout for the full-guide grid.

Kept out of ui.py so the positioning maths can be tested without a display,
the same split search.py makes for channel matching.

Positions are fractions of the visible window rather than pixels. The grid
scales to whatever width the canvas has, so a resize redraws from the same
layout instead of recomputing it, and the tests never need a Tk widget to
say where a programme belongs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .epg import Guide
from .models import Channel, Programme
from .search import sort_key

#: How much of the schedule one screenful shows.
DEFAULT_SPAN = timedelta(hours=3)
#: How far the ◀ / ▶ controls move the window.
PAGE_STEP = timedelta(hours=1)


@dataclass
class Block:
    """One programme, positioned across the visible window."""

    programme: Programme
    start_frac: float
    end_frac: float
    #: Runs past the window edge. The UI marks these, so a title cut off at
    #: the boundary does not read as the whole programme.
    clipped_left: bool = False
    clipped_right: bool = False

    @property
    def width_frac(self) -> float:
        return self.end_frac - self.start_frac


@dataclass
class Row:
    """One channel's strip of the grid."""

    channel: Channel
    blocks: list[Block] = field(default_factory=list)


def visible_channels(guide: Guide, channels: list[Channel]) -> list[Channel]:
    """Channels with guide data: alphabetical, one row per XMLTV id.

    Only about a quarter of the playlist carries a usable tvg-id, so most
    channels have no row at all. That is the normal case, not an error.

    A tvg-id is also shared by more than one channel — 15 of them in the live
    playlist, with Teledeporte / Teledeporte GEO and three copies of 3CatInfo
    among them. Each copy would otherwise draw an identical row, so the first
    name alphabetically wins, which in practice is the plain one rather than
    the GEO, SD or EN variant.
    """
    seen: set[str] = set()
    rows: list[Channel] = []
    for channel in sorted(channels, key=sort_key):
        channel_id = channel.tvg_id
        if not channel_id or not guide.has(channel_id) or channel_id in seen:
            continue
        seen.add(channel_id)
        rows.append(channel)
    return rows


def build(
    guide: Guide,
    channels: list[Channel],
    start: datetime,
    end: datetime,
) -> list[Row]:
    """Position every visible channel's programmes across [start, end).

    A channel with guide data but nothing scheduled in this window still gets
    an empty row: dropping it would make the rows reflow as the user pages
    through time, and a grid whose channels move under the pointer is worse
    than one with a gap in it.
    """
    span = (end - start).total_seconds()
    if span <= 0:
        return []

    rows: list[Row] = []
    for channel in visible_channels(guide, channels):
        programmes = guide.between(channel.tvg_id, start, end)
        blocks: list[Block] = []
        for index, programme in enumerate(programmes):
            stop = programme.end
            if stop is None:
                # XMLTV allows no stop time: the programme runs until the next
                # one starts, or to the window edge when it is the last.
                following = programmes[index + 1] if index + 1 < len(programmes) else None
                stop = following.start if following is not None else end

            left = (programme.start - start).total_seconds() / span
            right = (stop - start).total_seconds() / span
            block = Block(
                programme=programme,
                start_frac=max(left, 0.0),
                end_frac=min(right, 1.0),
                clipped_left=left < 0.0,
                clipped_right=right > 1.0,
            )
            # A programme ending exactly as the window opens has nothing to
            # draw; it would be an invisible click target.
            if block.width_frac > 0:
                blocks.append(block)
        rows.append(Row(channel=channel, blocks=blocks))
    return rows
