# ZapTV

A fast launcher for live TV channels on Linux. Browse the channel list, pick a channel, VLC opens. Nothing else.

Channels come from the [TDTChannels](https://www.tdtchannels.com/) playlist and are downloaded at runtime — none are shipped with the app.

## Requirements

- Python 3.13+
- Tkinter — `sudo apt install python3-tk`
- VLC — `sudo apt install vlc`
- Pillow — installed with the package; needed to decode channel logos

## Usage

```bash
pip install -e .
zaptv
```

Or run from a checkout without installing:

```bash
PYTHONPATH=src python3 -m zaptv           # open the channel list
PYTHONPATH=src python3 -m zaptv --list    # print channels as TSV instead
```

Add `--search <query>` to filter the TSV output, or `--now` to print what is on air.

## Keyboard

| Key | Action |
| --- | --- |
| `Enter` | Play the selected channel |
| `Ctrl+F` | Jump to the search box |
| `F` | Favorite / unfavorite |
| `Ctrl+R` | Update the playlist and guide now |
| `Ctrl+,` | Open settings |
| `Esc` | Clear the search |
| `Ctrl+Q` | Quit |

Search ignores accents, so `malaga` finds *101TV Málaga*. Favorites and recently watched channels appear at the top of the list.

## TV guide

Selecting a channel shows what is on now and what is next, from the TDTChannels XMLTV feed.

Guide data covers about a quarter of the channel list — the playlist rarely carries the `tvg-id` needed to match a channel to the guide — so many channels simply show *No guide data for this channel*.

## Files

The playlist is cached in `~/.local/share/zaptv/` and refreshed automatically when it is more than 24 hours old. Settings, favorites and recents live in `~/.config/zaptv/`.

## Appearance

Light and dark themes, channel logos, and a settings window (`Ctrl+,`) for the player,
theme, logos and automatic updates. Settings are saved to `~/.config/zaptv/settings.json`.

## Status

Milestone 4 — browse, search, favorites, recents, Now/Next guide, logos and theming.
Multiple playlist providers are next.

- [SPEC.md](SPEC.md) — what the app is and is not
- [STACK.md](STACK.md) — technology decisions
- [ROADMAP.md](ROADMAP.md) — milestones

## License

MIT
