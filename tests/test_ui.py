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
