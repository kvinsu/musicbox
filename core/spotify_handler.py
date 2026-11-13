"""Resolve Spotify links to YouTube search queries"""

import logging
import re

import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials

from config.settings import Config
from utils.errors import YTDLError

logger = logging.getLogger('musicbot')

# Checked in this order: shared "album?highlight=spotify:track:..." links mean the track
_KINDS = ('track', 'playlist', 'album')
_PLAYLIST_PAGE_SIZE = 100
_ALBUM_PAGE_SIZE = 50


def _search_query(track: dict) -> str:
    artists = ', '.join(artist['name'] for artist in track.get('artists', []))
    return f'{artists} - {track.get("name", "Unknown")}'


class SpotifyHandler:
    """Turns Spotify tracks, playlists and albums into 'artist - title' queries.

    spotipy is blocking, so call resolve() from an executor.
    """

    def __init__(self) -> None:
        self.spotify: spotipy.Spotify | None = None
        if Config.has_spotify():
            auth_manager = SpotifyClientCredentials(
                client_id=Config.SPOTIFY_CLIENT_ID,
                client_secret=Config.SPOTIFY_CLIENT_SECRET,
            )
            self.spotify = spotipy.Spotify(auth_manager=auth_manager)
            logger.info('Spotify integration enabled')
        else:
            logger.info('Spotify integration disabled (no credentials)')

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        return 'spotify.com/' in url or url.startswith('spotify:')

    @staticmethod
    def extract_id(url: str) -> tuple[str | None, str | None]:
        """Spotify ID and kind from open.spotify.com links and spotify: URIs"""
        for kind in _KINDS:
            if match := re.search(rf'{kind}[/:]([\w-]+)', url):
                return match.group(1), kind
        return None, None

    def resolve(self, url: str) -> list[str]:
        """Search queries for every track behind a Spotify URL"""
        spotify = self.spotify
        if not spotify:
            raise YTDLError('Spotify support not configured')

        spotify_id, kind = self.extract_id(url)
        if not spotify_id:
            raise YTDLError('Invalid Spotify URL')

        try:
            if kind == 'track':
                queries = [_search_query(spotify.track(spotify_id))]
            elif kind == 'playlist':
                queries = _playlist_queries(spotify, spotify_id)
            else:
                queries = _album_queries(spotify, spotify_id)
        except SpotifyException as e:
            reason = {403: 'no permission to access it', 404: 'not found or private'}.get(e.http_status, e.msg)
            raise YTDLError(f'Spotify {kind} unavailable: {reason}') from e

        logger.info(f'Resolved Spotify {kind}: {len(queries)} tracks')
        return queries


def _playlist_queries(spotify: spotipy.Spotify, playlist_id: str) -> list[str]:
    queries: list[str] = []
    offset = 0
    while len(queries) < Config.PLAYLIST_MAX:
        page = spotify.playlist_tracks(
            playlist_id,
            limit=min(_PLAYLIST_PAGE_SIZE, Config.PLAYLIST_MAX - len(queries)),
            offset=offset,
        )
        items = page.get('items') or []
        # Local files and removed tracks come back without a track object
        queries += [_search_query(item['track']) for item in items if item and item.get('track')]
        if not items or not page.get('next'):
            break
        offset += len(items)
    return queries[: Config.PLAYLIST_MAX]


def _album_queries(spotify: spotipy.Spotify, album_id: str) -> list[str]:
    album = spotify.album(album_id)
    tracks = album['tracks']['items']
    wanted = min(album['tracks']['total'], Config.PLAYLIST_MAX)
    while len(tracks) < wanted:
        page = spotify.album_tracks(album_id, limit=_ALBUM_PAGE_SIZE, offset=len(tracks))
        if not page.get('items'):
            break
        tracks += page['items']
    return [_search_query(track) for track in tracks[:wanted]]
