"""Guide grid window.

The layout maths lives in grid.py and is tested there without a display.
What is left here is the wiring: that the window draws, that paging moves
the visible span, that a double-click reaches the player, and that a
channel with no guide data gets no row.

Display-dependent tests skip rather than fail when there is no display, so
headless runs stay green. Nothing here may depend on VLC being installed —
CI runners have no player at all — so the play path is checked through a
callback rather than by launching anything.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from zaptv.epg import Guide
from zaptv.models import Channel, Programme

NOW = datetime(2026, 8, 13, 20, 15, tzinfo=timezone.utc)


def _tk_available() -> bool:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        import tkinter
    except ImportError:
        return False
    try:
        root = tkinter.Tk()
    except Exception:
        return False
    root.destroy()
    return True


def _programme(channel_id, title, offset_min, minutes):
    start = NOW + timedelta(minutes=offset_min)
    return Programme(
        channel=channel_id,
        title=title,
        start=start,
        end=start + timedelta(minutes=minutes),
    )


def _fixture():
    """Two channels with data, one without — the majority case in real life."""
    channels = [
        Channel(name="Uno", group="Generalistas", streams=["https://x.invalid/1"], tvg_id="A.TV"),
        Channel(name="Dos", group="Generalistas", streams=["https://x.invalid/2"], tvg_id="B.TV"),
        Channel(name="Sin guia", group="Generalistas", streams=["https://x.invalid/3"]),
    ]
    guide = Guide(
        {
            "A.TV": [
                _programme("A.TV", "Ahora en Uno", -15, 60),
                _programme("A.TV", "Después en Uno", 45, 60),
            ],
            "B.TV": [_programme("B.TV", "Ahora en Dos", 0, 120)],
        }
    )
    return channels, guide


def _window(root, on_play=None):
    from zaptv import theme, ui

    return ui.GuideWindow(
        root,
        _fixture()[1],
        _fixture()[0],
        theme.get("light"),
        on_play or (lambda _channel: None),
        now=NOW,
    )


def test_only_channels_with_guide_data_get_a_row():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        assert [row.channel.name for row in window._rows] == ["Dos", "Uno"]
        # The channel with no tvg-id is still counted in the footer, so the
        # user can see why their channel is missing rather than guessing.
        assert "2 of 3 channels" in window.footer.cget("text")
    finally:
        root.destroy()


def test_the_grid_draws_blocks_onto_the_canvas():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        # Three programmes fall in the default three-hour window, each drawn
        # as a rectangle plus its title.
        assert len(window.slots.find_withtag("all")) > 0
        assert window.slots.winfo_width() > 1
    finally:
        root.destroy()


def test_paging_moves_the_window_and_now_returns_to_it():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import grid

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        opening = window._start

        window._page_on()
        assert window._start == opening + grid.PAGE_STEP
        window._page_back()
        window._page_back()
        assert window._start == opening - grid.PAGE_STEP

        window._go_now()
        assert window._start == opening
    finally:
        root.destroy()


def test_the_window_opens_on_the_half_hour_containing_now():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        # NOW is 20:15, so the window opens at 20:00 rather than mid-label.
        assert window._start == NOW.replace(minute=0)
    finally:
        root.destroy()


def test_a_double_click_on_a_block_plays_that_channel():
    if not _tk_available():
        return
    import tkinter as tk

    played: list[Channel] = []
    root = tk.Tk()
    try:
        window = _window(root, on_play=played.append)
        window.geometry("900x560")
        root.update()

        event = tk.Event()
        # Just inside the first row, a third of the way across. Rows are
        # alphabetical, so row 0 is "Dos", whose two-hour programme covers
        # that point.
        event.x = window.slots.winfo_width() // 3
        event.y = 5
        window._on_activate(event)

        assert [c.name for c in played] == ["Dos"]
    finally:
        root.destroy()


def test_hit_testing_accounts_for_the_scroll_position():
    """Pinned against Tk's own canvasy, which is the ground truth here.

    ui._canvas_y does the conversion by hand because typeshed only recently
    annotated Canvas.canvasy: a mypy new enough to type it rejects the ignore
    an older one needs. Tests may call the untyped method (mypy relaxes
    disallow_untyped_calls for tests), so it can serve as the oracle.
    """
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import theme, ui

    # Enough rows to have something to scroll through.
    channels = [
        Channel(
            name=f"Canal {i:02d}",
            group="Generalistas",
            streams=["https://x.invalid/s"],
            tvg_id=f"{i:02d}.TV",
        )
        for i in range(40)
    ]
    guide = Guide(
        {f"{i:02d}.TV": [_programme(f"{i:02d}.TV", f"Show {i}", 0, 120)] for i in range(40)}
    )

    root = tk.Tk()
    try:
        window = ui.GuideWindow(
            root, guide, channels, theme.get("light"), lambda _c: None, now=NOW
        )
        window.geometry("700x240")
        root.update()

        window._yview("moveto", "0.5")
        root.update()
        assert window.slots.yview()[0] > 0, "nothing scrolled; the test proves nothing"

        event: tk.Event[tk.Canvas] = tk.Event()
        event.x = window.slots.winfo_width() // 2
        event.y = 5
        assert window._canvas_y(event) == pytest.approx(window.slots.canvasy(5))

        # And the click lands on a scrolled-to row, not the first one.
        found = window._at(event)
        assert found is not None
        assert found[0].name != "Canal 00"
    finally:
        root.destroy()


def test_a_click_on_empty_space_plays_nothing():
    if not _tk_available():
        return
    import tkinter as tk

    played: list[Channel] = []
    root = tk.Tk()
    try:
        window = _window(root, on_play=played.append)
        root.update()

        event = tk.Event()
        event.x = 10
        # Far below the last row.
        event.y = 5000
        window._on_activate(event)

        assert played == []
    finally:
        root.destroy()


def test_clicking_a_block_shows_its_details():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        window.geometry("900x560")
        root.update()

        event = tk.Event()
        event.x = window.slots.winfo_width() // 3
        event.y = 5
        window._on_click(event)

        assert "Ahora en Dos" in window.detail.cget("text")
    finally:
        root.destroy()


def test_an_empty_guide_draws_an_empty_grid_rather_than_failing():
    """No guide at all is a normal state, not an error."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import theme, ui

    root = tk.Tk()
    try:
        window = ui.GuideWindow(
            root,
            Guide(),
            _fixture()[0],
            theme.get("dark"),
            lambda _channel: None,
            now=NOW,
        )
        root.update()
        assert window._rows == []
        assert "0 of 3 channels" in window.footer.cget("text")
    finally:
        root.destroy()


def test_the_browser_opens_the_guide_window():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import ui
    from zaptv.player import VLCPlayer
    from zaptv.storage import Favorites, Recent

    channels, guide = _fixture()
    root = tk.Tk()
    try:
        browser = ui.ChannelBrowser(
            root, channels, VLCPlayer(), Favorites([]), Recent([]), guide
        )
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()

        browser.open_guide()
        root.update()
        opened = [w for w in browser.winfo_children() if isinstance(w, ui.GuideWindow)]
        assert len(opened) == 1
    finally:
        root.destroy()
