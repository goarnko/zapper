"""Tkinter channel browser.

One screen: a search box over a grouped channel list, with a Now/Next pane
underneath. Favorites and recently watched float to the top so the channels a
user actually watches are reachable without scrolling past several hundred
others.

The list is a ttk.Treeview rather than a Listbox because only Treeview can
show a per-row image, and channel logos are the point of Milestone 4.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont
from tkinter import messagebox, simpledialog, ttk

from . import epg as epg_module
from . import logos as logos_module
from . import providers as providers_module
from . import search, theme, updater
from .models import Channel, Programme
from .player import SELECTABLE, Player, PlayerNotFound, get_player
from .settings import Settings
from .storage import Favorites, Recent

_STAR = "★"

FAVORITES_LABEL = "★ FAVORITES"
RECENT_LABEL = "RECENT"

NO_GUIDE_TEXT = "No guide data for this channel"
#: How often the Now/Next pane re-evaluates which programme is on air.
GUIDE_TICK_MS = 60_000
#: How often newly downloaded logos are collected onto rows.
LOGO_TICK_MS = 400
#: Descriptions run to several hundred characters; the pane shows three lines.
DESCRIPTION_LIMIT = 165

ROW_HEIGHT = 28


def format_slot(programme: Programme | None) -> str:
    """One line for a programme, in the viewer's local time."""
    if programme is None:
        return "—"
    local = programme.start.astimezone()
    return f"{local:%H:%M}  {programme.title}"


def clip(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """Trim to a whole word and mark the cut, rather than stopping mid-word."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:")
    return f"{cut}…"


class GuidePane(tk.Frame):
    """Now / Next for the selected channel.

    Most channels have no guide data at all — the playlist carries far more
    channels than the XMLTV feed covers — so "no guide" is a normal state
    here, rendered quietly rather than as an error.
    """

    def __init__(self, master: tk.Misc, palette: theme.Palette):
        super().__init__(master)
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")

        self.channel_label = tk.Label(self, anchor="w", font=bold)
        self.now_label = tk.Label(self, anchor="w")
        self.next_label = tk.Label(self, anchor="w")
        self.description = tk.Label(
            self, anchor="nw", justify=tk.LEFT, wraplength=390, height=3
        )
        for widget in (self.channel_label, self.now_label, self.next_label, self.description):
            widget.pack(fill=tk.X)
        self.apply_palette(palette)

    def apply_palette(self, palette: theme.Palette) -> None:
        self.config(bg=palette.bg)
        for widget in (self.channel_label, self.now_label):
            widget.config(bg=palette.bg, fg=palette.fg)
        for widget in (self.next_label, self.description):
            widget.config(bg=palette.bg, fg=palette.muted)

    def show(
        self,
        channel: Channel | None,
        current: Programme | None,
        following: Programme | None,
    ) -> None:
        if channel is None:
            for widget in (self.channel_label, self.now_label, self.next_label, self.description):
                widget.config(text="")
            return

        self.channel_label.config(text=channel.name)
        if current is None and following is None:
            self.now_label.config(text=NO_GUIDE_TEXT)
            self.next_label.config(text="")
            self.description.config(text="")
            return

        self.now_label.config(text=f"Now   {format_slot(current)}")
        self.next_label.config(text=f"Next  {format_slot(following)}")
        self.description.config(text=clip(current.description) if current else "")


def style_dialog(style: ttk.Style, palette: theme.Palette) -> None:
    """Paint the ttk widgets used by the settings dialog.

    ttk ignores widget-level colour options, so each class needs a named
    style; without this the dialog stays light grey while the app is dark.
    """
    style.configure("Zap.TFrame", background=palette.bg)
    style.configure("Zap.TLabel", background=palette.bg, foreground=palette.fg)
    style.configure("Zap.TSeparator", background=palette.border)
    for widget in ("Zap.TRadiobutton", "Zap.TCheckbutton"):
        style.configure(
            widget,
            background=palette.bg,
            foreground=palette.fg,
            indicatorcolor=palette.field_bg,
        )
        style.map(
            widget,
            background=[("active", palette.bg)],
            foreground=[("disabled", palette.muted), ("active", palette.fg)],
            indicatorcolor=[("selected", palette.select_bg)],
        )
    style.configure(
        "Zap.TButton",
        background=palette.field_bg,
        foreground=palette.fg,
        bordercolor=palette.border,
        focuscolor=palette.select_bg,
    )
    style.map(
        "Zap.TButton",
        background=[("active", palette.select_bg)],
        foreground=[("active", palette.select_fg)],
    )
    # Column headings are their own element; without this they stay light
    # grey above a dark table. The main window's list has no headings, so
    # configuring the shared style here is safe.
    style.configure(
        "Treeview.Heading",
        background=palette.field_bg,
        foreground=palette.fg,
        relief=tk.FLAT,
    )
    style.map("Treeview.Heading", background=[("active", palette.select_bg)])


class ProvidersWindow(tk.Toplevel):
    """Add, remove and toggle playlist sources.

    The built-in source can be disabled but not deleted: losing it by
    accident would leave a new user with an empty app and no way back.
    """

    def __init__(
        self,
        master: tk.Misc,
        sources: providers_module.ProviderList,
        palette: theme.Palette,
        on_change,
    ):
        super().__init__(master)
        self.title("ZapTV Playlists")
        self.geometry("640x360")
        self.minsize(600, 300)
        self.transient(master.winfo_toplevel())
        self.configure(bg=palette.bg)
        style_dialog(ttk.Style(self), palette)
        self._sources = sources
        self._on_change = on_change
        self._dirty = False

        body = ttk.Frame(self, padding=12, style="Zap.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            body, columns=("url",), show="tree headings", selectmode="browse", height=8
        )
        self.tree.heading("#0", text="Playlist")
        self.tree.heading("url", text="Source")
        self.tree.column("#0", width=180, stretch=False)
        self.tree.column("url", width=300)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-Button-1>", lambda _e: self._toggle())

        buttons = ttk.Frame(body, style="Zap.TFrame")
        buttons.pack(fill=tk.X, pady=(10, 0))
        for text, command in (
            ("Add URL…", self._add_url),
            ("Add file…", self._add_file),
            ("Enable/Disable", self._toggle),
            ("Remove", self._remove),
        ):
            ttk.Button(buttons, text=text, command=command, style="Zap.TButton").pack(
                side=tk.LEFT, padx=(0, 6)
            )
        ttk.Button(buttons, text="Close", command=self._close, style="Zap.TButton").pack(
            side=tk.RIGHT
        )

        self.bind("<Escape>", lambda _e: self._close())
        self._populate()

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for provider in self._sources:
            mark = "☑" if provider.enabled else "☐"
            suffix = "  (built-in)" if provider.builtin else ""
            self.tree.insert(
                "", tk.END, iid=provider.name, text=f"{mark} {provider.name}{suffix}",
                values=(provider.url,),
            )

    def _selected_name(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _changed(self) -> None:
        self._dirty = True
        self._populate()

    def _toggle(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        provider = self._sources.get(name)
        if provider is None:
            return
        self._sources.set_enabled(name, not provider.enabled)
        self._changed()

    def _remove(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if not self._sources.remove(name):
            messagebox.showinfo(
                "Built-in playlist",
                "The built-in playlist cannot be removed, only disabled.",
                parent=self,
            )
            return
        self._changed()

    def _add_url(self) -> None:
        url = simpledialog.askstring("Add playlist", "Playlist URL:", parent=self)
        if not url:
            return
        name = simpledialog.askstring(
            "Add playlist", "Name for this playlist:", parent=self, initialvalue=url
        )
        if not name:
            return
        self._sources.add(name, url)
        self._changed()

    def _add_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose an M3U playlist",
            filetypes=[("M3U playlists", "*.m3u *.m3u8"), ("All files", "*")],
        )
        if not path:
            return
        name = simpledialog.askstring(
            "Add playlist",
            "Name for this playlist:",
            parent=self,
            initialvalue=Path(path).stem,
        )
        if not name:
            return
        self._sources.add(name, path)
        self._changed()

    def _close(self) -> None:
        # Reloading several hundred channels is not free, so only do it when
        # the source list actually changed.
        if self._dirty:
            self._on_change()
        self.destroy()


class SettingsWindow(tk.Toplevel):
    """Player, updates, theme and logos, saved on OK."""

    def __init__(self, master: tk.Misc, config: Settings, palette: theme.Palette, on_save):
        super().__init__(master)
        self.title("ZapTV Settings")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.configure(bg=palette.bg)
        style_dialog(ttk.Style(self), palette)
        self._config = config
        self._on_save = on_save

        self.player = tk.StringVar(value=config.player)
        self.auto_update = tk.BooleanVar(value=config.auto_update)
        self.theme_name = tk.StringVar(value=config.theme)
        self.show_logos = tk.BooleanVar(value=config.show_logos)

        body = ttk.Frame(self, padding=12, style="Zap.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Player", style="Zap.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        for column, name in enumerate(SELECTABLE):
            # Offer every backend but say which are actually installed, rather
            # than hiding the choice and leaving the user guessing.
            available = get_player(name).is_available()
            ttk.Radiobutton(
                body,
                text=name if available else f"{name} (not installed)",
                value=name,
                variable=self.player,
                state=tk.NORMAL if available else tk.DISABLED,
                style="Zap.TRadiobutton",
            ).grid(row=1, column=column, sticky="w", padx=(0, 12))

        ttk.Separator(body, orient=tk.HORIZONTAL, style="Zap.TSeparator").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=10
        )

        ttk.Label(body, text="Appearance", style="Zap.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 4))
        for column, name in enumerate(("light", "dark")):
            ttk.Radiobutton(
                body, text=name, value=name, variable=self.theme_name,
                style="Zap.TRadiobutton",
            ).grid(row=4, column=column, sticky="w", padx=(0, 12))

        ttk.Checkbutton(
            body, text="Show channel logos", variable=self.show_logos, style="Zap.TCheckbutton"
        ).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(
            body,
            text="Update playlist and guide automatically",
            variable=self.auto_update,
            style="Zap.TCheckbutton",
        ).grid(row=6, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(body, style="Zap.TFrame")
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy, style="Zap.TButton").pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save, style="Zap.TButton").pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._save())

    def _save(self) -> None:
        self._config.player = self.player.get()
        self._config.auto_update = bool(self.auto_update.get())
        self._config.theme = self.theme_name.get()
        self._config.show_logos = bool(self.show_logos.get())
        self._config.save()
        self._on_save(self._config)
        self.destroy()


class ChannelBrowser(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        channels: list[Channel],
        player: Player,
        favorites: Favorites,
        recent: Recent,
        guide: epg_module.Guide | None = None,
        config: Settings | None = None,
        logo_store: logos_module.LogoStore | None = None,
        sources: providers_module.ProviderList | None = None,
    ):
        super().__init__(master)
        self._channels = channels
        self._player = player
        self._favorites = favorites
        self._recent = recent
        self._guide = guide or epg_module.Guide()
        self._config = config or Settings()
        self._sources = sources
        self._palette = theme.get(self._config.theme)

        self._logos = logo_store
        # Tk images must be built on the main thread and kept referenced, or
        # they are garbage collected straight off the rows.
        self._images: dict[str, tk.PhotoImage] = {}

        #: Treeview row id -> channel. Headers are absent, which is what makes
        #: them unselectable.
        self._rows: dict[str, Channel] = {}
        self._row_order: list[str] = []

        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._refresh())

        self._build()
        self._refresh()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        self.style = ttk.Style()
        self._entry = tk.Entry(self, textvariable=self.query)
        self._entry.pack(fill=tk.X, pady=(0, 6))

        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(
            body,
            show="tree",
            selectmode="browse",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.guide_pane = GuidePane(self, self._palette)
        self.guide_pane.pack(fill=tk.X, pady=(6, 0))

        self.status = tk.Label(self, anchor="w")
        self.status.pack(fill=tk.X, pady=(6, 0))

        self.tree.bind("<Double-Button-1>", self._on_play)
        self.tree.bind("<Return>", self._on_play)
        # Plain "f" favorites the selection, but only from the list: inside
        # the search box it has to stay an ordinary character.
        self.tree.bind("<KeyPress-f>", self._on_toggle_favorite)
        self.tree.bind("<KeyPress-F>", self._on_toggle_favorite)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_guide())
        self._entry.bind("<Return>", self._on_play)
        self._entry.bind("<Down>", self._focus_list)

        self.apply_palette(self._palette)

        # Whichever programme is "now" changes without any user action.
        self.after(GUIDE_TICK_MS, self._tick_guide)
        if self._logos is not None:
            self.after(LOGO_TICK_MS, self._tick_logos)

    # -- theming ---------------------------------------------------------

    def apply_palette(self, palette: theme.Palette) -> None:
        self._palette = palette
        self.config(bg=palette.bg)
        self._entry.config(
            bg=palette.field_bg,
            fg=palette.fg,
            insertbackground=palette.fg,
            highlightthickness=1,
            highlightbackground=palette.border,
            highlightcolor=palette.select_bg,
            relief=tk.FLAT,
        )
        self.status.config(bg=palette.bg, fg=palette.muted)
        self.guide_pane.apply_palette(palette)

        # "clam" is the one built-in ttk theme that honours these colours on
        # Linux; the default theme ignores Treeview background settings.
        self.style.theme_use("clam")
        self.style.configure(
            "Treeview",
            background=palette.field_bg,
            fieldbackground=palette.field_bg,
            foreground=palette.fg,
            rowheight=ROW_HEIGHT,
            borderwidth=0,
        )
        self.style.map(
            "Treeview",
            background=[("selected", palette.select_bg)],
            foreground=[("selected", palette.select_fg)],
        )
        self.tree.tag_configure("header", foreground=palette.muted)
        self.tree.tag_configure("channel", foreground=palette.fg)

    def retheme(self, config: Settings) -> None:
        """Re-apply settings that change how the list looks."""
        self._config = config
        self._player = get_player(config.player)
        self.apply_palette(theme.get(config.theme))
        self._refresh()

    # -- list building ---------------------------------------------------

    def _refresh(self) -> None:
        # Rebuilding the list loses the selection; favoriting or playing must
        # not throw the user back to the top of several hundred channels.
        previous = self.selected()

        visible = search.filter_channels(self._channels, self.query.get())
        by_name = {c.name: c for c in visible}

        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        self._row_order.clear()

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
        # Selecting from code does not fire <<TreeviewSelect>>.
        self._update_guide()

    def _add_section(self, label: str, channels: list[Channel]) -> None:
        self.tree.insert("", tk.END, text=label, tags=("header",))
        for channel in channels:
            marker = f"{_STAR} " if channel.name in self._favorites else "   "
            item = self.tree.insert(
                "",
                tk.END,
                text=f"{marker}{channel.name}",
                image=self._image_for(channel),
                tags=("channel",),
            )
            self._rows[item] = channel
            self._row_order.append(item)

    def _update_status(self, count: int) -> None:
        total = len(self._channels)
        if count == total:
            self.status.config(text=f"{total} channels")
        else:
            self.status.config(text=f"{count} of {total} channels")

    def _restore_selection(self, previous: Channel | None) -> None:
        target = None
        if previous is not None:
            # Prefer the group entry over the favorites copy, so the channels
            # around the selection stay in view.
            for item in reversed(self._row_order):
                if self._rows[item] is previous:
                    target = item
                    break

        restored = target is not None
        if target is None and self._row_order:
            target = self._row_order[0]
        if target is None:
            return

        self.tree.selection_set(target)
        self.tree.focus(target)
        if restored:
            self.tree.see(target)
        else:
            # Nothing carried over — startup, or a search that dropped the
            # selection. Show the list from the very top so the first section
            # header is not scrolled out of sight.
            self.tree.yview_moveto(0.0)

    # -- logos -----------------------------------------------------------

    def _image_for(self, channel: Channel) -> str | tk.PhotoImage:
        """Row image, or "" while the logo is still being fetched."""
        if self._logos is None or not self._config.show_logos or not channel.logo:
            return ""
        cached = self._images.get(channel.logo)
        if cached is not None:
            return cached

        path = self._logos.path_for(channel.logo)
        if path is None:
            return ""
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return ""
        self._images[channel.logo] = image
        return image

    def _tick_logos(self) -> None:
        """Put newly downloaded logos onto their rows without a full rebuild."""
        if self._logos is None:
            return
        if self._logos.drain() and self._config.show_logos:
            for item, channel in self._rows.items():
                # Test the row, not the image cache: channels share logo URLs
                # (one Facebook logo covers 16 regional channels), so keying
                # off _images would fill only the first row of each group.
                if not channel.logo or self.tree.item(item, "image"):
                    continue
                image = self._image_for(channel)
                if image != "":
                    self.tree.item(item, image=image)
        self.after(LOGO_TICK_MS, self._tick_logos)

    # -- guide -----------------------------------------------------------

    def _update_guide(self) -> None:
        channel = self.selected()
        if channel is None:
            self.guide_pane.show(None, None, None)
            return
        current, following = self._guide.now_and_next(channel.tvg_id)
        self.guide_pane.show(channel, current, following)

    def _tick_guide(self) -> None:
        self._update_guide()
        self.after(GUIDE_TICK_MS, self._tick_guide)

    # -- selection -------------------------------------------------------

    def selected(self) -> Channel | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._rows.get(selection[0])

    # -- actions ---------------------------------------------------------

    def _on_play(self, _event: object = None) -> str:
        channel = self.selected()
        if channel is None:
            return "break"
        try:
            self._player_for(channel).play(channel.stream)
        except PlayerNotFound as exc:
            messagebox.showerror("Player not found", str(exc), parent=self)
            return "break"
        self._recent.push(channel.name)
        self._refresh()
        return "break"

    def _player_for(self, channel: Channel) -> Player:
        """The channel's own player when it names one, else the default.

        Web channels carry a page URL rather than a stream, so they must
        open in a browser however the user configured VLC or mpv.
        """
        if channel.player:
            return get_player(channel.player)
        return self._player

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
        self.tree.focus_set()
        return "break"

    def open_settings(self, _event: object = None) -> str:
        SettingsWindow(self, self._config, self._palette, self.retheme)
        return "break"

    def open_providers(self, _event: object = None) -> str:
        if self._sources is None:
            return "break"
        ProvidersWindow(self, self._sources, self._palette, self._reload_channels)
        return "break"

    def _reload_channels(self, force: bool = False) -> str:
        """Re-read channels from the configured providers.

        Keeps the current list when every source fails, so a dropped network
        never empties the window.
        """
        if self._sources is None:
            return "break"

        self.status.config(text="Loading playlists…")
        self.update_idletasks()
        max_age = 0 if force else updater.MAX_AGE_SECONDS
        channels, failed = self._sources.load_channels(max_age=max_age)
        if channels:
            self._channels = channels

        self._refresh()
        if failed:
            self.status.config(text=f"Unavailable: {', '.join(failed)}")
            self.update_idletasks()
        return "break"

    def reload(self, _event: object = None) -> str:
        """Force a refresh of every playlist and the guide."""
        self._reload_channels(force=True)

        # The guide is optional: a failure here should not spoil a successful
        # playlist refresh, so it is reported only in the status line.
        try:
            self._guide = epg_module.load(updater.download_epg())
            self._update_guide()
        except OSError:
            self.status.config(text="Channel lists updated; guide unavailable")
            self.update_idletasks()
        return "break"


def run(
    channels: list[Channel],
    config: Settings | None = None,
    favorites: Favorites | None = None,
    recent: Recent | None = None,
    guide: epg_module.Guide | None = None,
    sources: providers_module.ProviderList | None = None,
) -> None:
    config = config or Settings.load()

    root = tk.Tk()
    root.title("ZapTV")
    root.geometry("420x760")
    set_window_icon(root)

    store = logos_module.LogoStore() if config.show_logos else None
    browser = ChannelBrowser(
        root,
        channels,
        get_player(config.player),
        favorites or Favorites.load(),
        recent or Recent.load(),
        guide,
        config,
        store,
        sources,
    )
    browser.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    root.config(bg=browser._palette.bg)

    root.bind("<Control-f>", browser.focus_search)
    root.bind("<Control-r>", browser.reload)
    root.bind("<Control-comma>", browser.open_settings)
    root.bind("<Control-p>", browser.open_providers)
    root.bind("<Escape>", browser.clear_search)
    root.bind("<Control-q>", lambda _e: root.destroy())

    browser.tree.focus_set()
    try:
        root.mainloop()
    finally:
        if store is not None:
            store.stop()


def set_window_icon(root: tk.Tk) -> None:
    """Set the window icon, ignoring a missing or unreadable asset.

    The asset lives inside the package so it survives installation; a plain
    repo path would only work from a source checkout.
    """
    from pathlib import Path

    icon = Path(__file__).resolve().parent / "assets" / "icon-64.png"
    if not icon.exists():
        return
    try:
        # Kept on the root, or the image is collected and the icon blanks.
        root._zaptv_icon = tk.PhotoImage(file=str(icon))  # type: ignore[attr-defined]
        root.iconphoto(True, root._zaptv_icon)  # type: ignore[attr-defined]
    except tk.TclError:
        pass
