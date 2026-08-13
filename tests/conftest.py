"""Keep the suite out of the developer's own config and cache.

Several code paths persist without being asked to: `Settings.save` writes
whenever a section is collapsed, `Favorites.toggle` and `Recent.push` write
on every change, and the update check caches its answer. All of them fall
back to a module-level path under ~/.config or ~/.local/share, so a test
that constructs the real object and pokes it will quietly rewrite the
developer's own files — which is exactly what happened once here, replacing
a real settings.json with test values.

Redirecting the paths for every test makes that impossible rather than
merely unlikely, and costs nothing: tests that pass an explicit path are
unaffected.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_files(tmp_path_factory, monkeypatch):
    from zaptv import settings, storage, updates

    # A directory of its own, not the test's tmp_path: tests do assert on
    # exactly what tmp_path contains, and adding to it under their feet
    # breaks them.
    base = tmp_path_factory.mktemp("userfiles")
    config = base / "config"
    data = base / "data"
    config.mkdir()
    data.mkdir()

    monkeypatch.setattr(settings, "SETTINGS_PATH", config / "settings.json")
    monkeypatch.setattr(storage, "FAVORITES_PATH", config / "favorites.json")
    monkeypatch.setattr(storage, "RECENT_PATH", config / "recent.json")
    # updates resolves its cache through a function, not a constant.
    monkeypatch.setattr(updates, "state_path", lambda: data / "update-check.json")
    yield
