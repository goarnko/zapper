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

from dataclasses import dataclass
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
    channels: list[tuple[str, str, str]] = SEED_CHANNELS,
    group: str = GROUP,
    header: str = HEADER,
) -> str:
    lines = [header]
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


# -- other countries -----------------------------------------------------
#
# The same mechanism covers France's TNT and the UK's Freeview, for users
# travelling there or living there. Open streams exist for the majors in
# community lists, but on measurement nearly all were unofficial restreams
# (bare IPs, URL shorteners) rather than anything the broadcaster publishes,
# so the official live page is the only source that fits this app's rules.
#
# These differ from the Spanish list in two ways. They are registered
# disabled, because most of their pages are geo-restricted to their own
# country and would only clutter a Spanish user's list. And each carries its
# own guide feed, downloaded only while the list is enabled, so nobody pays
# for listings of channels they have switched off.


@dataclass(frozen=True)
class RegionalList:
    provider: str
    filename: str
    group: str
    #: (name, page URL, XMLTV id in `guide`'s feed; "" when it has none).
    channels: list[tuple[str, str, str]]
    #: (cache slug, URL) of the XMLTV feed these ids come from.
    guide: tuple[str, str]

    @property
    def header(self) -> str:
        return HEADER + (
            "# Most of these pages only play inside their own country, and some\n"
            "# ask for a free account on the broadcaster's site.\n"
        )

    def path(self, directory: Path | None = None) -> Path:
        return (directory or config_dir()) / self.filename

    def render(self) -> str:
        return render(self.channels, self.group, self.header)


#: Ids from xmltvfr.fr's TNT feed: 30 channels, about ten days ahead, kept
#: deliberately small. Some ids predate a rename and say so — NT1 is TFX,
#: Numero23 is RMC Story, Cherie25 is RMC Life. France 24 is not TNT and has
#: no id there; it is listed because it is the one French channel whose page
#: plays from abroad.
FRANCE = RegionalList(
    provider="Web channels (France)",
    filename="web-channels-fr.m3u",
    group="France (TNT)",
    channels=[
        ("TF1", "https://www.tf1.fr/tf1/direct", "TF1.fr"),
        ("France 2", "https://www.france.tv/france-2/direct.html", "France2.fr"),
        ("France 3", "https://www.france.tv/france-3/direct.html", "France3.fr"),
        ("France 4", "https://www.france.tv/france-4/direct.html", "France4.fr"),
        ("France 5", "https://www.france.tv/france-5/direct.html", "France5.fr"),
        ("M6", "https://www.m6.fr/m6/direct", "M6.fr"),
        ("Arte", "https://www.arte.tv/fr/direct/", "Arte.fr"),
        ("LCP", "https://lcp.fr/direct-lcp-5434", "LaChaineParlementaire.fr"),
        ("W9", "https://www.m6.fr/w9/direct", "W9.fr"),
        ("TMC", "https://www.tf1.fr/tmc/direct", "TMC.fr"),
        ("TFX", "https://www.tf1.fr/tfx/direct", "NT1.fr"),
        ("Gulli", "https://www.m6.fr/gulli/direct", "Gulli.fr"),
        ("BFM TV", "https://www.bfmtv.com/en-direct/", "BFMTV.fr"),
        ("CNews", "https://www.cnews.fr/le-direct", "CNews.fr"),
        ("LCI", "https://www.tf1.fr/lci/direct", "LCI.fr"),
        ("franceinfo", "https://www.france.tv/franceinfo/direct.html", "FranceInfo.fr"),
        ("T18", "https://t18.fr/direct", "T18.fr"),
        ("TF1 Séries Films", "https://www.tf1.fr/tf1-series-films/direct", "TF1SeriesFilms.fr"),
        ("L'Équipe", "https://www.lequipe.fr/tv/", "LEquipe21.fr"),
        ("6ter", "https://www.m6.fr/6ter/direct", "6ter.fr"),
        ("RMC Story", "https://www.rmcplus.fr/direct/rmc_story", "Numero23.fr"),
        ("RMC Découverte", "https://www.rmcplus.fr/direct/rmc_decouverte", "RMCDecouverte.fr"),
        ("RMC Life", "https://www.rmcplus.fr/direct/rmc_life", "Cherie25.fr"),
        ("France 24", "https://www.france24.com/fr/direct", ""),
    ],
    guide=("xmltvfr", "https://xmltvfr.fr/xmltv/xmltv_tnt.xml.gz"),
)

#: Ids from epgshare01's UK feed, the same publisher as the Atresmedia
#: guide. iPlayer picks the viewer's own BBC One region; the London listing
#: stands in for all of them. Sky News is absent because TDTChannels already
#: carries it as an open stream, and ITVBe has no listing in the feed.
UK = RegionalList(
    provider="Web channels (UK)",
    filename="web-channels-uk.m3u",
    group="UK (Freeview)",
    channels=[
        ("BBC One", "https://www.bbc.co.uk/iplayer/live/bbcone", "BBC.One.Lon.HD.uk"),
        ("BBC Two", "https://www.bbc.co.uk/iplayer/live/bbctwo", "BBC.Two.HD.uk"),
        ("BBC Three", "https://www.bbc.co.uk/iplayer/live/bbcthree", "BBC.Three.HD.uk"),
        ("BBC Four", "https://www.bbc.co.uk/iplayer/live/bbcfour", "BBC.Four.HD.uk"),
        ("CBBC", "https://www.bbc.co.uk/iplayer/live/cbbc", "CBBC.HD.uk"),
        ("CBeebies", "https://www.bbc.co.uk/iplayer/live/cbeebies", "CBeebies.HD.uk"),
        ("BBC News", "https://www.bbc.co.uk/iplayer/live/bbcnews", "BBC.NEWS.HD.uk"),
        (
            "BBC Parliament",
            "https://www.bbc.co.uk/iplayer/live/bbcparliament",
            "BBC.Parliament.HD.uk",
        ),
        ("BBC Scotland", "https://www.bbc.co.uk/iplayer/live/bbcscotland", "BBCScotlandHD.uk"),
        ("BBC Alba", "https://www.bbc.co.uk/iplayer/live/bbcalba", "BBC.ALBA.HD.uk"),
        ("ITV1", "https://www.itv.com/watch?channel=itv", "ITV1.HD.uk"),
        ("ITV2", "https://www.itv.com/watch?channel=itv2", "ITV2.HD.uk"),
        ("ITVBe", "https://www.itv.com/watch?channel=itvbe", ""),
        ("ITV3", "https://www.itv.com/watch?channel=itv3", "ITV3.HD.uk"),
        ("ITV4", "https://www.itv.com/watch?channel=itv4", "ITV4.HD.uk"),
        ("Channel 4", "https://www.channel4.com/now/C4", "Channel.4.HD.uk"),
        ("E4", "https://www.channel4.com/now/E4", "E4.HD.uk"),
        ("More4", "https://www.channel4.com/now/M4", "More4.HD.uk"),
        ("Film4", "https://www.channel4.com/now/F4", "Film4.HD.uk"),
        ("4seven", "https://www.channel4.com/now/4S", "4seven.uk"),
        ("Channel 5", "https://www.channel5.com/live", "Channel.5.HD.uk"),
        ("S4C", "https://www.s4c.cymru/clic/live/", "S4C.HD.uk"),
        ("GB News", "https://www.gbnews.com/watch/live", "GB.News.HD.uk"),
    ],
    guide=("epgshare01-uk", "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"),
)

REGIONAL_LISTS = [FRANCE, UK]


def install_regional(sources: "ProviderList", directory: Path | None = None) -> list[str]:
    """Write and register each regional list, disabled, once.

    The same rule as install(): an existing file or an existing provider
    means it was set up before, and a user who removed it keeps it removed.
    Returns the providers that were added.
    """
    added = []
    for regional in REGIONAL_LISTS:
        path = regional.path(directory)
        if path.exists() or sources.get(regional.provider) is not None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".m3u.part")
        tmp.write_text(regional.render(), encoding="utf-8")
        tmp.replace(path)
        sources.add(regional.provider, str(path), enabled=False)
        added.append(regional.provider)
    return added


def guide_sources(sources: "ProviderList | None") -> list[tuple[str, str]]:
    """The extra guide feeds the enabled regional lists need."""
    if sources is None:
        return []
    wanted = []
    for regional in REGIONAL_LISTS:
        provider = sources.get(regional.provider)
        if provider is not None and provider.enabled:
            wanted.append(regional.guide)
    return wanted
