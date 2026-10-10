"""UI tests.

`clip` is pure and runs anywhere. The scroll regression needs a real Tk
display: that bug only appears on a listbox that has not been mapped yet,
where see() scrolls the target to the very top and hides the header above
it. Display-dependent tests skip (rather than fail) when there is no
display, so headless runs stay green.
"""

import os
import threading


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


def test_first_section_header_is_visible_at_startup():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.storage import Favorites, Recent

    channels = [
        Channel(name=f"Channel {i:03d}", group="Generalistas", streams=["https://x.invalid/s"])
        for i in range(200)
    ]

    root = tk.Tk()
    root.geometry("420x640")
    try:
        browser = ui.ChannelBrowser(
            root,
            channels,
            VLCPlayer(),
            Favorites(["Channel 005"]),
            Recent(["Channel 010"]),
        )
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()

        first = browser.tree.get_children()[0]
        assert browser.tree.item(first, "text") == ui.FAVORITES_LABEL
        # The header must be the topmost visible row, not scrolled above it.
        assert browser.tree.yview()[0] == 0.0
        # ...and a channel is still selected, so Enter plays immediately.
        assert browser.selected() is not None
    finally:
        root.destroy()


def test_section_headers_are_not_selectable():
    """Headers are absent from the row map, so selected() ignores them."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.storage import Favorites, Recent

    channels = [Channel(name="Only", group="G", streams=["https://x.invalid/s"])]

    root = tk.Tk()
    try:
        browser = ui.ChannelBrowser(root, channels, VLCPlayer(), Favorites([]), Recent([]))
        browser.pack()
        root.update()

        header = browser.tree.get_children()[0]
        browser.tree.selection_set(header)
        assert browser.selected() is None
    finally:
        root.destroy()


def test_theme_switch_repaints_the_list():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import theme, ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    channels = [Channel(name="Only", group="G", streams=["https://x.invalid/s"])]

    root = tk.Tk()
    try:
        config = Settings(theme="light", show_logos=False)
        browser = ui.ChannelBrowser(
            root, channels, VLCPlayer(), Favorites([]), Recent([]), None, config
        )
        browser.pack()
        root.update()
        assert browser._palette is theme.LIGHT

        config.theme = "dark"
        browser.retheme(config)
        root.update()
        assert browser._palette is theme.DARK
        assert browser.status.cget("bg") == theme.DARK.bg
        # The channel survives the rebuild that retheme triggers.
        assert browser.selected() is not None
    finally:
        root.destroy()


def test_clip_shortens_at_a_word_boundary():
    from zaptv.ui import clip

    text = "Magazine matinal de la 1 en el que se reúne información de actualidad social"
    clipped = clip(text, 40)
    assert clipped.endswith("…")
    assert len(clipped) <= 41
    assert not clipped[:-1].endswith(" ")
    # Never splits a word in half.
    assert text.startswith(clipped[:-1])


def test_clip_leaves_short_text_alone():
    from zaptv.ui import clip

    assert clip("Short one", 40) == "Short one"


def test_clip_collapses_whitespace():
    from zaptv.ui import clip

    assert clip("two\n  lines   here", 40) == "two lines here"


def test_late_logos_reach_every_row_sharing_a_url(tmp_path):
    """Channels share logo URLs; a late arrival must fill all their rows.

    One Facebook logo covers 16 regional channels in the real playlist, so
    filling only the first row of a shared group leaves the rest blank.
    """
    if not _tk_available():
        return

    import io
    import tkinter as tk

    from PIL import Image

    from zaptv import logos, ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    buffer = io.BytesIO()
    Image.new("RGBA", (24, 24), (200, 30, 30, 255)).save(buffer, "PNG")
    cached = logos.convert(buffer.getvalue(), tmp_path / "shared.png", size=24)

    shared = "https://example.invalid/shared.png"
    channels = [
        Channel(name=f"Shared {i}", group="G", streams=["https://x.invalid/s"], logo=shared)
        for i in range(3)
    ]

    class LateStore:
        """Reports nothing until `ready`, then reports the logo once."""

        def __init__(self):
            self.ready = False
            self._announced = False

        def path_for(self, url):
            return cached if (self.ready and url) else None

        def drain(self):
            if self.ready and not self._announced:
                self._announced = True
                return [shared]
            return []

    store = LateStore()
    root = tk.Tk()
    try:
        browser = ui.ChannelBrowser(
            root, channels, VLCPlayer(), Favorites([]), Recent([]), None,
            Settings(show_logos=True), store,
        )
        browser.pack()
        root.update()
        assert all(not browser.tree.item(i, "image") for i in browser._rows)

        store.ready = True
        browser._tick_logos()
        root.update()
        assert all(browser.tree.item(i, "image") for i in browser._rows)
    finally:
        root.destroy()


def test_web_channels_open_in_the_browser_whatever_the_default_player():
    """A channel naming its own player overrides the configured default."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import BrowserPlayer, VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    stream = Channel(name="La 1", group="G", streams=["https://x.invalid/s"])
    web = Channel(
        name="Antena 3", group="G", streams=["https://atresplayer.invalid/a3"], player="browser"
    )

    root = tk.Tk()
    try:
        browser = ui.ChannelBrowser(
            root, [stream, web], VLCPlayer(), Favorites([]), Recent([]), None,
            Settings(show_logos=False),
        )
        browser.pack()
        root.update()

        assert isinstance(browser._player_for(stream), VLCPlayer)
        assert isinstance(browser._player_for(web), BrowserPlayer)
    finally:
        root.destroy()


def test_playing_records_the_channel_as_recent():
    """The play path is shared by Enter and the Play-with menu."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import Player, VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    played = []

    class FakePlayer(Player):
        command = "fake"
        label = "Fake"

        def args(self, stream_url):
            return ["fake", stream_url]

        def play(self, stream_url):
            played.append(stream_url)
            return None

    channel = Channel(name="La 1", group="G", streams=["https://x.invalid/s"])
    root = tk.Tk()
    try:
        recent = Recent([])
        browser = ui.ChannelBrowser(
            root, [channel], VLCPlayer(), Favorites([]), recent, None,
            Settings(show_logos=False),
        )
        browser.pack()
        root.update()

        browser._play(channel, FakePlayer())
        root.update()
        assert played == ["https://x.invalid/s"]
        assert recent.names == ["La 1"]
    finally:
        root.destroy()


def test_a_missing_player_does_not_record_a_play(monkeypatch):
    """A channel you could not watch has not been watched."""
    if not _tk_available():
        return

    import tkinter as tk
    from tkinter import messagebox

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import Player, PlayerNotFound, VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    class MissingPlayer(Player):
        command = "absent"
        label = "Absent"

        def args(self, stream_url):
            return []

        def play(self, stream_url):
            raise PlayerNotFound("Absent not found")

    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)

    channel = Channel(name="La 1", group="G", streams=["https://x.invalid/s"])
    root = tk.Tk()
    try:
        recent = Recent([])
        browser = ui.ChannelBrowser(
            root, [channel], VLCPlayer(), Favorites([]), recent, None,
            Settings(show_logos=False),
        )
        browser.pack()
        root.update()

        browser._play(channel, MissingPlayer())
        assert recent.names == []
    finally:
        root.destroy()


def test_right_click_does_not_play_the_first_menu_entry(monkeypatch):
    """Opening the Play with... menu must not start playing anything.

    tk_popup posts the menu with its top-left corner on the pointer. Posted on
    <Button-3>, the matching release then lands on the menu, and Tk's own
    `bind Menu <ButtonRelease>` invokes whichever entry is active — the first
    one, if the pointer is inside it. Both halves are pinned here: the menu is
    posted on the release so none is left to deliver, and a one-pixel border
    keeps the pointer out of entry zero.

    The whole gesture is driven, press and release, so this fails against
    either binding rather than merely noticing which one is in use.
    """
    if not _tk_available():
        return

    import shutil
    import time
    import tkinter as tk

    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import Player, VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    # Every backend must look installed, or its entry is disabled and could
    # not be invoked whatever the bindings do. CI has neither VLC nor mpv.
    monkeypatch.setattr(shutil, "which", lambda command: f"/usr/bin/{command}")

    played: list[str] = []
    monkeypatch.setattr(Player, "play", lambda self, stream_url: played.append(stream_url))

    channels = [
        Channel(name=f"Channel {i:03d}", group="Generalistas", streams=[f"https://x.invalid/{i}"])
        for i in range(20)
    ]

    root = tk.Tk()
    root.geometry("420x640")
    try:
        browser = ui.ChannelBrowser(
            root, channels, VLCPlayer(), Favorites([]), Recent([]), None,
            Settings(show_logos=False),
        )
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()

        # Channel rows are children of their section header, not top level.
        row = browser._row_order[0]
        box = browser.tree.bbox(row)
        assert box, "the row must be on screen for a right-click to reach it"
        x, y = box[0] + 20, box[1] + 5

        # One right-click, in full: press, then release with the pointer still
        # where it was pressed.
        browser.tree.event_generate("<Button-3>", x=x, y=y)
        root.update()
        browser.tree.event_generate("<ButtonRelease-3>", x=x, y=y)
        root.update()

        menus = [w for w in browser.winfo_children() if isinstance(w, tk.Menu)]
        assert menus, "the right-click should have posted a menu"
        menu = menus[-1]
        assert menu.winfo_ismapped(), "the menu should be posted"

        # X delivers the release of that same click to the menu now under the
        # pointer, which is what used to invoke entry zero.
        menu.event_generate("<Enter>", x=0, y=0)
        root.update()
        menu.event_generate("<ButtonRelease-3>", x=0, y=0)
        root.update()

        assert played == [], "opening the menu must not play anything"
        # Why it cannot: the pointer lands in the border, so no entry is active
        # for a release to invoke.
        assert menu.index("@0,0") is None
        assert menu.index("active") is None

        # Opening a menu that nothing can close would be no better than the
        # bug, and what keeps it closable is holding the grab tk_popup took:
        # measured against the real thing, releasing that grab left an outside
        # click unable to close the menu four times out of four, while keeping
        # it closed on all four.
        #
        # That the grab is held is the part this code decides, so it is
        # asserted first and on its own.
        assert str(root.grab_current()) == str(menu), "the menu must keep its grab"

        # Then that the menu does close, by calling Tk's Escape handler rather
        # than generating the key. Tk delivers a synthetic key to whatever holds
        # focus, and under a bare X server there is no window manager to give
        # anything focus, so `event_generate("<Escape>")` never reaches the menu
        # and the menu looks stuck when it is not. Calling the handler needs no
        # focus and behaves the same on Xvfb and a real desktop.
        root.tk.call("tk::MenuEscape", menu)
        for _ in range(100):
            root.update()
            if not menu.winfo_ismapped():
                break
            time.sleep(0.01)
        assert not menu.winfo_ismapped(), "the menu must close"
    finally:
        root.destroy()


# -- collapsible groups --------------------------------------------------


def _browser_with_groups(root, settings=None, favorites=None, recent=None):
    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    channels = [
        Channel(name="Alfa", group="Uno", streams=["https://x.invalid/1"]),
        Channel(name="Beta", group="Uno", streams=["https://x.invalid/2"]),
        Channel(name="Gamma", group="Dos", streams=["https://x.invalid/3"]),
    ]
    return ui.ChannelBrowser(
        root,
        channels,
        VLCPlayer(),
        Favorites(favorites or []),
        Recent(recent or []),
        None,
        settings or Settings(show_logos=False),
    )


def _section(browser, label):
    for item, name in browser._sections.items():
        if name == label:
            return item
    raise AssertionError(f"no section {label!r} in {list(browser._sections.values())}")


def test_channels_are_children_of_their_group():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        browser = _browser_with_groups(root)
        browser.pack()
        root.update()

        # Top level is sections only; channels hang off them.
        top = browser.tree.get_children()
        assert all(i not in browser._rows for i in top)
        uno = _section(browser, "UNO")
        assert [browser.tree.item(c, "text").strip() for c in browser.tree.get_children(uno)] == [
            "Alfa",
            "Beta",
        ]
    finally:
        root.destroy()


def test_groups_start_expanded_by_default():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        browser = _browser_with_groups(root)
        browser.pack()
        root.update()
        assert all(browser.tree.item(i, "open") for i in browser._sections)
    finally:
        root.destroy()


def test_a_collapsed_group_from_settings_starts_closed():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv.settings import Settings

    root = tk.Tk()
    try:
        browser = _browser_with_groups(
            root, Settings(show_logos=False, collapsed_groups=["UNO"])
        )
        browser.pack()
        root.update()
        assert not browser.tree.item(_section(browser, "UNO"), "open")
        assert browser.tree.item(_section(browser, "DOS"), "open")
    finally:
        root.destroy()


def test_collapsing_is_saved_to_settings(tmp_path, monkeypatch):
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import settings as settings_module
    from zaptv.settings import Settings

    path = tmp_path / "settings.json"
    # save() with no argument falls back to the module-level path, so this
    # keeps the test off the user's real config file.
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", path)
    config = Settings(show_logos=False)
    config.save()

    root = tk.Tk()
    try:
        browser = _browser_with_groups(root, config)
        browser.pack()
        root.update()

        uno = _section(browser, "UNO")
        browser.tree.item(uno, open=False)
        browser.tree.focus(uno)
        browser._on_section_toggled(True)

        assert Settings.load(path).collapsed_groups == ["UNO"]

        browser.tree.focus(uno)
        browser._on_section_toggled(False)
        assert Settings.load(path).collapsed_groups == []
    finally:
        root.destroy()


def test_collapsing_survives_a_refresh():
    """The list is rebuilt on every keystroke, favorite and play."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv.settings import Settings

    root = tk.Tk()
    try:
        browser = _browser_with_groups(
            root, Settings(show_logos=False, collapsed_groups=["UNO"])
        )
        browser.pack()
        root.update()

        browser._refresh()
        root.update()
        assert not browser.tree.item(_section(browser, "UNO"), "open")
    finally:
        root.destroy()


def test_a_rebuild_does_not_record_its_own_open_events(monkeypatch):
    """_refresh and see() both fire the same events a user click does."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv.settings import Settings

    root = tk.Tk()
    try:
        browser = _browser_with_groups(
            root, Settings(show_logos=False, collapsed_groups=["UNO"])
        )
        browser.pack()
        root.update()

        saved = []
        monkeypatch.setattr(browser._config, "save", lambda: saved.append(1))

        browser._refresh()
        root.update()
        assert saved == [], "a redraw persisted a collapse state change"
        assert browser._collapsed == {"UNO"}
    finally:
        root.destroy()


def test_searching_opens_every_section_without_changing_the_saved_state():
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv.settings import Settings

    root = tk.Tk()
    try:
        browser = _browser_with_groups(
            root, Settings(show_logos=False, collapsed_groups=["UNO"])
        )
        browser.pack()
        root.update()

        browser.query.set("alfa")
        root.update()
        # The match lives in the collapsed group; hiding it would look broken.
        assert all(browser.tree.item(i, "open") for i in browser._sections)
        assert browser._collapsed == {"UNO"}

        browser.query.set("")
        root.update()
        assert not browser.tree.item(_section(browser, "UNO"), "open")
    finally:
        root.destroy()


def test_collapsing_moves_the_selection_out_of_the_hidden_group():
    """Otherwise Enter would play a channel that is no longer on screen."""
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        browser = _browser_with_groups(root)
        browser.pack()
        root.update()

        # Groups sort alphabetically, so DOS comes first and _row_order[0] is
        # Gamma; Alfa has to be looked up rather than assumed.
        alfa = next(i for i, c in browser._rows.items() if c.name == "Alfa")
        browser.tree.selection_set(alfa)
        assert browser.selected().name == "Alfa"

        uno = _section(browser, "UNO")
        browser.tree.item(uno, open=False)
        browser.tree.focus(uno)
        browser._on_section_toggled(True)

        chosen = browser.selected()
        assert chosen is not None, "nothing selected after collapsing"
        assert chosen.name == "Gamma", "selection stayed inside the closed group"
    finally:
        root.destroy()


def test_collapsing_everything_leaves_nothing_selected():
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    try:
        browser = _browser_with_groups(root)
        browser.pack()
        root.update()

        for label in ("UNO", "DOS"):
            item = _section(browser, label)
            browser.tree.item(item, open=False)
            browser.tree.focus(item)
            browser._on_section_toggled(True)

        # Better nothing selected than a hidden channel Enter would play.
        assert browser.selected() is None
    finally:
        root.destroy()


def test_enabling_a_regional_list_fetches_its_guide(tmp_path, monkeypatch):
    """The playlists window only reloads channels; the guide has to follow.

    Without this, switching on France would list its channels with no
    listings until the next restart, and switching it off would keep
    downloading a feed nobody looks at.
    """
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import refresh, webchannels
    from zaptv.providers import ProviderList

    sources = ProviderList([], tmp_path / "p.json")
    webchannels.install_regional(sources, tmp_path)
    requested = []

    def fake(providers, extra, force):
        requested.append(list(extra))
        return refresh.Refreshed([], [], None)

    monkeypatch.setattr(refresh, "refresh", fake)

    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, [], sources)
        browser.start_refresh()
        _settle(root, browser)
        assert requested == [[]], "regional lists start disabled: no extra feeds"

        sources.set_enabled(webchannels.FRANCE.provider, True)
        browser.start_refresh()
        _settle(root, browser)
        assert requested[-1] == [webchannels.FRANCE.guide]

        sources.set_enabled(webchannels.FRANCE.provider, False)
        browser.start_refresh()
        _settle(root, browser)
        assert requested[-1] == []
    finally:
        root.destroy()


# -- background refresh ----------------------------------------------------


def _refreshing_browser(root, channels, sources=None):
    import tempfile
    from pathlib import Path

    from zaptv import ui
    from zaptv.player import VLCPlayer
    from zaptv.providers import Provider, ProviderList
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    if sources is None:
        # Never the default path: that is the developer's own providers.json.
        path = Path(tempfile.mkdtemp()) / "providers.json"
        sources = ProviderList([Provider("TDT", "https://lists.invalid/tv.m3u")], path)
    browser = ui.ChannelBrowser(
        root, channels, VLCPlayer(), Favorites([]), Recent([]), None,
        Settings(show_logos=False), None, sources,
    )
    browser.pack()
    root.update()
    return browser


def _settle(root, browser, timeout=5.0):
    """Pump Tk until the refresh, and any queued one, has been applied."""
    import time

    deadline = time.monotonic() + timeout
    while browser._refreshing is not None or browser._pending_force is not None:
        assert time.monotonic() < deadline, "the refresh never finished"
        root.update()
        time.sleep(0.01)
    root.update()


def _channels(*names):
    from zaptv.models import Channel

    return [Channel(name=n, group="Uno", streams=[f"https://x.invalid/{n}"]) for n in names]


def test_a_refresh_swaps_in_new_channels_and_keeps_the_selection(monkeypatch):
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import epg, refresh

    guide = epg.Guide()
    monkeypatch.setattr(
        refresh, "refresh",
        lambda providers, extra, force: refresh.Refreshed(
            _channels("Alfa", "Beta", "Gamma"), [], guide),
    )
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, _channels("Alfa", "Beta"))
        beta = next(i for i, c in browser._rows.items() if c.name == "Beta")
        browser.tree.selection_set(beta)

        browser.start_refresh()
        _settle(root, browser)

        assert sorted(c.name for c in browser._rows.values()) == ["Alfa", "Beta", "Gamma"]
        assert browser.selected().name == "Beta"
        assert browser._guide is guide
        assert browser.status.cget("text") == "3 channels"
    finally:
        root.destroy()


def test_a_failed_refresh_keeps_the_list_and_names_the_source(monkeypatch):
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import epg, refresh

    monkeypatch.setattr(
        refresh, "refresh",
        lambda providers, extra, force: refresh.Refreshed([], ["TDT"], None),
    )
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, _channels("Alfa", "Beta"))
        guide_before = browser._guide

        browser.start_refresh()
        _settle(root, browser)

        assert sorted(c.name for c in browser._rows.values()) == ["Alfa", "Beta"]
        assert browser._guide is guide_before
        assert "Unavailable: TDT" in browser.status.cget("text")
        assert isinstance(browser._guide, epg.Guide)
    finally:
        root.destroy()


def test_an_outdated_list_is_named_with_its_date(monkeypatch):
    if not _tk_available():
        return
    import tkinter as tk
    from datetime import datetime

    from zaptv import refresh

    when = datetime(2026, 10, 7, 13, 18).timestamp()
    monkeypatch.setattr(
        refresh, "refresh",
        lambda providers, extra, force: refresh.Refreshed(
            _channels("Alfa"), ["Blackhole"], None, [("TDTChannels", when)]),
    )
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, _channels("Alfa"))
        browser.start_refresh()
        _settle(root, browser)

        text = browser.status.cget("text")
        assert "Unavailable: Blackhole" in text
        assert "TDTChannels not updated since 7 Oct" in text
    finally:
        root.destroy()


def test_the_status_bar_wraps_to_the_window_width():
    """A report naming several providers must wrap, not be cut off."""
    if not _tk_available():
        return
    import tkinter as tk

    root = tk.Tk()
    root.geometry("420x640")
    try:
        browser = _refreshing_browser(root, _channels("Alfa"))
        browser.pack(fill=tk.BOTH, expand=True)
        root.update()
        width = browser.status.winfo_width()
        assert width > 1
        assert int(browser.status.cget("wraplength")) == width
    finally:
        root.destroy()


def test_an_empty_window_says_what_happened(monkeypatch):
    """First launch with no cache: a window explaining itself, not nothing."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import refresh

    release = threading.Event()

    def slow(providers, extra, force):
        release.wait(5)
        return refresh.Refreshed([], ["TDT"], None)

    monkeypatch.setattr(refresh, "refresh", slow)
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, [])
        browser.start_refresh()
        assert browser.status.cget("text") == "Loading playlists…"

        release.set()
        _settle(root, browser)
        assert "No playlist could be downloaded" in browser.status.cget("text")
        assert "Ctrl+R" in browser.status.cget("text")
    finally:
        root.destroy()


def test_requests_during_a_refresh_run_once_afterwards(monkeypatch):
    """Not dropped (a provider just enabled would be lost), not run in
    parallel (two workers would race on the cache files)."""
    if not _tk_available():
        return
    import tkinter as tk

    from zaptv import refresh

    release = threading.Event()
    forces = []

    def slow(providers, extra, force):
        forces.append(force)
        release.wait(5)
        return refresh.Refreshed(_channels("Alfa"), [], None)

    monkeypatch.setattr(refresh, "refresh", slow)
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, _channels("Alfa"))
        browser.start_refresh(force=False)
        browser.start_refresh(force=True)
        browser.start_refresh(force=False)
        release.set()
        _settle(root, browser)

        assert forces == [False, True]
    finally:
        root.destroy()


def test_ctrl_r_returns_at_once_while_the_download_runs(monkeypatch):
    if not _tk_available():
        return
    import time
    import tkinter as tk

    from zaptv import refresh

    release = threading.Event()
    forces = []

    def slow(providers, extra, force):
        forces.append(force)
        release.wait(5)
        return refresh.Refreshed(_channels("Alfa"), [], None)

    monkeypatch.setattr(refresh, "refresh", slow)
    root = tk.Tk()
    try:
        browser = _refreshing_browser(root, _channels("Alfa"))
        started = time.monotonic()
        assert browser.reload() == "break"
        assert time.monotonic() - started < 0.5
        assert browser.status.cget("text") == "Updating playlists…"

        release.set()
        _settle(root, browser)
        assert forces == [True]
    finally:
        root.destroy()


# -- choosing a browser --------------------------------------------------


def _fake_browsers(monkeypatch):
    from zaptv import browsers

    found = [
        browsers.Browser("firefox_firefox.desktop", "Firefox", "/snap/bin/firefox %u"),
        browsers.Browser("opera_opera.desktop", "Opera", "/snap/bin/opera %U"),
    ]
    monkeypatch.setattr(browsers, "installed", lambda dirs=None: found)
    monkeypatch.setattr(browsers, "system_default", lambda: "firefox_firefox.desktop")


def _radios(window):
    from tkinter import ttk

    body = window.winfo_children()[0]
    return [w for w in body.winfo_children() if isinstance(w, ttk.Radiobutton)]


def test_settings_offer_every_browser_and_save_the_choice(monkeypatch):
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import theme, ui
    from zaptv.settings import Settings

    _fake_browsers(monkeypatch)
    saved = []
    monkeypatch.setattr(Settings, "save", lambda self, path=None: saved.append(self.browser))

    root = tk.Tk()
    try:
        config = Settings()
        window = ui.SettingsWindow(root, config, theme.get("light"), lambda _c: None)
        texts = [r.cget("text") for r in _radios(window)]
        assert "System default (Firefox)" in texts
        assert "Opera" in texts

        window.browser.set("opera_opera.desktop")
        window._save()
        assert saved == ["opera_opera.desktop"]
        assert config.browser == "opera_opera.desktop"
    finally:
        root.destroy()


def test_an_uninstalled_choice_stays_visible_but_disabled(monkeypatch):
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import theme, ui
    from zaptv.settings import Settings

    _fake_browsers(monkeypatch)
    root = tk.Tk()
    try:
        config = Settings(browser="brave-browser.desktop")
        window = ui.SettingsWindow(root, config, theme.get("light"), lambda _c: None)
        (gone,) = [r for r in _radios(window) if "brave" in r.cget("text")]
        assert gone.cget("text") == "brave-browser.desktop (not installed)"
        assert str(gone.cget("state")) == "disabled"
    finally:
        root.destroy()


def test_web_channels_use_the_configured_browser():
    """Read at play time, so a settings change applies to the next channel."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv.models import Channel
    from zaptv.player import BrowserPlayer
    from zaptv.settings import Settings

    root = tk.Tk()
    try:
        settings = Settings(show_logos=False)
        browser = _browser_with_groups(root, settings)
        web = Channel(name="TF1", group="France", streams=["https://x.invalid"], player="browser")

        assert browser._player_for(web).browser == ""
        settings.browser = "opera_opera.desktop"
        chosen = browser._player_for(web)
        assert isinstance(chosen, BrowserPlayer)
        assert chosen.browser == "opera_opera.desktop"
    finally:
        root.destroy()
