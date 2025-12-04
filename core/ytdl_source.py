"""YouTube-DL source handling"""
import asyncio
import functools
import logging
import concurrent.futures
from dataclasses import dataclass
from typing import Any
import discord
import yt_dlp
from config.settings import Config
from utils.errors import YTDLError
from core.spotify_handler import SpotifyHandler

logger = logging.getLogger("musicbot")

_YTDL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=Config.YTDL_MAX_WORKERS)
_SPOTIFY_HANDLER = SpotifyHandler()

@dataclass
class Track:
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

class YTDLSource(discord.PCMVolumeTransformer):
    ytdl_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'socket_timeout': 30
    }
    
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -q:a 5'
    }
    
    ytdl = yt_dlp.YoutubeDL(ytdl_options)  # type: ignore[arg-type]
    
    def __init__(self, source, *, data, volume=0.5):
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
    async def search(cls, query: str, *, loop=None) -> tuple[list[Track], list[str]]:
        """
        Search and return metadata only (lightweight)
        Resolve Spotify URLs if applicable
        """
        loop = loop or asyncio.get_event_loop()

        # Check if it's a Spotify URL
        if _SPOTIFY_HANDLER.is_spotify_url(query):
            if not Config.has_spotify():
                raise YTDLError(
                    "Spotify support not configured. "
                    "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables."
                )
            
            try:
                # Resolve Spotify URL to YouTube search queries
                search_queries = await _SPOTIFY_HANDLER.resolve(query)
                logger.info(f"Resolved Spotify URL to {len(search_queries)} search queries")
            except Exception as e:
                logger.exception("Spotify resolution failed")
                raise YTDLError(f"Failed to resolve Spotify URL: {e}")
            
            # Search YouTube for each resolved query
            all_tracks = []
            all_errors = []
            
            for search_query in search_queries:
                try:
                    tracks, errors = await cls._search_youtube(search_query, loop)
                    # Only take the first (best) result for each Spotify track
                    if tracks:
                        all_tracks.append(tracks[0])
                    all_errors.extend(errors)
                except YTDLError as e:
                    all_errors.append(f"{search_query}: {str(e)}")
                    continue
            
            if not all_tracks:
                raise YTDLError("Could not find any tracks from Spotify URL on YouTube")
            
            return all_tracks, all_errors
        
        # Regular YouTube search
        return await cls._search_youtube(query, loop)
    
    @classmethod
    async def _search_youtube(cls, query: str, loop) -> tuple[list[Track], list[str]]:
        """Internal method for YouTube search"""
        partial = functools.partial(cls.ytdl.extract_info, query, download=False, process=False)
        
        try:
            data = await loop.run_in_executor(_YTDL_EXECUTOR, partial)
        except Exception as e:
            logger.exception("YTDL search failed")
            raise YTDLError(f"Search failed: {e}")
        
        if not data:
            raise YTDLError(f"No results for: {query}")
        
        tracks = []
        errors = []
        
        if 'entries' in data:
            entries = list(data.get('entries') or [])[:Config.PLAYLIST_MAX]
            for entry in entries:
                if entry:
                    tracks.append(Track(info=dict(entry)))
                else:
                    errors.append("Empty playlist entry")
        else:
            tracks.append(Track(info=dict(data)))
        
        return tracks, errors
    
    @classmethod
    async def create_source(cls, track: Track, *, loop=None):
        """Create playable source from Track metadata"""
        loop = loop or asyncio.get_event_loop()
        webpage = track.url or f"https://www.youtube.com/watch?v={track.info.get('id')}"
        
        if not webpage:
            raise YTDLError("No URL available")
        
        partial = functools.partial(cls.ytdl.extract_info, webpage, download=False)
        try:
            data = await loop.run_in_executor(_YTDL_EXECUTOR, partial)
        except Exception as e:
            raise YTDLError(f"Failed to fetch: {e}")
        
        if not data:
            raise YTDLError("No data available")
        
        if 'entries' in data:
            data = next((e for e in data.get('entries', []) if e), None)
            if not data:
                raise YTDLError("Empty playlist entry")
        
        # Check for URL availability
        if 'url' not in data or not data['url']:
            raise YTDLError("No stream URL available")
        
        # Convert to regular dict and preserve requester/channel from original track
        data_dict = dict(data)
        data_dict['requester'] = track.info.get('requester')
        data_dict['channel'] = track.info.get('channel')
        
        stream_url: str = data['url']  # type: ignore[assignment]
        try:
            audio = discord.FFmpegPCMAudio(stream_url, before_options=cls.ffmpeg_options['before_options'], options=cls.ffmpeg_options['options'])
            return cls(audio, data=data_dict)
        except Exception as e:
            raise YTDLError(f"FFmpeg error: {e}")