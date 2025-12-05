"""Spotify URL resolver"""
import logging
import re
from typing import Optional
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from config.settings import Config
from utils.errors import YTDLError

logger = logging.getLogger("musicbot")

class SpotifyHandler:
    """Handle Spotify URL resolution"""
    
    def __init__(self):
        self.spotify: Optional[spotipy.Spotify] = None
        if Config.has_spotify():
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=Config.SPOTIFY_CLIENT_ID,
                    client_secret=Config.SPOTIFY_CLIENT_SECRET
                )
                self.spotify = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify integration enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Spotify client: {e}")
        else:
            logger.info("Spotify integration disabled (no credentials)")
    
    def is_spotify_url(self, url: str) -> bool:
        """Check if URL is a Spotify link"""
        return 'spotify.com' in url or 'open.spotify' in url
    
    def extract_id(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract Spotify ID and type (track/playlist/album) from URL"""
        # Matches: https://open.spotify.com/track/ID or spotify:track:ID
        track_match = re.search(r'(?:track[/:])([\w-]+)', url)
        if track_match:
            return track_match.group(1), 'track'
        
        playlist_match = re.search(r'(?:playlist[/:])([\w-]+)', url)
        if playlist_match:
            return playlist_match.group(1), 'playlist'
        
        album_match = re.search(r'(?:album[/:])([\w-]+)', url)
        if album_match:
            return album_match.group(1), 'album'
        
        return None, None
    
    async def resolve_track(self, track_id: str) -> Optional[str]:
        """Resolve Spotify track to YouTube search query"""
        if not self.spotify:
            raise YTDLError("Spotify support not configured")
        
        try:
            track = self.spotify.track(track_id)
            artists = ', '.join([artist['name'] for artist in track['artists']])
            query = f"{artists} - {track['name']}"
            logger.info(f"Resolved Spotify track: {query}")
            return query
        except Exception as e:
            logger.error(f"Failed to resolve Spotify track {track_id}: {e}")
            raise YTDLError(f"Failed to resolve Spotify track: {e}")
        
    async def resolve_playlist(self, playlist_id: str) -> list[str]:
        """Resolve Spotify playlist to list of YouTube search queries"""
        if not self.spotify:
            raise YTDLError("Spotify support not configured")
        
        try:
            queries = []
            offset = 0
            limit = 100  # fixed Spotify API limit per request
            
            while len(queries) < Config.PLAYLIST_MAX:
                try:
                    results = self.spotify.playlist_tracks(
                        playlist_id, 
                        limit=min(limit, Config.PLAYLIST_MAX - len(queries)),
                        offset=offset
                    )
                except Exception as e:
                    # Handle 404 or permission errors
                    if '404' in str(e):
                        raise YTDLError("Spotify playlist not found or is private")
                    elif '403' in str(e):
                        raise YTDLError("No permission to access this Spotify playlist")
                    raise
                
                items = results.get('items', [])
                if not items:
                    break
                
                for item in items:
                    if not item or not item.get('track'):
                        continue
                    track = item['track']
                    artists = ', '.join([artist['name'] for artist in track.get('artists', [])])
                    track_name = track.get('name', 'Unknown')
                    query = f"{artists} - {track_name}"
                    queries.append(query)
                    
                    if len(queries) >= Config.PLAYLIST_MAX:
                        break
                
                # Check if there are more items
                if not results.get('next'):
                    break
                    
                offset += limit
            
            logger.info(f"Resolved Spotify playlist: {len(queries)} tracks")
            return queries
        except Exception as e:
            logger.error(f"Failed to resolve Spotify playlist {playlist_id}: {e}")
            raise YTDLError(f"Failed to resolve Spotify playlist: {e}")
    
    async def resolve_album(self, album_id: str) -> list[str]:
        """Resolve Spotify album to list of YouTube search queries"""
        if not self.spotify:
            raise YTDLError("Spotify support not configured")
        
        try:
            album = self.spotify.album(album_id)
            queries = []
            
            # Get all tracks (albums are usually smaller, but paginate if needed)
            tracks = album['tracks']['items']
            offset = len(tracks)
            
            # If album has more tracks, fetch them
            while len(tracks) < album['tracks']['total'] and len(queries) < Config.PLAYLIST_MAX:
                more_tracks = self.spotify.album_tracks(album_id, limit=50, offset=offset)
                if not more_tracks.get('items'):
                    break
                tracks.extend(more_tracks['items'])
                offset += 50
            
            for track in tracks[:Config.PLAYLIST_MAX]:
                artists = ', '.join([artist['name'] for artist in track.get('artists', [])])
                track_name = track.get('name', 'Unknown')
                query = f"{artists} - {track_name}"
                queries.append(query)
            
            logger.info(f"Resolved Spotify album: {len(queries)} tracks")
            return queries
        except Exception as e:
            logger.error(f"Failed to resolve Spotify album {album_id}: {e}")
            raise YTDLError(f"Failed to resolve Spotify album: {e}")
    
    async def resolve(self, url: str) -> list[str]:
        """
        Resolve Spotify URL to YouTube search queries.
        Returns list of search queries (one for track, multiple for playlist/album).
        """
        spotify_id, spotify_type = self.extract_id(url)
        
        if not spotify_id or not spotify_type:
            raise YTDLError("Invalid Spotify URL")
        
        if spotify_type == 'track':
            query = await self.resolve_track(spotify_id)
            return [query] if query else []
        elif spotify_type == 'playlist':
            return await self.resolve_playlist(spotify_id)
        elif spotify_type == 'album':
            return await self.resolve_album(spotify_id)
        
        raise YTDLError(f"Unsupported Spotify type: {spotify_type}")