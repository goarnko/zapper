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
from typing import Protocol

from .epg import Guide
from .models import Channel, Programme
from .search import normalize, sort_key

#: Section heading for favorited channels, matching the channel list.
FAVORITES_LABEL = "★ FAVORITES"


class Names(Protocol):
    """Anything that can answer "is this channel name in here".

    A Protocol rather than `Container[str]`, which requires
    `__contains__(object)`: `storage.Favorites` narrows its parameter to
    `str` and so does not satisfy it. This matches what Favorites actually
    offers, and a plain set of names satisfies it too — the same reason
    `logos.LogoSource` is a Protocol rather than the concrete store.
    """

    def __contains__(self, name: str) -> bool: ...


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


@dataclass
class Section:
    """A collapsible band of rows: favorites, or one channel group."""

    label: str
    rows: list[Row] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class Line:
    """One drawn line of the grid, top to bottom.

    Either a section header (`row is None`) or a channel inside it. Flattening
    the sections here rather than in the UI keeps the index-to-content mapping
    — which is what hit testing needs — testable without a display.
    """

    section: Section
    row: Row | None = None

    @property
    def is_header(self) -> bool:
        return self.row is None


def lines(sections: list[Section]) -> list[Line]:
    """Header, then rows for each expanded section, in drawing order."""
    out: list[Line] = []
    for section in sections:
        out.append(Line(section))
        if not section.collapsed:
            out.extend(Line(section, row) for row in section.rows)
    return out


def visible_channels(
    guide: Guide,
    channels: list[Channel],
    favorites: "Names | None" = None,
) -> list[Channel]:
    """Channels with guide data: favorites first, then alphabetical.

    Only about a quarter of the playlist carries a usable tvg-id, so most
    channels have no row at all. That is the normal case, not an error.

    A tvg-id is also shared by more than one channel — 15 of them in the live
    playlist, with Teledeporte / Teledeporte GEO and three copies of 3CatInfo
    among them. Each copy would otherwise draw an identical row, so the first
    name alphabetically wins, which in practice is the plain one rather than
    the GEO, SD or EN variant.

    Favorites float to the top as they do in the channel list, but unlike it
    they appear **once**. The list repeats a favorite under its group because
    it is grouped and the channel belongs in both places; the grid has no
    groups, so a second copy would just be the same schedule twice — which
    is exactly what deduplicating by tvg-id exists to prevent.
    """
    favorites = favorites if favorites is not None else frozenset()

    def order(channel: Channel) -> tuple[bool, str, str]:
        # False sorts before True, so "not favorite" puts favorites first.
        return (channel.name not in favorites, *sort_key(channel))

    seen: set[str] = set()
    rows: list[Channel] = []
    for channel in sorted(channels, key=order):
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
    favorites: "Names | None" = None,
    collapsed: "Names | None" = None,
) -> list[Section]:
    """Group the visible channels and position their programmes.

    Sections mirror the channel list: favorites first, then one per group in
    alphabetical order. A favorite appears **only** under FAVORITES and not
    again in its group — the list can afford that duplication because its
    rows are one line each, but here it would draw the same schedule twice.

    A channel with guide data but nothing scheduled in this window still gets
    an empty row: dropping it would make the rows reflow as the user pages
    through time, and a grid whose channels move under the pointer is worse
    than one with a gap in it.
    """
    span = (end - start).total_seconds()
    if span <= 0:
        return []

    favorites = favorites if favorites is not None else frozenset()
    collapsed = collapsed if collapsed is not None else frozenset()

    grouped: dict[str, list[Row]] = {}
    starred: list[Row] = []
    for channel in visible_channels(guide, channels, favorites):
        row = _row_for(guide, channel, start, end, span)
        if channel.name in favorites:
            starred.append(row)
        else:
            grouped.setdefault(channel.group.upper(), []).append(row)

    sections = []
    if starred:
        sections.append(
            Section(FAVORITES_LABEL, starred, FAVORITES_LABEL in collapsed)
        )
    for label in sorted(grouped, key=normalize):
        sections.append(Section(label, grouped[label], label in collapsed))
    return sections


def _row_for(
    guide: Guide, channel: Channel, start: datetime, end: datetime, span: float
) -> Row:
    """Lay one channel's programmes out across the window."""
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
    return Row(channel=channel, blocks=blocks)
