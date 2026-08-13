import gzip
import io
from datetime import datetime, timedelta, timezone

from zaptv import epg
from zaptv.models import Programme

XML = """<?xml version='1.0' encoding='utf-8'?>
<tv>
  <channel id="La1.TV"><display-name>La 1</display-name></channel>
  <programme channel="La1.TV" start="20260806050000 +0000" stop="20260806063000 +0000">
    <title>Telediario Matinal</title>
    <desc>Las noticias de la mañana.</desc>
    <category>NEWS</category>
  </programme>
  <programme channel="La1.TV" start="20260806063000 +0000" stop="20260806080000 +0000">
    <title>La hora de La 1</title>
  </programme>
  <programme channel="La2.TV" start="20260806050000 +0000" stop="20260806060000 +0000">
    <title>Documental</title>
  </programme>
</tv>
"""


def at(hour, minute=0):
    return datetime(2026, 8, 6, hour, minute, tzinfo=timezone.utc)


def guide():
    return epg.parse(io.StringIO(XML))


# -- timestamps ---------------------------------------------------------


def test_timestamp_with_offset():
    parsed = epg.parse_timestamp("20260806050000 +0200")
    assert parsed == datetime(2026, 8, 6, 5, tzinfo=timezone(timedelta(hours=2)))


def test_timestamp_without_offset_is_utc():
    assert epg.parse_timestamp("20260806050000") == at(5)


def test_truncated_timestamp_is_padded():
    assert epg.parse_timestamp("20260806") == at(0)


def test_unparseable_timestamps_return_none():
    for value in ["", "not-a-date", "2026080605000099999", "20261306050000"]:
        assert epg.parse_timestamp(value) is None


def test_bad_offset_falls_back_to_utc():
    assert epg.parse_timestamp("20260806050000 nonsense") == at(5)


# -- parsing ------------------------------------------------------------


def test_parses_fields():
    programme, _ = guide().now_and_next("La1.TV", at(5, 30))
    assert programme is not None
    assert programme.title == "Telediario Matinal"
    assert programme.description == "Las noticias de la mañana."
    assert programme.category == "NEWS"
    assert programme.end == at(6, 30)


def test_counts_all_programmes():
    assert len(guide()) == 3


def test_programmes_without_a_title_are_skipped():
    xml = '<tv><programme channel="X" start="20260806050000"></programme></tv>'
    assert len(epg.parse(io.StringIO(xml))) == 0


def test_programmes_without_a_start_are_skipped():
    xml = '<tv><programme channel="X"><title>T</title></programme></tv>'
    assert len(epg.parse(io.StringIO(xml))) == 0


# -- now and next -------------------------------------------------------


def test_now_and_next():
    current, following = guide().now_and_next("La1.TV", at(5, 30))
    assert current is not None and following is not None
    assert current.title == "Telediario Matinal"
    assert following.title == "La hora de La 1"


def test_start_boundary_is_inclusive():
    current, _ = guide().now_and_next("La1.TV", at(6, 30))
    assert current is not None
    assert current.title == "La hora de La 1"


def test_gap_before_the_schedule_has_no_current_programme():
    current, following = guide().now_and_next("La1.TV", at(4))
    assert current is None
    assert following is not None
    assert following.title == "Telediario Matinal"


def test_after_the_schedule_ends_there_is_nothing():
    assert guide().now_and_next("La1.TV", at(23)) == (None, None)


def test_unknown_channel_returns_nothing():
    assert guide().now_and_next("Nope.TV", at(5, 30)) == (None, None)


def test_channel_without_a_tvg_id_returns_nothing():
    assert guide().now_and_next(None, at(5, 30)) == (None, None)


def test_gap_between_programmes_has_no_current():
    programmes = {
        "X": [
            Programme("X", "A", at(5), at(6)),
            Programme("X", "B", at(8), at(9)),
        ]
    }
    current, following = epg.Guide(programmes).now_and_next("X", at(7))
    assert current is None
    assert following is not None
    assert following.title == "B"


def test_programme_without_an_end_stays_live():
    programmes = {"X": [Programme("X", "Open ended", at(5), None)]}
    current, _ = epg.Guide(programmes).now_and_next("X", at(23))
    assert current is not None
    assert current.title == "Open ended"


def test_programmes_are_sorted_regardless_of_input_order():
    programmes = {
        "X": [
            Programme("X", "Second", at(6), at(7)),
            Programme("X", "First", at(5), at(6)),
        ]
    }
    current, following = epg.Guide(programmes).now_and_next("X", at(5, 30))
    assert current is not None and following is not None
    assert (current.title, following.title) == ("First", "Second")


# -- upcoming -----------------------------------------------------------


def test_upcoming_returns_future_programmes_only():
    upcoming = guide().upcoming("La1.TV", at(5, 30))
    assert [p.title for p in upcoming] == ["La hora de La 1"]


def test_upcoming_respects_the_limit():
    programmes = {"X": [Programme("X", f"P{i}", at(5 + i), at(6 + i)) for i in range(6)]}
    assert len(epg.Guide(programmes).upcoming("X", at(4), limit=3)) == 3


def test_upcoming_for_unknown_channel_is_empty():
    assert guide().upcoming("Nope.TV", at(5)) == []


# -- loading ------------------------------------------------------------


def test_loads_gzipped_file(tmp_path):
    path = tmp_path / "epg.xml.gz"
    path.write_bytes(gzip.compress(XML.encode("utf-8")))
    assert len(epg.load(path)) == 3


def test_loads_plain_xml_file(tmp_path):
    path = tmp_path / "epg.xml"
    path.write_text(XML, encoding="utf-8")
    assert len(epg.load(path)) == 3


def test_corrupt_file_gives_an_empty_guide(tmp_path):
    path = tmp_path / "epg.xml"
    path.write_text("<tv><programme>truncated", encoding="utf-8")
    assert len(epg.load(path)) == 0


def test_missing_file_gives_an_empty_guide(tmp_path):
    assert len(epg.load(tmp_path / "absent.xml.gz")) == 0


def test_empty_guide_answers_safely():
    assert epg.Guide().now_and_next("La1.TV") == (None, None)
    assert epg.Guide().has(None) is False


# -- merging several sources --------------------------------------------

SECOND_XML = """<?xml version='1.0' encoding='utf-8'?>
<tv>
  <channel id="Antena.3.es"><display-name>Antena 3</display-name></channel>
  <programme channel="Antena.3.es" start="20260806050000 +0000" stop="20260806060000 +0000">
    <title>Espejo Público</title>
  </programme>
  <programme channel="La1.TV" start="20260806050000 +0000" stop="20260806060000 +0000">
    <title>Something else entirely</title>
  </programme>
</tv>
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_bytes(gzip.compress(text.encode("utf-8")))
    return path


def test_load_all_merges_channels_from_every_source(tmp_path):
    first = _write(tmp_path, "a.xml.gz", XML)
    second = _write(tmp_path, "b.xml.gz", SECOND_XML)
    merged = epg.load_all([first, second])
    assert merged.channels == {"La1.TV", "La2.TV", "Antena.3.es"}


def test_load_all_lets_the_first_source_own_a_shared_channel(tmp_path):
    """Two schedules for one channel would overlap on the grid."""
    first = _write(tmp_path, "a.xml.gz", XML)
    second = _write(tmp_path, "b.xml.gz", SECOND_XML)

    merged = epg.load_all([first, second])
    current, _ = merged.now_and_next("La1.TV", at(5, 30))
    assert current is not None and current.title == "Telediario Matinal"
    # ...and the loser's programme is not smuggled in alongside it.
    assert len(merged.between("La1.TV", at(5), at(6))) == 1

    # Reversing the order reverses who wins, so this is order, not luck.
    other = epg.load_all([second, first])
    won, _ = other.now_and_next("La1.TV", at(5, 30))
    assert won is not None and won.title == "Something else entirely"


def test_load_all_skips_an_unreadable_source(tmp_path):
    good = _write(tmp_path, "a.xml.gz", XML)
    bad = tmp_path / "b.xml.gz"
    bad.write_text("not xml at all", encoding="utf-8")
    merged = epg.load_all([good, bad, tmp_path / "absent.xml.gz"])
    assert merged.channels == {"La1.TV", "La2.TV"}


def test_load_all_of_nothing_is_an_empty_guide():
    assert len(epg.load_all([])) == 0
