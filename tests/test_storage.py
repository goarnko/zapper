import json

from zaptv.storage import Favorites, Recent


def test_favorites_toggle_round_trips(tmp_path):
    path = tmp_path / "favorites.json"
    favorites = Favorites(path=path)

    assert favorites.toggle("La 1") is True
    assert "La 1" in favorites
    assert "La 1" in Favorites.load(path)

    assert favorites.toggle("La 1") is False
    assert "La 1" not in Favorites.load(path)


def test_favorites_file_is_a_plain_name_list(tmp_path):
    path = tmp_path / "favorites.json"
    favorites = Favorites(path=path)
    favorites.toggle("La 2")
    favorites.toggle("La 1")
    assert json.loads(path.read_text(encoding="utf-8")) == ["La 1", "La 2"]


def test_favorites_survive_a_corrupt_file(tmp_path):
    path = tmp_path / "favorites.json"
    path.write_text("not json at all", encoding="utf-8")
    assert len(Favorites.load(path)) == 0


def test_favorites_ignore_non_string_entries(tmp_path):
    path = tmp_path / "favorites.json"
    path.write_text('["La 1", 42, null]', encoding="utf-8")
    favorites = Favorites.load(path)
    assert len(favorites) == 1
    assert "La 1" in favorites


def test_recent_puts_newest_first(tmp_path):
    recent = Recent(path=tmp_path / "recent.json")
    recent.push("La 1")
    recent.push("La 2")
    assert recent.names == ["La 2", "La 1"]


def test_recent_moves_a_repeat_to_the_front_without_duplicating(tmp_path):
    recent = Recent(path=tmp_path / "recent.json")
    recent.push("La 1")
    recent.push("La 2")
    recent.push("La 1")
    assert recent.names == ["La 1", "La 2"]


def test_recent_is_capped(tmp_path):
    recent = Recent(path=tmp_path / "recent.json", limit=3)
    for name in ["A", "B", "C", "D"]:
        recent.push(name)
    assert recent.names == ["D", "C", "B"]


def test_recent_persists(tmp_path):
    path = tmp_path / "recent.json"
    Recent(path=path).push("La 1")
    assert Recent.load(path).names == ["La 1"]


def test_recent_load_truncates_an_oversized_file(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text(json.dumps([f"C{i}" for i in range(50)]), encoding="utf-8")
    assert len(Recent.load(path, limit=10)) == 10
