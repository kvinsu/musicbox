"""Custom exceptions"""


class MusicBotError(Exception):
    """Base exception"""


class YTDLError(MusicBotError):
    """Searching, extracting or resolving a track failed"""
