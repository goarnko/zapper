"""Light and dark palettes.

Tk has no theme switch of its own: classic widgets take explicit colours and
ttk widgets take a configured style. Keeping every colour in one place means
adding a theme is a dict, not a hunt through the UI code.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    field_bg: str
    fg: str
    muted: str
    select_bg: str
    select_fg: str
    border: str


LIGHT = Palette(
    bg="#f2f2f2",
    field_bg="#ffffff",
    fg="#1c1c1c",
    muted="#6d6d6d",
    select_bg="#cfe0f5",
    select_fg="#10233a",
    border="#cccccc",
)

DARK = Palette(
    bg="#1f1f1f",
    field_bg="#2a2a2a",
    fg="#e8e8e8",
    muted="#9a9a9a",
    select_bg="#2f5b8c",
    select_fg="#ffffff",
    border="#3a3a3a",
)

PALETTES = {"light": LIGHT, "dark": DARK}
DEFAULT = "light"


def get(name: str) -> Palette:
    return PALETTES.get(name.lower(), PALETTES[DEFAULT])
