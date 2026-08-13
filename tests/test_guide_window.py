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


def test_the_main_window_has_a_guide_button_that_opens_it():
    """Ctrl+G alone is undiscoverable, so the button is the visible route."""
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

        assert browser.guide_button.cget("text") == "Guide"
        # It must not take focus, or Enter after a click would re-press the
        # button instead of playing the selected channel.
        assert str(browser.guide_button.cget("takefocus")) in ("0", "False", "")

        browser.guide_button.invoke()
        root.update()
        opened = [w for w in browser.winfo_children() if isinstance(w, ui.GuideWindow)]
        assert len(opened) == 1
    finally:
        root.destroy()


def test_the_guide_button_is_themed_in_dark_mode():
    """ttk ignores widget colours, so an unstyled button stays light grey."""
    if not _tk_available():
        return
    import tkinter as tk
    from tkinter import ttk

    from zaptv import theme, ui
    from zaptv.player import VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    channels, guide = _fixture()
    root = tk.Tk()
    try:
        browser = ui.ChannelBrowser(
            root,
            channels,
            VLCPlayer(),
            Favorites([]),
            Recent([]),
            guide,
            Settings(theme="dark"),
        )
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()

        dark = theme.get("dark")
        style = ttk.Style(root)
        assert style.lookup("Zap.TButton", "background") == dark.field_bg
        assert style.lookup("Zap.TButton", "foreground") == dark.fg
    finally:
        root.destroy()


def test_favorites_are_first_and_starred_in_the_grid():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import theme, ui

    channels, guide = _fixture()
    root = tk.Tk()
    try:
        window = ui.GuideWindow(
            root, guide, channels, theme.get("light"), lambda _c: None,
            favorites={"Uno"}, now=NOW,
        )
        root.update()

        # Alphabetically "Dos" precedes "Uno"; favoriting reverses that.
        assert [r.channel.name for r in window._rows] == ["Uno", "Dos"]

        labels = [
            window.names.itemcget(item, "text")
            for item in window.names.find_withtag("all")
        ]
        assert any(label.startswith("★") and "Uno" in label for label in labels)
        assert not any(label.startswith("★") and "Dos" in label for label in labels)
    finally:
        root.destroy()


def test_the_browser_hands_its_favorites_to_the_guide():
    """Opening the guide must reflect the favorites the list is showing."""
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
            root, channels, VLCPlayer(), Favorites(["Uno"]), Recent([]), guide
        )
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()

        browser.open_guide()
        root.update()
        opened = [w for w in browser.winfo_children() if isinstance(w, ui.GuideWindow)]
        assert len(opened) == 1
        window = opened[0]
        # A statement-level assert narrows where the comprehension does not:
        # winfo_children is typed as returning Widget, and Toplevel is not a
        # Widget subclass in typeshed.
        assert isinstance(window, ui.GuideWindow)
        assert [r.channel.name for r in window._rows] == ["Uno", "Dos"]
    finally:
        root.destroy()


# -- filtering -----------------------------------------------------------


def test_the_filter_narrows_the_rows():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        assert [r.channel.name for r in window._rows] == ["Dos", "Uno"]

        window.query.set("uno")
        root.update()
        assert [r.channel.name for r in window._rows] == ["Uno"]

        window.query.set("")
        root.update()
        assert [r.channel.name for r in window._rows] == ["Dos", "Uno"]
    finally:
        root.destroy()


def test_the_filter_ignores_accents_like_the_channel_list():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import theme, ui
    from zaptv.epg import Guide

    channels = [
        Channel(name="Málaga TV", group="Andalucía", streams=["https://x"], tvg_id="M.TV")
    ]
    guide = Guide({"M.TV": [_programme("M.TV", "Show", 0, 60)]})

    root = tk.Tk()
    try:
        window = ui.GuideWindow(
            root, guide, channels, theme.get("light"), lambda _c: None, now=NOW
        )
        root.update()
        window.query.set("malaga")
        root.update()
        assert [r.channel.name for r in window._rows] == ["Málaga TV"]
    finally:
        root.destroy()


def test_the_footer_counts_matches_while_filtering():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        assert "2 of 3 channels have guide data" in window.footer.cget("text")

        window.query.set("uno")
        root.update()
        # Against the rows there could be, not the whole playlist.
        assert "1 of 2 channels match" in window.footer.cget("text")
    finally:
        root.destroy()


def test_filtering_scrolls_back_to_the_top():
    """Otherwise a filter applied while scrolled down shows empty space."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import theme, ui
    from zaptv.epg import Guide

    channels = [
        Channel(
            name=f"Canal {i:02d}", group="G", streams=["https://x"], tvg_id=f"{i:02d}.TV"
        )
        for i in range(40)
    ]
    guide = Guide({f"{i:02d}.TV": [_programme(f"{i:02d}.TV", f"S{i}", 0, 120)] for i in range(40)})

    root = tk.Tk()
    try:
        window = ui.GuideWindow(
            root, guide, channels, theme.get("light"), lambda _c: None, now=NOW
        )
        window.geometry("700x240")
        root.update()
        window._yview("moveto", "0.5")
        root.update()
        assert window.slots.yview()[0] > 0

        window.query.set("canal 3")
        root.update()
        assert window.slots.yview()[0] == 0.0
    finally:
        root.destroy()


def test_escape_clears_the_filter_before_closing():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        window.query.set("uno")
        root.update()

        window._on_escape()
        assert window.query.get() == ""
        assert window.winfo_exists()

        # A second Escape, with nothing typed, closes it.
        window._on_escape()
        root.update()
        assert not window.winfo_exists()
    finally:
        if window.winfo_exists():
            root.destroy()
        else:
            root.destroy()


def test_arrow_keys_do_not_page_while_typing_in_the_filter():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        opening = window._start

        window._filter.focus_force()
        root.update()
        window._arrow(window._page_back)
        assert window._start == opening, "arrow paged while editing the filter"
    finally:
        root.destroy()


def test_the_paging_buttons_work_regardless_of_filter_focus():
    """The guard belongs on the key binding, not the shared method."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import grid

    root = tk.Tk()
    try:
        window = _window(root)
        root.update()
        window._filter.focus_force()
        root.update()

        opening = window._start
        window._page_back()
        assert window._start == opening - grid.PAGE_STEP
    finally:
        root.destroy()
