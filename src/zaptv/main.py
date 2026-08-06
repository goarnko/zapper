"""Entry point: refresh the playlist if stale, parse it, show the list."""

import sys

from . import playlist, updater
from .settings import Settings


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

    if "--list" in argv:
        for channel in sorted(channels, key=lambda c: (c.group, c.name.casefold())):
            print(f"{channel.group}\t{channel.name}\t{channel.stream}")
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

    ui.run(channels, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
