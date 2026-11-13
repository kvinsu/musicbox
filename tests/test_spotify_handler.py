from unittest.mock import MagicMock

import pytest
from spotipy.exceptions import SpotifyException

from config.settings import Config
from core.spotify_handler import SpotifyHandler
from utils.errors import YTDLError


def playlist_item(name: str, artist: str = 'Artist') -> dict:
    return {'track': {'name': name, 'artists': [{'name': artist}]}}


@pytest.fixture
def handler() -> SpotifyHandler:
    handler = SpotifyHandler()
    handler.spotify = MagicMock()
    return handler


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC', ('4uLU6hMCjMI75M1A2tKUQC', 'track')),
    ('https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc', ('37i9dQZF1DXcBWIGoYBM5M', 'playlist')),
    ('https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3', ('1DFixLWuPkv3KT3TnV35m3', 'album')),
    ('spotify:track:4uLU6hMCjMI75M1A2tKUQC', ('4uLU6hMCjMI75M1A2tKUQC', 'track')),
    ('https://open.spotify.com/artist/0OdUWJ0sBjDrqHygGUXeCF', (None, None)),
])
def test_extract_id(handler, url, expected):
    assert handler.extract_id(url) == expected


def test_detects_spotify_urls(handler):
    assert handler.is_spotify_url('https://open.spotify.com/track/x')
    assert not handler.is_spotify_url('https://www.youtube.com/watch?v=x')


def test_resolve_track_builds_search_query(handler):
    handler.spotify.track.return_value = {
        'name': 'Song', 'artists': [{'name': 'A'}, {'name': 'B'}],
    }

    assert handler.resolve('https://open.spotify.com/track/abc') == ['A, B - Song']


def test_resolve_playlist_follows_pages(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 10)
    handler.spotify.playlist_tracks.side_effect = [
        {'items': [playlist_item('a'), playlist_item('b'), playlist_item('c')], 'next': 'page2'},
        {'items': [playlist_item('d'), playlist_item('e')], 'next': None},
    ]

    queries = handler.resolve_playlist('pid')

    assert queries == ['Artist - a', 'Artist - b', 'Artist - c', 'Artist - d', 'Artist - e']
    calls = handler.spotify.playlist_tracks.call_args_list
    assert [(c.kwargs['offset'], c.kwargs['limit']) for c in calls] == [(0, 10), (3, 7)]


def test_resolve_playlist_skips_missing_tracks_without_skipping_items(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 3)
    handler.spotify.playlist_tracks.side_effect = [
        {'items': [{'track': None}, playlist_item('a'), playlist_item('b')], 'next': 'page2'},
        {'items': [playlist_item('c')], 'next': None},
    ]

    queries = handler.resolve_playlist('pid')

    assert queries == ['Artist - a', 'Artist - b', 'Artist - c']
    assert handler.spotify.playlist_tracks.call_args_list[1].kwargs['offset'] == 3


def test_resolve_playlist_stops_at_limit(handler, monkeypatch):
    monkeypatch.setattr(Config, 'PLAYLIST_MAX', 2)
    handler.spotify.playlist_tracks.return_value = {
        'items': [playlist_item('a'), playlist_item('b'), playlist_item('c')], 'next': 'page2',
    }

    assert handler.resolve_playlist('pid') == ['Artist - a', 'Artist - b']
    assert handler.spotify.playlist_tracks.call_count == 1


@pytest.mark.parametrize(('status', 'message'), [
    (404, 'not found or is private'),
    (403, 'No permission'),
])
def test_resolve_playlist_explains_api_errors(handler, status, message):
    handler.spotify.playlist_tracks.side_effect = SpotifyException(status, -1, 'error')

    with pytest.raises(YTDLError, match=message):
        handler.resolve_playlist('pid')


def test_resolve_album_fetches_remaining_tracks(handler):
    handler.spotify.album.return_value = {
        'tracks': {'items': [playlist_item('a')['track'], playlist_item('b')['track']], 'total': 3},
    }
    handler.spotify.album_tracks.return_value = {'items': [playlist_item('c')['track']]}

    assert handler.resolve_album('aid') == ['Artist - a', 'Artist - b', 'Artist - c']
    handler.spotify.album_tracks.assert_called_once_with('aid', limit=50, offset=2)


def test_resolve_rejects_unsupported_urls(handler):
    with pytest.raises(YTDLError, match='Invalid Spotify URL'):
        handler.resolve('https://open.spotify.com/artist/abc')


def test_resolve_requires_credentials(handler):
    handler.spotify = None

    with pytest.raises(YTDLError, match='not configured'):
        handler.resolve('https://open.spotify.com/track/abc')
