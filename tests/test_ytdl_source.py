import shlex
import time

import discord
import pytest
import yt_dlp

from config.settings import Config
from core import ytdl_source
from core.ytdl_source import Track, YTDLSource
from utils.errors import YTDLError

VIDEO_URL = 'https://youtu.be/x'


class FakeYoutubeDL:
    """Returns canned extract_info results (computed per URL when given a callable) and records the URLs"""

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.extracted: list[str] = []
        self.processed = 0

    def extract_info(self, url, download=False, process=True):
        self.extracted.append(url)
        if self.error:
            raise self.error
        return self.result(url) if callable(self.result) else self.result

    def process_ie_result(self, info, download=False):
        # The real one selects a stream from the extracted formats, without network access
        self.processed += 1
        return {**info, 'url': info.get('url') or 'https://stream.example/selected'}


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
    lines = ffmpeg_headers(
        YTDLSource.build_ffmpeg_before_options(
            {
                'User-Agent': 'stream-agent',
                'Accept': '*/*',
            }
        )
    )

    assert 'User-Agent: stream-agent' in lines
    assert 'Accept: */*' in lines
    assert sum(line.startswith('User-Agent:') for line in lines) == 1


def test_track_defaults():
    track = Track(info={'url': 'https://example.com/stream'})

    assert track.title == 'Unknown'
    assert track.duration == 0
    assert track.url == 'https://example.com/stream'


# yt-dlp itself would take the last two for a video and a playlist ID
@pytest.mark.parametrize('query', ['some song', 'xxxtentacio', 'FLEETWOODMAC'])
async def test_text_is_searched_when_it_starts(query):
    # The offline yt-dlp stub fails the test if anything is searched up front
    tracks, errors = await YTDLSource.search(query)

    assert [(t.title, t.url) for t in tracks] == [(query, f'ytsearch:{query}')]
    assert errors == []


async def test_link_without_scheme_is_left_to_ytdl(fake_ytdl):
    # What yt-dlp returns for it with process=False: a redirect to the link with a scheme
    fake = fake_ytdl(result={'_type': 'url', 'url': 'http://youtu.be/x'})

    tracks, _ = await YTDLSource.search('youtu.be/x')

    assert fake.extracted == ['youtu.be/x']
    assert [(t.title, t.url) for t in tracks] == [('youtu.be/x', 'http://youtu.be/x')]
    # Processing an unresolved result would resolve it on the spot, which is play-time work
    assert fake.processed == 0


async def test_url_keeps_extracted_title(fake_ytdl):
    fake_ytdl(result={'title': 'Real Title', 'webpage_url': VIDEO_URL})

    tracks, _ = await YTDLSource.search(VIDEO_URL)

    assert tracks[0].title == 'Real Title'


async def test_single_url_is_extracted_only_once(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake = fake_ytdl(result={'title': 'Song', 'webpage_url': VIDEO_URL})

    tracks, _ = await YTDLSource.search(VIDEO_URL)
    source = await YTDLSource.create_source(tracks[0])

    assert fake.extracted == [VIDEO_URL]
    assert source.original.url == 'https://stream.example/selected'


async def test_extractions_keep_only_what_playback_uses(fake_ytdl):
    fake_ytdl(
        result={
            'title': 'Song',
            'webpage_url': VIDEO_URL,
            'formats': [{'url': 'https://stream.example/f'}] * 48,
            'automatic_captions': {'en': [{'url': 'https://captions.example'}]},
        }
    )

    tracks, _ = await YTDLSource.search(VIDEO_URL)

    assert tracks[0].title == 'Song'
    assert 'formats' not in tracks[0].info
    assert 'automatic_captions' not in tracks[0].info


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
        await YTDLSource.search(VIDEO_URL)
    assert excinfo.value.__cause__ is cause


async def test_spotify_url_requires_credentials(monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', None)

    with pytest.raises(YTDLError, match='not configured'):
        await YTDLSource.search('https://open.spotify.com/track/abc')


async def test_spotify_errors_are_not_wrapped_twice(monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', 'id')
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_SECRET', 'secret')

    def resolve(url):
        raise YTDLError('Spotify playlist unavailable: not found or private')

    monkeypatch.setattr(ytdl_source._SPOTIFY_HANDLER, 'resolve', resolve)

    with pytest.raises(YTDLError, match=r'^Spotify playlist unavailable: not found or private$'):
        await YTDLSource.search('https://open.spotify.com/playlist/abc')


async def test_spotify_tracks_are_searched_when_they_start(monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', 'id')
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(ytdl_source._SPOTIFY_HANDLER, 'resolve', lambda url: ['A - x', 'B - y'])

    # The offline yt-dlp stub fails the test if anything is searched up front
    tracks, errors = await YTDLSource.search('https://open.spotify.com/playlist/abc')

    assert [(t.title, t.url) for t in tracks] == [('A - x', 'ytsearch:A - x'), ('B - y', 'ytsearch:B - y')]
    assert errors == []


async def test_empty_spotify_link_is_reported(monkeypatch):
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_ID', 'id')
    monkeypatch.setattr(Config, 'SPOTIFY_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(ytdl_source._SPOTIFY_HANDLER, 'resolve', lambda url: [])

    with pytest.raises(YTDLError, match='No tracks found'):
        await YTDLSource.search('https://open.spotify.com/playlist/abc')


async def test_create_source_streams_with_extracted_headers(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake_ytdl(
        result={
            'url': 'https://stream.example/audio',
            'title': 'Song',
            'webpage_url': 'https://youtu.be/x',
            'http_headers': {'User-Agent': 'stream-agent'},
        }
    )
    track = Track(info={'webpage_url': 'https://youtu.be/x', 'requester': 'user', 'channel': 'chan'})

    source = await YTDLSource.create_source(track)

    assert source.title == 'Song'
    assert source.data['requester'] == 'user'
    assert source.data['channel'] == 'chan'
    assert source.original.url == 'https://stream.example/audio'
    assert 'User-Agent: stream-agent' in ffmpeg_headers(source.original.before_options)
    assert source.original.options == YTDLSource.FFMPEG_OPTIONS


def search_for(*videos: dict | Exception):
    """extract_info results for a search whose results extract to these videos, or raise these errors"""
    urls = [f'https://www.youtube.com/watch?v={i}' for i in range(len(videos))]

    def result(url):
        if url.startswith('ytsearch'):
            # What yt-dlp returns for it with process=False: lazy references to the videos
            return {'_type': 'playlist', 'entries': ({'_type': 'url', 'url': u} for u in urls)}
        video = videos[urls.index(url)]
        if isinstance(video, Exception):
            raise video
        return {'webpage_url': url, **video}

    return result, urls


async def test_search_plays_first_result(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    result, urls = search_for(
        {'url': 'https://stream.example/1', 'title': 'First'}, {'url': 'https://stream.example/2'}
    )
    fake = fake_ytdl(result=result)

    track = Track(info={'title': 'song', 'url': 'ytsearch:song'})
    source = await YTDLSource.create_source(track)

    assert source.title == 'First'
    # Only the result that is played gets extracted
    assert fake.extracted == [f'ytsearch{ytdl_source._SEARCH_RESULTS}:song', urls[0]]
    # Fetched again from the video itself, not by searching again
    assert track.url == urls[0]


async def test_search_skips_results_that_cannot_be_played(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    unavailable = yt_dlp.utils.DownloadError('ERROR: [youtube] 0: This video is not available')
    result, urls = search_for(unavailable, {'url': 'https://stream.example/2', 'title': 'Second'}, {'url': 'x'})
    fake = fake_ytdl(result=result)

    source = await YTDLSource.create_source(Track(info={'url': 'ytsearch:song'}))

    assert source.title == 'Second'
    assert fake.extracted[1:] == urls[:2]


async def test_search_reports_first_error_when_no_result_plays(fake_ytdl):
    result, _ = search_for(
        yt_dlp.utils.DownloadError('This video is not available'),
        yt_dlp.utils.DownloadError('Video unavailable'),
    )
    fake_ytdl(result=result)

    with pytest.raises(YTDLError, match=r'^Failed to fetch: This video is not available$'):
        await YTDLSource.create_source(Track(info={'url': 'ytsearch:song'}))


async def test_search_without_results_is_reported(fake_ytdl):
    result, _ = search_for()
    fake_ytdl(result=result)

    with pytest.raises(YTDLError, match='No data available'):
        await YTDLSource.create_source(Track(info={'url': 'ytsearch:song'}))


async def test_link_to_a_playlist_plays_its_first_video(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake_ytdl(result={'entries': [None, {'url': 'https://stream.example/1', 'title': 'First'}]})

    source = await YTDLSource.create_source(Track(info={'url': 'https://youtube.com/playlist?list=x'}))

    assert source.title == 'First'


async def test_create_source_requires_stream_url(fake_ytdl):
    fake_ytdl(result={'title': 'No stream'})

    with pytest.raises(YTDLError, match='No stream URL'):
        await YTDLSource.create_source(Track(info={'webpage_url': VIDEO_URL}))


async def test_prefetched_stream_is_used_when_the_track_starts(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake = fake_ytdl(result={'url': 'https://stream.example/audio', 'title': 'Song'})
    track = Track(info={'webpage_url': VIDEO_URL})

    track.prefetch()
    track.prefetch()
    # Starts while the prefetch is still running, so it has to wait for it rather than fetch again
    source = await YTDLSource.create_source(track)

    assert fake.extracted == [VIDEO_URL]
    assert source.original.url == 'https://stream.example/audio'


async def test_failed_prefetch_is_retried_when_the_track_starts(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    attempts = []

    def result(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError('timed out')
        return {'url': 'https://stream.example/audio', 'title': 'Song'}

    fake_ytdl(result=result)
    track = Track(info={'webpage_url': VIDEO_URL})

    track.prefetch()
    source = await YTDLSource.create_source(track)

    assert len(attempts) == 2
    assert source.title == 'Song'


async def test_fresh_stream_is_not_fetched_again(monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    track = Track(info={'webpage_url': VIDEO_URL, 'url': 'https://stream.example/audio'}, fetched_at=time.monotonic())

    # The offline yt-dlp stub fails the test on any fetch
    source = await YTDLSource.create_source(track)

    assert source.original.url == 'https://stream.example/audio'


async def test_expired_stream_is_fetched_again(fake_ytdl, monkeypatch):
    monkeypatch.setattr(discord, 'FFmpegPCMAudio', FakeAudio)
    fake_ytdl(result={'url': 'https://stream.example/new', 'title': 'Song'})
    expired = time.monotonic() - ytdl_source._STREAM_TTL - 1
    track = Track(info={'webpage_url': VIDEO_URL, 'url': 'https://stream.example/old'}, fetched_at=expired)

    source = await YTDLSource.create_source(track)

    assert source.original.url == 'https://stream.example/new'
