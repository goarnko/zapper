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

    def play(self, stream_url: str) -> subprocess.Popen:
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
        return [self.executable(), stream_url]


PLAYERS: dict[str, type[Player]] = {
    "vlc": VLCPlayer,
    "mpv": MPVPlayer,
}

DEFAULT_PLAYER = "vlc"


def get_player(name: str = DEFAULT_PLAYER) -> Player:
    return PLAYERS.get(name.lower(), PLAYERS[DEFAULT_PLAYER])()
