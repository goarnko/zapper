# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Milestones 1–3 are done: download → parse → browse → play, settings, search with instant filtering, favorites, recently-watched, and a Now/Next guide from XMLTV. Channel logos and the rest of Milestone 4 (polish) are not implemented.

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
python3 -m pytest tests -q                         # tests
python3 -m ruff check src tests                    # lint
python3 -m mypy                                    # type check (config in pyproject)
```

`--list`/`--search` exercise the download, parse and filter paths without a display or Tkinter — use them to verify changes there. The leading `*` column marks favorites.

Installed (`pip install -e .`) the entry point is `zaptv`.

## Architectural constraints

These come from `SPEC.md`/`STACK.md`; don't relitigate them without the user asking.

- **Zero runtime dependencies.** Only Python and an external player. M3U parsing is hand-rolled, EPG will use stdlib `gzip` + `xml.etree.ElementTree`, networking is `urllib.request` (not requests/curl/wget), storage is plain JSON. Dev tooling (pytest/ruff/mypy) is the only exception.
- **No video playback in-process, ever.** Players live behind the `Player` ABC in `player.py`; a new backend is a new subclass plus a `PLAYERS` entry. `VLCPlayer` is the default, `MPVPlayer` exists for Milestone 6.
- **Channels are never hardcoded or shipped.** The playlist is always downloaded from a provider at runtime.
- **Not a media center.** No library, movies, series, music, PVR, torrents, streaming server, accounts, or cloud sync. `ROADMAP.md` lists these as explicitly out of scope.

## UI conventions

`ui.py` holds only widget wiring; matching and ordering live in `search.py` so they can be tested without a display (Tkinter is unavailable here — see below).

- The list is rebuilt from scratch on every keystroke, favorite toggle, and play. `_refresh` therefore saves and restores the selection; without that, favoriting throws the user back to the top of ~471 channels.
- **`see()` on an unmapped listbox scrolls its target to the very top**, hiding the section header above it — the list then looks unlabelled at startup. `_restore_selection` uses `yview_moveto(0)` when nothing carried over (startup, or a search that dropped the selection) and only calls `see()` when genuinely restoring a selection, by which point the widget is mapped. `after_idle` does *not* fix this: idle callbacks run before the window is mapped. `tests/test_ui_scroll.py` guards it.
- A favorited channel appears **twice** — once under `★ FAVORITES`, once in its group. `_index_of` deliberately returns the *last* match so selection lands on the group copy, keeping neighbours in view.
- Something is always selected, so Enter plays straight after typing a search without an arrow key in between.
- Search is accent-insensitive in both directions (`malaga` ↔ `Málaga`) because Spanish channel names are full of accents users don't type. Tokens are ANDed.

Shortcuts follow `SPEC.md`: Enter plays, `Ctrl+F` focuses search, `F` favorites, `Ctrl+R` forces a playlist update, `Esc` clears the search. **`Esc` no longer quits** — `Ctrl+Q` does.

## Paths

XDG-split, and both honor their env vars:

- Cache (disposable): `~/.local/share/zaptv/` — `playlist.m3u`, `epg.xml.gz`, later `logos/`. Refreshed when >24h old.
- Config (user intent): `~/.config/zaptv/` — `settings.json`, `favorites.json`, `recent.json`.

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

61 XMLTV channel ids have programmes but no playlist channel — Atresmedia and Mediaset (`Cuatro.TV`, `Telecinco.TV`, `Bemad.TV`, …) among them. They have guide data but no stream, because those broadcasters gate live playback behind their own platforms. Adding them to the list would need a different playback mechanism, not a playlist fix.

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
