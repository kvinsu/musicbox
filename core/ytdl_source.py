"""yt-dlp search and audio source creation"""

import asyncio
import concurrent.futures
import functools
import itertools
import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Self

import discord
import yt_dlp

from config.settings import Config
from core.spotify_handler import SpotifyHandler
from utils.errors import YTDLError

logger = logging.getLogger('musicbot')

_YTDL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=Config.YTDL_MAX_WORKERS)
_SPOTIFY_HANDLER = SpotifyHandler()


@dataclass
class Track:
    """Metadata for a queued track; the stream URL is only fetched right before playback"""

    info: dict[str, Any]

    @property
    def title(self) -> str:
        return self.info.get('title', 'Unknown')

    @property
    def duration(self) -> int:
        return self.info.get('duration') or 0

    @property
    def url(self) -> str:
        return self.info.get('webpage_url') or self.info.get('url') or ''


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
    FFMPEG_OPTIONS = '-vn -q:a 5'

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

        Only metadata is fetched here; create_source() fetches the stream when a track starts.
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

        tracks: list[Track] = []
        errors: list[str] = []
        for spotify_query in queries:
            try:
                found, search_errors = await cls._search_youtube(spotify_query)
            except YTDLError as e:
                errors.append(f'{spotify_query}: {e}')
            else:
                tracks += found[:1]
                errors += search_errors
        if not tracks:
            raise YTDLError('Could not find any tracks from Spotify URL on YouTube')
        return tracks, errors

    @classmethod
    async def _search_youtube(cls, query: str) -> tuple[list[Track], list[str]]:
        try:
            data = await _run_ytdl(cls.ytdl.extract_info, query, download=False, process=False)
        except Exception as e:
            logger.exception('YTDL search failed')
            raise YTDLError(f'Search failed: {e}') from e

        if not data:
            raise YTDLError(f'No results for: {query}')

        if 'entries' not in data:
            # Text searches come back unresolved without a title, show the query until playback
            return [Track(info={**data, 'title': data.get('title') or query})], []

        tracks: list[Track] = []
        errors: list[str] = []
        # Entries are lazy, islice avoids fetching pages past the limit
        for entry in itertools.islice(data['entries'] or [], Config.PLAYLIST_MAX):
            if entry:
                tracks.append(Track(info=dict(entry)))
            else:
                errors.append('Empty playlist entry')
        return tracks, errors

    @classmethod
    async def create_source(cls, track: Track) -> Self:
        """Fetch the stream for a track and start FFmpeg on it"""
        if not track.url:
            raise YTDLError('No URL available')

        try:
            data = await _run_ytdl(cls.ytdl.extract_info, track.url, download=False)
        except Exception as e:
            raise YTDLError(f'Failed to fetch: {e}') from e

        if data and 'entries' in data:
            # Search results: play the best match
            data = next((entry for entry in data['entries'] if entry), None)
        if not data:
            raise YTDLError('No data available')
        if not data.get('url'):
            raise YTDLError('No stream URL available')

        data = {**data, 'requester': track.info.get('requester'), 'channel': track.info.get('channel')}
        try:
            audio = discord.FFmpegPCMAudio(
                data['url'],
                before_options=cls.build_ffmpeg_before_options(data.get('http_headers')),
                options=cls.FFMPEG_OPTIONS,
            )
        except Exception as e:
            raise YTDLError(f'FFmpeg error: {e}') from e
        return cls(audio, data=data)
