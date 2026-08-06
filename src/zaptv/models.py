"""Core data types.

A `Channel` is a logical channel, not a playlist entry. The TDTChannels
playlist lists the same channel several times, once per mirror, so each
`Channel` holds every stream URL that was published for it.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Channel:
    name: str
    group: str
    streams: list[str] = field(default_factory=list)
    logo: str | None = None
    tvg_id: str | None = None
    favorite: bool = False
    #: Name of the provider this channel came from. When the same channel is
    #: offered by several sources, this is the first one that supplied it.
    provider: str = ""

    @property
    def stream(self) -> str:
        """Preferred stream. Mirrors are ordered as the playlist listed them."""
        return self.streams[0]


@dataclass
class Programme:
    """One entry from the XMLTV guide.

    `channel` is the XMLTV channel id, which is what `Channel.tvg_id` holds
    when the playlist bothered to supply one. `end` is optional: XMLTV allows
    a programme with no stop time, which then runs until the next one starts.
    """

    channel: str
    title: str
    start: datetime
    end: datetime | None = None
    description: str = ""
    category: str = ""

    def is_live(self, at: datetime) -> bool:
        if at < self.start:
            return False
        return self.end is None or at < self.end
