from zaptv import search
from zaptv.models import Channel


def channel(name, group="Generalistas"):
    return Channel(name=name, group=group, streams=["https://example.invalid/s.m3u8"])


def test_normalize_strips_accents_and_case():
    assert search.normalize("Málaga") == "malaga"
    assert search.normalize("ARAGÓN") == "aragon"


def test_prefix_search_matches():
    channels = [channel("Clan"), channel("Classic TV"), channel("La 1")]
    assert [c.name for c in search.filter_channels(channels, "cla")] == ["Clan", "Classic TV"]


def test_search_is_accent_insensitive_both_ways():
    channels = [channel("101TV Málaga")]
    assert search.filter_channels(channels, "malaga")
    assert search.filter_channels(channels, "Málaga")


def test_search_matches_group_too():
    channels = [channel("Canal Sur", group="Andalucía")]
    assert search.filter_channels(channels, "andalucia")


def test_multiple_tokens_narrow_the_result():
    channels = [channel("101TV Málaga"), channel("101TV Sevilla")]
    assert len(search.filter_channels(channels, "101tv")) == 2
    assert len(search.filter_channels(channels, "101tv sevilla")) == 1


def test_tokens_match_in_any_order():
    channels = [channel("101TV Málaga")]
    assert search.filter_channels(channels, "malaga 101tv")


def test_empty_query_returns_everything():
    channels = [channel("A"), channel("B")]
    assert len(search.filter_channels(channels, "")) == 2
    assert len(search.filter_channels(channels, "   ")) == 2


def test_no_match_returns_empty():
    assert search.filter_channels([channel("La 1")], "zzz") == []


def test_sort_key_orders_accented_names_naturally():
    names = ["Ávila", "Zamora", "Barcelona"]
    ordered = sorted((channel(n) for n in names), key=search.sort_key)
    assert [c.name for c in ordered] == ["Ávila", "Barcelona", "Zamora"]
