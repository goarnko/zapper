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

        assert browser.listbox.get(0) == ui.FAVORITES_LABEL
        # The header must be the topmost visible row, not scrolled above it.
        assert browser.listbox.nearest(0) == 0
        assert browser.listbox.yview()[0] == 0.0
        # ...and a channel is still selected, so Enter plays immediately.
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
