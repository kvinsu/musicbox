"""Bot entry point"""

import logging
import platform
import sys

import discord
from discord.ext import commands

from config.settings import Config

logger = logging.getLogger('musicbot')

EXTENSIONS = ('cogs.admin', 'cogs.general', 'cogs.music')


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=Config.COMMAND_PREFIX,
            intents=intents,
            # cogs.general provides a hybrid help command instead
            help_command=None,
            activity=discord.Game(name=f'{Config.COMMAND_PREFIX}about'),
        )

    async def setup_hook(self) -> None:
        """Runs once before connecting, unlike on_ready which fires again after reconnects"""
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        # Prefix commands and previously synced slash commands still work, so don't stop startup
        try:
            synced = await self.tree.sync()
            logger.info(f'Synced {len(synced)} slash command(s)')
        except Exception:
            logger.exception('Failed to sync slash commands')

    async def on_ready(self) -> None:
        logger.info(f'Bot ready: {self.user}')
        logger.info(f'Python {platform.python_version()}, discord.py {discord.__version__}')

    async def on_guild_join(self, guild: discord.Guild) -> None:
        channel = discord.utils.get(guild.text_channels, name='general') or guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(f'🎧 **Hello {guild.name}!** Use `{Config.COMMAND_PREFIX}help` for commands.')
        logger.info(f'Joined guild: {guild.name}')

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f'❌ Command not found. Use `{Config.COMMAND_PREFIX}help` for help.')
            return
        await ctx.send(f'⚠️ {error}')
        logger.error(f'Command error: {error}', exc_info=error)


def main() -> None:
    token = Config.BOT_TOKEN
    if not token:
        sys.exit('Configuration error: BOT_TOKEN is required')

    logging.basicConfig(level=Config.LOG_LEVEL.upper(), format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    # log_handler=None keeps discord.py on the logging setup above
    MusicBot().run(token, log_handler=None)


if __name__ == '__main__':
    main()
