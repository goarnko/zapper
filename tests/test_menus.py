"""Menu bar and shortcut help.

The menus add discovery, not behaviour: every entry is a shortcut that
already exists. So the tests that matter are the ones checking the three
descriptions of a shortcut — the binding, the menu accelerator and the help
window — cannot drift apart.

Display-dependent tests skip rather than fail when there is no display.
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


def _app(root):
    """A ChannelBrowser wired up as run() does, menu bar included."""
    from zaptv import ui
    from zaptv.models import Channel
    from zaptv.player import VLCPlayer
    from zaptv.settings import Settings
    from zaptv.storage import Favorites, Recent

    channels = [
        Channel(name="Alfa", group="Uno", streams=["https://x.invalid/1"]),
        Channel(name="Beta", group="Dos", streams=["https://x.invalid/2"]),
    ]
    browser = ui.ChannelBrowser(
        root, channels, VLCPlayer(), Favorites([]), Recent([]), None,
        Settings(show_logos=False),
    )
    browser.pack()
    return browser


# -- the shortcut table --------------------------------------------------


def test_every_shortcut_has_a_key_and_a_description():
    from zaptv import ui

    for heading, entries in ui.SHORTCUTS:
        assert heading
        assert entries, f"{heading} lists no shortcuts"
        for keys, what in entries:
            assert keys.strip(), f"{heading}: empty key"
            assert what.strip(), f"{heading}: {keys} has no description"


def test_the_documented_keys_are_actually_bound():
    """Guards the help window against promising a key nothing listens to."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui

    root = tk.Tk()
    try:
        browser = _app(root)
        ui.bind_shortcuts(root, browser)
        ui.build_menubar(root, browser)
        root.update()

        bound = set(root.bind()) | set(browser.tree.bind()) | set(browser._entry.bind())
        expected = {
            "Ctrl+F": "<Control-Key-f>",
            "Ctrl+G": "<Control-Key-g>",
            "Ctrl+P": "<Control-Key-p>",
            "Ctrl+R": "<Control-Key-r>",
            "Ctrl+Q": "<Control-Key-q>",
            "F1": "<Key-F1>",
            "Esc": "<Key-Escape>",
            # Tk reports a plain-letter binding as the bare letter, not as
            # the <KeyPress-f> the source spells.
            "F": "f",
            "Enter": "<Key-Return>",
        }
        listed = {k for _h, entries in ui.SHORTCUTS for k, _d in entries}
        for label, sequence in expected.items():
            assert label in listed, f"{label} is bound but missing from SHORTCUTS"
            assert sequence in bound, f"SHORTCUTS lists {label} but nothing binds {sequence}"
    finally:
        root.destroy()


# -- help window ---------------------------------------------------------


def test_help_window_lists_every_shortcut():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import theme, ui

    root = tk.Tk()
    try:
        window = ui.HelpWindow(root, theme.get("light"))
        root.update()

        shown = {
            child.cget("text")
            for child in window.winfo_children()[0].winfo_children()
            if isinstance(child, tk.Label)
        }
        for heading, entries in ui.SHORTCUTS:
            assert heading in shown
            for keys, what in entries:
                assert keys in shown, f"{keys} missing from the help window"
                assert what in shown, f"description of {keys} missing"
    finally:
        root.destroy()


def test_f1_opens_help_from_the_browser():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui

    root = tk.Tk()
    try:
        browser = _app(root)
        root.update()
        browser.open_help()
        root.update()
        opened = [w for w in browser.winfo_children() if isinstance(w, ui.HelpWindow)]
        assert len(opened) == 1
    finally:
        root.destroy()


def test_help_is_themed_dark():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import theme, ui

    root = tk.Tk()
    try:
        window = ui.HelpWindow(root, theme.get("dark"))
        root.update()
        assert window.cget("bg") == theme.DARK.bg
    finally:
        root.destroy()


# -- menu bar ------------------------------------------------------------


def _labels(menu):
    out = []
    for index in range(menu.index("end") + 1 if menu.index("end") is not None else 0):
        if menu.type(index) != "separator":
            out.append(menu.entrycget(index, "label"))
    return out


def test_the_menubar_has_the_expected_menus():
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui

    root = tk.Tk()
    try:
        browser = _app(root)
        bar = ui.build_menubar(root, browser)
        root.update()
        assert _labels(bar) == ["File", "Channel", "View", "Help"]
        # And it is actually attached, not merely built.
        assert root.cget("menu") == str(bar)
    finally:
        root.destroy()


def test_menu_entries_carry_the_matching_accelerator():
    """A menu promising Ctrl+R must name the key that really does it."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui

    root = tk.Tk()
    try:
        browser = _app(root)
        bar = ui.build_menubar(root, browser)
        root.update()

        file_menu = root.nametowidget(bar.entrycget(0, "menu"))
        pairs = {}
        for index in range(file_menu.index("end") + 1):
            if file_menu.type(index) == "separator":
                continue
            pairs[file_menu.entrycget(index, "label")] = file_menu.entrycget(
                index, "accelerator"
            )
        assert pairs["Update now"] == "Ctrl+R"
        assert pairs["Playlists…"] == "Ctrl+P"
        assert pairs["Settings…"] == "Ctrl+,"
        assert pairs["Quit"] == "Ctrl+Q"
    finally:
        root.destroy()


def test_the_menu_plays_through_the_same_path_as_enter():
    if not _tk_available():
        return

    from zaptv import ui

    played = []
    import tkinter as tk

    root = tk.Tk()
    try:
        browser = _app(root)
        ui.build_menubar(root, browser)
        root.update()
        browser._play = lambda channel, player: played.append(channel.name)

        browser.play_selected()
        # Groups sort alphabetically, so DOS/Beta is selected at startup.
        assert played == ["Beta"], played
    finally:
        root.destroy()


def test_play_with_on_an_empty_selection_does_nothing():
    """The menu is clickable even when the list has no selection."""
    if not _tk_available():
        return

    import tkinter as tk

    from zaptv import ui

    root = tk.Tk()
    try:
        browser = _app(root)
        ui.build_menubar(root, browser)
        root.update()
        browser.tree.selection_remove(*browser.tree.selection())

        played = []
        browser._play = lambda channel, player: played.append(channel.name)
        browser.play_with_command("vlc")()
        assert played == []
    finally:
        root.destroy()
