"""Fakes for the Discord, voice and playback boundaries"""

import asyncio
from unittest.mock import AsyncMock

import discord

from core.ytdl_source import Track


class FakeVoice:
    """Voice client with the playback semantics of discord.VoiceClient.

    Like the real player, ending playback (stop, disconnect or the track
    finishing) invokes the `after` callback passed to play().
    """

    def __init__(self, *, connected: bool = True, play_error: Exception | None = None):
        self.channel = object()
        self.connected = connected
        self.play_error = play_error
        self.source = None
        self.paused = False
        self.play_calls = 0
        self._after = None
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    async def _disconnect(self, *, force: bool = False) -> None:
        self.stop()
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def is_playing(self) -> bool:
        return self.source is not None and not self.paused

    def is_paused(self) -> bool:
        return self.source is not None and self.paused

    def play(self, source, *, after=None) -> None:
        self.play_calls += 1
        if self.play_error:
            raise self.play_error
        if not self.connected:
            raise discord.ClientException('Not connected to voice.')
        if self.is_playing():
            raise discord.ClientException('Already playing audio.')
        self.source = source
        self.paused = False
        self._after = after

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> None:
        self.finish()

    def finish(self, error: Exception | None = None) -> None:
        """End the current track, as when FFmpeg reaches the end of the stream"""
        after, self._after = self._after, None
        self.source = None
        self.paused = False
        if after:
            after(error)


class FakeSource:
    """Stands in for a YTDLSource created from a track"""

    def __init__(self, info: dict):
        self.data = dict(info)
        self.requester = info.get('requester')
        self.channel = info.get('channel')
        self.title = info.get('title')
        self.url = info.get('webpage_url')
        self.duration = info.get('duration') or 0
        self.uploader = info.get('uploader')
        self.uploader_url = info.get('uploader_url')
        self.thumbnail = info.get('thumbnail')


def make_track(title: str, **info) -> Track:
    return Track(info={'title': title, 'webpage_url': f'https://youtu.be/{title}', **info})


async def eventually(predicate) -> None:
    """Wait for work scheduled through the after-play callback to land"""
    async with asyncio.timeout(1):
        # Polling on purpose, the condition is arbitrary state rather than an event
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0)
