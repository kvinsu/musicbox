import pytest

from core.embed_builder import EmbedBuilder
from tests.fakes import FakeSource, make_track


@pytest.mark.parametrize(('seconds', 'expected'), [
    (0, '/'),
    (59, '59s'),
    (60, '1m'),
    (3661, '1h 1m 1s'),
    (90061, '1d 1h 1m 1s'),
])
def test_format_duration(seconds, expected):
    assert EmbedBuilder._format_duration(seconds) == expected


def test_queue_list_shows_first_ten_and_total_duration():
    tracks = [make_track(f't{i}', duration=60) for i in range(12)]

    embed = EmbedBuilder.queue_list(tracks)

    assert embed.description.count('\n') == 9
    assert '**10.** t9' in embed.description
    assert 't10' not in embed.description
    fields = {f.name: f.value for f in embed.fields}
    assert fields['Total Duration'] == '12m'
    assert fields['...and more'] == '2 more songs'


def test_now_playing_shows_track_details():
    source = FakeSource({
        'title': 'Song', 'webpage_url': 'https://youtu.be/x', 'duration': 125,
        'uploader': 'Artist', 'uploader_url': 'https://youtube.com/@artist',
    })

    embed = EmbedBuilder.music_now_playing(source, requester='someone')

    assert embed.description == 'Song'
    assert embed.url == 'https://youtu.be/x'
    fields = {f.name: f.value for f in embed.fields}
    assert fields['Duration'] == '2m 5s'
    assert fields['Uploader'] == '[Artist](https://youtube.com/@artist)'
    assert embed.footer.text == 'Requested by someone'
