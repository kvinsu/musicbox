import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.music import Music
from config.settings import Config
from tests.fakes import FakeSource, FakeVoice


@pytest.fixture(autouse=True)
def default_config(monkeypatch):
    """Keep tests independent of the developer's .env"""
    defaults = {
        'TENOR_TOKEN': None,
        'SPOTIFY_CLIENT_ID': None,
        'SPOTIFY_CLIENT_SECRET': None,
        'PLAYLIST_MAX': 100,
        'DISCONNECT_TIMEOUT': 300,
    }
    for name, value in defaults.items():
        monkeypatch.setattr(Config, name, value)


@pytest.fixture
def voice() -> FakeVoice:
    return FakeVoice()


@pytest.fixture
def ctx(voice: FakeVoice) -> MagicMock:
    ctx = MagicMock()
    ctx.interaction = None
    ctx.guild.id = 1
    ctx.voice_client = voice
    ctx.send = AsyncMock()
    ctx.invoke = AsyncMock()
    ctx.channel.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.voice.channel = voice.channel
    return ctx


@pytest.fixture
async def cog():
    client = MagicMock()
    # The after-play callback schedules onto the bot's loop from the player thread
    client.loop = asyncio.get_running_loop()
    cog = Music(client)
    yield cog
    for task in cog._disconnect_tasks.values():
        task.cancel()


@pytest.fixture
def created_sources(monkeypatch) -> list[FakeSource]:
    """Make create_source succeed for every track and record what it built"""
    created = []

    async def create_source(track, *, loop=None):
        # Yield like the real extraction does, so concurrent callers interleave
        await asyncio.sleep(0)
        source = FakeSource(track.info)
        created.append(source)
        return source

    monkeypatch.setattr('cogs.music.YTDLSource.create_source', create_source)
    return created
