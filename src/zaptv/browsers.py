"""Which web browsers are installed, and how to launch a specific one.

Web channels open in a browser, and a user with several installed may want
a particular one. Browsers are found the way the desktop itself finds them:
from the .desktop entries in the XDG application directories, not from a
list of executable names. That is what makes snaps and flatpaks visible —
on this machine Firefox and Opera are both snaps, launched through
/snap/bin, which a desktop session's PATH need not include.

Stdlib only, per STACK.md. Desktop entries are not strict INI (localised
keys, several sections), so they are read line by line rather than with
configparser.
"""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_HANDLES = ("x-scheme-handler/http", "x-scheme-handler/https")


@dataclass(frozen=True)
class Browser:
    #: Desktop-file id, e.g. "firefox_firefox.desktop". Stable across
    #: upgrades, which is why settings store it rather than the name.
    id: str
    name: str
    exec: str

    def args(self, url: str) -> list[str]:
        """The Exec line as an argument vector, with the URL in place.

        Field codes follow the Desktop Entry spec: %u/%U/%f/%F take the URL,
        the rest (%i, %c, %k and deprecated ones) are dropped, and %% is a
        literal percent. An Exec with no URL code gets the URL appended, as
        launchers do.
        """
        argv: list[str] = []
        placed = False
        for word in shlex.split(self.exec):
            if word in ("%u", "%U", "%f", "%F"):
                argv.append(url)
                placed = True
            elif len(word) == 2 and word.startswith("%") and word != "%%":
                continue
            else:
                argv.append(word.replace("%%", "%"))
        if not placed:
            argv.append(url)
        return argv


def application_dirs() -> list[Path]:
    """XDG application directories, most important first."""
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs: list[Path] = []
    for base in [home, *system.split(":")]:
        if not base:
            continue
        path = Path(base) / "applications"
        if path not in dirs:
            dirs.append(path)
    return dirs


def _read_entry(path: Path) -> dict[str, str]:
    """Keys of the [Desktop Entry] section; other sections are ignored."""
    entry: dict[str, str] = {}
    in_entry = False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return entry
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if in_entry and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            entry.setdefault(key.strip(), value.strip())
    return entry


def _is_browser(entry: dict[str, str]) -> bool:
    """A visible application that both calls itself a browser and opens
    web links.

    Both conditions, because each alone admits impostors: media players
    claim stream schemes, and a "WebBrowser" category on a helper entry
    that opens no links would launch nothing useful.
    """
    if entry.get("Type", "Application") != "Application" or not entry.get("Exec"):
        return False
    if entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true":
        return False
    categories = entry.get("Categories", "").split(";")
    mimes = entry.get("MimeType", "").split(";")
    if "WebBrowser" not in categories or not any(m in mimes for m in _HANDLES):
        return False
    try_exec = entry.get("TryExec")
    return not try_exec or shutil.which(try_exec) is not None


def installed(dirs: list[Path] | None = None) -> list[Browser]:
    """Installed browsers, sorted by name.

    The first directory to define a desktop id owns it, as the spec says, so
    a user's own override in ~/.local/share — including one that hides the
    browser — wins over the system copy.
    """
    seen: set[str] = set()
    found: list[Browser] = []
    for directory in dirs if dirs is not None else application_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.desktop")):
            desktop_id = str(path.relative_to(directory)).replace(os.sep, "-")
            if desktop_id in seen:
                continue
            seen.add(desktop_id)
            entry = _read_entry(path)
            if _is_browser(entry):
                found.append(Browser(desktop_id, entry.get("Name") or desktop_id, entry["Exec"]))
    return sorted(found, key=lambda b: b.name.lower())


def find(desktop_id: str, dirs: list[Path] | None = None) -> Browser | None:
    if not desktop_id:
        return None
    return next((b for b in installed(dirs) if b.id == desktop_id), None)


def system_default() -> str | None:
    """Desktop id of the desktop's default browser, or None if unknown."""
    if shutil.which("xdg-settings") is None:
        return None
    try:
        result = subprocess.run(
            ["xdg-settings", "get", "default-web-browser"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None
