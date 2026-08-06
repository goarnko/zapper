from zaptv import playlist

BASIC = """#EXTM3U
#EXTINF:-1 tvg-id="La1.TV" tvg-logo="http://x/la1.png" group-title="Generalistas",La 1
https://example.invalid/la1.m3u8
"""


def test_parses_attributes_and_name():
    (channel,) = playlist.parse(BASIC)
    assert channel.name == "La 1"
    assert channel.group == "Generalistas"
    assert channel.tvg_id == "La1.TV"
    assert channel.logo == "http://x/la1.png"
    assert channel.stream == "https://example.invalid/la1.m3u8"


def test_commas_inside_attribute_values_do_not_split_the_name():
    text = (
        '#EXTINF:-1 tvg-logo="http://x/fill/w_200,h_200,q_85/logo.png" '
        'group-title="Cantabria",Tevecan 9\n'
        "https://example.invalid/t9.m3u8\n"
    )
    (channel,) = playlist.parse(text)
    assert channel.name == "Tevecan 9"
    assert channel.logo == "http://x/fill/w_200,h_200,q_85/logo.png"


def test_mirrors_of_one_channel_collapse_into_a_single_entry():
    text = (
        '#EXTINF:-1 group-title="Generalistas",La 1\n'
        "https://a.invalid/la1.m3u8\n"
        '#EXTINF:-1 group-title="Generalistas",La 1\n'
        "https://b.invalid/la1.m3u8\n"
    )
    (channel,) = playlist.parse(text)
    assert channel.streams == ["https://a.invalid/la1.m3u8", "https://b.invalid/la1.m3u8"]
    assert channel.stream == "https://a.invalid/la1.m3u8"


def test_duplicate_stream_urls_are_not_repeated():
    text = (
        '#EXTINF:-1 group-title="G",X\n'
        "https://a.invalid/x.m3u8\n"
        '#EXTINF:-1 group-title="G",X\n'
        "https://a.invalid/x.m3u8\n"
    )
    (channel,) = playlist.parse(text)
    assert channel.streams == ["https://a.invalid/x.m3u8"]


def test_same_name_in_different_groups_stays_separate():
    text = (
        '#EXTINF:-1 group-title="Andalucía",Canal 7\n'
        "https://a.invalid/1.m3u8\n"
        '#EXTINF:-1 group-title="Galicia",Canal 7\n'
        "https://b.invalid/2.m3u8\n"
    )
    assert len(playlist.parse(text)) == 2


def test_missing_optional_attributes():
    text = "#EXTINF:-1,Sin Datos\nhttps://example.invalid/s.m3u8\n"
    (channel,) = playlist.parse(text)
    assert channel.group == playlist.DEFAULT_GROUP
    assert channel.tvg_id is None
    assert channel.logo is None


def test_ignores_headers_stray_urls_and_blank_lines():
    text = (
        "#EXTM3U url-tvg=\"http://x/TV.xml.gz\"\n"
        "\n"
        "https://orphan.invalid/nothing.m3u8\n"
        '#EXTINF:-1 group-title="G",Real\n'
        "https://example.invalid/real.m3u8\n"
    )
    (channel,) = playlist.parse(text)
    assert channel.name == "Real"


def test_extinf_without_a_url_is_dropped():
    text = '#EXTINF:-1 group-title="G",Dangling\n'
    assert playlist.parse(text) == []


# -- merging across providers -------------------------------------------


def test_merge_pools_streams_for_the_same_channel():
    a = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://a.invalid/1\n', "A")
    b = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://b.invalid/2\n', "B")
    (channel,) = playlist.merge([a, b])
    assert channel.streams == ["https://a.invalid/1", "https://b.invalid/2"]


def test_merge_keeps_the_first_providers_metadata():
    a = playlist.parse('#EXTINF:-1 tvg-id="X" group-title="G",La 1\nhttps://a.invalid/1\n', "A")
    b = playlist.parse('#EXTINF:-1 tvg-id="Y" group-title="G",La 1\nhttps://b.invalid/2\n', "B")
    (channel,) = playlist.merge([a, b])
    assert channel.provider == "A"
    assert channel.tvg_id == "X"


def test_merge_fills_metadata_the_first_provider_lacked():
    a = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://a.invalid/1\n', "A")
    b = playlist.parse(
        '#EXTINF:-1 tvg-id="Y" tvg-logo="http://l/x.png" group-title="G",La 1\n'
        "https://b.invalid/2\n",
        "B",
    )
    (channel,) = playlist.merge([a, b])
    assert channel.tvg_id == "Y"
    assert channel.logo == "http://l/x.png"


def test_merge_keeps_distinct_channels_apart():
    a = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://a.invalid/1\n', "A")
    b = playlist.parse('#EXTINF:-1 group-title="G",Antena 3\nhttps://b.invalid/2\n', "B")
    assert len(playlist.merge([a, b])) == 2


def test_merge_does_not_duplicate_an_identical_stream():
    a = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://same.invalid/1\n', "A")
    b = playlist.parse('#EXTINF:-1 group-title="G",La 1\nhttps://same.invalid/1\n', "B")
    (channel,) = playlist.merge([a, b])
    assert channel.streams == ["https://same.invalid/1"]


def test_merge_of_nothing_is_empty():
    assert playlist.merge([]) == []


def test_parse_records_the_provider():
    (channel,) = playlist.parse('#EXTINF:-1 group-title="G",X\nhttps://a.invalid/1\n', "Src")
    assert channel.provider == "Src"
