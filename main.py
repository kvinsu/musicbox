import logging
import platform
import asyncio
import discord
from discord.ext import commands, tasks
from config.settings import Config

# Validate config on startup
try:
    Config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
    exit(1)

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("musicbot")

# Set intents
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

client = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents)
# Remove default help command for hybrid command support
client.remove_command('help')

# Load cogs
async def load_cogs():
    logger.info('Loading cogs from ./cogs')
    for file in ['admin', 'general', 'music']:
        try:
            await client.load_extension(f'cogs.{file}')
            logger.info(f"Loaded '{file}' cog")
        except Exception as e:
            logger.exception(f"Failed to load cog {file}")

@tasks.loop(minutes=1.0)
async def status_task():
    try:
        await client.change_presence(activity=discord.Game(name=f"{Config.COMMAND_PREFIX}about"))
    except Exception:
        logger.exception("Failed to set status")

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        await ctx.send(f'❌ Command not found. Use `{Config.COMMAND_PREFIX}help` for help.')
    else:
        await ctx.send(f"⚠️ {str(error)}")
        logger.error(f"Command error: {error}", exc_info=error)

@client.event
async def on_guild_join(guild):
    channel = discord.utils.get(guild.text_channels, name='general') or guild.system_channel
    if channel and channel.permissions_for(guild.me).send_messages:
        await channel.send(f'🎧 **Hello {guild.name}!** Use `{Config.COMMAND_PREFIX}help` for commands.')
    logger.info(f'Joined guild: {guild.name}')

@client.event
async def on_ready():
    # Fetch application info to get owner
    if not client.owner_id:
        app_info = await client.application_info()
        client.owner_id = app_info.owner.id
        logger.info(f'Bot owner: {app_info.owner} (ID: {app_info.owner.id})')
    
    logger.info(f'Bot ready: {client.user}')
    logger.info(f'Python: {platform.python_version()}')
    logger.info(f'Discord.py: {discord.__version__}')
    logger.info(f'Platform: {platform.system()} {platform.release()}')

    # Sync slash commands
    try:
        synced = await client.tree.sync()
        logger.info(f'Synced {len(synced)} slash command(s)')
    except Exception as e:
        logger.exception(f'Failed to sync slash commands: {e}')
    
    if not status_task.is_running():
        status_task.start()

async def main():
    try:
        await load_cogs()
        if Config.BOT_TOKEN is None:
            raise ValueError("BOT_TOKEN is not set")
        await client.start(Config.BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception:
        logger.exception("Bot crashed")
    finally:
        if not client.is_closed():
            await client.close()

if __name__ == '__main__':
    asyncio.run(main())