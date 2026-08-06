import json
import queue
import urllib.request

from zaptv import updates
from zaptv.updates import Release

# -- version comparison -------------------------------------------------


def test_parse_version_strips_the_tag_prefix():
    assert updates.parse_version("v0.2.1") == (0, 2, 1)
    assert updates.parse_version("0.2.1") == (0, 2, 1)


def test_parse_version_drops_prerelease_and_build_metadata():
    assert updates.parse_version("1.2.0-rc1") == (1, 2, 0)
    assert updates.parse_version("1.2.0+build7") == (1, 2, 0)


def test_parse_version_stops_at_the_first_non_numeric_part():
    assert updates.parse_version("1.2.x") == (1, 2)
    assert updates.parse_version("nonsense") == ()


def test_newer_versions_are_detected():
    assert updates.is_newer("v0.2.0", "0.1.0")
    assert updates.is_newer("v1.0.0", "0.9.9")
    assert updates.is_newer("v0.1.1", "0.1.0")


def test_same_or_older_versions_are_not():
    assert not updates.is_newer("v0.1.0", "0.1.0")
    assert not updates.is_newer("v0.1.0", "0.2.0")
    assert not updates.is_newer("v0.1.0", "1.0.0")


def test_trailing_zeros_do_not_count_as_newer():
    assert not updates.is_newer("v0.2.0", "0.2")
    assert not updates.is_newer("v0.2", "0.2.0")


def test_an_unparseable_tag_is_never_newer():
    """Better to say nothing than to nag about a release that may not exist."""
    assert not updates.is_newer("garbage", "0.1.0")
    assert not updates.is_newer("", "0.1.0")


def test_a_prerelease_does_not_look_newer_than_its_release():
    assert not updates.is_newer("1.0.0-rc1", "1.0.0")


# -- fetching -----------------------------------------------------------


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def fake_urlopen(payload, monkeypatch):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(body)
    )


def test_fetch_reads_the_tag_and_link(monkeypatch):
    fake_urlopen({"tag_name": "v0.2.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    assert updates.fetch_latest() == Release("v0.2.0", "https://example.invalid/r")


def test_fetch_falls_back_to_the_releases_page(monkeypatch):
    fake_urlopen({"tag_name": "v0.2.0"}, monkeypatch)
    release = updates.fetch_latest()
    assert release is not None
    assert release.url == updates.RELEASES_URL


def test_fetch_returns_none_without_a_tag(monkeypatch):
    fake_urlopen({"html_url": "https://example.invalid/r"}, monkeypatch)
    assert updates.fetch_latest() is None


def test_fetch_survives_a_network_error(monkeypatch):
    def explode(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    assert updates.fetch_latest() is None


def test_fetch_survives_junk(monkeypatch):
    fake_urlopen(b"<html>not json</html>", monkeypatch)
    assert updates.fetch_latest() is None


# -- checking and caching -----------------------------------------------


def test_check_reports_a_newer_release(tmp_path, monkeypatch):
    fake_urlopen({"tag_name": "v0.2.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    release = updates.check("0.1.0", tmp_path / "state.json")
    assert release is not None
    assert release.version == "v0.2.0"


def test_check_is_silent_when_current(tmp_path, monkeypatch):
    fake_urlopen({"tag_name": "v0.1.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    assert updates.check("0.1.0", tmp_path / "state.json") is None


def test_check_writes_its_answer_to_the_cache(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    fake_urlopen({"tag_name": "v0.2.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    updates.check("0.1.0", path)

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["version"] == "v0.2.0"
    assert "checked_at" in state


def test_a_fresh_cache_is_used_instead_of_the_network(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"checked_at": 1000.0, "version": "v0.3.0", "url": "https://x.invalid/r"}),
        encoding="utf-8",
    )

    def explode(*_a, **_k):
        raise AssertionError("should not ask GitHub while the cache is fresh")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    release = updates.check("0.1.0", path, interval=100, now=1050.0)
    assert release is not None
    assert release.version == "v0.3.0"


def test_a_stale_cache_triggers_a_new_request(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"checked_at": 1000.0, "version": "v0.2.0", "url": "https://x.invalid/r"}),
        encoding="utf-8",
    )
    fake_urlopen({"tag_name": "v0.4.0", "html_url": "https://example.invalid/r"}, monkeypatch)

    release = updates.check("0.1.0", path, interval=100, now=5000.0)
    assert release is not None
    assert release.version == "v0.4.0"


def test_a_corrupt_cache_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    fake_urlopen({"tag_name": "v0.2.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    assert updates.check("0.1.0", path) is not None


def test_check_is_silent_when_github_is_unreachable(tmp_path, monkeypatch):
    """A private repo, an outage or no network must all just say nothing."""

    def explode(*_a, **_k):
        raise OSError("404")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    assert updates.check("0.1.0", tmp_path / "state.json") is None


def test_check_async_delivers_on_a_queue(tmp_path, monkeypatch):
    fake_urlopen({"tag_name": "v0.9.0", "html_url": "https://example.invalid/r"}, monkeypatch)
    monkeypatch.setattr(updates, "state_path", lambda: tmp_path / "state.json")

    result = updates.check_async("0.1.0")
    try:
        release = result.get(timeout=10)
    except queue.Empty:
        raise AssertionError("the check never reported back") from None
    assert release is not None
    assert release.version == "v0.9.0"
