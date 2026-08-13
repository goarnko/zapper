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


def test_collapsed_groups_default_to_none_collapsed():
    assert Settings().collapsed_groups == []


def test_collapsed_groups_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    Settings(collapsed_groups=["ANDALUCÍA", "MUSICALES"]).save(path)
    assert Settings.load(path).collapsed_groups == ["ANDALUCÍA", "MUSICALES"]


def test_a_settings_file_without_the_key_collapses_nothing(tmp_path):
    """Upgrading must not suddenly hide every group."""
    path = tmp_path / "settings.json"
    path.write_text('{"player": "mpv", "theme": "dark"}', encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.collapsed_groups == []
    assert loaded.player == "mpv"


def test_a_string_instead_of_a_list_is_ignored(tmp_path):
    """It would otherwise iterate as characters and collapse "A", "n", "d"..."""
    path = tmp_path / "settings.json"
    path.write_text('{"collapsed_groups": "ANDALUCIA"}', encoding="utf-8")
    assert Settings.load(path).collapsed_groups == []


def test_a_list_of_non_strings_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"collapsed_groups": [1, 2, null]}', encoding="utf-8")
    assert Settings.load(path).collapsed_groups == []
