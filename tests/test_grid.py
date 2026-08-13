"""Grid layout, tested without a display.

The positions here are fractions of the visible window, so every assertion
is arithmetic rather than pixels — which is the point of keeping the layout
out of ui.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from zaptv import grid
from zaptv.epg import Guide
from zaptv.models import Channel, Programme

START = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=3)


def programme(channel_id, title, start_min, minutes, end=True):
    start = START + timedelta(minutes=start_min)
    return Programme(
        channel=channel_id,
        title=title,
        start=start,
        end=start + timedelta(minutes=minutes) if end else None,
    )


def channel(name, channel_id=None, group="Generalistas"):
    return Channel(name=name, group=group, streams=["http://x"], tvg_id=channel_id)


def build_rows(*args, **kwargs):
    """grid.build returns sections now; most assertions are about rows."""
    return [line.row for line in grid.lines(grid.build(*args, **kwargs)) if line.row]


def guide_of(*programmes):
    by_channel: dict[str, list[Programme]] = {}
    for item in programmes:
        by_channel.setdefault(item.channel, []).append(item)
    return Guide(by_channel)


# -- which channels get a row ------------------------------------------------


def test_channels_without_a_tvg_id_have_no_row():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    rows = build_rows(guide, [channel("Nameless")], START, END)
    assert rows == []


def test_channels_whose_tvg_id_is_absent_from_the_guide_have_no_row():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    rows = build_rows(guide, [channel("Other", "B.TV")], START, END)
    assert rows == []


def test_favorites_come_first_then_alphabetical():
    guide = guide_of(
        programme("A.TV", "Show", 0, 60),
        programme("B.TV", "Show", 0, 60),
        programme("C.TV", "Show", 0, 60),
    )
    channels = [channel("Alfa", "A.TV"), channel("Beta", "B.TV"), channel("Gamma", "C.TV")]
    rows = build_rows(guide, channels, START, END, favorites={"Gamma"})
    assert [row.channel.name for row in rows] == ["Gamma", "Alfa", "Beta"]


def test_several_favorites_stay_alphabetical_among_themselves():
    guide = guide_of(
        programme("A.TV", "Show", 0, 60),
        programme("B.TV", "Show", 0, 60),
        programme("C.TV", "Show", 0, 60),
    )
    channels = [channel("Alfa", "A.TV"), channel("Beta", "B.TV"), channel("Gamma", "C.TV")]
    rows = build_rows(guide, channels, START, END, favorites={"Gamma", "Beta"})
    assert [row.channel.name for row in rows] == ["Beta", "Gamma", "Alfa"]


def test_a_favorite_appears_once_not_twice():
    """The channel list repeats a favorite under its group; the grid has no
    groups, so a second copy would just be the same schedule twice."""
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    rows = build_rows(guide, [channel("Alfa", "A.TV")], START, END, favorites={"Alfa"})
    assert [row.channel.name for row in rows] == ["Alfa"]


def test_favoriting_a_variant_makes_it_win_the_shared_id():
    """Teledeporte and Teledeporte GEO share an id and draw one row; the
    favorited one is the one worth keeping."""
    guide = guide_of(programme("TDP.TV", "Ciclismo", 0, 60))
    channels = [channel("Teledeporte", "TDP.TV"), channel("Teledeporte GEO", "TDP.TV")]
    rows = build_rows(guide, channels, START, END, favorites={"Teledeporte GEO"})
    assert [row.channel.name for row in rows] == ["Teledeporte GEO"]


def test_no_favorites_leaves_the_order_alphabetical():
    guide = guide_of(programme("A.TV", "Show", 0, 60), programme("B.TV", "Show", 0, 60))
    channels = [channel("Beta", "B.TV"), channel("Alfa", "A.TV")]
    assert [r.channel.name for r in build_rows(guide, channels, START, END)] == ["Alfa", "Beta"]
    assert [
        r.channel.name for r in build_rows(guide, channels, START, END, favorites=set())
    ] == ["Alfa", "Beta"]


def test_a_favorite_without_guide_data_still_gets_no_row():
    """Favoriting cannot conjure a schedule the feed does not carry."""
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    channels = [channel("Alfa", "A.TV"), channel("Sin guia")]
    rows = build_rows(guide, channels, START, END, favorites={"Sin guia"})
    assert [row.channel.name for row in rows] == ["Alfa"]


def test_rows_are_alphabetical_and_accent_insensitive():
    guide = guide_of(
        programme("A.TV", "Show", 0, 60),
        programme("B.TV", "Show", 0, 60),
        programme("C.TV", "Show", 0, 60),
    )
    channels = [channel("Zeta", "C.TV"), channel("Ávila", "A.TV"), channel("beta", "B.TV")]
    rows = build_rows(guide, channels, START, END)
    assert [row.channel.name for row in rows] == ["Ávila", "beta", "Zeta"]


def test_a_shared_tvg_id_draws_one_row_not_several():
    """15 ids in the live playlist are shared; each copy would repeat the row."""
    guide = guide_of(programme("TDP.TV", "Ciclismo", 0, 60))
    channels = [channel("Teledeporte GEO", "TDP.TV"), channel("Teledeporte", "TDP.TV")]
    rows = build_rows(guide, channels, START, END)
    assert [row.channel.name for row in rows] == ["Teledeporte"]


def test_a_channel_with_data_but_nothing_in_the_window_keeps_an_empty_row():
    """Dropping it would reflow the rows as the user pages through time."""
    guide = guide_of(programme("A.TV", "Yesterday", -600, 60))
    rows = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    assert len(rows) == 1
    assert rows[0].blocks == []


# -- positioning -------------------------------------------------------------


def test_a_programme_filling_the_window_spans_it_exactly():
    guide = guide_of(programme("A.TV", "Long", 0, 180))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    (block,) = row.blocks
    assert (block.start_frac, block.end_frac) == (0.0, 1.0)
    assert not block.clipped_left and not block.clipped_right


def test_positions_are_fractions_of_the_window():
    guide = guide_of(programme("A.TV", "Middle", 60, 30))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    (block,) = row.blocks
    assert block.start_frac == pytest.approx(1 / 3)
    assert block.end_frac == pytest.approx(0.5)
    # Subtracting two floats, so exact equality would be luck.
    assert block.width_frac == pytest.approx(1 / 6)


def test_a_programme_already_running_is_clipped_to_the_left_edge():
    guide = guide_of(programme("A.TV", "Started earlier", -60, 120))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    (block,) = row.blocks
    assert block.start_frac == 0.0
    assert block.clipped_left
    assert not block.clipped_right


def test_a_programme_running_past_the_end_is_clipped_to_the_right_edge():
    guide = guide_of(programme("A.TV", "Overruns", 120, 180))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    (block,) = row.blocks
    assert block.end_frac == 1.0
    assert block.clipped_right
    assert not block.clipped_left


def test_a_programme_ending_exactly_as_the_window_opens_is_not_drawn():
    """A zero-width block would be an invisible click target."""
    guide = guide_of(programme("A.TV", "Just finished", -60, 60))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    assert row.blocks == []


def test_a_programme_starting_exactly_as_the_window_closes_is_not_drawn():
    guide = guide_of(programme("A.TV", "Next up", 180, 60))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    assert row.blocks == []


def test_blocks_are_ordered_by_start():
    guide = guide_of(
        programme("A.TV", "Third", 120, 30),
        programme("A.TV", "First", 0, 30),
        programme("A.TV", "Second", 60, 30),
    )
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    assert [b.programme.title for b in row.blocks] == ["First", "Second", "Third"]


# -- programmes with no stop time --------------------------------------------


def test_a_programme_without_an_end_runs_until_the_next_one():
    guide = guide_of(
        programme("A.TV", "Open ended", 0, 0, end=False),
        programme("A.TV", "Follows", 90, 30),
    )
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    first = row.blocks[0]
    assert first.end_frac == 0.5


def test_a_trailing_programme_without_an_end_runs_to_the_window_edge():
    guide = guide_of(programme("A.TV", "Open ended", 60, 0, end=False))
    (row,) = build_rows(guide, [channel("Uno", "A.TV")], START, END)
    (block,) = row.blocks
    assert block.end_frac == 1.0


# -- degenerate windows ------------------------------------------------------


def test_an_empty_window_lays_nothing_out():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    assert build_rows(guide, [channel("Uno", "A.TV")], START, START) == []


def test_a_reversed_window_lays_nothing_out():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    assert build_rows(guide, [channel("Uno", "A.TV")], END, START) == []


def test_an_empty_guide_lays_nothing_out():
    assert build_rows(Guide(), [channel("Uno", "A.TV")], START, END) == []


# -- Guide.between -----------------------------------------------------------


def test_between_includes_the_programme_already_on_air():
    guide = guide_of(programme("A.TV", "Running", -30, 60))
    found = guide.between("A.TV", START, END)
    assert [p.title for p in found] == ["Running"]


def test_between_excludes_programmes_wholly_outside_the_window():
    guide = guide_of(
        programme("A.TV", "Before", -120, 30),
        programme("A.TV", "Inside", 30, 30),
        programme("A.TV", "After", 240, 30),
    )
    found = guide.between("A.TV", START, END)
    assert [p.title for p in found] == ["Inside"]


def test_between_of_an_unknown_channel_is_empty():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    assert guide.between("B.TV", START, END) == []
    assert guide.between(None, START, END) == []


# -- sections ------------------------------------------------------------


def test_sections_are_favorites_then_groups_alphabetically():
    guide = guide_of(
        programme("A.TV", "Show", 0, 60),
        programme("B.TV", "Show", 0, 60),
        programme("C.TV", "Show", 0, 60),
    )
    channels = [
        channel("Alfa", "A.TV", group="Zeta"),
        channel("Beta", "B.TV", group="Alfa"),
        channel("Gamma", "C.TV", group="Zeta"),
    ]
    sections = grid.build(guide, channels, START, END, favorites={"Gamma"})
    assert [s.label for s in sections] == [grid.FAVORITES_LABEL, "ALFA", "ZETA"]
    assert [r.channel.name for r in sections[0].rows] == ["Gamma"]
    assert [r.channel.name for r in sections[2].rows] == ["Alfa"]


def test_a_favorite_is_not_repeated_in_its_group():
    """The list can afford that duplication; a grid would draw the same
    schedule twice."""
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    sections = grid.build(
        guide, [channel("Alfa", "A.TV", group="Zeta")], START, END, favorites={"Alfa"}
    )
    assert [s.label for s in sections] == [grid.FAVORITES_LABEL]


def test_no_favorites_means_no_favorites_section():
    guide = guide_of(programme("A.TV", "Show", 0, 60))
    sections = grid.build(guide, [channel("Alfa", "A.TV", group="Zeta")], START, END)
    assert [s.label for s in sections] == ["ZETA"]


def test_a_collapsed_section_is_marked_collapsed():
    guide = guide_of(programme("A.TV", "Show", 0, 60), programme("B.TV", "Show", 0, 60))
    channels = [channel("Alfa", "A.TV", group="Uno"), channel("Beta", "B.TV", group="Dos")]
    sections = grid.build(guide, channels, START, END, collapsed={"UNO"})
    by_label = {s.label: s for s in sections}
    assert by_label["UNO"].collapsed
    assert not by_label["DOS"].collapsed
    # Collapsing hides rows from the drawing order, never from the section.
    assert len(by_label["UNO"].rows) == 1


# -- flattening into drawn lines -----------------------------------------


def test_lines_put_a_header_before_each_section():
    guide = guide_of(programme("A.TV", "Show", 0, 60), programme("B.TV", "Show", 0, 60))
    channels = [channel("Alfa", "A.TV", group="Uno"), channel("Beta", "B.TV", group="Dos")]
    lines = grid.lines(grid.build(guide, channels, START, END))
    assert [(line.section.label, line.is_header) for line in lines] == [
        ("DOS", True),
        ("DOS", False),
        ("UNO", True),
        ("UNO", False),
    ]


def test_a_collapsed_section_contributes_only_its_header():
    guide = guide_of(programme("A.TV", "Show", 0, 60), programme("B.TV", "Show", 0, 60))
    channels = [channel("Alfa", "A.TV", group="Uno"), channel("Beta", "B.TV", group="Dos")]
    lines = grid.lines(grid.build(guide, channels, START, END, collapsed={"UNO"}))
    assert [(line.section.label, line.is_header) for line in lines] == [
        ("DOS", True),
        ("DOS", False),
        ("UNO", True),
    ]


def test_lines_of_nothing_is_empty():
    assert grid.lines([]) == []
