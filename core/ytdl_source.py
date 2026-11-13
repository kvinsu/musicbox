"""yt-dlp search and audio source creation"""

import asyncio
import concurrent.futures
import functools
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

import discord
import yt_dlp

from config.settings import Config
from core.spotify_handler import SpotifyHandler
from utils.errors import YTDLError

logger = logging.getLogger('musicbot')

_YTDL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=Config.YTDL_MAX_WORKERS)
_SPOTIFY_HANDLER = SpotifyHandler()

# YouTube stream URLs expire after about six hours, fetch again well before that
_STREAM_TTL = 3600
# All playback and the embeds use; a full extraction also carries every format and caption track (~600 KiB)
_PLAYBACK_FIELDS = ('title', 'webpage_url', 'url', 'duration', 'uploader', 'uploader_url', 'thumbnail', 'http_headers')


@dataclass
class Track:
    """A queued track. Its stream URL is fetched when it starts, or ahead of time by prefetch()"""

    info: dict[str, Any]
    # When info['url'] was set to a stream URL; None until then
    fetched_at: float | None = field(default=None, compare=False)
    _loading: asyncio.Task[None] | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def title(self) -> str:
        return self.info.get('title', 'Unknown')

    @property
    def duration(self) -> int:
        return self.info.get('duration') or 0

    @property
    def url(self) -> str:
        return self.info.get('webpage_url') or self.info.get('url') or ''

    @property
    def has_stream(self) -> bool:
        """Whether info holds a stream URL that hasn't expired"""
        return self.fetched_at is not None and time.monotonic() - self.fetched_at < _STREAM_TTL

    def prefetch(self) -> None:
        """Start fetching the stream in the background, so the track can start without a gap"""
        if self._loading is None and not self.has_stream:
            self._loading = asyncio.create_task(self._prefetch())

    async def load_stream(self) -> None:
        """Make sure info holds a stream URL that hasn't expired"""
        if self._loading:
            await self._loading
        if not self.has_stream:
            await self._fetch_stream()

    async def _prefetch(self) -> None:
        try:
            await self._fetch_stream()
        except YTDLError as e:
            # Retried, and reported to the channel if it fails again, when the track starts
            logger.warning(f'Prefetch failed for {self.title}: {e}')

    async def _fetch_stream(self) -> None:
        if not self.url:
            raise YTDLError('No URL available')
        try:
            data = await _run_ytdl(YTDLSource.ytdl.extract_info, self.url, download=False)
        except Exception as e:
            raise YTDLError(f'Failed to fetch: {e}') from e
        if data and 'entries' in data:
            # Search results: play the best match
            data = next((entry for entry in data['entries'] if entry), None)
        if not data:
            raise YTDLError('No data available')
        # info['url'] becomes the stream URL, so keep the page URL to fetch it again later
        self.info.update({'webpage_url': self.url} | _playback_info(data))
        self.fetched_at = time.monotonic()


def _playback_info(data: dict[str, Any]) -> dict[str, Any]:
    """The fields playback needs from an extraction"""
    if not data.get('url'):
        raise YTDLError('No stream URL available')
    return {key: data[key] for key in _PLAYBACK_FIELDS if key in data}


async def _run_ytdl(func, *args, **kwargs):
    """Run a blocking yt-dlp call on the bounded yt-dlp executor"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_YTDL_EXECUTOR, functools.partial(func, *args, **kwargs))


class YTDLSource(discord.PCMVolumeTransformer):
    YOUTUBE_DEFAULT_HEADERS: ClassVar[dict[str, str]] = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/126.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com',
    }

    # Options for FFmpeg's output side; the input side depends on the stream, see build_ffmpeg_before_options
    FFMPEG_OPTIONS = '-vn'

    ytdl = yt_dlp.YoutubeDL(
        {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            # Bind to IPv4, IPv6 sometimes causes trouble with YouTube
            'source_address': '0.0.0.0',
            'socket_timeout': 30,
        }
    )

    def __init__(self, source: discord.AudioSource, *, data: dict[str, Any], volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.requester = data.get('requester')
        self.channel = data.get('channel')
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration') or 0
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    def build_ffmpeg_before_options(cls, http_headers: dict[str, str] | None = None) -> str:
        """FFmpeg input options, including the request headers YouTube expects"""
        headers = {**cls.YOUTUBE_DEFAULT_HEADERS, **(http_headers or {})}
        header_string = ''.join(f'{key}: {value}\r\n' for key, value in headers.items())
        return f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -headers "{header_string}"'

    @classmethod
    async def search(cls, query: str) -> tuple[list[Track], list[str]]:
        """Tracks for a URL, search term or Spotify link, plus messages for entries that were skipped.

        Mostly metadata: streams are fetched when a track starts or is prefetched. Only a single
        video URL gets its stream here, since its extraction already has everything needed.
        """
        if not _SPOTIFY_HANDLER.is_spotify_url(query):
            return await cls._search_youtube(query)

        if not Config.has_spotify():
            raise YTDLError(
                'Spotify support not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.'
            )
        try:
            # spotipy is blocking
            queries = await asyncio.get_running_loop().run_in_executor(None, _SPOTIFY_HANDLER.resolve, query)
        except YTDLError:
            raise
        except Exception as e:
            logger.exception('Spotify resolution failed')
            raise YTDLError(f'Failed to resolve Spotify URL: {e}') from e

        if not queries:
            raise YTDLError('No tracks found behind that Spotify link')
        # Each one is searched on YouTube when it starts (or is prefetched), not all up front
        return [Track(info={'title': query, 'url': f'ytsearch:{query}'}) for query in queries], []

    @classmethod
    async def _search_youtube(cls, query: str) -> tuple[list[Track], list[str]]:
        try:
            data = await _run_ytdl(cls.ytdl.extract_info, query, download=False, process=False)
            if data and data.get('_type', 'video') == 'video':
                # Already fully extracted, picking its stream now (~0.1s) saves a second extraction at play time
                data = await _run_ytdl(cls.ytdl.process_ie_result, data, download=False)
        except Exception as e:
            logger.exception('YTDL search failed')
            raise YTDLError(f'Search failed: {e}') from e

        if not data:
            raise YTDLError(f'No results for: {query}')

        if 'entries' in data:
            tracks: list[Track] = []
            errors: list[str] = []
            # Entries are lazy, islice avoids fetching pages past the limit
            for entry in itertools.islice(data['entries'] or [], Config.PLAYLIST_MAX):
                if entry:
                    tracks.append(Track(info=dict(entry)))
                else:
                    errors.append('Empty playlist entry')
            return tracks, errors

        if data.get('_type', 'video') != 'video':
            # Text searches come back unresolved without a title, show the query until playback
            return [Track(info={**data, 'title': data.get('title') or query})], []
        return [Track(info=_playback_info(data), fetched_at=time.monotonic())], []

    @classmethod
    async def create_source(cls, track: Track) -> Self:
        """Start FFmpeg on the track's stream, fetching it first unless it is already loaded"""
        await track.load_stream()
        data = dict(track.info)
        try:
            audio = discord.FFmpegPCMAudio(
                data['url'],
                before_options=cls.build_ffmpeg_before_options(data.get('http_headers')),
                options=cls.FFMPEG_OPTIONS,
            )
        except Exception as e:
            raise YTDLError(f'FFmpeg error: {e}') from e
        return cls(audio, data=data)
