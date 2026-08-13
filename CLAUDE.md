# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Milestones 1–8 are done: download → parse → browse → play, settings, search, favorites, recently-watched, a Now/Next guide from XMLTV, channel logos, light/dark themes, a settings window, an app icon, and multiple playlist providers with merging.

A `BrowserPlayer` backend and a "Web channels" playlist are how the Atresmedia and Mediaset channels appear.

Much of Milestone 6 was already delivered incrementally — the VLC and mpv backends, selection in the settings window, and `is_available` detection all predate it. What it added was **resolution** (`player.resolve`), a per-channel *Play with…* menu, and `--players`.

**Not** done: Pluto TV is not bundled as a named provider (Milestone 5) — addable by URL, but no built-in entry. Milestone 7's "automatic updates" ships as a **check only** (`updates.py`): it reports a newer release, it does not download or replace anything, because a `.deb` updates through apt and an AppImage by replacing the file.

Note the git repo is named `zapper` but the project is **ZapTV** (`zaptv`) — the rename happened after the repo was created.

## Documents

Three specs, and they do not fully agree — `STACK.md` and `ROADMAP.md` are newer and win:

- `SPEC.md` — product spec: UX, features, non-goals, philosophy. (Originally `zapper.md`.)
- `STACK.md` — authoritative technology decisions and repository layout.
- `ROADMAP.md` — 8 milestones. Note it renumbers `SPEC.md`'s v0.1–v1.0 scheme; use milestones.

## Commands

```bash
PYTHONPATH=src python3 -m zaptv                    # run the GUI
PYTHONPATH=src python3 -m zaptv --list             # channels as TSV (no GUI needed)
PYTHONPATH=src python3 -m zaptv --search malaga    # same, filtered
PYTHONPATH=src python3 -m zaptv --now              # Now/Next per channel
PYTHONPATH=src python3 -m zaptv --providers        # configured playlist sources
PYTHONPATH=src python3 -m zaptv --players          # which player backends are installed
PYTHONPATH=src python3 -m zaptv --player mpv       # override the configured player

packaging/build-deb.sh                             # -> dist/zaptv_<v>_all.deb
packaging/build-appimage.sh                        # -> dist/ZapTV-<v>-x86_64.AppImage
packaging/install-user.sh [--uninstall]            # rootless install from a checkout
python3 -m pytest tests -q                         # tests
python3 -m ruff check src tests                    # lint
python3 -m mypy                                    # type check (config in pyproject)
```

`--list`/`--search` exercise the download, parse and filter paths without a display or Tkinter — use them to verify changes there. The leading `*` column marks favorites.

Installed (`pip install -e .`) the entry point is `zaptv`.

## Architectural constraints

These come from `SPEC.md`/`STACK.md`; don't relitigate them without the user asking.

- **Near-zero runtime dependencies.** M3U parsing is hand-rolled, EPG uses stdlib `gzip` + `xml.etree.ElementTree`, networking is `urllib.request` (not requests/curl/wget), storage is plain JSON. **Pillow is the one deliberate exception**, agreed for Milestone 4: nearly every channel logo is JPEG and Tk's `PhotoImage` reads only PNG/GIF, so there is no stdlib path to logos. Don't add a second dependency without asking. Dev tooling (pytest/ruff/mypy) doesn't count.
- **No video playback in-process, ever.** Players live behind the `Player` ABC in `player.py`; a new backend is a new subclass plus a `PLAYERS` entry. `VLCPlayer` is the default, `MPVPlayer` exists for Milestone 6, `BrowserPlayer` handles channels whose "stream" is a web page. `PLAYERS` is every backend; `SELECTABLE` is the subset a user may pick as their default — the browser is chosen per channel only.
- **`get_player` vs `resolve`.** `get_player(name)` guards only against an unknown *name*; a configured player that has since been uninstalled would still be returned and fail the moment the user pressed Enter. `resolve(name)` substitutes an installed backend at startup and the UI reports the substitution in the status bar. Use `resolve` for the default player, `get_player` when the caller has already decided (a channel's own `player`, a *Play with…* entry). `resolve` never substitutes the browser, since it is not in `SELECTABLE`.
- **Never work around DRM or extract protected streams.** Where a broadcaster publishes no open stream, ZapTV opens the official live page in a browser. That is the whole approach; scraping session-bound stream URLs is both out of bounds and unmaintainable.
- **Channels are never hardcoded or shipped.** Playlists are always downloaded (or read from a user's file) at runtime.
- **The built-in TDTChannels provider can be disabled but never deleted.** Removing it by accident would leave a new user with an empty app and no route back; `ProviderList.load` re-inserts it if a config file lacks it.
- **Not a media center.** No library, movies, series, music, PVR, torrents, streaming server, accounts, or cloud sync. `ROADMAP.md` lists these as explicitly out of scope.

## UI conventions

`ui.py` holds only widget wiring; matching and ordering live in `search.py` so they can be tested without a display.

The list is a **`ttk.Treeview`**, not a `Listbox` — only Treeview supports a per-row image, which channel logos need. Section headers are Treeview rows *absent from `_rows`*, which is exactly what makes them unselectable: `selected()` returns `None` for them.

- The list is rebuilt from scratch on every keystroke, favorite toggle, and play. `_refresh` therefore saves and restores the selection; without that, favoriting throws the user back to the top of ~471 channels.
- **`see()` on an unmapped widget scrolls its target to the very top**, hiding the section header above it — the list then looks unlabelled at startup. `_restore_selection` uses `yview_moveto(0)` when nothing carried over (startup, or a search that dropped the selection) and only calls `see()` when genuinely restoring a selection, by which point the widget is mapped. `after_idle` does *not* fix this: idle callbacks run before the window is mapped.
- A favorited channel appears **twice** — once under `★ FAVORITES`, once in its group. `_restore_selection` scans `_row_order` in reverse so selection lands on the group copy, keeping neighbours in view.
- Something is always selected, so Enter plays straight after typing a search without an arrow key in between.
- Search is accent-insensitive in both directions (`malaga` ↔ `Málaga`) because Spanish channel names are full of accents users don't type. Tokens are ANDed.
- **Logo URLs are shared between channels** — one Facebook logo covers 16 regional channels, and 471 channels resolve to 360 distinct logos. `_tick_logos` therefore tests whether *the row* already has an image, never whether the URL is in `_images`; keying off the image cache fills only the first row of each shared group and silently leaves the rest blank.
- Tk images must be built on the main thread and kept referenced (`_images`), or they are garbage collected straight off the rows. `LogoStore` workers only write files; the UI collects them via `drain()`.
- **The *Play with…* menu is posted on `<ButtonRelease-3>`, keeps its grab, and must never have `borderwidth=0`.** All three guard one bug: `tk_popup` puts the menu's top-left corner on the pointer, so with no border `index @0,0` is entry 0, Tk's `<Enter>` handler activates it, and the release of the very click that opened the menu hits `bind Menu <ButtonRelease>` and plays the channel with VLC. Posting on the release leaves no such release to deliver; a flat one-pixel border (invisible — drawn in the menu's own background) keeps the pointer out of entry 0. Releasing the grab, as the Tkinter docs' `finally: grab_release()` idiom does, is only right where `tk_popup` blocks until the menu closes; on X11 it leaves a menu an outside click cannot close (measured: stuck 4 times out of 4). Tk hands the grab back itself on unpost.

  This is where a screenshot cannot help: the menu is a separate override-redirect X window, so `xwd -id <app>` never contains it, and `xwd` on the menu itself fails `BadMatch` under XWayland. `xwininfo -root -tree | grep '"!menu"'` shows whether it is posted and where. Driving it needs real pointer events — there is no `xdotool` here, but `libXtst` takes `XTestFakeMotionEvent`/`XTestFakeButtonEvent` through `ctypes`. Verify against a window that has been `focus_force`ed: XTEST key events go to whatever holds focus, so testing an unfocused window makes Escape look broken and a stale grab-holding menu swallows later clicks. Both misled this investigation before the controlled run corrected it.

  **Never assert menu dismissal by generating `<Escape>`.** Tk delivers a synthetic key to whatever holds *focus*, and a bare X server has no window manager to give anything focus, so under Xvfb the event never reaches the menu, no binding fires, and a perfectly healthy menu reads as stuck — two red CI runs went that way. `tk focus` is `''` there and `.` on a real desktop; `Priv(popup)` still names the menu and `unpost()` works fine. Call `root.tk.call("tk::MenuEscape", menu)` instead: it needs no focus and behaves identically on Xvfb and a real desktop. `focus_force()` does not rescue the key — it moves focus to the toplevel, so the menu stops receiving it on *both*.

Theming lives in `theme.py`. ttk ignores widget-level colour options, so the Treeview and the settings dialog need configured *styles* (`style_dialog`), and the `clam` theme is used because the default Linux ttk theme ignores Treeview background settings entirely.

Shortcuts follow `SPEC.md`: Enter plays, `Ctrl+F` focuses search, `F` favorites, `Ctrl+R` forces a playlist and guide update, `Esc` clears the search, `Ctrl+,` opens settings, `Ctrl+P` opens the playlist sources window, `Ctrl+G` opens the guide grid. **`Esc` no longer quits** — `Ctrl+Q` does.

## The guide grid

`Ctrl+G` opens `GuideWindow`: the whole schedule at once, one row per channel. It is a view over the `Guide` already loaded in `ChannelBrowser` — it downloads nothing, caches nothing and touches no parsing.

- **`grid.py` holds the layout, `ui.py` only draws it**, the same split `search.py` makes for matching. `grid.build` returns positions as **fractions of the visible window**, never pixels, so the canvas width is the UI's business and every layout test is arithmetic with no display.
- **Time is paged, not scrolled horizontally.** `◀`/`▶` move an hour; the window spans three. This is why only the visible window is ever drawn — measured at ~1,060 canvas items against the 11,180 programmes the feed carries. It also means the canvas never scrolls in x, so click handling uses `event.x` directly and needs `canvasy` only for y.
- **A tvg-id shared by several channels must draw one row, not several.** 15 ids in the live playlist are shared — `Teledeporte`/`Teledeporte GEO`, three copies of `3CatInfo`, `EnerGeek Retro HD`/`SD` — and each copy would otherwise repeat an identical row. `visible_channels` keeps the alphabetically first name, which in every sampled case is the plain one rather than the GEO, SD or EN variant.
- **A channel with guide data but nothing in the current window keeps an empty row.** Dropping it would reflow the rows as the user pages through time, and a grid whose channels move under the pointer is worse than one with a gap.
- Two canvases (names, slots) share one scrollbar through `_yview`; only `slots` reports back to the scrollbar, or the two feed each other. The names column sits under a blank spacer the height of the ruler so the labels stay level with their rows.
- `Guide.between` is the query behind it: programmes *overlapping* a window, stepping back one from the bisect so the programme already on air occupies the left edge instead of vanishing.
- **`_canvas_y` converts window y to canvas y by hand, and must not use `Canvas.canvasy`.** This is a second local-vs-CI stub gap, and it runs the *opposite* way to the Pillow one: typeshed only recently annotated `canvasy`, so the pinned local mypy (1.18.2) demands `type: ignore[no-untyped-call]` while CI's newer mypy rejects that same ignore as `unused-ignore`. No single annotation satisfies both — one red CI run went that way. `yview()` is typed in both, and `_draw` sets the scrollregion itself, so the offset is just `yview()[0] * height`. `tests/test_guide_window.py` pins the arithmetic against Tk's real `canvasy` at a scrolled position, which tests *may* call because mypy relaxes `disallow_untyped_calls` for `tests.*`.

## Providers

`providers.py` owns playlist sources. A provider is a name plus an M3U source — an http(s) URL to download or a local file to read (`is_local` covers bare paths and `file://`).

- **Each provider caches separately**, in `playlists/<slug>.m3u`, so one unreachable source never invalidates another's channels.
- **Failures are reported, not swallowed.** `load_channels` returns `(channels, failed_names)`; the UI puts the failing names in the status bar rather than silently showing a shorter list. An empty playlist counts as a failure.
- **Merging happens on `(name, group)`** — the same key `playlist.parse` uses for mirrors within one file. A second source offering the same channel contributes another stream rather than a duplicate row, and the *first* provider to supply a channel owns its metadata, so provider order is preference order. Gaps (missing `tvg_id`/`logo`) are filled from later sources without overwriting.
- `migrate_legacy_cache` moves the pre-Milestone-5 `playlist.m3u` into the built-in's per-provider cache, so upgrading doesn't force a re-download.

This is the machinery the Atresmedia/Mediaset note under Milestone 5 refers to: pointing ZapTV at a list carrying working URLs for those channels works end to end (verified with a local M3U adding Antena 3).

## Web channels

`webchannels.py` solves the Atresmedia/Mediaset gap. Those broadcasters publish no open stream, so their channels list the **official live page** as the stream and carry a non-standard `zaptv-player="browser"` attribute; `playlist.parse` reads it into `Channel.player`, and `ChannelBrowser._player_for` lets a channel's own player override the configured default. Other M3U readers ignore the unknown attribute.

Two things to know before changing it:

- **The seed list is written into the user's config, not shipped in the package.** `install()` writes `~/.config/zaptv/web-channels.m3u` once and registers it as an ordinary local provider; after that it is the user's file to edit or delete. This is a deliberate reading of the "channels are never shipped" rule — nothing is baked in at runtime, and the seed is only a starting point. `install()` is a no-op if either the file exists or the provider is registered, so a user who removes it does not get it back silently.
- **Page URLs are stable brand addresses**, unlike session-bound stream URLs, which is why this survives where a scraped playlist rots. All 13 were verified to return 200; `mitele.es` now redirects to `mediasetinfinity.es`, so the canonical URLs are stored.

### Mirror failover was considered and rejected

75 of 471 channels carry more than one mirror (up to 9), and only `streams[0]` is ever played. Automatic failover was measured against the live playlist before building it: 13 of 14 sampled first mirrors returned 200, and the one failure (ETB Deportes) returned 403 on *every* mirror — geo-blocking, which failover cannot fix. A pre-flight probe would have added 0.1–1.4s to every play for almost no benefit. Don't add it without new evidence; a manual "next mirror" action would be the better shape if this comes up again.

All 13 web channels now show Now/Next, but their ids come from **two different feeds**. Mediaset's are TDTChannels' (`Telecinco.TV`, `Cuatro.TV`, `FDF.TV`, `Energy.TV`, `Divinity.TV`, `Boing.TV`, `Bemad.TV`). Atresmedia is absent from that feed entirely, so `Antena.3.es`, `laSexta.es`, `Neox.es`, `Nova.es`, `Mega.es` and `Atreseries.es` come from the second source in `updater.EPG_SOURCES`. The two feeds share no ids at all, so mixing them in one seed file is unambiguous.

`upgrade_seed` exists because those six shipped with **no** id: `install()` is a no-op once the file exists, so without it an existing user would never gain the data. It rewrites a line only when that line still matches byte-for-byte what ZapTV wrote — the file is the user's, and an edited line keeps no guide rather than being silently rewritten.

## Quality gates

All three pass; keep them passing.

- **ruff** — `line-length = 100`, rules `E,F,I,UP,B,SIM`. One deliberate `noqa`: `epg._open` returns an open handle by design (SIM115), because callers close it with `with`.
- **mypy** — `strict`, over `src` *and* `tests`. Two overrides in `pyproject.toml`: Pillow needs `ignore_missing_imports` *locally*, and tests relax `disallow_untyped_defs`/`incomplete_defs`/`untyped_calls` because annotating every fake adds noise without catching bugs. Everything else stays strict.
  - `tests/` is a package (`tests/__init__.py`) purely so the mypy override can name `tests.*`; mypy rejects partial-component patterns like `test_*`.
  - **Local mypy is weaker than CI here.** This machine's apt `python3-pil` has no `py.typed`, so the override makes mypy skip PIL analysis entirely; CI installs Pillow from pip, which *does* ship type information, and checks every PIL call. CI pins it via `PILLOW_VERSION` in `ci.yml` — currently 12.3.0 — so **bumping that pin is the only way new Pillow stubs ever get exercised**; leaving it stale hides type errors that nothing else can catch. `pyproject.toml` deliberately keeps the loose `pillow>=10`, because the `.deb` depends on the distro's `python3-pil` and pinning a desktop app's runtime dependency to one release would be wrong.
  - **A pinned Pillow is not a cure for the 3.13 abort.** One CI run died with a bare `Fatal Python error: Aborted` inside `PIL.Image.preinit` while `test_logos.py` saved a JPEG, and the identical commit passed on re-run — both on 12.3.0, so it is a race in Pillow's *lazy* plugin registration, not a bad release. `logos.LogoStore` runs daemon worker threads that call PIL while the main thread does too, which is exactly the shape that triggers it. If it recurs, the fix is to force registration once at import (`PIL.Image.preinit()`) before any worker starts, not another pin. A green local mypy is therefore not proof — CI caught two real errors in `logos.convert` this way (`convert()` returns `Image`, not `ImageFile`, and `Image.LANCZOS` is a legacy alias the stubs do not declare; use `Image.Resampling.LANCZOS`). To reproduce CI locally, unzip a Pillow wheel and point `MYPYPATH` at it, then read only the `src/`- and `tests/`-prefixed errors.
  - `logos.LogoSource` is a `Protocol` covering just `path_for`/`drain`. `ChannelBrowser` takes that rather than `LogoStore`, so test doubles satisfy it structurally instead of needing a cast.
- **pytest** — 189 unit tests, plus 5 integration tests that are **off unless `ZAPTV_INTEGRATION=1`**. (Those five gate with `if not ENABLED: return` inside each body rather than a skip marker, so a normal run reports 194 passed and no skips — they are off, but the count gives no sign of it.) Those hit the live feeds and assert loose bounds (≥250 channels, ≥1000 programmes, playlist and guide still share tvg-ids, broadcaster pages still 200). They exist to catch the feed changing shape, which no unit test can. CI runs them weekly and on demand, never on a PR.

**Tests must not depend on what is installed.** Anything touching a player patches `shutil.which` rather than assuming VLC or `xdg-open` exists — CI runners have neither. To check, run the suite with `shutil.which` stubbed to return `None` for `vlc`, `mpv` and `xdg-open`.

Display-dependent tests skip rather than fail when there is no `DISPLAY`, so headless runs stay green; CI runs the suite twice, once under `xvfb-run` and once without, so the GUI tests cannot silently stop running.

## Update check

`updates.py` asks the GitHub releases API whether a newer tag exists. It **checks and reports; it never updates**. Deliberate properties:

- **Every failure is silent.** No network, an outage, a rate limit, or the repo being private all produce `None` and no message. A version check is the least important thing the app does and must never interrupt watching TV.
- **Cached for 24h** in `~/.local/share/zaptv/update-check.json`, so launching repeatedly is not a request to GitHub each time.
- **Runs on a daemon thread** and reports through a queue the UI polls, so startup never waits on GitHub and quitting is never blocked by a hung request.
- **Reported in the status bar, once.** No dialog, nothing to dismiss.
- Controlled by `Settings.check_updates` (default on), toggleable in the settings window. `--check-updates` runs it from the CLI.
- An unparseable or lower tag is never "newer", so a malformed release cannot nag users.

**The repository is public**, which this feature needs: the unauthenticated releases API returns 404 for a private repo, so the check silently did nothing until the visibility changed. `gh api` masked this during development because it authenticates as the user.

## Packaging

`packaging/` holds three routes, all verified to build and run here:

- **`build-deb.sh`** — plain `dpkg-deb` over a staged tree, not `dpkg-buildpackage`. The package is pure Python with nothing to compile, so a control file says everything debhelper would. Payload lands in `/usr/lib/python3/dist-packages/zaptv`, with a launcher at `/usr/bin/zaptv`, the desktop entry, and eight hicolor icon sizes. `postrm` needs its own script — it receives `remove`/`purge`, never `configure`, so a copy of `postinst` silently does nothing on uninstall.
- **`install-user.sh`** — rootless. The launcher *points back at the checkout* rather than copying it, so a `git pull` updates the installed app. The desktop entry's `Exec` is rewritten to an absolute path, because a desktop session does not inherit a shell `PATH`.
- **`build-appimage.sh`** — fetches `appimagetool` and **extracts** it rather than running it, since AppImages need FUSE that many systems and every container lack. The result is a *thin* AppImage: ZapTV travels with it, but Python, Tkinter and Pillow come from the host, and `AppRun` names whichever is missing. Bundling a real interpreter would mean building on a `python-appimage` base — a much larger job, deliberately not attempted.

`.desktop` uses `StartupWMClass=Tk`, matching the WM_CLASS Tk actually sets (`("tk" "Tk")`). `build/` and `dist/` are gitignored.

## Paths

XDG-split, and both honor their env vars:

- Cache (disposable): `~/.local/share/zaptv/` — `playlists/<slug>.m3u` (one per provider), `epg-<slug>.xml.gz` (one per EPG source), `logos/`. Playlists and guides refresh when >24h old; logos are cached forever under a hash of their URL plus the render size. `migrate_legacy_epg` renames the pre-multi-source `epg.xml.gz` to `epg-tdtchannels.xml.gz`, so upgrading does not force a re-download.
- Config (user intent): `~/.config/zaptv/` — `settings.json`, `providers.json`, `favorites.json`, `recent.json`.

Favorites and recents are keyed by **channel name**, not `(name, group)`, matching the flat JSON list in `SPEC.md`. That keeps a favorite alive when a channel changes group in an updated playlist; the cost is that two channels sharing a name across groups are favorited together. All three JSON files fall back to defaults rather than raising when corrupt — a bad config file must never stop playback.

## What the real playlist looks like

Verified against the live TDTChannels list — these shaped the parser and will bite anyone assuming the spec's simpler model:

- **Channels repeat.** 586 `#EXTINF` entries collapse to ~471 channels; a channel is listed once per mirror. `Channel.streams` is a **list**; `Channel.stream` is the first (preferred) mirror. Parse without merging and "La 1" shows up three times.
- **`tvg-id` is mostly absent** — ~2/3 of entries have none, and it's shared across unrelated variants where present. It is *not* a usable identity key; channels are keyed by `(name, group)`.
- **Attribute values contain commas** (logo URLs like `w_200,h_200`), so the display name can't be recovered by splitting the line on `,`. `playlist._parse_extinf` strips quoted attributes first, then reads the name from the remainder.
- Groups are regional/thematic Spanish labels (`Generalistas`, `Andalucía`, `Musicales`, …), ~30 of them.

`tests/test_playlist.py` pins each of these.

## What the real guide looks like

The XMLTV feed is well-formed — all timestamps 14-digit and `+0000`, no missing stop times or titles, ~11k programmes over ~3.5 days, 52 ms to parse — so the parser's tolerance is about surviving a bad *download*, not bad data.

The coverage gap is the thing to design around: **137 of 482 channels have guide data** (~28%; 126 of 471 when first measured, 115 of 482 before the second EPG source — the feeds drift, so re-measure rather than trusting the figure). Mind the unit when comparing: that is a count of *channels*, and 15 tvg-ids are shared by more than one channel, so it is only **121 unique ids** — which is why the grid draws 121 rows, not 137. The playlist mostly lacks `tvg-id`, which is the only join key.

**Guide data comes from more than one XMLTV feed.** `updater.EPG_SOURCES` lists them in preference order and each caches separately, so one being unreachable costs only its own channels — the rule `providers.py` already applies to playlists. `epg.load_all` merges them, and **the first source to carry a channel id owns it**: two feeds' programmes are never interleaved for one channel, because two overlapping schedules would show a channel apparently airing two things at once. Measured when added: the two feeds shared 0 ids out of 170 and 373, so nothing is being silently shadowed, and the second contributes exactly the six Atresmedia channels and nothing else. So "no guide" is the *majority* case and is rendered as a quiet line in the pane, never an error. Every `Guide` lookup returns `None`/empty rather than raising, and a missing or corrupt cache yields an empty `Guide`.

61 XMLTV channel ids have programmes but no playlist channel — Atresmedia and Mediaset (`Cuatro.TV`, `Telecinco.TV`, `Bemad.TV`, …) among them. They have guide data but no stream, because those broadcasters gate live playback behind their own platforms (Atresplayer, Mitele). This is a known gap, scheduled under **Milestone 5**, and it is not a parser bug — don't try to fix it in `playlist.py`.

Two halves to it, worth keeping apart:

- Milestone 5 supplies the *plumbing* — provider abstraction, custom M3U, merging sources into one list. If a third-party list carrying working URLs exists, that machinery is enough.
- If no such list exists, the channels need a **different playback mechanism**: launching the broadcaster's web player instead of VLC. That is a player backend, closer to Milestone 6, which currently names only VLC and MPV.

## Environment gotchas

- **No `pip` and no `venv` on this machine** — `sudo apt install python3-venv` fixes it properly. Until then the toolchain can still be run without installing anything: ruff ships a standalone binary, and pytest and mypy publish pure-Python wheels that can be unzipped onto `PYTHONPATH`.

  ```bash
  # ruff: static binary from GitHub releases
  curl -fsSL -o ruff.tar.gz \
    https://github.com/astral-sh/ruff/releases/latest/download/ruff-x86_64-unknown-linux-gnu.tar.gz
  # pytest: pytest, pluggy, iniconfig, packaging
  # mypy:   mypy (1.x — 2.x needs the compiled librt), mypy_extensions,
  #         typing_extensions, pathspec, tomli
  # unzip each -py3-none-any.whl into one directory, then:
  PYTHONPATH=<that dir>:src python3 -m pytest tests -q
  ```

  Run mypy **from the repository root** or it will not find `[tool.mypy]` in `pyproject.toml` and will exit with "Missing target module".

  Note the mypy pin drifts: 1.20 already imports the compiled `librt`, so "1.x" is no longer enough — 1.18.2 is the newest that still runs pure-Python. Check with `python3 -c "import mypy.build"` before trusting a version.
- Tkinter **is** installed (Tk 8.6) and the session is Wayland with XWayland on `:0`, so the GUI runs.
- **Xvfb is not installed, and CI runs the GUI suite under it.** That gap is worth closing before trusting a GUI test, because a bare X server has no window manager and Tk behaves differently — it cost two red CI runs here. `sudo apt install xvfb` needs a password, but Xvfb runs perfectly well extracted, the same trick as the Python toolchain:

  ```bash
  apt-get download xvfb xserver-common x11-xkb-utils xkb-data libxfont2 libpixman-1-0 libunwind8
  for d in *.deb; do dpkg -x "$d" root; done
  LD_LIBRARY_PATH=root/usr/lib/x86_64-linux-gnu \
    root/usr/bin/Xvfb :99 -screen 0 1280x1024x24 -xkbdir root/usr/share/X11/xkb &
  DISPLAY=:99 <toolchain> python3 -m pytest tests -q       # what CI actually runs
  ```

  Run the GUI suite on **both** `:0` and `:99`; a green `:0` is not evidence about CI.

VLC is present at `/usr/bin/vlc`; mpv is not installed.

To inspect the GUI without a screenshot tool (only `xwd` and `xwininfo` are available, and `xwd -root` fails under XWayland):

```bash
DISPLAY=:0 xwininfo -root -tree | grep '"Tk")'    # find the window id (field 1)
DISPLAY=:0 xwd -id <id> -silent -out win.xwd      # capture that window, not the root
```

`xwd` output needs converting — PIL is available but has no XWD reader, so parse the big-endian header and build the image from `raw`/`BGRX`. Two traps in that header, both of which produced `cannot decode image data` here: the field list has **`bits_per_pixel` between `bitmap_pad` and `bytes_per_line`**, so counting fields by eye puts every later index one out (`bytes_per_line` is `h[12]`, `ncolors` is `h[19]`); and **`header_size` is not 100** — the window name is appended to it, so a "ZapTV Guide" capture reports 112. Pixel data starts at `header_size + ncolors * 12`; check that against the file length before decoding. Beware: `grep -oP '0x[0-9a-f]+'` on the `xwininfo` line matches `0x640` inside the geometry `420x640`; take field 1 instead. Multiple instances appear as `("tk" "Tk")`, `("tk #2" "Tk")`.
