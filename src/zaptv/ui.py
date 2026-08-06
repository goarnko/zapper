"""Tkinter channel list.

Milestone 1 is deliberately one screen: the channel list, grouped, with
Enter or double-click launching the player. Search and favorites are
Milestone 2.
"""

import tkinter as tk
from tkinter import messagebox

from .models import Channel
from .player import Player, PlayerNotFound, get_player
from .settings import Settings

_HEADER_FG = "#6d6d6d"


class ChannelList(tk.Frame):
    def __init__(self, master: tk.Misc, channels: list[Channel], player: Player):
        super().__init__(master)
        self._player = player
        # Index-aligned with the listbox: None marks a group header row.
        self._rows: list[Channel | None] = []

        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            self,
            activestyle="none",
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.listbox.bind("<Double-Button-1>", self._on_activate)
        self.listbox.bind("<Return>", self._on_activate)

        self._populate(channels)

    def _populate(self, channels: list[Channel]) -> None:
        for group in sorted({c.group for c in channels}):
            members = sorted(
                (c for c in channels if c.group == group),
                key=lambda c: c.name.casefold(),
            )
            self._append_header(group)
            for channel in members:
                self._append_channel(channel)

    def _append_header(self, group: str) -> None:
        if self._rows:
            self.listbox.insert(tk.END, "")
            self._rows.append(None)
        self.listbox.insert(tk.END, group.upper())
        self.listbox.itemconfig(tk.END, foreground=_HEADER_FG, selectbackground=_HEADER_FG)
        self._rows.append(None)

    def _append_channel(self, channel: Channel) -> None:
        self.listbox.insert(tk.END, f"   {channel.name}")
        self._rows.append(channel)

    def selected(self) -> Channel | None:
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self._rows[selection[0]]

    def _on_activate(self, _event: object = None) -> None:
        channel = self.selected()
        if channel is None:
            return
        try:
            self._player.play(channel.stream)
        except PlayerNotFound as exc:
            messagebox.showerror("Player not found", str(exc), parent=self)


def run(channels: list[Channel], config: Settings | None = None) -> None:
    config = config or Settings.load()

    root = tk.Tk()
    root.title("ZapTV")
    root.geometry("420x640")

    channel_list = ChannelList(root, channels, get_player(config.player))
    channel_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    root.bind("<Escape>", lambda _e: root.destroy())
    channel_list.listbox.focus_set()
    root.mainloop()
