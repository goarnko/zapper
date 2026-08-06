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


# -- detection and resolution -------------------------------------------


def test_available_lists_only_installed_backends(monkeypatch):
    monkeypatch.setattr(player.shutil, "which", lambda cmd: "/usr/bin/vlc" if cmd == "vlc" else None)
    assert player.available() == ["vlc"]


def test_available_can_be_empty(monkeypatch):
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: None)
    assert player.available() == []


def test_resolve_keeps_an_installed_choice(monkeypatch):
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: "/usr/bin/x")
    assert isinstance(player.resolve("mpv"), player.MPVPlayer)


def test_resolve_substitutes_an_uninstalled_choice(monkeypatch):
    """A player removed after being configured must not fail at play time."""
    monkeypatch.setattr(player.shutil, "which", lambda cmd: "/usr/bin/vlc" if cmd == "vlc" else None)
    assert isinstance(player.resolve("mpv"), player.VLCPlayer)


def test_resolve_returns_the_request_when_nothing_is_installed(monkeypatch):
    """So the eventual error names the player the user actually chose."""
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: None)
    resolved = player.resolve("mpv")
    assert isinstance(resolved, player.MPVPlayer)
    try:
        resolved.args("https://example.invalid/s")
    except player.PlayerNotFound as exc:
        assert "mpv" in str(exc)
    else:
        raise AssertionError("expected PlayerNotFound")


def test_resolve_never_substitutes_the_browser(monkeypatch):
    """The browser is per-channel only; it must not become a stream default."""
    monkeypatch.setattr(
        player.shutil, "which", lambda cmd: "/usr/bin/xdg-open" if cmd == "xdg-open" else None
    )
    assert not isinstance(player.resolve("vlc"), player.BrowserPlayer)


def test_mpv_runs_without_a_terminal(monkeypatch):
    """Spawned detached with no tty, mpv must not try to drive one."""
    monkeypatch.setattr(player.shutil, "which", lambda _cmd: "/usr/bin/mpv")
    args = player.MPVPlayer().args("https://example.invalid/s")
    assert "--no-terminal" in args
    # The URL still goes last, where every player expects it.
    assert args[-1] == "https://example.invalid/s"
