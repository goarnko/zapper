# ZapTV

A fast launcher for live TV channels on Linux. Browse the channel list, pick a channel, VLC opens. Nothing else.

Channels come from the [TDTChannels](https://www.tdtchannels.com/) playlist and are downloaded at runtime — none are shipped with the app.

## Requirements

- Python 3.13+
- Tkinter — `sudo apt install python3-tk`
- VLC — `sudo apt install vlc`

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

Add `--search <query>` to filter the TSV output.

## Keyboard

| Key | Action |
| --- | --- |
| `Enter` | Play the selected channel |
| `Ctrl+F` | Jump to the search box |
| `F` | Favorite / unfavorite |
| `Ctrl+R` | Update the playlist now |
| `Esc` | Clear the search |
| `Ctrl+Q` | Quit |

Search ignores accents, so `malaga` finds *101TV Málaga*. Favorites and recently watched channels appear at the top of the list.

## Files

The playlist is cached in `~/.local/share/zaptv/` and refreshed automatically when it is more than 24 hours old. Settings, favorites and recents live in `~/.config/zaptv/`.

## Status

Milestone 2 — browse, search, favorites, recents. EPG and channel logos are planned.

- [SPEC.md](SPEC.md) — what the app is and is not
- [STACK.md](STACK.md) — technology decisions
- [ROADMAP.md](ROADMAP.md) — milestones

## License

MIT
