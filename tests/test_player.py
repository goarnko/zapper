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
