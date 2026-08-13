"""Channels that play only on the broadcaster's own site.

Atresmedia and Mediaset publish no open stream for their channels, so they
are absent from TDTChannels and cannot be handed to VLC. They do stream
free on their own players, so ZapTV lists them with the official live page
as the "stream" and opens it in a browser.

The list is written once into the user's config as an ordinary M3U and
registered as an ordinary local provider. After that it is the user's file:
editable, disableable, removable. That keeps the "channels are never
shipped" rule intact in spirit — nothing is baked into the app at runtime,
and the seed below is only a starting point.

Page URLs, unlike stream URLs, are stable brand addresses rather than
session-bound links, which is why this survives where a scraped playlist
would not.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from .settings import config_dir

if TYPE_CHECKING:
    from .providers import ProviderList

PROVIDER_NAME = "Web channels"
GROUP = "Generalistas"

#: (name, page URL, XMLTV id). Mediaset's ids come from the TDTChannels
#: guide; Atresmedia is absent from that feed entirely, so theirs come from
#: the second EPG source in updater.EPG_SOURCES. The two feeds share no ids,
#: so mixing them here is unambiguous.
SEED_CHANNELS = [
    ("Antena 3", "https://www.atresplayer.com/directos/antena3/", "Antena.3.es"),
    ("laSexta", "https://www.atresplayer.com/directos/lasexta/", "laSexta.es"),
    ("Neox", "https://www.atresplayer.com/directos/neox/", "Neox.es"),
    ("Nova", "https://www.atresplayer.com/directos/nova/", "Nova.es"),
    ("Mega", "https://www.atresplayer.com/directos/mega/", "Mega.es"),
    ("Atreseries", "https://www.atresplayer.com/directos/atreseries/", "Atreseries.es"),
    ("Telecinco", "https://www.mediasetinfinity.es/directo/telecinco/", "Telecinco.TV"),
    ("Cuatro", "https://www.mediasetinfinity.es/directo/cuatro/", "Cuatro.TV"),
    ("FDF", "https://www.mediasetinfinity.es/directo/fdf/", "FDF.TV"),
    ("Energy", "https://www.mediasetinfinity.es/directo/energy/", "Energy.TV"),
    ("Divinity", "https://www.mediasetinfinity.es/directo/divinity/", "Divinity.TV"),
    ("Boing", "https://www.mediasetinfinity.es/directo/boing/", "Boing.TV"),
    ("Be Mad", "https://www.mediasetinfinity.es/directo/bemad/", "Bemad.TV"),
]

HEADER = (
    "#EXTM3U\n"
    "# ZapTV web channels.\n"
    "# These channels stream only on the broadcaster's own site, so the URL\n"
    "# below is the official live page and zaptv-player=\"browser\" tells\n"
    "# ZapTV to open it in a browser instead of VLC.\n"
    "# This file is yours: edit, add or remove entries freely.\n"
)


def playlist_path() -> Path:
    return config_dir() / "web-channels.m3u"


def render(
    channels: list[tuple[str, str, str]] = SEED_CHANNELS, group: str = GROUP
) -> str:
    lines = [HEADER]
    for name, url, tvg_id in channels:
        attrs = f'zaptv-player="browser" group-title="{group}"'
        if tvg_id:
            attrs = f'tvg-id="{tvg_id}" {attrs}'
        lines.append(f"#EXTINF:-1 {attrs},{name}\n{url}\n")
    return "".join(lines)


def write_seed(path: Path | None = None) -> Path:
    """Write the starter playlist, overwriting whatever is there."""
    path = path or playlist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".m3u.part")
    tmp.write_text(render(), encoding="utf-8")
    tmp.replace(path)
    return path


#: How the Atresmedia entries were written before they had guide ids. Kept
#: verbatim so upgrade_seed can recognise an untouched line and refuse to
#: rewrite one the user has edited.
_LEGACY_ATRESMEDIA = [
    (name, url) for name, url, _ in SEED_CHANNELS if "atresplayer.com" in url
]


def upgrade_seed(path: Path | None = None) -> int:
    """Add the Atresmedia guide ids to an already-written seed file.

    Those six shipped with no tvg-id, because at the time no feed carried
    them. install() is a no-op once the file exists, so without this an
    existing user would never get the guide data the new EPG source makes
    available.

    A line is only rewritten when it still matches exactly what ZapTV wrote:
    the file belongs to the user, and a line they have touched is left alone
    even at the cost of that channel keeping no guide. Returns how many
    lines were changed.
    """
    path = path or playlist_path()
    if not path.exists():
        return 0

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0

    changed = 0
    for name, url in _LEGACY_ATRESMEDIA:
        old = f'#EXTINF:-1 zaptv-player="browser" group-title="{GROUP}",{name}\n{url}'
        if old not in text:
            continue
        tvg_id = next(i for n, u, i in SEED_CHANNELS if n == name and u == url)
        new = (
            f'#EXTINF:-1 tvg-id="{tvg_id}" zaptv-player="browser" '
            f'group-title="{GROUP}",{name}\n{url}'
        )
        text = text.replace(old, new)
        changed += 1

    if changed:
        tmp = path.with_suffix(".m3u.part")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return changed


def install(sources: "ProviderList", path: Path | None = None) -> bool:
    """Create the playlist and register it, once.

    Returns True when something was set up. Deleting the provider is
    respected: if the file exists but the provider does not, the user
    removed it on purpose and it is not silently added back.
    """
    path = path or playlist_path()
    if path.exists():
        return False
    if sources.get(PROVIDER_NAME) is not None:
        return False

    write_seed(path)
    sources.add(PROVIDER_NAME, str(path))
    return True
