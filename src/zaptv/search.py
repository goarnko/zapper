"""Channel filtering.

Kept out of ui.py so the matching rules can be tested without a display.

Spanish channel names are full of accents (Andalucía, Málaga, Aragón). Users
type without them, so matching is accent-insensitive as well as
case-insensitive: "malaga" finds "101TV Málaga".
"""

import unicodedata

from .models import Channel


def normalize(text: str) -> str:
    """Casefold and strip accents, so "Málaga" and "malaga" compare equal."""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.casefold()


def matches(channel: Channel, query: str) -> bool:
    """True when every whitespace-separated token appears in name or group.

    Tokens are ANDed so a longer query narrows rather than widens, which is
    what typing more characters should do.
    """
    tokens = normalize(query).split()
    if not tokens:
        return True
    haystack = f"{normalize(channel.name)} {normalize(channel.group)}"
    return all(token in haystack for token in tokens)


def filter_channels(channels: list[Channel], query: str) -> list[Channel]:
    if not query.strip():
        return list(channels)
    return [c for c in channels if matches(c, query)]


def sort_key(channel: Channel) -> tuple[str, str]:
    """Alphabetical by name, accent- and case-insensitive."""
    return (normalize(channel.name), channel.name)
