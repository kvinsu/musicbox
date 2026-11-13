import shlex

import discord
import pytest

from config.settings import Config
from core import ytdl_source
from core.ytdl_source import Track, YTDLSource
from utils.errors import YTDLError


class FakeYoutubeDL:
    """Returns canned extract_info results, keyed by URL when given a callable"""

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    def extract_info(self, url, download=False, process=True):
        self.calls.append((url, process))
        if self.error:
            raise self.error
        return self.result(url) if callable(self.result) else self.result


class FakeAudio(discord.AudioSource):
    def __init__(self, url, *, before_options=None, options=None):
        self.url = url
        self.before_options = before_options
        self.options = options

    def read(self) -> bytes:
        return b''


def ffmpeg_headers(before_options: str) -> list[str]:
    """Header lines exactly as FFmpeg receives them"""
    tokens = shlex.split(before_options)
    headers = tokens[tokens.index('-headers') + 1]
    assert headers.endswith('\r\n')
    return headers.split('\r\n')[:-1]


@pytest.fixture
def fake_ytdl(monkeypatch):
    def install(**kwargs) -> FakeYoutubeDL:
        fake = FakeYoutubeDL(**kwargs)
        monkeypatch.setattr(YTDLSource, 'ytdl', fake)
        return fake
    return install


def test_ffmpeg_before_options_include_youtube_headers():
    before_options = YTDLSource.build_ffmpeg_before_options()

    assert 'Referer: https://www.youtube.com/' in before_options
    assert 'User-Agent:' in before_options
    assert '-reconnect' in before_options


def test_ffmpeg_headers_are_crlf_terminated():
    lines = ffmpeg_headers(YTDLSource.build_ffmpeg_before_options())

    assert lines == [f'{k}: {v}' for k, v in YTDLSource.YOUTUBE_DEFAULT_HEADERS.items()]


def test_ffmpeg_headers_prefer_stream_headers():
    lines = ffmpeg_headers(YTDLSource.build_ffmpeg_before_options({
        'User-Agent': 'stream-agent', 'Accept': '*/*',
    }))

    assert 'User-Agent: stream-agent' in lines
    assert 'Accept: */*' in lines
    assert sum(line.startswith('User-Agent:') for line in lines) == 1


def test_track_defaults():
    track = Track(info={'url': 'https://example.com/stream'})

    assert track.title == 'Unknown'
    assert track.duration == 0
    assert track.url == 'https://example.com/stream'


async def test_text_search_uses_query_as_title(fake_ytdl):
    # What yt-dlp returns for a plain query with process=False
    fake_ytdl(result={'_type': 'url', 'url': 'ytsearch:some song', 'webpage_url': 'some song'})

    tracks, errors = await YTDLSource.search('some song')

    assert [t.title for t in tracks] == ['some song']
    assert errors == []


async def test_url_keeps_extracted_title(fake_ytdl):
    fake_ytdl(result={'title': 'Real Title', 'webpage_url': 'https://youtu.be/x'})

    tracks, _ = await YTDLSource.search('https://youtu.be/x')

    assert tracks[0].title == 'Real Title'


async def test_playlist_stops_reading_entries_at_limit(fake_ytdl, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 2)
    consumed = []

    def entries():
        for i in range(5):
            consumed.append(i)
            yield {'title': f't{i}', 'url': f'https://youtu.be/{i}'}

    fake_ytdl(result={'entries': entries()})

    tracks, _ = await YTDLSource.search('https://youtube.com/playlist?list=x')

    assert [t.title for t in tracks] == ['t0', 't1']
    assert consumed == [0, 1]


async def test_playlist_reports_empty_entries(fake_ytdl):
    fake_ytdl(result={'entries': [None, {'title': 'ok'}]})

    tracks, errors = await YTDLSource.search('https://youtube.com/playlist?list=x')

    assert [t.title for t in tracks] == ['ok']
    assert errors == ['Empty playlist entry']


async def test_search_failure_keeps_cause(fake_ytdl):
    cause = RuntimeError('network down')
    fake_ytdl(error=cause)

    with pytest.raises(YTDLError, match='Search failed') as excinfo:
        await YTDLSource.search('some song')
    assert excinfo.value.__cause__ is cause


async def test_spotify_url_requires_credentials(monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', None)

    with pytest.raises(YTDLError, match='not configured'):
        await YTDLSource.search('https://open.spotify.com/track/abc')


async def test_spotify_url_becomes_youtube_searches(fake_ytdl, monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', 'id')
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(ytdl_source._SPOTIFY_HANDLER, 'resolve', lambda url: ['A - x', 'B - y'])
    fake = fake_ytdl(result=lambda query: {'_type': 'url', 'url': f'ytsearch:{query}', 'webpage_url': query})

    tracks, errors = await YTDLSource.search('https://open.spotify.com/playlist/abc')

    assert [t.title for t in tracks] == ['A - x', 'B - y']
    assert [url for url, _ in fake.calls] == ['A - x', 'B - y']
    assert errors == []


async def test_create_source_streams_with_extracted_headers(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake_ytdl(result={
        'url': 'https://stream.example/audio', 'title': 'Song', 'webpage_url': 'https://youtu.be/x',
        'http_headers': {'User-Agent': 'stream-agent'},
    })
    track = Track(info={'webpage_url': 'https://youtu.be/x', 'requester': 'user', 'channel': 'chan'})

    source = await YTDLSource.create_source(track)

    assert source.title == 'Song'
    assert source.data['requester'] == 'user'
    assert source.data['channel'] == 'chan'
    assert source.original.url == 'https://stream.example/audio'
    assert 'User-Agent: stream-agent' in ffmpeg_headers(source.original.before_options)
    assert source.original.options == YTDLSource.ffmpeg_options['options']


async def test_create_source_plays_first_search_result(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake_ytdl(result={'entries': [None, {'url': 'https://stream.example/1', 'title': 'First'}]})

    source = await YTDLSource.create_source(Track(info={'url': 'ytsearch:song'}))

    assert source.title == 'First'


async def test_create_source_requires_stream_url(fake_ytdl):
    fake_ytdl(result={'title': 'No stream'})

    with pytest.raises(YTDLError, match='No stream URL'):
        await YTDLSource.create_source(Track(info={'webpage_url': 'https://youtu.be/x'}))
