"""Custom exceptions"""

class MusicBotError(Exception):
    """Base exception"""
    pass

class YTDLError(MusicBotError):
    """YTDL-related errors"""
    pass

class VoiceError(MusicBotError):
    """Voice channel errors"""
    pass

class QueueError(MusicBotError):
    """Queue operation errors"""
    pass