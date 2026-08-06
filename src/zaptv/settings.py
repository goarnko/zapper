"""User settings, stored as JSON under ~/.config/zaptv/.

Config and cache are deliberately separate: settings are user intent and
belong in XDG config, the playlist is disposable and belongs in XDG data.
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "zaptv"


SETTINGS_PATH = config_dir() / "settings.json"


@dataclass
class Settings:
    player: str = "vlc"
    auto_update: bool = True
    theme: str = "light"
    show_logos: bool = True
    #: Ask GitHub, at most daily, whether a newer ZapTV was released. This
    #: only reports; nothing is downloaded or replaced.
    check_updates: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Read settings, falling back to defaults on anything unreadable.

        A corrupt or hand-edited settings file must not stop the user from
        watching TV, so unknown keys are dropped and bad files are ignored.
        """
        path = path or SETTINGS_PATH
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()

        if not isinstance(data, dict):
            return cls()

        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
