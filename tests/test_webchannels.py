from zaptv import playlist, webchannels
from zaptv.providers import Provider, ProviderList


def test_seed_covers_atresmedia_and_mediaset():
    names = {name for name, _url, _id in webchannels.SEED_CHANNELS}
    assert {"Antena 3", "laSexta", "Neox", "Nova", "Mega", "Atreseries"} <= names
    assert {"Telecinco", "Cuatro", "FDF", "Energy", "Divinity", "Boing", "Be Mad"} <= names


def test_every_seed_entry_is_an_official_https_page():
    for _name, url, _id in webchannels.SEED_CHANNELS:
        assert url.startswith("https://")
        assert "atresplayer.com" in url or "mediasetinfinity.es" in url


def test_rendered_playlist_parses_back():
    channels = playlist.parse(webchannels.render())
    assert len(channels) == len(webchannels.SEED_CHANNELS)


def test_rendered_channels_all_request_the_browser():
    for channel in playlist.parse(webchannels.render()):
        assert channel.player == "browser"


def test_mediaset_entries_carry_a_guide_id():
    by_name = {c.name: c for c in playlist.parse(webchannels.render())}
    assert by_name["Telecinco"].tvg_id == "Telecinco.TV"
    assert by_name["Cuatro"].tvg_id == "Cuatro.TV"
    # Atresmedia is absent from the TDTChannels guide, so it has no id.
    assert by_name["Antena 3"].tvg_id is None


def test_stream_is_the_page_url():
    by_name = {c.name: c for c in playlist.parse(webchannels.render())}
    assert by_name["Antena 3"].stream == "https://www.atresplayer.com/directos/antena3/"


def test_install_creates_the_file_and_registers_it(tmp_path):
    path = tmp_path / "web.m3u"
    sources = ProviderList([], tmp_path / "p.json")

    assert webchannels.install(sources, path)
    assert path.exists()
    provider = sources.get(webchannels.PROVIDER_NAME)
    assert provider is not None
    assert provider.is_local


def test_install_is_idempotent(tmp_path):
    path = tmp_path / "web.m3u"
    sources = ProviderList([], tmp_path / "p.json")
    webchannels.install(sources, path)

    assert not webchannels.install(sources, path)
    assert len([p for p in sources if p.name == webchannels.PROVIDER_NAME]) == 1


def test_install_does_not_resurrect_a_provider_the_user_removed(tmp_path):
    """Deleting the provider is a decision, not something to undo silently."""
    path = tmp_path / "web.m3u"
    sources = ProviderList([], tmp_path / "p.json")
    webchannels.install(sources, path)
    sources.remove(webchannels.PROVIDER_NAME)

    assert not webchannels.install(sources, path)
    assert sources.get(webchannels.PROVIDER_NAME) is None


def test_install_leaves_user_edits_alone(tmp_path):
    path = tmp_path / "web.m3u"
    path.write_text("#EXTM3U\n# my own edits\n", encoding="utf-8")
    sources = ProviderList([], tmp_path / "p.json")

    assert not webchannels.install(sources, path)
    assert "my own edits" in path.read_text(encoding="utf-8")


def test_installed_channels_load_through_the_provider(tmp_path, monkeypatch):
    from zaptv import providers

    monkeypatch.setattr(providers, "migrate_legacy_cache", lambda: None)
    path = tmp_path / "web.m3u"
    webchannels.write_seed(path)
    sources = ProviderList([Provider(webchannels.PROVIDER_NAME, str(path))], tmp_path / "p.json")

    channels, failed = sources.load_channels()
    assert failed == []
    assert {c.player for c in channels} == {"browser"}
    assert {c.provider for c in channels} == {webchannels.PROVIDER_NAME}
