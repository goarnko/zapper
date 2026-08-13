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


def test_every_seed_entry_carries_a_guide_id():
    """The ids come from two different feeds, which share no ids at all.

    Mediaset's are TDTChannels'; Atresmedia is absent from that feed
    entirely, so theirs come from the second source in updater.EPG_SOURCES.
    """
    by_name = {c.name: c for c in playlist.parse(webchannels.render())}
    assert by_name["Telecinco"].tvg_id == "Telecinco.TV"
    assert by_name["Cuatro"].tvg_id == "Cuatro.TV"
    assert by_name["Antena 3"].tvg_id == "Antena.3.es"
    assert by_name["Atreseries"].tvg_id == "Atreseries.es"
    assert all(c.tvg_id for c in playlist.parse(webchannels.render()))


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


# -- upgrading an existing seed -----------------------------------------


def _legacy_seed():
    """The seed exactly as it was written before Atresmedia had guide ids."""
    legacy = [
        (name, url, "" if "atresplayer.com" in url else tvg_id)
        for name, url, tvg_id in webchannels.SEED_CHANNELS
    ]
    return webchannels.render(legacy)


def test_upgrade_adds_the_atresmedia_guide_ids(tmp_path):
    path = tmp_path / "web-channels.m3u"
    path.write_text(_legacy_seed(), encoding="utf-8")

    assert webchannels.upgrade_seed(path) == 6

    channels = playlist.parse(path.read_text(encoding="utf-8"))
    by_name = {c.name: c for c in channels}
    assert by_name["Antena 3"].tvg_id == "Antena.3.es"
    assert by_name["laSexta"].tvg_id == "laSexta.es"
    # Mediaset already had ids and must be untouched.
    assert by_name["Telecinco"].tvg_id == "Telecinco.TV"


def test_upgrade_is_idempotent(tmp_path):
    path = tmp_path / "web-channels.m3u"
    path.write_text(_legacy_seed(), encoding="utf-8")
    webchannels.upgrade_seed(path)
    before = path.read_text(encoding="utf-8")

    assert webchannels.upgrade_seed(path) == 0
    assert path.read_text(encoding="utf-8") == before


def test_upgrade_leaves_a_line_the_user_edited_alone(tmp_path):
    """The file is the user's; a touched line keeps no guide rather than
    being silently rewritten."""
    path = tmp_path / "web-channels.m3u"
    edited = _legacy_seed().replace(
        'group-title="Generalistas",Antena 3', 'group-title="Mis canales",Antena 3'
    )
    path.write_text(edited, encoding="utf-8")

    assert webchannels.upgrade_seed(path) == 5

    by_name = {c.name: c for c in playlist.parse(path.read_text(encoding="utf-8"))}
    assert by_name["Antena 3"].tvg_id is None
    assert by_name["Antena 3"].group == "Mis canales"
    assert by_name["Neox"].tvg_id == "Neox.es"


def test_upgrade_of_a_missing_file_does_nothing(tmp_path):
    assert webchannels.upgrade_seed(tmp_path / "absent.m3u") == 0


def test_a_fresh_seed_needs_no_upgrade(tmp_path):
    path = webchannels.write_seed(tmp_path / "web-channels.m3u")
    assert webchannels.upgrade_seed(path) == 0
