"""UI tests.

`clip` is pure and runs anywhere. The scroll regression needs a real Tk
display: that bug only appears on a listbox that has not been mapped yet,
where see() scrolls the target to the very top and hides the header above
it. Display-dependent tests skip (rather than fail) when there is no
display, so headless runs stay green.
"""

import os


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

        row = next(i for i in browser.tree.get_children() if i in browser._rows)
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
        # bug. It stays dismissable because it keeps the grab tk_popup took:
        # measured against the real thing, releasing that grab left an outside
        # click unable to close the menu in four tries out of four.
        assert str(root.grab_current()) == str(menu), "the menu must keep its grab"
        menu.event_generate("<Escape>")
        root.update()
        assert not menu.winfo_ismapped(), "Escape must close the menu"
    finally:
        root.destroy()
