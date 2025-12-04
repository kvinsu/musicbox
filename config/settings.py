import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_ID = os.getenv("BOT_ID")
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
    SELF_HOST = os.getenv("SELF_HOST", "true").lower() in ("1", "true", "yes")
    
    # API Keys
    TENOR_TOKEN = os.getenv("TENOR_TOKEN")
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

    # Music
    PLAYLIST_MAX = int(os.getenv("PLAYLIST_MAX", "100"))
    YTDL_MAX_WORKERS = int(os.getenv("YTDL_MAX_WORKERS", "4"))
    DISCONNECT_TIMEOUT = int(os.getenv("DISCONNECT_TIMEOUT", "300"))
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls):
        """Validate required config"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not cls.BOT_ID:
            raise ValueError("BOT_ID is required")
        
    @classmethod
    def has_spotify(cls) -> bool:
        """Check if Spotify credentials are configured"""
        return bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET)