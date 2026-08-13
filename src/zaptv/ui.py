"""Tkinter channel browser.

One screen: a search box over a grouped channel list, with a Now/Next pane
underneath. Favorites and recently watched float to the top so the channels a
user actually watches are reachable without scrolling past several hundred
others.

The list is a ttk.Treeview rather than a Listbox because only Treeview can
show a per-row image, and channel logos are the point of Milestone 4.
"""

import queue
import tkinter as tk
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import __version__, grid, search, theme, updater
from . import epg as epg_module
from . import logos as logos_module
from . import providers as providers_module
from . import updates as updates_module
from .models import Channel, Programme
from .player import PLAYERS, SELECTABLE, Player, PlayerNotFound, get_player, resolve
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
#: How often the background update check is polled for its answer.
UPDATE_TICK_MS = 1000
#: Descriptions run to several hundred characters; the pane shows three lines.
DESCRIPTION_LIMIT = 165

ROW_HEIGHT = 28

#: Width of the frozen channel-name column in the guide grid.
GRID_NAME_WIDTH = 150
#: Height of the time ruler above the grid.
GRID_RULER_HEIGHT = 22
#: Breathing room between a block's edge and its title.
GRID_BLOCK_PAD = 4
#: How far channel names sit inside their section heading.
GRID_INDENT = 16


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
        on_change: Callable[[], None],
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

    def __init__(
        self,
        master: tk.Misc,
        config: Settings,
        palette: theme.Palette,
        on_save: Callable[[Settings], None],
    ):
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
        self.check_updates = tk.BooleanVar(value=config.check_updates)

        body = ttk.Frame(self, padding=12, style="Zap.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Player", style="Zap.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
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

        ttk.Label(body, text="Appearance", style="Zap.TLabel").grid(
            row=3, column=0, sticky="w", pady=(0, 4)
        )
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
        ttk.Checkbutton(
            body,
            text="Tell me when a new ZapTV is released",
            variable=self.check_updates,
            style="Zap.TCheckbutton",
        ).grid(row=7, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(body, style="Zap.TFrame")
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(
            buttons, text="Cancel", command=self.destroy, style="Zap.TButton"
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save, style="Zap.TButton").pack(
            side=tk.RIGHT
        )

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._save())

    def _save(self) -> None:
        self._config.player = self.player.get()
        self._config.auto_update = bool(self.auto_update.get())
        self._config.theme = self.theme_name.get()
        self._config.show_logos = bool(self.show_logos.get())
        self._config.check_updates = bool(self.check_updates.get())
        self._config.save()
        self._on_save(self._config)
        self.destroy()


class GuideWindow(tk.Toplevel):
    """The whole schedule at once: one row per channel, time across the top.

    A view over the XMLTV already in memory — it downloads nothing and adds no
    cache. Only channels whose tvg-id the guide knows get a row, which is
    roughly a quarter of the playlist, so the footer says how many are shown
    rather than leaving the user hunting for a channel that was never going
    to appear.

    Time is *paged*, not scrolled horizontally. grid.build returns positions
    as fractions of the visible window, so they map onto whatever width the
    canvas happens to have and a resize simply redraws. Drawing only the
    visible window also keeps the canvas at a few hundred items rather than
    the eleven thousand programmes the feed carries.
    """

    def __init__(
        self,
        master: tk.Misc,
        guide: epg_module.Guide,
        channels: list[Channel],
        palette: theme.Palette,
        on_play: Callable[[Channel], None],
        favorites: grid.Names | None = None,
        config: Settings | None = None,
        now: datetime | None = None,
    ):
        super().__init__(master)
        self.title("ZapTV Guide")
        self.geometry("900x560")
        self.minsize(640, 360)
        self.transient(master.winfo_toplevel())
        self.configure(bg=palette.bg)
        style_dialog(ttk.Style(self), palette)

        self._guide = guide
        self._channels = channels
        self._palette = palette
        self._on_play = on_play
        self._favorites = favorites
        #: Injectable so the tests do not depend on what is on air today.
        self._now = now
        self._sections: list[grid.Section] = []
        #: Flattened sections in drawing order — index is the y position.
        self._lines: list[grid.Line] = []
        #: The guide keeps its own collapsed set, deliberately separate
        #: from the channel list's: folding the list down to launch
        #: quickly should not empty the window you open to see what is on.
        self._config = config
        self._collapsed: set[str] = set(config.collapsed_guide_groups) if config else set()
        self._span = grid.DEFAULT_SPAN
        self._start = self._floor(self._clock())

        #: Rows the grid would show unfiltered — the denominator the footer
        #: reports against while a filter is active.
        self._total = len(grid.visible_channels(guide, channels, favorites))

        self._font = tkfont.nametofont("TkDefaultFont")
        self._build()
        self._reload()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 6), style="Zap.TFrame")
        toolbar.pack(fill=tk.X)
        for text, command in (("◀", self._page_back), ("Now", self._go_now), ("▶", self._page_on)):
            ttk.Button(
                toolbar,
                text=text,
                width=4,
                command=command,
                style="Zap.TButton",
                # Paging must not pull focus out of the filter box mid-typing.
                takefocus=False,
            ).pack(side=tk.LEFT, padx=(0, 4))
        self.window_label = ttk.Label(toolbar, style="Zap.TLabel")
        self.window_label.pack(side=tk.LEFT, padx=(10, 0))

        # Same filtering as the channel list, on the same search module, so
        # "malaga" finds "101TV Málaga" here too. 121 rows is a lot to scroll
        # when you know which channel you want.
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._on_query())
        self._filter = tk.Entry(
            toolbar,
            textvariable=self.query,
            width=18,
            bg=self._palette.field_bg,
            fg=self._palette.fg,
            insertbackground=self._palette.fg,
            highlightthickness=1,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.select_bg,
            relief=tk.FLAT,
        )
        self._filter.pack(side=tk.RIGHT)

        middle = tk.Frame(self, bg=self._palette.bg)
        middle.pack(fill=tk.BOTH, expand=True, padx=8)

        left = tk.Frame(middle, bg=self._palette.bg)
        left.pack(side=tk.LEFT, fill=tk.Y)
        # A blank corner keeps the channel names level with the rows once the
        # ruler has taken its height out of the column beside it.
        tk.Frame(left, height=GRID_RULER_HEIGHT, bg=self._palette.bg).pack(fill=tk.X)
        self.names = tk.Canvas(
            left,
            width=GRID_NAME_WIDTH,
            bg=self._palette.bg,
            highlightthickness=0,
        )
        self.names.pack(fill=tk.Y, expand=True)

        scrollbar = ttk.Scrollbar(middle, orient=tk.VERTICAL, command=self._yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right = tk.Frame(middle, bg=self._palette.bg)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.ruler = tk.Canvas(
            right,
            height=GRID_RULER_HEIGHT,
            bg=self._palette.bg,
            highlightthickness=0,
        )
        self.ruler.pack(fill=tk.X)
        self.slots = tk.Canvas(
            right,
            bg=self._palette.field_bg,
            highlightthickness=0,
            yscrollcommand=scrollbar.set,
        )
        self.slots.pack(fill=tk.BOTH, expand=True)

        self.detail = tk.Label(
            self,
            anchor="nw",
            justify=tk.LEFT,
            height=3,
            bg=self._palette.bg,
            fg=self._palette.muted,
        )
        self.detail.pack(fill=tk.X, padx=8, pady=(4, 0))

        self.footer = tk.Label(self, anchor="w", bg=self._palette.bg, fg=self._palette.muted)
        self.footer.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.slots.bind("<Configure>", lambda _e: self._draw())
        self.slots.bind("<Button-1>", self._on_click)
        self.names.bind("<Button-1>", self._toggle_section)
        self.slots.bind("<Double-Button-1>", self._on_activate)
        for canvas in (self.slots, self.names):
            # X11 reports the wheel as buttons 4 and 5, not <MouseWheel>.
            canvas.bind("<Button-4>", lambda _e: self._scroll(-1))
            canvas.bind("<Button-5>", lambda _e: self._scroll(1))
        # Bound on the toplevel, so they fire whatever has focus — including
        # the filter box, where Tk's own class binding has already moved the
        # caret by the time these run. Paging as well would make the arrow
        # keys unusable for editing, hence the guard in _typing.
        self.bind("<Left>", lambda _e: self._arrow(self._page_back))
        self.bind("<Right>", lambda _e: self._arrow(self._page_on))
        self.bind("<Control-f>", lambda _e: self.focus_filter())
        self.bind("<Escape>", lambda _e: self._on_escape())

    # -- time window -----------------------------------------------------

    def _clock(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    @staticmethod
    def _floor(moment: datetime) -> datetime:
        """Round down to the half hour, so the ruler lands on tidy labels."""
        return moment.replace(minute=moment.minute // 30 * 30, second=0, microsecond=0)

    @property
    def _end(self) -> datetime:
        return self._start + self._span

    def _typing(self) -> bool:
        """True when the filter box has focus, so arrows edit rather than page."""
        return self.focus_get() is self._filter

    def focus_filter(self, _event: object = None) -> str:
        self._filter.focus_set()
        self._filter.select_range(0, tk.END)
        return "break"

    def _on_escape(self) -> str:
        """Clear the filter if there is one, otherwise close.

        Matches the main window, where Escape clears the search rather than
        quitting, while keeping Escape as the way out of a window with
        nothing typed in it.
        """
        if self.query.get():
            self.query.set("")
            return "break"
        self.destroy()
        return "break"

    def _page_back(self) -> str:
        self._start -= grid.PAGE_STEP
        self._reload()
        return "break"

    def _page_on(self) -> str:
        self._start += grid.PAGE_STEP
        self._reload()
        return "break"

    def _arrow(self, page: Callable[[], str]) -> str:
        """Page on an arrow key, unless the filter box is being typed in.

        The guard belongs here and not in _page_back/_page_on, which the
        toolbar buttons also call: putting it there would make clicking ◀
        silently do nothing whenever the filter had focus.
        """
        if self._typing():
            return ""
        return page()

    def _go_now(self) -> str:
        self._start = self._floor(self._clock())
        self._reload()
        return "break"

    # -- drawing ---------------------------------------------------------

    def _on_query(self) -> None:
        """Rebuild for a new filter, and go back to the top.

        Without the scroll reset, filtering 121 rows down to three while
        scrolled near the bottom leaves the canvas showing empty space.
        """
        self._reload()
        self._yview("moveto", "0")

    def _reload(self) -> None:
        query = self.query.get()
        # A filter forces every section open, exactly as the channel list
        # does: matches hidden inside folded groups read as a failed search.
        self._sections = grid.build(
            self._guide,
            search.filter_channels(self._channels, query),
            self._start,
            self._end,
            self._favorites,
            frozenset() if query.strip() else self._collapsed,
        )
        self._lines = grid.lines(self._sections)
        local_start = self._start.astimezone()
        local_end = self._end.astimezone()
        self.window_label.config(text=f"{local_start:%a %d %b  %H:%M} – {local_end:%H:%M}")
        if query.strip():
            # Against the number of rows there could be, not the whole
            # playlist: "3 of 482" would suggest the filter had thrown away
            # channels that never had guide data to begin with.
            shown = sum(len(s.rows) for s in self._sections)
            self.footer.config(text=f"{shown} of {self._total} channels match")
        else:
            self.footer.config(
                text=f"{self._total} of {len(self._channels)} channels have guide data"
            )
        self._draw()

    def _draw(self) -> None:
        width = self.slots.winfo_width()
        # Before the window is mapped the canvas reports width 1; the
        # <Configure> that follows mapping draws it properly.
        if width <= 1:
            return

        self.slots.delete(tk.ALL)
        self.names.delete(tk.ALL)
        self.ruler.delete(tk.ALL)

        self._draw_ruler(width)
        for index, line in enumerate(self._lines):
            self._draw_line(index, line, width)
        self._draw_now_line(width)

        height = self._height()
        for canvas in (self.slots, self.names):
            canvas.config(scrollregion=(0, 0, width, height))

    def _draw_ruler(self, width: int) -> None:
        span = self._span.total_seconds()
        marker = self._start
        while marker <= self._end:
            frac = (marker - self._start).total_seconds() / span
            x = frac * width
            self.ruler.create_line(
                x, GRID_RULER_HEIGHT - 5, x, GRID_RULER_HEIGHT, fill=self._palette.border
            )
            if marker < self._end:
                self.ruler.create_text(
                    x + 3,
                    GRID_RULER_HEIGHT / 2,
                    text=f"{marker.astimezone():%H:%M}",
                    anchor="w",
                    fill=self._palette.muted,
                    font=self._font,
                )
            marker += timedelta(minutes=30)

    def _draw_line(self, index: int, line: grid.Line, width: int) -> None:
        if line.is_header:
            self._draw_header(index, line.section, width)
            return
        assert line.row is not None
        self._draw_row(index, line.row, width)

    def _draw_header(self, index: int, section: grid.Section, width: int) -> None:
        """A collapsible section heading, spanning both canvases.

        The band across the grid is what makes the header feel like one row
        rather than a label floating over the previous channel's programmes,
        and it doubles as the click target on that side.
        """
        top = index * ROW_HEIGHT
        arrow = "▶" if section.collapsed else "▼"
        count = len(section.rows)
        self.names.create_rectangle(
            0, top, GRID_NAME_WIDTH, top + ROW_HEIGHT,
            fill=self._palette.bg, outline="",
        )
        self.names.create_text(
            4,
            top + ROW_HEIGHT / 2,
            text=self._fit(f"{arrow} {section.label} ({count})", GRID_NAME_WIDTH - 8),
            anchor="w",
            fill=self._palette.muted,
            font=self._font,
        )
        self.slots.create_rectangle(
            0, top, width, top + ROW_HEIGHT,
            fill=self._palette.bg, outline="",
        )

    def _draw_row(self, index: int, row: grid.Row, width: int) -> None:
        top = index * ROW_HEIGHT
        favorite = self._favorites is not None and row.channel.name in self._favorites
        label = f"{_STAR} {row.channel.name}" if favorite else row.channel.name
        self.names.create_text(
            GRID_INDENT,
            top + ROW_HEIGHT / 2,
            text=self._fit(label, GRID_NAME_WIDTH - GRID_INDENT - 4),
            anchor="w",
            fill=self._palette.fg,
            font=self._font,
        )

        at = self._clock()
        for block in row.blocks:
            x0 = block.start_frac * width
            x1 = block.end_frac * width
            live = block.programme.is_live(at)
            self.slots.create_rectangle(
                x0,
                top + 1,
                x1 - 1,
                top + ROW_HEIGHT - 1,
                fill=self._palette.select_bg if live else self._palette.bg,
                outline=self._palette.border,
            )
            label = block.programme.title
            if block.clipped_left:
                label = f"‹ {label}"
            if block.clipped_right:
                label = f"{label} ›"
            room = x1 - x0 - GRID_BLOCK_PAD * 2
            text = self._fit(label, room)
            if text:
                self.slots.create_text(
                    x0 + GRID_BLOCK_PAD,
                    top + ROW_HEIGHT / 2,
                    text=text,
                    anchor="w",
                    fill=self._palette.select_fg if live else self._palette.fg,
                    font=self._font,
                )

    def _draw_now_line(self, width: int) -> None:
        at = self._clock()
        if not self._start <= at < self._end:
            return
        frac = (at - self._start).total_seconds() / self._span.total_seconds()
        x = frac * width
        height = self._height()
        self.slots.create_line(x, 0, x, height, fill=self._palette.fg, width=2)
        self.ruler.create_line(x, 0, x, GRID_RULER_HEIGHT, fill=self._palette.fg, width=2)

    def _fit(self, text: str, room: float) -> str:
        """Trim to what actually fits, measured rather than guessed at."""
        if room <= 0:
            return ""
        if self._font.measure(text) <= room:
            return text
        for size in range(len(text) - 1, 0, -1):
            candidate = f"{text[:size].rstrip()}…"
            if self._font.measure(candidate) <= room:
                return candidate
        return ""

    # -- interaction -----------------------------------------------------

    def _yview(self, *args: str) -> None:
        # One scrollbar drives both columns, or the names slide out of step
        # with the rows they label.
        self.names.yview(*args)
        self.slots.yview(*args)

    def _scroll(self, amount: int) -> str:
        self._yview("scroll", str(amount), "units")
        return "break"

    def _height(self) -> int:
        """Scrollable height, which is also what _draw sets as the region."""
        return max(len(self._lines) * ROW_HEIGHT, 1)

    def _canvas_y(self, event: "tk.Event[tk.Canvas]") -> float:
        """Pointer y in canvas coordinates rather than widget coordinates.

        The two differ once the grid has been scrolled. Canvas.canvasy would
        do this, but typeshed only started annotating it recently: a version
        new enough to type it rejects the ignore the older one needs, so the
        project cannot satisfy both. yview is typed either way, and since
        _draw sets the scrollregion itself the offset is exactly the first
        fraction times that height.

        x needs no conversion: time is paged rather than scrolled, so the
        canvas never moves horizontally.
        """
        return event.y + self.slots.yview()[0] * self._height()

    @property
    def rows(self) -> list[grid.Row]:
        """Channel rows currently drawn, without the section headings."""
        return [line.row for line in self._lines if line.row is not None]

    def _line_at(self, event: "tk.Event[tk.Canvas]") -> grid.Line | None:
        index = int(self._canvas_y(event) // ROW_HEIGHT)
        if not 0 <= index < len(self._lines):
            return None
        return self._lines[index]

    def _at(self, event: "tk.Event[tk.Canvas]") -> tuple[Channel, Programme] | None:
        """The channel and programme under the pointer, if any."""
        width = self.slots.winfo_width()
        line = self._line_at(event)
        if line is None or line.row is None or width <= 1:
            return None
        frac = event.x / width
        for block in line.row.blocks:
            if block.start_frac <= frac < block.end_frac:
                return line.row.channel, block.programme
        return None

    def _toggle_section(self, event: "tk.Event[tk.Canvas]") -> str:
        """Fold or unfold the section whose header was clicked.

        Both canvases route here, so the heading works whether it is clicked
        on the channel-name side or the band across the grid.
        """
        line = self._line_at(event)
        if line is None or not line.is_header:
            return ""
        label = line.section.label
        if label in self._collapsed:
            self._collapsed.discard(label)
        else:
            self._collapsed.add(label)
        self._save_collapsed()
        self._reload()
        return "break"

    def _save_collapsed(self) -> None:
        """Remember the fold state, unless a filter is forcing sections open.

        While filtering, every section is drawn open regardless; recording a
        toggle made in that state would rewrite the user's real choice.
        """
        if self._config is None or self.query.get().strip():
            return
        self._config.collapsed_guide_groups = sorted(self._collapsed)
        self._config.save()

    def _on_click(self, event: "tk.Event[tk.Canvas]") -> str:
        line = self._line_at(event)
        if line is not None and line.is_header:
            return self._toggle_section(event)

        found = self._at(event)
        if found is None:
            return "break"
        channel, programme = found
        local = programme.start.astimezone()
        when = f"{local:%H:%M}"
        if programme.end is not None:
            when = f"{when}–{programme.end.astimezone():%H:%M}"
        self.detail.config(
            text=f"{channel.name}  {when}  {programme.title}\n{clip(programme.description)}"
        )
        return "break"

    def _on_activate(self, event: "tk.Event[tk.Canvas]") -> str:
        """Double-click plays the channel, which is what the app is for."""
        found = self._at(event)
        if found is None:
            return "break"
        self._on_play(found[0])
        return "break"


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
        logo_store: logos_module.LogoSource | None = None,
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

        self._updates: queue.Queue[updates_module.Release | None] | None = None

        #: Treeview row id -> channel. Headers are absent, which is what makes
        #: them unselectable.
        self._rows: dict[str, Channel] = {}
        self._row_order: list[str] = []
        #: Treeview row id -> section label, for the collapsible headers.
        self._sections: dict[str, str] = {}
        self._collapsed: set[str] = set(self._config.collapsed_groups)
        #: True while _refresh is rebuilding, so the open/close events it
        #: causes are not mistaken for the user collapsing something.
        self._rebuilding = False

        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._refresh())

        self._build()
        self._refresh()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        self.style = ttk.Style()

        # Search box and Guide button share a row. The button exists purely
        # for discoverability: Ctrl+G opens the same window, but a shortcut
        # with nothing on screen to hint at it is a feature most users never
        # find, and SPEC.md asks for the app to be usable without reading
        # anything.
        self._top = tk.Frame(self)
        self._top.pack(fill=tk.X, pady=(0, 6))
        self._entry = tk.Entry(self._top, textvariable=self.query)
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.guide_button = ttk.Button(
            self._top,
            text="Guide",
            width=7,
            style="Zap.TButton",
            command=self.open_guide,
            # Focus stays where the user put it, so Enter still plays the
            # selected channel straight after a click here.
            takefocus=False,
        )
        self.guide_button.pack(side=tk.LEFT, padx=(6, 0))

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
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._on_section_toggled(False))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._on_section_toggled(True))
        # On the release, not the press: a menu posted on <Button-3> is still
        # under the pointer when the matching <ButtonRelease-3> arrives, and
        # Tk's own binding turns that release into an invoke of the active
        # entry. Posting on the release means there is none left to deliver.
        self.tree.bind("<ButtonRelease-3>", self._on_context_menu)
        self._entry.bind("<Return>", self._on_play)
        self._entry.bind("<Down>", self._focus_list)

        self.apply_palette(self._palette)

        # Whichever programme is "now" changes without any user action.
        self.after(GUIDE_TICK_MS, self._tick_guide)
        if self._config.check_updates:
            self._updates = updates_module.check_async(__version__)
            self.after(UPDATE_TICK_MS, self._tick_updates)
        if self._logos is not None:
            self.after(LOGO_TICK_MS, self._tick_logos)

    # -- theming ---------------------------------------------------------

    def apply_palette(self, palette: theme.Palette) -> None:
        self._palette = palette
        self.config(bg=palette.bg)
        self._top.config(bg=palette.bg)
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
        # After theme_use, never before: ttk keeps style settings per theme,
        # so configuring them first and then switching theme silently throws
        # the configuration away. The Guide button is ttk and ignores
        # widget-level colours, so without this it stays light grey in a
        # dark app.
        style_dialog(self.style, palette)
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
        self._player = resolve(config.player)
        self.apply_palette(theme.get(config.theme))
        self._refresh()

    # -- list building ---------------------------------------------------

    def _refresh(self) -> None:
        # Rebuilding the list loses the selection; favoriting or playing must
        # not throw the user back to the top of several hundred channels.
        previous = self.selected()
        self._rebuilding = True

        visible = search.filter_channels(self._channels, self.query.get())
        by_name = {c.name: c for c in visible}

        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        self._row_order.clear()
        self._sections.clear()

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
        self._rebuilding = False
        # Selecting from code does not fire <<TreeviewSelect>>.
        self._update_guide()

    def _add_section(self, label: str, channels: list[Channel]) -> None:
        # Channels are children of their section, which is what makes the
        # section collapsible at all. Headers stay out of _rows, so they
        # remain unselectable exactly as when everything was flat.
        #
        # A filter forces every section open: searching and being shown a
        # row of collapsed headers, with the matches hidden inside them,
        # would look like the search had failed. The saved state is not
        # touched, so clearing the filter restores what the user chose.
        section = self.tree.insert(
            "",
            tk.END,
            text=label,
            tags=("header",),
            open=bool(self.query.get().strip()) or label not in self._collapsed,
        )
        self._sections[section] = label
        for channel in channels:
            marker = f"{_STAR} " if channel.name in self._favorites else "   "
            item = self.tree.insert(
                section,
                tk.END,
                text=f"{marker}{channel.name}",
                image=self._image_for(channel),
                tags=("channel",),
            )
            self._rows[item] = channel
            self._row_order.append(item)

    # -- collapsing sections ---------------------------------------------

    def _on_section_toggled(self, collapsed: bool) -> None:
        """Record the user opening or closing a section, and remember it.

        Only user actions reach here with effect: _refresh sets `open` as it
        inserts, and Treeview.see opens ancestors to reveal a selection, both
        of which fire the same virtual events. Persisting those would let a
        redraw silently undo what the user chose.
        """
        if self._rebuilding:
            return
        item = self.tree.focus()
        label = self._sections.get(item)
        if label is None:
            return

        if collapsed:
            self._collapsed.add(label)
            self._hide_selection_inside(item)
        else:
            self._collapsed.discard(label)

        # A filter forces sections open for the duration; recording that as
        # intent would wipe the user's collapsed set the moment they typed.
        if self.query.get().strip():
            return
        self._config.collapsed_groups = sorted(self._collapsed)
        self._config.save()

    def _is_visible(self, item: str) -> bool:
        """True when every ancestor of a row is open, so the row is on screen."""
        parent = self.tree.parent(item)
        while parent:
            if not self.tree.item(parent, "open"):
                return False
            parent = self.tree.parent(parent)
        return True

    def _hide_selection_inside(self, section: str) -> None:
        """Move the selection out of a section the user just collapsed.

        Leaving it there would keep a channel selected that is no longer on
        screen, so Enter would play something invisible.
        """
        current = self.tree.selection()
        if not current or self.tree.parent(current[0]) != section:
            return
        for item in self._row_order:
            if self._is_visible(item):
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.tree.see(item)
                self._update_guide()
                return
        # Everything is collapsed: better nothing selected than a hidden
        # channel that Enter would play.
        self.tree.selection_remove(*current)
        self._update_guide()

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
            # around the selection stay in view — and only a row that is
            # actually on screen, because see() opens a row's ancestors and
            # would quietly re-expand a section the user had collapsed.
            for item in reversed(self._row_order):
                if self._rows[item] is previous and self._is_visible(item):
                    target = item
                    break

        restored = target is not None
        if target is None:
            target = next((i for i in self._row_order if self._is_visible(i)), None)
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

    # -- updates ---------------------------------------------------------

    def _tick_updates(self) -> None:
        """Report a newer release once, in the status bar.

        Deliberately quiet: no dialog, nothing to dismiss. Someone opening
        the app wants to watch television, not to be interrupted.
        """
        if self._updates is None:
            return
        try:
            release = self._updates.get_nowait()
        except queue.Empty:
            self.after(UPDATE_TICK_MS, self._tick_updates)
            return

        self._updates = None
        if release is not None:
            self.status.config(text=f"ZapTV {release.version} is available — {release.url}")

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
        self._play(channel, self._player_for(channel))
        return "break"

    def _on_context_menu(self, event: "tk.Event[ttk.Treeview]") -> str:
        """Offer the other players for this one channel."""
        row = self.tree.identify_row(event.y)
        if row not in self._rows:
            return "break"
        self.tree.selection_set(row)
        channel = self._rows[row]

        # tk.Menu is a classic widget: it takes colours directly, and without
        # them it renders light grey over a dark app.
        #
        # The border must not be zero. tk_popup puts the menu's top-left corner
        # exactly on the pointer, so with no border the pointer lands inside
        # the first entry, which Tk then activates on <Enter>. A flat one-pixel
        # border is drawn in the menu's own background — invisible, but enough
        # that "@0,0" resolves to no entry at all.
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=self._palette.field_bg,
            fg=self._palette.fg,
            activebackground=self._palette.select_bg,
            activeforeground=self._palette.select_fg,
            disabledforeground=self._palette.muted,
            borderwidth=1,
            relief=tk.FLAT,
        )
        for name in PLAYERS:
            backend = get_player(name)
            label = f"Play with {backend.label}"
            menu.add_command(
                label=label if backend.is_available() else f"{label} (not installed)",
                state=tk.NORMAL if backend.is_available() else tk.DISABLED,
                command=self._play_command(channel, name),
            )
        # The grab tk_popup takes is what makes the menu dismissable: a click
        # outside only reaches it while it holds one, and Tk hands the grab back
        # itself when it unposts. Releasing it here — the idiom the Tkinter docs
        # give, written for the platforms where tk_popup blocks until the menu
        # closes — leaves a menu on X11 that a click cannot close. Until the
        # first entry stopped firing on the opening click, which unposted the
        # menu immediately, that was invisible. It is released only if posting
        # failed, so a half-posted menu cannot leave the pointer grabbed.
        try:
            menu.tk_popup(event.x_root, event.y_root)
        except tk.TclError:
            menu.grab_release()
        return "break"

    def _play_command(self, channel: Channel, player_name: str) -> Callable[[], None]:
        """Bind a menu entry to one channel and one player."""

        def command() -> None:
            self._play(channel, get_player(player_name))

        return command

    def _play(self, channel: Channel, player: Player) -> None:
        """Hand a channel to a player and record that it was watched."""
        try:
            player.play(channel.stream)
        except PlayerNotFound as exc:
            messagebox.showerror("Player not found", str(exc), parent=self)
            return
        self._recent.push(channel.name)
        self._refresh()

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

    def open_guide(self, _event: object = None) -> str:
        """The whole schedule, over the guide already loaded here."""
        GuideWindow(
            self,
            self._guide,
            self._channels,
            self._palette,
            lambda channel: self._play(channel, self._player_for(channel)),
            self._favorites,
            self._config,
        )
        return "break"

    def open_providers(self, _event: object = None) -> str:
        if self._sources is None:
            return "break"
        ProvidersWindow(self, self._sources, self._palette, self._reload_channels)
        return "break"

    def _reload_channels(self, force: bool = False) -> None:
        """Re-read channels from the configured providers.

        Keeps the current list when every source fails, so a dropped network
        never empties the window.
        """
        if self._sources is None:
            return

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

    def reload(self, _event: object = None) -> str:
        """Force a refresh of every playlist and the guide."""
        self._reload_channels(force=True)

        # The guide is optional: a failure here should not spoil a successful
        # playlist refresh, so it is reported only in the status line.
        # download_epgs keeps whatever succeeded rather than raising, so an
        # empty list — not an exception — is what "no guide at all" looks
        # like. One source failing while another works is silent on purpose:
        # the user loses some channels' listings, not the feature.
        paths = updater.download_epgs()
        self._guide = epg_module.load_all(paths)
        self._update_guide()
        if not paths:
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
    chosen = resolve(config.player)
    browser = ChannelBrowser(
        root,
        channels,
        chosen,
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
    root.bind("<Control-g>", browser.open_guide)
    root.bind("<Escape>", browser.clear_search)
    root.bind("<Control-q>", lambda _e: root.destroy())

    # Say so up front rather than letting the first Enter fail.
    if chosen.command != get_player(config.player).command:
        browser.status.config(
            text=f"{config.player} is not installed — using {chosen.label}"
        )

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
