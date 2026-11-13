"""Configuration from environment variables (and a local .env file)"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Bot
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')

    # API keys
    TENOR_TOKEN = os.getenv('TENOR_TOKEN')
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

    # Music
    PLAYLIST_MAX = int(os.getenv('PLAYLIST_MAX', '400'))
    YTDL_MAX_WORKERS = int(os.getenv('YTDL_MAX_WORKERS', '4'))
    DISCONNECT_TIMEOUT = int(os.getenv('DISCONNECT_TIMEOUT', '300'))

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def has_spotify(cls) -> bool:
        return bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET)
