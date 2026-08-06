import io

from PIL import Image

from zaptv import logos, updater


def png_bytes(size=(200, 120), mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, (10, 120, 200)).save(buffer, "PNG")
    return buffer.getvalue()


def jpeg_bytes(size=(200, 120)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_cache_path_is_stable_and_url_specific():
    a = logos.cache_path("https://example.invalid/a.png")
    b = logos.cache_path("https://example.invalid/a.png")
    c = logos.cache_path("https://example.invalid/b.png")
    assert a == b
    assert a != c
    assert a.suffix == ".png"


def test_cache_path_survives_query_strings():
    path = logos.cache_path("https://example.invalid/pic?width=200&height=200")
    assert "?" not in path.name
    assert "&" not in path.name


def test_cache_path_changes_with_size():
    url = "https://x.invalid/a"
    assert logos.cache_path(url, 24) != logos.cache_path(url, 48)


def test_convert_writes_a_downscaled_png(tmp_path):
    out = logos.convert(jpeg_bytes(), tmp_path / "logo.png", size=24)
    with Image.open(out) as image:
        assert image.format == "PNG"
        assert max(image.size) == 24
        # Aspect ratio is kept rather than squashed.
        assert image.size == (24, 14)


def test_convert_handles_png_input(tmp_path):
    out = logos.convert(png_bytes(), tmp_path / "logo.png", size=24)
    with Image.open(out) as image:
        assert image.format == "PNG"


def test_convert_leaves_no_partial_file(tmp_path):
    logos.convert(jpeg_bytes(), tmp_path / "logo.png", size=24)
    assert [p.name for p in tmp_path.iterdir()] == ["logo.png"]


def test_prepare_reuses_the_cache_without_downloading(tmp_path, monkeypatch):
    path = tmp_path / "cached.png"
    logos.convert(png_bytes(), path, size=24)

    monkeypatch.setattr(logos, "cache_path", lambda _url, _size=24: path)

    def explode(*_a, **_k):
        raise AssertionError("should not download when cached")

    monkeypatch.setattr(updater, "fetch", explode)
    assert logos.prepare("https://example.invalid/a.png") == path


def test_prepare_returns_none_on_a_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "cache_path", lambda _url, _size=24: tmp_path / "x.png")

    def explode(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(updater, "fetch", explode)
    assert logos.prepare("https://example.invalid/a.png") is None


def test_prepare_returns_none_on_undecodable_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "cache_path", lambda _url, _size=24: tmp_path / "x.png")
    monkeypatch.setattr(updater, "fetch", lambda *_a, **_k: b"<html>not an image</html>")
    assert logos.prepare("https://example.invalid/a.png") is None


def test_store_serves_an_already_cached_logo_without_a_worker(tmp_path, monkeypatch):
    url = "https://example.invalid/a.png"
    path = tmp_path / "cached.png"
    logos.convert(png_bytes(), path, size=24)
    monkeypatch.setattr(logos, "cache_path", lambda _url, _size=24: path)

    store = logos.LogoStore(workers=0)
    try:
        assert store.path_for(url) == path
    finally:
        store.stop()


def test_store_ignores_channels_without_a_logo():
    store = logos.LogoStore(workers=0)
    try:
        assert store.path_for(None) is None
        assert store.path_for("") is None
    finally:
        store.stop()


def test_store_queues_a_missing_logo_once(tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "cache_path", lambda _url, _size=24: tmp_path / "absent.png")
    store = logos.LogoStore(workers=0)
    try:
        assert store.path_for("https://example.invalid/a.png") is None
        assert store.path_for("https://example.invalid/a.png") is None
        assert store._work.qsize() == 1
    finally:
        store.stop()


def test_drain_is_empty_when_nothing_finished():
    store = logos.LogoStore(workers=0)
    try:
        assert store.drain() == []
    finally:
        store.stop()
