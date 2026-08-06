"""Entry point: refresh the playlist if stale, parse it, show the list."""

import sys

from . import epg, playlist, search, updater
from .settings import Settings
from .storage import Favorites, Recent


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--version" in argv:
        from . import __version__

        print(__version__)
        return 0

    config = Settings.load()

    try:
        path = updater.ensure() if config.auto_update else updater.PLAYLIST_PATH
    except OSError as exc:
        print(f"Could not download the channel list: {exc}", file=sys.stderr)
        return 1

    if not path.exists():
        print(f"No cached playlist at {path} and auto-update is off.", file=sys.stderr)
        return 1

    channels = playlist.load(path)
    if not channels:
        print(f"No channels found in {path}", file=sys.stderr)
        return 1

    if "--search" in argv:
        index = argv.index("--search")
        query = argv[index + 1] if index + 1 < len(argv) else ""
        channels = search.filter_channels(channels, query)

    if "--now" in argv:
        return _print_now(channels, config)

    if "--list" in argv or "--search" in argv:
        favorites = Favorites.load()
        for channel in sorted(channels, key=lambda c: (search.normalize(c.group), search.sort_key(c))):
            marker = "*" if channel.name in favorites else " "
            print(f"{marker}\t{channel.group}\t{channel.name}\t{channel.stream}")
        return 0

    try:
        from . import ui
    except ImportError:
        print(
            "Tkinter is missing. Install it with: sudo apt install python3-tk\n"
            "(or run with --list for a text dump)",
            file=sys.stderr,
        )
        return 1

    ui.run(channels, config, Favorites.load(), Recent.load(), _load_guide(config))
    return 0


def _load_guide(config: Settings) -> epg.Guide:
    """Fetch and parse the guide, tolerating its absence.

    The guide is a nice-to-have: every failure here degrades to an empty
    Guide, and the app still lists and plays channels.
    """
    path = updater.ensure_epg() if config.auto_update else updater.EPG_PATH
    if path is None or not path.exists():
        return epg.Guide()
    return epg.load(path)


def _print_now(channels: list, config: Settings) -> int:
    """Print Now/Next per channel — the guide equivalent of --list."""
    guide = _load_guide(config)
    if not len(guide):
        print("No guide data available.", file=sys.stderr)
        return 1

    covered = 0
    for channel in sorted(channels, key=search.sort_key):
        current, following = guide.now_and_next(channel.tvg_id)
        if current is None and following is None:
            continue
        covered += 1
        print(channel.name)
        for label, programme in (("Now ", current), ("Next", following)):
            if programme is None:
                continue
            local = programme.start.astimezone()
            print(f"  {label}  {local:%H:%M}  {programme.title}")
    print(f"\n{covered} of {len(channels)} channels have guide data.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
