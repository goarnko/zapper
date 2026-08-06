# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Milestones 1–5 are done: download → parse → browse → play, settings, search, favorites, recently-watched, a Now/Next guide from XMLTV, channel logos, light/dark themes, a settings window, an app icon, and multiple playlist providers with merging.

**Not** done in Milestone 5: Pluto TV is not bundled as a named provider. Users can add its M3U by URL, but there is no built-in entry for it.

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
python3 -m pytest tests -q                         # tests
python3 -m ruff check src tests                    # lint
python3 -m mypy                                    # type check (config in pyproject)
```

`--list`/`--search` exercise the download, parse and filter paths without a display or Tkinter — use them to verify changes there. The leading `*` column marks favorites.

Installed (`pip install -e .`) the entry point is `zaptv`.

## Architectural constraints

These come from `SPEC.md`/`STACK.md`; don't relitigate them without the user asking.

- **Near-zero runtime dependencies.** M3U parsing is hand-rolled, EPG uses stdlib `gzip` + `xml.etree.ElementTree`, networking is `urllib.request` (not requests/curl/wget), storage is plain JSON. **Pillow is the one deliberate exception**, agreed for Milestone 4: nearly every channel logo is JPEG and Tk's `PhotoImage` reads only PNG/GIF, so there is no stdlib path to logos. Don't add a second dependency without asking. Dev tooling (pytest/ruff/mypy) doesn't count.
- **No video playback in-process, ever.** Players live behind the `Player` ABC in `player.py`; a new backend is a new subclass plus a `PLAYERS` entry. `VLCPlayer` is the default, `MPVPlayer` exists for Milestone 6.
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

Theming lives in `theme.py`. ttk ignores widget-level colour options, so the Treeview and the settings dialog need configured *styles* (`style_dialog`), and the `clam` theme is used because the default Linux ttk theme ignores Treeview background settings entirely.

Shortcuts follow `SPEC.md`: Enter plays, `Ctrl+F` focuses search, `F` favorites, `Ctrl+R` forces a playlist and guide update, `Esc` clears the search, `Ctrl+,` opens settings, `Ctrl+P` opens the playlist sources window. **`Esc` no longer quits** — `Ctrl+Q` does.

## Providers

`providers.py` owns playlist sources. A provider is a name plus an M3U source — an http(s) URL to download or a local file to read (`is_local` covers bare paths and `file://`).

- **Each provider caches separately**, in `playlists/<slug>.m3u`, so one unreachable source never invalidates another's channels.
- **Failures are reported, not swallowed.** `load_channels` returns `(channels, failed_names)`; the UI puts the failing names in the status bar rather than silently showing a shorter list. An empty playlist counts as a failure.
- **Merging happens on `(name, group)`** — the same key `playlist.parse` uses for mirrors within one file. A second source offering the same channel contributes another stream rather than a duplicate row, and the *first* provider to supply a channel owns its metadata, so provider order is preference order. Gaps (missing `tvg_id`/`logo`) are filled from later sources without overwriting.
- `migrate_legacy_cache` moves the pre-Milestone-5 `playlist.m3u` into the built-in's per-provider cache, so upgrading doesn't force a re-download.

This is the machinery the Atresmedia/Mediaset note under Milestone 5 refers to: pointing ZapTV at a list carrying working URLs for those channels now works end to end (verified with a local M3U adding Antena 3).

## Paths

XDG-split, and both honor their env vars:

- Cache (disposable): `~/.local/share/zaptv/` — `playlists/<slug>.m3u` (one per provider), `epg.xml.gz`, `logos/`. Playlists and guide refresh when >24h old; logos are cached forever under a hash of their URL plus the render size.
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

The coverage gap is the thing to design around: **only 126 of 471 channels have guide data** (~27%). The playlist mostly lacks `tvg-id`, which is the only join key. So "no guide" is the *majority* case and is rendered as a quiet line in the pane, never an error. Every `Guide` lookup returns `None`/empty rather than raising, and a missing or corrupt cache yields an empty `Guide`.

61 XMLTV channel ids have programmes but no playlist channel — Atresmedia and Mediaset (`Cuatro.TV`, `Telecinco.TV`, `Bemad.TV`, …) among them. They have guide data but no stream, because those broadcasters gate live playback behind their own platforms (Atresplayer, Mitele). This is a known gap, scheduled under **Milestone 5**, and it is not a parser bug — don't try to fix it in `playlist.py`.

Two halves to it, worth keeping apart:

- Milestone 5 supplies the *plumbing* — provider abstraction, custom M3U, merging sources into one list. If a third-party list carrying working URLs exists, that machinery is enough.
- If no such list exists, the channels need a **different playback mechanism**: launching the broadcaster's web player instead of VLC. That is a player backend, closer to Milestone 6, which currently names only VLC and MPV.

## Environment gotchas

- **Python is 3.12.3, but `pyproject.toml` requires >=3.13** per `STACK.md`. `pip install -e .` will refuse, so run via `PYTHONPATH=src python3 -m zaptv`. The code avoids 3.13-only syntax.
- **No `pip`, no `venv`** — `sudo apt install python3-venv`. Until then pytest/ruff/mypy cannot be installed and tests must be driven by a stdlib runner that shims `tmp_path` and `monkeypatch`.
- Tkinter **is** installed (Tk 8.6) and the session is Wayland with XWayland on `:0`, so the GUI runs.

VLC is present at `/usr/bin/vlc`; mpv is not installed.

To inspect the GUI without a screenshot tool (only `xwd` and `xwininfo` are available, and `xwd -root` fails under XWayland):

```bash
DISPLAY=:0 xwininfo -root -tree | grep '"Tk")'    # find the window id (field 1)
DISPLAY=:0 xwd -id <id> -silent -out win.xwd      # capture that window, not the root
```

`xwd` output needs converting — PIL is available but has no XWD reader, so parse the 100-byte big-endian header and build the image from `raw`/`BGRX`. Beware: `grep -oP '0x[0-9a-f]+'` on the `xwininfo` line matches `0x640` inside the geometry `420x640`; take field 1 instead. Multiple instances appear as `("tk" "Tk")`, `("tk #2" "Tk")`.
