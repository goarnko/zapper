# ZapTV

A fast launcher for live TV channels on Linux. Browse the channel list, pick a channel, VLC opens. Nothing else.

Channels come from the [TDTChannels](https://www.tdtchannels.com/) playlist and are downloaded at runtime — none are shipped with the app.

## Requirements

- Python 3.10+
- Tkinter — `sudo apt install python3-tk`
- VLC — `sudo apt install vlc` (mpv also works: `sudo apt install mpv`)
- Pillow — installed with the package; needed to decode channel logos

## Install

**Debian / Ubuntu package** — builds a `.deb` and installs the launcher, desktop entry and icons:

```bash
sudo apt install "$(packaging/build-deb.sh)"
```

Each packaging script prints the file it wrote, so the command above always installs the
build it just made — no version number to keep in step, and no chance of picking up an
older `.deb` left in `dist/`.

**From a checkout, for your user only** — no root; the launcher points back at the
checkout, so `git pull` updates the installed app:

```bash
packaging/install-user.sh      # and --uninstall to undo
```

**AppImage:**

```bash
"$(packaging/build-appimage.sh)"
```

Note the AppImage is *thin*: it carries ZapTV but uses the host's Python, Tkinter and
Pillow rather than bundling an interpreter. It tells you which one is missing if any is.

**Or just run it in place:**

```bash
pip install -e . && zaptv
PYTHONPATH=src python3 -m zaptv           # without installing
PYTHONPATH=src python3 -m zaptv --list    # print channels as TSV instead
```

Add `--search <query>` to filter the TSV output, `--now` to print what is on air, or
`--providers` to list the configured playlists.

## Keyboard

| Key | Action |
| --- | --- |
| `Enter` | Play the selected channel |
| `Ctrl+F` | Jump to the search box |
| `F` | Favorite / unfavorite |
| `Ctrl+R` | Update the playlist and guide now |
| `Ctrl+G` | Open the full guide grid |
| `Ctrl+,` | Open settings |
| `Ctrl+P` | Manage playlists |
| `Esc` | Clear the search |
| `Ctrl+Q` | Quit |

Right-click a channel for **Play with…** to send it to a different player just once.

Search ignores accents, so `malaga` finds *101TV Málaga*. Favorites and recently watched channels appear at the top of the list.

Channels are grouped — 30 regional and thematic sections — and each one folds away by clicking its arrow. Collapsed groups are remembered between runs. Searching temporarily opens everything, so a match is never hidden inside a folded group.

## TV guide

Selecting a channel shows what is on now and what is next, from the TDTChannels XMLTV feed.

The **Guide** button beside the search box — or `Ctrl+G` — opens the whole schedule as a grid — one row per channel, time across the top,
whatever is on air right now highlighted and marked with a line. Favorites come first, starred,
as they do in the channel list. The box in the top right filters the rows, with the same
accent-insensitive matching as the main search. Click a programme for its description,
double-click to play that channel. `◀` and `▶` (or the arrow keys) move three
hours at a time, and **Now** jumps back to the present.

Guide data covers about a quarter of the channel list — the playlist rarely carries the `tvg-id` needed to match a channel to the guide — so many channels simply show *No guide data for this channel*.

## Files

The playlist is cached in `~/.local/share/zaptv/` and refreshed automatically when it is more than 24 hours old. Settings, favorites and recents live in `~/.config/zaptv/`.

## Appearance

Light and dark themes, channel logos, and a settings window (`Ctrl+,`) for the player,
theme, logos and automatic updates. Settings are saved to `~/.config/zaptv/settings.json`.

## Playlists

ZapTV ships with the TDTChannels list and can merge in others — press `Ctrl+P` to add a
playlist by URL or from a local `.m3u` file. When two sources carry the same channel their
streams are pooled, so the second becomes a fallback rather than a duplicate row.

The built-in list can be disabled but not removed.

## Atresmedia and Mediaset

Antena 3, laSexta, Neox, Nova, Mega, Atreseries, Telecinco, Cuatro, FDF, Energy, Divinity,
Boing and Be Mad are missing from the TDTChannels playlist: those broadcasters stream only
through their own sites, so there is no open URL to hand to VLC.

ZapTV lists them anyway, under a **Web channels** playlist created in `~/.config/zaptv/` on
first run. Selecting one opens the broadcaster's official live page in your browser instead
of VLC. Nothing is scraped or decrypted — it is the page the broadcaster intends you to
watch, and the file is yours to edit or remove.

All thirteen show Now/Next. The Mediaset ones come from the TDTChannels guide; Atresmedia is
missing from that feed entirely, so those six are filled in from a second XMLTV source.

## Updates

ZapTV checks once a day whether a newer release exists and mentions it in the status bar.
It only ever reports — nothing is downloaded or replaced. Turn it off in settings
(`Ctrl+,`), or check on demand:

```bash
zaptv --check-updates
```

## Development

```bash
pip install -e ".[dev]"

pytest tests -q          # unit tests
ruff check src tests     # lint
mypy                     # type check (strict)

ZAPTV_INTEGRATION=1 pytest tests/test_integration.py -q   # hits the live feeds
```

Integration tests are off by default: they need the network and exist to catch the
upstream feeds changing shape. CI runs them weekly.

## Status

Milestone 8 — feature complete against the roadmap, bar application self-update.
Browse, search, favorites, recents, Now/Next guide, logos, theming, multiple playlist
sources, selectable players (VLC, mpv, browser), packaging and CI.

- [SPEC.md](SPEC.md) — what the app is and is not
- [STACK.md](STACK.md) — technology decisions
- [ROADMAP.md](ROADMAP.md) — milestones

## License

MIT
