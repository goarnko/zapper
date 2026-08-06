"""Playlist sources.

A provider is just a named M3U source: a URL to download or a local file to
read. TDTChannels ships as a built-in so a fresh install still works with no
configuration, and users can add their own lists alongside it.

Each provider caches to its own file, so one unreachable source never
invalidates another's channels.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlparse

from . import updater
from .models import Channel
from .settings import config_dir

PROVIDERS_PATH = config_dir() / "providers.json"

TDTCHANNELS_NAME = "TDTChannels"

#: Effectively infinite age, used to read caches without refreshing them.
_NEVER_STALE = 10**9

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    """Filesystem-safe id for a provider name."""
    cleaned = _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")
    return cleaned or "provider"


@dataclass
class Provider:
    name: str
    url: str
    enabled: bool = True
    #: Built-ins cannot be deleted, only disabled — losing TDTChannels by
    #: accident would leave a new user with an empty app and no way back.
    builtin: bool = False

    @property
    def slug(self) -> str:
        return slug(self.name)

    @property
    def is_local(self) -> bool:
        """True when the source is a file on disk rather than a download."""
        parsed = urlparse(self.url)
        return parsed.scheme in ("", "file")

    @property
    def local_path(self) -> Path:
        parsed = urlparse(self.url)
        return Path(parsed.path if parsed.scheme == "file" else self.url).expanduser()

    @property
    def cache_path(self) -> Path:
        return updater.CACHE_DIR / "playlists" / f"{self.slug}.m3u"

    def resolve(self, max_age: int = updater.MAX_AGE_SECONDS) -> Path | None:
        """Path to a readable playlist for this provider, or None.

        Local files are read where they are; remote ones are downloaded to
        this provider's own cache. Returns None rather than raising so one
        broken source cannot stop the app from starting.
        """
        if self.is_local:
            path = self.local_path
            return path if path.exists() else None
        try:
            return updater.ensure(self.cache_path, max_age, self.url)
        except OSError:
            return None


def migrate_legacy_cache() -> None:
    """Move the pre-Milestone-5 single playlist into the built-in's cache.

    Before providers existed everything lived in one playlist.m3u. Moving it
    saves a fresh download on first run after upgrading; if anything goes
    wrong the file is simply left alone and re-fetched.
    """
    legacy = updater.PLAYLIST_PATH
    target = updater.CACHE_DIR / "playlists" / f"{slug(TDTCHANNELS_NAME)}.m3u"
    if not legacy.exists() or target.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(target)
    except OSError:
        pass


def default_providers() -> list[Provider]:
    return [
        Provider(
            name=TDTCHANNELS_NAME,
            url=updater.PLAYLIST_URL,
            enabled=True,
            builtin=True,
        )
    ]


class ProviderList:
    """The configured sources, persisted as JSON."""

    def __init__(self, providers: list[Provider] | None = None, path: Path | None = None):
        self.path = path or PROVIDERS_PATH
        self._providers = providers if providers is not None else default_providers()

    # -- persistence -----------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> "ProviderList":
        """Read the provider list, falling back to the built-in default.

        A corrupt file must not leave the user with no channels, so anything
        unreadable yields the default list.
        """
        path = path or PROVIDERS_PATH
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(None, path)

        if not isinstance(data, list):
            return cls(None, path)

        known = {f.name for f in fields(Provider)}
        providers = []
        for item in data:
            if not isinstance(item, dict) or not item.get("name") or not item.get("url"):
                continue
            providers.append(Provider(**{k: v for k, v in item.items() if k in known}))

        if not providers:
            return cls(None, path)

        # The built-in must always be present, even if an old file predates it.
        if not any(p.builtin for p in providers):
            providers = default_providers() + providers
        return cls(providers, path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.part")
        payload = json.dumps([asdict(p) for p in self._providers], indent=2, ensure_ascii=False)
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(self.path)

    # -- collection ------------------------------------------------------

    def __iter__(self) -> Iterator[Provider]:
        return iter(self._providers)

    def __len__(self) -> int:
        return len(self._providers)

    @property
    def enabled(self) -> list[Provider]:
        return [p for p in self._providers if p.enabled]

    def get(self, name: str) -> Provider | None:
        return next((p for p in self._providers if p.name == name), None)

    def add(self, name: str, url: str) -> Provider:
        """Add a source. Names are unique, so a repeat updates the URL."""
        name = name.strip() or url
        existing = self.get(name)
        if existing is not None:
            existing.url = url
            existing.enabled = True
            self.save()
            return existing

        provider = Provider(name=name, url=url)
        self._providers.append(provider)
        self.save()
        return provider

    def remove(self, name: str) -> bool:
        provider = self.get(name)
        if provider is None or provider.builtin:
            return False
        self._providers.remove(provider)
        self.save()
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        provider = self.get(name)
        if provider is None:
            return False
        provider.enabled = enabled
        self.save()
        return True

    # -- loading ---------------------------------------------------------

    def load_channels(
        self, max_age: int = updater.MAX_AGE_SECONDS, refresh: bool = True
    ) -> tuple[list[Channel], list[str]]:
        """Channels from every enabled provider, merged.

        Returns the channels and the names of providers that yielded nothing,
        so the UI can say which source is broken instead of silently showing
        a shorter list.
        """
        from . import playlist

        migrate_legacy_cache()

        sources: list[list[Channel]] = []
        failed: list[str] = []
        for provider in self.enabled:
            path = provider.resolve(max_age if refresh else _NEVER_STALE)
            if path is None:
                failed.append(provider.name)
                continue
            try:
                channels = playlist.load(path, provider.name)
            except OSError:
                failed.append(provider.name)
                continue
            if channels:
                sources.append(channels)
            else:
                failed.append(provider.name)

        return playlist.merge(sources), failed
