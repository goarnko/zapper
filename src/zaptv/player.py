"""Playback, delegated entirely to an external player.

ZapTV never implements video playback. Players sit behind the `Player`
interface so a new backend is a new subclass and nothing else changes.
"""

import shutil
import subprocess
from abc import ABC, abstractmethod


class PlayerNotFound(Exception):
    pass


class Player(ABC):
    #: Executable to look for on PATH.
    command: str
    #: Human-readable name, used in error messages.
    label: str

    def executable(self) -> str:
        path = shutil.which(self.command)
        if path is None:
            raise PlayerNotFound(
                f"{self.label} not found on PATH. Install it with: sudo apt install {self.command}"
            )
        return path

    def is_available(self) -> bool:
        return shutil.which(self.command) is not None

    @abstractmethod
    def args(self, stream_url: str) -> list[str]:
        """Full argument vector to spawn for this stream."""

    def play(self, stream_url: str) -> subprocess.Popen[bytes] | None:
        """Spawn the player detached.

        Closing the player must not close ZapTV, and player chatter must not
        pollute our stdout.
        """
        return subprocess.Popen(
            self.args(stream_url),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


class VLCPlayer(Player):
    command = "vlc"
    label = "VLC"

    def args(self, stream_url: str) -> list[str]:
        return [self.executable(), stream_url]


class MPVPlayer(Player):
    command = "mpv"
    label = "mpv"

    def args(self, stream_url: str) -> list[str]:
        # We spawn detached with no tty and output to DEVNULL; --no-terminal
        # stops mpv trying to drive a terminal it does not have.
        return [self.executable(), "--no-terminal", stream_url]


class BrowserPlayer(Player):
    """Opens a page in the user's browser instead of a media player.

    Some broadcasters publish no open stream and play only through their own
    site. For those channels the "stream" is the official live page, and the
    right player is whatever handles http:// — no stream extraction, no DRM
    workaround, just the page the broadcaster intends people to watch.
    """

    command = "xdg-open"
    label = "Web browser"

    def args(self, page_url: str) -> list[str]:
        return [self.executable(), page_url]

    def play(self, page_url: str) -> subprocess.Popen[bytes] | None:
        """Hand the page to the desktop, falling back to Python's own opener."""
        if self.is_available():
            return super().play(page_url)
        # Minimal desktops may lack xdg-open; webbrowser knows other ways.
        import webbrowser

        if not webbrowser.open(page_url):
            raise PlayerNotFound("No web browser found to open this channel.")
        return None


PLAYERS: dict[str, type[Player]] = {
    "vlc": VLCPlayer,
    "mpv": MPVPlayer,
    "browser": BrowserPlayer,
}

#: Players a user can pick as their default; the browser is only ever
#: selected per channel, never for ordinary streams.
SELECTABLE = ("vlc", "mpv")

DEFAULT_PLAYER = "vlc"


def get_player(name: str = DEFAULT_PLAYER) -> Player:
    """The named backend, or the default for an unknown name."""
    return PLAYERS.get(name.lower(), PLAYERS[DEFAULT_PLAYER])()


def available(names: tuple[str, ...] = SELECTABLE) -> list[str]:
    """Selectable backends actually installed on this machine."""
    return [name for name in names if get_player(name).is_available()]


def resolve(name: str = DEFAULT_PLAYER) -> Player:
    """The named backend if it is installed, else one that is.

    get_player alone only guards against an unknown *name*; a configured
    player that has been uninstalled would still be handed back and fail at
    the moment the user pressed Enter. Substituting at startup turns that
    into something we can report before it ruins a click.

    With nothing installed the configured player is returned anyway, so the
    eventual PlayerNotFound names what the user actually asked for.
    """
    chosen = get_player(name)
    if chosen.is_available():
        return chosen
    for alternative in available():
        return get_player(alternative)
    return chosen
