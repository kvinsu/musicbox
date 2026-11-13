from unittest.mock import MagicMock

import pytest
from spotipy.exceptions import SpotifyException

from config.settings import Config
from core.spotify_handler import SpotifyHandler
from utils.errors import YTDLError

PLAYLIST_URL = 'https://open.spotify.com/playlist/pid'
ALBUM_URL = 'https://open.spotify.com/album/aid'


def spotify_track(name: str, *artists: str) -> dict:
    return {'name': name, 'artists': [{'name': artist} for artist in artists or ['Artist']]}


def playlist_page(*names: str, next_page: str | None = None, missing: int = 0) -> dict:
    items = [{'track': None}] * missing + [{'track': spotify_track(name)} for name in names]
    return {'items': items, 'next': next_page}


@pytest.fixture
def handler() -> SpotifyHandler:
    handler = SpotifyHandler()
    handler.spotify = MagicMock()
    return handler


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC', ('4uLU6hMCjMI75M1A2tKUQC', 'track')),
        ('https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc', ('37i9dQZF1DXcBWIGoYBM5M', 'playlist')),
        ('https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3', ('1DFixLWuPkv3KT3TnV35m3', 'album')),
        ('spotify:track:4uLU6hMCjMI75M1A2tKUQC', ('4uLU6hMCjMI75M1A2tKUQC', 'track')),
        # Sharing a track from an album page links the album and highlights the track
        ('https://open.spotify.com/album/abc?highlight=spotify:track:xyz', ('xyz', 'track')),
        ('https://open.spotify.com/artist/0OdUWJ0sBjDrqHygGUXeCF', (None, None)),
    ],
)
def test_extract_id(url, expected):
    assert SpotifyHandler.extract_id(url) == expected


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://open.spotify.com/track/x', True),
        ('spotify:album:x', True),
        ('https://www.youtube.com/watch?v=x', False),
        ('spotify songs', False),
    ],
)
def test_is_spotify_url(url, expected):
    assert SpotifyHandler.is_spotify_url(url) is expected


def test_track_becomes_artist_title_query(handler):
    handler.spotify.track.return_value = spotify_track('Song', 'A', 'B')

    assert handler.resolve('https://open.spotify.com/track/abc') == ['A, B - Song']


def test_playlist_follows_pages(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 10)
    handler.spotify.playlist_tracks.side_effect = [
        playlist_page('a', 'b', 'c', next_page='page2'),
        playlist_page('d', 'e'),
    ]

    assert handler.resolve(PLAYLIST_URL) == ['Artist - a', 'Artist - b', 'Artist - c', 'Artist - d', 'Artist - e']
    calls = handler.spotify.playlist_tracks.call_args_list
    assert [(c.kwargs['offset'], c.kwargs['limit']) for c in calls] == [(0, 10), (3, 7)]


def test_playlist_skips_missing_tracks_without_skipping_items(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 3)
    handler.spotify.playlist_tracks.side_effect = [
        playlist_page('a', 'b', missing=1, next_page='page2'),
        playlist_page('c'),
    ]

    assert handler.resolve(PLAYLIST_URL) == ['Artist - a', 'Artist - b', 'Artist - c']
    assert handler.spotify.playlist_tracks.call_args_list[1].kwargs['offset'] == 3


def test_playlist_stops_at_limit(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 2)
    handler.spotify.playlist_tracks.return_value = playlist_page('a', 'b', 'c', next_page='page2')

    assert handler.resolve(PLAYLIST_URL) == ['Artist - a', 'Artist - b']
    assert handler.spotify.playlist_tracks.call_count == 1


@pytest.mark.parametrize(('status', 'reason'), [(404, 'not found or private'), (403, 'no permission')])
def test_api_errors_are_explained(handler, status, reason):
    handler.spotify.playlist_tracks.side_effect = SpotifyException(status, -1, 'error')

    with pytest.raises(YTDLError, match=f'Spotify playlist unavailable: {reason}'):
        handler.resolve(PLAYLIST_URL)


def test_album_fetches_remaining_tracks(handler):
    handler.spotify.album.return_value = {
        'tracks': {'items': [spotify_track('a'), spotify_track('b')], 'total': 3},
    }
    handler.spotify.album_tracks.return_value = {'items': [spotify_track('c')]}

    assert handler.resolve(ALBUM_URL) == ['Artist - a', 'Artist - b', 'Artist - c']
    handler.spotify.album_tracks.assert_called_once_with('aid', limit=50, offset=2)


def test_album_stops_at_limit(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 1)
    handler.spotify.album.return_value = {
        'tracks': {'items': [spotify_track('a'), spotify_track('b')], 'total': 30},
    }

    assert handler.resolve(ALBUM_URL) == ['Artist - a']
    handler.spotify.album_tracks.assert_not_called()


def test_rejects_unsupported_urls(handler):
    with pytest.raises(YTDLError, match='Invalid Spotify URL'):
        handler.resolve('https://open.spotify.com/artist/abc')


def test_requires_credentials(handler):
    handler.spotify = None

    with pytest.raises(YTDLError, match='not configured'):
        handler.resolve('https://open.spotify.com/track/abc')
