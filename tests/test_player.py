from zaptv import player


def test_get_player_returns_requested_backend():
    assert isinstance(player.get_player("vlc"), player.VLCPlayer)
    assert isinstance(player.get_player("mpv"), player.MPVPlayer)


def test_get_player_is_case_insensitive():
    assert isinstance(player.get_player("VLC"), player.VLCPlayer)


def test_unknown_player_falls_back_to_default():
    assert isinstance(player.get_player("nonexistent"), player.VLCPlayer)


def test_args_put_the_stream_last():
    args = player.VLCPlayer().args("https://example.invalid/s.m3u8")
    assert args[-1] == "https://example.invalid/s.m3u8"
    assert args[0].endswith("vlc")


def test_missing_executable_raises(monkeypatch):
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: None)
    instance = player.MPVPlayer()
    assert not instance.is_available()
    try:
        instance.args("https://example.invalid/s.m3u8")
    except player.PlayerNotFound as exc:
        assert "mpv" in str(exc)
    else:
        raise AssertionError("expected PlayerNotFound")


# -- browser backend ----------------------------------------------------


def test_browser_player_is_registered_but_not_user_selectable():
    assert isinstance(player.get_player("browser"), player.BrowserPlayer)
    # The browser is chosen per channel, never as a default for streams.
    assert "browser" not in player.SELECTABLE
    assert set(player.SELECTABLE) <= set(player.PLAYERS)


def test_browser_player_passes_the_page_url_through():
    args = player.BrowserPlayer().args("https://www.atresplayer.com/directos/antena3/")
    assert args[-1] == "https://www.atresplayer.com/directos/antena3/"
    assert args[0].endswith("xdg-open")


def test_browser_player_falls_back_to_webbrowser(monkeypatch):
    """Minimal desktops have no xdg-open; Python's opener knows other ways."""
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: None)
    opened = []
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    assert player.BrowserPlayer().play("https://example.invalid/live") is None
    assert opened == ["https://example.invalid/live"]


def test_browser_player_raises_when_nothing_can_open_a_page(monkeypatch):
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: None)
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda _url: False)
    try:
        player.BrowserPlayer().play("https://example.invalid/live")
    except player.PlayerNotFound:
        pass
    else:
        raise AssertionError("expected PlayerNotFound")
