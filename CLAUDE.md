# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Milestone 1 is scaffolded: download playlist → parse M3U → list channels → launch VLC, plus settings. Search, favorites, EPG, and logos are not implemented.

Note the git repo is named `zapper` but the project is **ZapTV** (`zaptv`) — the rename happened after the repo was created.

## Documents

Three specs, and they do not fully agree — `STACK.md` and `ROADMAP.md` are newer and win:

- `SPEC.md` — product spec: UX, features, non-goals, philosophy. (Originally `zapper.md`.)
- `STACK.md` — authoritative technology decisions and repository layout.
- `ROADMAP.md` — 8 milestones. Note it renumbers `SPEC.md`'s v0.1–v1.0 scheme; use milestones.

## Commands

```bash
PYTHONPATH=src python3 -m zaptv           # run the GUI
PYTHONPATH=src python3 -m zaptv --list    # channels as group/name/stream TSV (no GUI needed)
python3 -m pytest tests -q                # tests
python3 -m ruff check src tests           # lint
python3 -m mypy                           # type check (config in pyproject)
```

`--list` exercises the whole download + parse path without a display or Tkinter — use it to verify parser changes.

Installed (`pip install -e .`) the entry point is `zaptv`.

## Architectural constraints

These come from `SPEC.md`/`STACK.md`; don't relitigate them without the user asking.

- **Zero runtime dependencies.** Only Python and an external player. M3U parsing is hand-rolled, EPG will use stdlib `gzip` + `xml.etree.ElementTree`, networking is `urllib.request` (not requests/curl/wget), storage is plain JSON. Dev tooling (pytest/ruff/mypy) is the only exception.
- **No video playback in-process, ever.** Players live behind the `Player` ABC in `player.py`; a new backend is a new subclass plus a `PLAYERS` entry. `VLCPlayer` is the default, `MPVPlayer` exists for Milestone 6.
- **Channels are never hardcoded or shipped.** The playlist is always downloaded from a provider at runtime.
- **Not a media center.** No library, movies, series, music, PVR, torrents, streaming server, accounts, or cloud sync. `ROADMAP.md` lists these as explicitly out of scope.

## Paths

XDG-split, and both honor their env vars:

- Cache (disposable): `~/.local/share/zaptv/` — `playlist.m3u`, later `epg.xml.gz`, `logos/`. Refreshed when >24h old.
- Config (user intent): `~/.config/zaptv/` — `settings.json`, later `favorites.json`, `recent.json`.

## What the real playlist looks like

Verified against the live TDTChannels list — these shaped the parser and will bite anyone assuming the spec's simpler model:

- **Channels repeat.** 586 `#EXTINF` entries collapse to ~471 channels; a channel is listed once per mirror. `Channel.streams` is a **list**; `Channel.stream` is the first (preferred) mirror. Parse without merging and "La 1" shows up three times.
- **`tvg-id` is mostly absent** — ~2/3 of entries have none, and it's shared across unrelated variants where present. It is *not* a usable identity key; channels are keyed by `(name, group)`.
- **Attribute values contain commas** (logo URLs like `w_200,h_200`), so the display name can't be recovered by splitting the line on `,`. `playlist._parse_extinf` strips quoted attributes first, then reads the name from the remainder.
- Groups are regional/thematic Spanish labels (`Generalistas`, `Andalucía`, `Musicales`, …), ~30 of them.

`tests/test_playlist.py` pins each of these.

## Environment gotchas

This machine cannot run the GUI or pytest as-is:

- **Python is 3.12.3, but `pyproject.toml` requires >=3.13** per `STACK.md`. `pip install -e .` will refuse. The code itself avoids 3.13-only syntax, so `PYTHONPATH=src python3 -m zaptv` still runs.
- **Tkinter is not installed** — `sudo apt install python3-tk`. `main.py` catches the ImportError and points at the fix.
- **No `pip`, no `venv`** — `sudo apt install python3-venv`. Until then pytest/ruff/mypy cannot be installed and the test functions have to be driven by a stdlib runner that shims `tmp_path` and `monkeypatch`.

VLC is present at `/usr/bin/vlc`; mpv is not installed.
