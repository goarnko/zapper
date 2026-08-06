"""Favorites and recently-watched channels, stored as JSON under ~/.config/zaptv/.

Both files are plain lists of channel names, matching the format in SPEC.md.
Names — not (name, group) pairs — are the key, so a favorite survives the
channel moving between groups in an updated playlist. The trade-off is that
two channels sharing a name across groups are favorited together; that is
rare enough in the TDTChannels list to be worth the simpler file.
"""

import json
from pathlib import Path

from .settings import config_dir

FAVORITES_PATH = config_dir() / "favorites.json"
RECENT_PATH = config_dir() / "recent.json"

MAX_RECENT = 10


def _read_names(path: Path) -> list[str]:
    """Load a JSON list of names, tolerating anything unreadable.

    A corrupt favorites file must not stop the user from watching TV.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _write_names(path: Path, names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(names, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class Favorites:
    """Unordered set of favorited channel names, persisted on every change."""

    def __init__(self, names: list[str] | None = None, path: Path | None = None):
        self.path = path or FAVORITES_PATH
        self._names: set[str] = set(names or [])

    @classmethod
    def load(cls, path: Path | None = None) -> "Favorites":
        path = path or FAVORITES_PATH
        return cls(_read_names(path), path)

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def __len__(self) -> int:
        return len(self._names)

    def toggle(self, name: str) -> bool:
        """Flip a channel's favorite state. Returns the new state."""
        if name in self._names:
            self._names.discard(name)
            favorited = False
        else:
            self._names.add(name)
            favorited = True
        self.save()
        return favorited

    def save(self) -> None:
        _write_names(self.path, sorted(self._names, key=str.casefold))


class Recent:
    """Most-recently-watched channel names, newest first, capped."""

    def __init__(
        self,
        names: list[str] | None = None,
        path: Path | None = None,
        limit: int = MAX_RECENT,
    ):
        self.path = path or RECENT_PATH
        self.limit = limit
        self._names: list[str] = list(names or [])[:limit]

    @classmethod
    def load(cls, path: Path | None = None, limit: int = MAX_RECENT) -> "Recent":
        path = path or RECENT_PATH
        return cls(_read_names(path), path, limit)

    @property
    def names(self) -> list[str]:
        return list(self._names)

    def __len__(self) -> int:
        return len(self._names)

    def push(self, name: str) -> None:
        """Record a play, moving the channel to the front without duplicating it."""
        self._names = [name] + [n for n in self._names if n != name]
        del self._names[self.limit :]
        self.save()

    def save(self) -> None:
        _write_names(self.path, self._names)
