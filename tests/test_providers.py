import json

from zaptv import providers, updater
from zaptv.providers import Provider, ProviderList

M3U = """#EXTM3U
#EXTINF:-1 group-title="G",Alpha
https://a.invalid/alpha.m3u8
#EXTINF:-1 group-title="G",Beta
https://a.invalid/beta.m3u8
"""


def write_playlist(tmp_path, name="list.m3u", text=M3U):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# -- slugs and paths ----------------------------------------------------


def test_slug_is_filesystem_safe():
    assert providers.slug("TDTChannels") == "tdtchannels"
    assert providers.slug("My List / 2026!") == "my-list-2026"
    assert providers.slug("Ünïcode") == "n-code"


def test_slug_never_empty():
    assert providers.slug("!!!") == "provider"
    assert providers.slug("") == "provider"


def test_local_detection():
    assert Provider("f", "/home/me/list.m3u").is_local
    assert Provider("f", "file:///home/me/list.m3u").is_local
    assert not Provider("r", "https://example.invalid/list.m3u8").is_local


def test_local_path_handles_file_urls_and_tilde():
    assert Provider("f", "file:///tmp/a.m3u").local_path.as_posix() == "/tmp/a.m3u"
    assert "~" not in Provider("f", "~/a.m3u").local_path.as_posix()


def test_providers_cache_to_separate_files():
    a = Provider("One", "https://x.invalid/1.m3u8").cache_path
    b = Provider("Two", "https://x.invalid/2.m3u8").cache_path
    assert a != b
    assert a.parent == b.parent


# -- resolving ----------------------------------------------------------


def test_local_provider_resolves_to_the_file(tmp_path):
    path = write_playlist(tmp_path)
    assert Provider("Local", str(path)).resolve() == path


def test_missing_local_file_resolves_to_none(tmp_path):
    assert Provider("Local", str(tmp_path / "absent.m3u")).resolve() is None


def test_unreachable_remote_provider_resolves_to_none(monkeypatch, tmp_path):
    provider = Provider("Remote", "https://example.invalid/list.m3u8")
    monkeypatch.setattr(type(provider), "cache_path", property(lambda _s: tmp_path / "r.m3u"))

    def explode(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(updater, "ensure", explode)
    assert provider.resolve() is None


# -- the list -----------------------------------------------------------


def test_defaults_include_the_builtin(tmp_path):
    listing = ProviderList.load(tmp_path / "absent.json")
    assert len(listing) == 1
    builtin = listing.get(providers.TDTCHANNELS_NAME)
    assert builtin is not None and builtin.builtin


def test_add_and_persist(tmp_path):
    path = tmp_path / "providers.json"
    listing = ProviderList.load(path)
    listing.add("Mine", "https://x.invalid/m.m3u8")

    reloaded = ProviderList.load(path)
    assert [p.name for p in reloaded] == [providers.TDTCHANNELS_NAME, "Mine"]
    mine = reloaded.get("Mine")
    assert mine is not None
    assert mine.url == "https://x.invalid/m.m3u8"
    assert not mine.builtin


def test_adding_an_existing_name_updates_it(tmp_path):
    listing = ProviderList.load(tmp_path / "p.json")
    listing.add("Mine", "https://x.invalid/one.m3u8")
    listing.set_enabled("Mine", False)
    listing.add("Mine", "https://x.invalid/two.m3u8")

    assert len(listing) == 2
    mine = listing.get("Mine")
    assert mine is not None
    assert mine.url == "https://x.invalid/two.m3u8"
    # Re-adding a disabled source turns it back on.
    assert mine.enabled


def test_remove(tmp_path):
    listing = ProviderList.load(tmp_path / "p.json")
    listing.add("Mine", "https://x.invalid/m.m3u8")
    assert listing.remove("Mine")
    assert listing.get("Mine") is None


def test_the_builtin_cannot_be_removed(tmp_path):
    listing = ProviderList.load(tmp_path / "p.json")
    assert not listing.remove(providers.TDTCHANNELS_NAME)
    assert listing.get(providers.TDTCHANNELS_NAME) is not None


def test_the_builtin_can_be_disabled(tmp_path):
    listing = ProviderList.load(tmp_path / "p.json")
    assert listing.set_enabled(providers.TDTCHANNELS_NAME, False)
    assert listing.enabled == []


def test_removing_an_unknown_provider_is_a_no_op(tmp_path):
    listing = ProviderList.load(tmp_path / "p.json")
    assert not listing.remove("Nope")


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("not json", encoding="utf-8")
    assert len(ProviderList.load(path)) == 1


def test_entries_without_a_name_or_url_are_dropped(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps([{"name": "Good", "url": "https://x.invalid/g"}, {"name": "NoUrl"}, {}]),
        encoding="utf-8",
    )
    listing = ProviderList.load(path)
    assert [p.name for p in listing] == [providers.TDTCHANNELS_NAME, "Good"]


def test_a_file_missing_the_builtin_regains_it(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps([{"name": "Only Mine", "url": "https://x.invalid/m"}]), encoding="utf-8"
    )
    listing = ProviderList.load(path)
    builtin = listing.get(providers.TDTCHANNELS_NAME)
    assert builtin is not None
    assert builtin.builtin


# -- loading channels ---------------------------------------------------


def test_load_channels_tags_the_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "migrate_legacy_cache", lambda: None)
    path = write_playlist(tmp_path)
    listing = ProviderList([Provider("Local", str(path))], tmp_path / "p.json")

    channels, failed = listing.load_channels()
    assert failed == []
    assert {c.provider for c in channels} == {"Local"}
    assert sorted(c.name for c in channels) == ["Alpha", "Beta"]


def test_load_channels_reports_a_broken_source(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "migrate_legacy_cache", lambda: None)
    good = write_playlist(tmp_path)
    listing = ProviderList(
        [Provider("Good", str(good)), Provider("Bad", str(tmp_path / "absent.m3u"))],
        tmp_path / "p.json",
    )

    channels, failed = listing.load_channels()
    assert failed == ["Bad"]
    # The working source still produced its channels.
    assert len(channels) == 2


def test_disabled_providers_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "migrate_legacy_cache", lambda: None)
    path = write_playlist(tmp_path)
    listing = ProviderList([Provider("Off", str(path), enabled=False)], tmp_path / "p.json")
    assert listing.load_channels() == ([], [])


def test_an_empty_playlist_counts_as_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "migrate_legacy_cache", lambda: None)
    empty = write_playlist(tmp_path, "empty.m3u", "#EXTM3U\n")
    listing = ProviderList([Provider("Empty", str(empty))], tmp_path / "p.json")
    assert listing.load_channels() == ([], ["Empty"])


# -- legacy migration ---------------------------------------------------


def test_legacy_cache_is_moved_once(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    legacy = cache / "playlist.m3u"
    legacy.write_text(M3U, encoding="utf-8")
    monkeypatch.setattr(updater, "CACHE_DIR", cache)
    monkeypatch.setattr(updater, "PLAYLIST_PATH", legacy)

    providers.migrate_legacy_cache()
    target = cache / "playlists" / "tdtchannels.m3u"
    assert target.exists()
    assert not legacy.exists()

    # Running again with no legacy file must not raise.
    providers.migrate_legacy_cache()


def test_migration_leaves_an_existing_cache_alone(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "playlists").mkdir(parents=True)
    legacy = cache / "playlist.m3u"
    legacy.write_text("legacy", encoding="utf-8")
    target = cache / "playlists" / "tdtchannels.m3u"
    target.write_text("current", encoding="utf-8")
    monkeypatch.setattr(updater, "CACHE_DIR", cache)
    monkeypatch.setattr(updater, "PLAYLIST_PATH", legacy)

    providers.migrate_legacy_cache()
    assert target.read_text(encoding="utf-8") == "current"
