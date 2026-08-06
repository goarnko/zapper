"""Core data types.

A `Channel` is a logical channel, not a playlist entry. The TDTChannels
playlist lists the same channel several times, once per mirror, so each
`Channel` holds every stream URL that was published for it.
"""

from dataclasses import dataclass, field


@dataclass
class Channel:
    name: str
    group: str
    streams: list[str] = field(default_factory=list)
    logo: str | None = None
    tvg_id: str | None = None
    favorite: bool = False

    @property
    def stream(self) -> str:
        """Preferred stream. Mirrors are ordered as the playlist listed them."""
        return self.streams[0]
