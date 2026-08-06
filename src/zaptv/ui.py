"""Tkinter channel browser.

One screen: a search box over a grouped channel list. Favorites and recently
watched float to the top so the channels a user actually watches are reachable
without scrolling past several hundred others.
"""

import tkinter as tk
from tkinter import messagebox

from . import playlist, search, updater
from .models import Channel
from .player import Player, PlayerNotFound, get_player
from .settings import Settings
from .storage import Favorites, Recent

_HEADER_FG = "#6d6d6d"
_STAR = "★"

FAVORITES_LABEL = "★ FAVORITES"
RECENT_LABEL = "RECENT"


class ChannelBrowser(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        channels: list[Channel],
        player: Player,
        favorites: Favorites,
        recent: Recent,
    ):
        super().__init__(master)
        self._channels = channels
        self._player = player
        self._favorites = favorites
        self._recent = recent
        # Index-aligned with the listbox; None marks a section header or spacer.
        self._rows: list[Channel | None] = []

        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._refresh())

        self._build()
        self._refresh()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        entry = tk.Entry(self, textvariable=self.query)
        entry.pack(fill=tk.X, pady=(0, 6))
        self._entry = entry

        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(body, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            body,
            activestyle="none",
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, anchor="w", fg=_HEADER_FG)
        self.status.pack(fill=tk.X, pady=(6, 0))

        self.listbox.bind("<Double-Button-1>", self._on_play)
        self.listbox.bind("<Return>", self._on_play)
        # Plain "f" favorites the selection, but only from the list: inside
        # the search box it has to stay an ordinary character.
        self.listbox.bind("<KeyPress-f>", self._on_toggle_favorite)
        self.listbox.bind("<KeyPress-F>", self._on_toggle_favorite)
        entry.bind("<Return>", self._on_search_return)
        entry.bind("<Down>", self._focus_list)

    # -- list building ---------------------------------------------------

    def _refresh(self) -> None:
        # Rebuilding the list loses the selection; favoriting or playing must
        # not throw the user back to the top of several hundred channels.
        previous = self.selected()

        visible = search.filter_channels(self._channels, self.query.get())
        by_name = {c.name: c for c in visible}

        self.listbox.delete(0, tk.END)
        self._rows = []

        favorites = sorted(
            (c for c in visible if c.name in self._favorites), key=search.sort_key
        )
        if favorites:
            self._add_section(FAVORITES_LABEL, favorites)

        recent = [by_name[n] for n in self._recent.names if n in by_name]
        if recent:
            self._add_section(RECENT_LABEL, recent)

        for group in sorted({c.group for c in visible}, key=search.normalize):
            members = sorted((c for c in visible if c.group == group), key=search.sort_key)
            self._add_section(group.upper(), members)

        self._update_status(len(visible))
        self._restore_selection(previous)

    def _add_section(self, label: str, channels: list[Channel]) -> None:
        if self._rows:
            self.listbox.insert(tk.END, "")
            self._rows.append(None)
        self.listbox.insert(tk.END, label)
        self.listbox.itemconfig(tk.END, foreground=_HEADER_FG, selectbackground=_HEADER_FG)
        self._rows.append(None)
        for channel in channels:
            marker = _STAR if channel.name in self._favorites else " "
            self.listbox.insert(tk.END, f" {marker} {channel.name}")
            self._rows.append(channel)

    def _update_status(self, count: int) -> None:
        total = len(self._channels)
        if count == total:
            self.status.config(text=f"{total} channels")
        else:
            self.status.config(text=f"{count} of {total} channels")

    def _restore_selection(self, previous: Channel | None) -> None:
        """Reselect the previous channel, else the first one.

        Always leaving something selected means Enter works straight after
        typing a search, with no arrow key in between.
        """
        restored = self._index_of(previous) if previous is not None else None
        target = restored
        if target is None:
            target = next((i for i, row in enumerate(self._rows) if row is not None), None)
        if target is None:
            return

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(target)

        if restored is None:
            # Nothing carried over — startup, or a search that dropped the old
            # selection. Show the list from the very top; see() here would put
            # the first channel flush against the top edge and scroll its
            # section header out of sight.
            self.listbox.yview_moveto(0.0)
        else:
            self.listbox.see(max(target - 1, 0))
            self.listbox.see(target)

    def _index_of(self, channel: Channel) -> int | None:
        """Row of a channel, preferring its group entry over its favorites copy.

        A favorited channel is listed twice; landing on the group copy keeps
        the surrounding channels in view.
        """
        matches = [i for i, row in enumerate(self._rows) if row is channel]
        return matches[-1] if matches else None

    # -- selection -------------------------------------------------------

    def selected(self) -> Channel | None:
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self._rows[selection[0]]

    # -- actions ---------------------------------------------------------

    def _on_play(self, _event: object = None) -> str:
        channel = self.selected()
        if channel is None:
            return "break"
        try:
            self._player.play(channel.stream)
        except PlayerNotFound as exc:
            messagebox.showerror("Player not found", str(exc), parent=self)
            return "break"
        self._recent.push(channel.name)
        self._refresh()
        return "break"

    def _on_search_return(self, _event: object = None) -> str:
        """Enter in the search box plays the top hit, so search-then-watch
        never needs the mouse or an extra keystroke."""
        return self._on_play()

    def _on_toggle_favorite(self, _event: object = None) -> str:
        channel = self.selected()
        if channel is None:
            return "break"
        self._favorites.toggle(channel.name)
        self._refresh()
        return "break"

    def focus_search(self, _event: object = None) -> str:
        self._entry.focus_set()
        self._entry.select_range(0, tk.END)
        return "break"

    def clear_search(self, _event: object = None) -> str:
        self.query.set("")
        return "break"

    def _focus_list(self, _event: object = None) -> str:
        self.listbox.focus_set()
        return "break"

    def reload(self, _event: object = None) -> str:
        """Force a playlist download, keeping the old list if it fails."""
        self.status.config(text="Updating…")
        self.update_idletasks()
        try:
            path = updater.download()
            channels = playlist.load(path)
        except OSError as exc:
            messagebox.showerror("Update failed", str(exc), parent=self)
            self._refresh()
            return "break"

        if channels:
            self._channels = channels
        self._refresh()
        return "break"


def run(
    channels: list[Channel],
    config: Settings | None = None,
    favorites: Favorites | None = None,
    recent: Recent | None = None,
) -> None:
    config = config or Settings.load()

    root = tk.Tk()
    root.title("ZapTV")
    root.geometry("420x640")

    browser = ChannelBrowser(
        root,
        channels,
        get_player(config.player),
        favorites or Favorites.load(),
        recent or Recent.load(),
    )
    browser.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    root.bind("<Control-f>", browser.focus_search)
    root.bind("<Control-r>", browser.reload)
    root.bind("<Escape>", browser.clear_search)
    root.bind("<Control-q>", lambda _e: root.destroy())

    browser.listbox.focus_set()
    root.mainloop()
