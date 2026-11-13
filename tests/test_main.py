from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

import main
from config.settings import Config
from main import MusicBot


@pytest.fixture
async def bot():
    bot = MusicBot()
    yield bot
    await bot.close()


async def test_setup_loads_every_cog_and_syncs_slash_commands(bot, monkeypatch):
    sync = AsyncMock(return_value=[])
    monkeypatch.setattr(bot.tree, 'sync', sync)

    await bot.setup_hook()

    assert set(bot.cogs) == {'admin', 'general', 'Music'}
    sync.assert_awaited_once()
    # The hybrid help command from cogs.general replaces discord.py's default
    assert bot.get_command('help').cog_name == 'general'
    assert bot.get_command('queue').callback.__name__ == 'show_queue'


async def test_failed_slash_sync_does_not_stop_startup(bot, monkeypatch):
    monkeypatch.setattr(bot.tree, 'sync', AsyncMock(side_effect=OSError('network down')))

    await bot.setup_hook()

    assert 'Music' in bot.cogs


@pytest.mark.parametrize(
    ('error', 'reply'),
    [
        (commands.CommandError('Something broke'), '⚠️ Something broke'),
        (commands.CommandNotFound('nope'), '❌ Command not found. Use `!help` for help.'),
    ],
)
async def test_command_errors_are_reported_to_the_user(bot, error, reply):
    ctx = MagicMock()
    ctx.send = AsyncMock()

    await bot.on_command_error(ctx, error)

    ctx.send.assert_awaited_once_with(reply)


def test_main_exits_without_token(monkeypatch):
    monkeypatch.setattr(Config, 'BOT_TOKEN', None)

    with pytest.raises(SystemExit, match='BOT_TOKEN is required'):
        main.main()
