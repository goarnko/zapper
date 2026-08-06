from zaptv.settings import Settings


def test_defaults():
    config = Settings()
    assert config.player == "vlc"
    assert config.auto_update is True


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    Settings(player="mpv", auto_update=False).save(path)
    assert Settings.load(path) == Settings(player="mpv", auto_update=False)


def test_missing_file_falls_back_to_defaults(tmp_path):
    assert Settings.load(tmp_path / "absent.json") == Settings()


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"player": "mpv", "from_the_future": 1}', encoding="utf-8")
    assert Settings.load(path) == Settings(player="mpv")
