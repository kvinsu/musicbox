'''
Main file for this music bot
* starts the bot
* loads cogs on startup
* key functionality is defined under ./cogs
'''

import os
import logging
import platform
from dotenv import load_dotenv

import discord
from discord.ext import commands, tasks

# Get bot token
load_dotenv()
bot_token = os.getenv("BOT_TOKEN")
SELF_HOST = os.getenv("SELF_HOST", "false").lower() in ("1", "true", "yes")

# Set intents
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.voice_states = True

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("musicbot")

# Customize !help command
class EmbedHelpCommand(commands.MinimalHelpCommand):
    async def send_pages(self):
        destination = self.get_destination()
        e = discord.Embed(title='🎧  Commands', color=discord.Color.blurple(), description='')
        for page in self.paginator.pages:
            e.description += page
        await destination.send(embed=e)

client = commands.Bot(command_prefix='!', intents=intents)
client.help_command = EmbedHelpCommand(no_category='misc')

# Load cogs
def load_all_cogs():
    logger.info('Loading cogs from ./cogs')
    for file in os.listdir('./cogs'):
        if file.endswith('.py'):
            extension = file[:-3]
            try:
                client.load_extension(f'cogs.{extension}')
                logger.info(f"Loaded '{extension}' cog")
            except Exception as e:
                logger.exception(f"Failed to load cog {extension}: {e}")

load_all_cogs()

# Periodic status task
@tasks.loop(minutes=1.0)
async def status_task():
    try:
        await client.change_presence(activity=discord.Game(name="!help"))
    except Exception:
        logger.exception("Failed to set status")

# Send error messages
@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        await ctx.send('❌ Huh? There is no such command (yet). Check commands via ``!help``.')
    else:
        await ctx.send(f"⚠️ {str(error)}")

# Send first welcome message
@client.event
async def on_guild_join(guild):
    general = discord.utils.get(guild.text_channels, name='general')
    allgemein = discord.utils.get(guild.text_channels, name='allgemein')

    msg = f'🎧 **Hello {guild.name}!** My prefix is \'!\', use ``!help`` for more info :)'
    if general and general.permissions_for(guild.me).send_messages:
        await general.send(msg)
    elif allgemein and allgemein.permissions_for(guild.me).send_messages:
        await allgemein.send(msg)
    
    logger.info(f'Joined the server {guild.name}.')

# Startup behavior
@client.event
async def on_ready():
    logger.info('MusicBox is up and running!')
    logger.info(f'Python version: {platform.python_version()}')
    logger.info(f'Running on: {platform.system()} {platform.release()} ({os.name})')
    logger.info('-------------------')
    if not status_task.is_running():
        status_task.start()

# Start the bot
if __name__ == '__main__':
    if not bot_token:
        logger.error("BOT_TOKEN is not set. Set BOT_TOKEN in your .env or environment.")
        if SELF_HOST:
            logger.info("SELF_HOST is enabled but BOT_TOKEN is missing. Exiting.")
        else:
            logger.info("If you're self-hosting, create a .env with BOT_TOKEN. On Heroku, set config vars.")
        raise SystemExit(1)

    try:
        client.run(bot_token)
    except Exception:
        logger.exception("Bot terminated with an exception")
