import os

import asyncio
import functools

import discord
from discord.ext import commands, tasks
import youtube_dl

from async_timeout import timeout

bot_token = ''

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLError(Exception):
    pass

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(webpage_url))

        return cls(discord.FFmpegPCMAudio(info['url'], **ffmpeg_options), data=info)

class admin(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def shutdown(self, ctx):
        await ctx.message.add_reaction('💤')
        await client.close()
        #cleanup()

    def setup(client):
        client.add_cog(admin(client))

class general(commands.Cog):
    def __init__(self, client):
            self.client = client

    @commands.command(help='This command returns the current latency of the bot')
    async def ping(self, ctx):
        await ctx.send(f'**Pong:** {round(client.latency * 1000)} ms')

    @commands.command(help='This command says hi to the user')
    async def hello(ctx):
        await ctx.send('Moin')

    def setup(client):
        client.add_cog(general(client))

repeating = False
songs = []
current_song = None

class music(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.command(help='This command makes the bot join the voice channel')
    async def join(self, ctx):
        if ctx.author.voice is None:
            await ctx.send("Ur not in a voice channel lmao.")
        else:
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect()
            else:
                await ctx.voice_client.move_to(voice_channel)

    
    @commands.command(help='This command makes the bot leave the voice channel and empties the queue')
    async def leave(self, ctx):
        global songs, repeating, current_song
        
        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        else:
            await ctx.voice_client.disconnect()
            await ctx.message.add_reaction('👋')

            songs = []
            repeating = False
            current_song = None
            #cleanup()

    @commands.command(help='This command skips the current song')
    async def skip(self, ctx):
        global songs

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('Nothing to skip.')
            return
        else:
            ctx.voice_client.stop()
            if(repeating):
                await ctx.send('Skipped, but still in repeat mode!')
            else:
                await ctx.send('Skipped.')

    @commands.command(help='This command pauses the song')
    async def pause(self, ctx):
        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('Nothing to pause.')
            return
        else:
            voice.pause()
            await ctx.message.add_reaction('⏸️')

    @commands.command(help='This command resumes the song')
    async def resume(self, ctx):
        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not voice.is_paused():
            await ctx.send('Nothing is paused.')
            return
        else:
            voice.resume()
            await ctx.message.add_reaction('▶️')

    @commands.command(help='This command repeats/unrepeats the current song')
    async def repeat(self, ctx):
        global repeating

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not voice.is_playing() or current_song == '':
            await ctx.send('Nothing to repeat.')
            return
        else:
            repeating = not repeating
            if repeating:
                await ctx.message.add_reaction('🔁')
            else:
                await ctx.message.add_reaction('➡️')

    @commands.command(help='This command stops the current song and empties the queue')
    async def stop(self, ctx):
        global songs, current_song, repeating

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('Nothing to stop.')
            return
        else:
            songs = []
            current_song = None
            repeating = False
            
            voice.stop()
            await ctx.message.add_reaction('⏹️')

    @commands.command(name='remove', help='This command removes a specific song from the current queue')
    async def _remove(self, ctx, index: int):
        global songs

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if not await voice_check(ctx, voice):
            return
        elif not songs:
            await ctx.send('Queue is empty.')
            return
        else:
            tmp = songs[index - 1]
            del(songs[index - 1])
            await ctx.send(f'`{tmp.title}` removed from queue.')

    @commands.command(help='This command displays the current queue')
    async def queue(self, ctx):
        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        
        if not await voice_check(ctx, voice):
            return
        elif not songs:
            await ctx.send('Queue is empty.')
            return
        else:
            await ctx.send(f'The current queue is: `{[song.title for song in songs]}!`')

    @commands.command(help='This command plays songs or adds them to the current queue')
    async def play(self, ctx, *, url):
        global songs, current_song, repeating

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if ctx.author.voice is None:
            await ctx.send("Ur not in a voice channel lmao.")
            return
        elif voice and ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.send('Ur not in that voice channel. 🌚')
            return

        if not voice:
            await ctx.invoke(self.client.get_command('join'))

        voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if voice:
            # TODO: catch missing url exception
            if url != '':
                song = await YTDLSource.create_source(ctx, url, loop=self.client.loop)
                songs.append(song)
            else:
                await ctx.send('Nothing to play!')
                return

            if not voice.is_playing():
                try:
                    if not repeating:
                        current_song = songs.pop(0)
                        ctx.voice_client.play(current_song, after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
                        await ctx.send('**Now playing:** {}'.format(current_song.title))
                    else:
                        current_song = await YTDLSource.create_source(ctx, current_song.title, loop=self.client.loop)
                        ctx.voice_client.play(current_song, after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
                except YTDLError as e:
                    await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
            else:
                await ctx.send(f'`{song.title}` added to queue!')

    async def play_next(self, ctx):
        global songs, current_song, repeating

        if songs or repeating:
            try:
                if not repeating:
                    current_song = songs.pop(0)
                    ctx.voice_client.play(current_song, after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
                    await ctx.send('**Now playing:** {}'.format(current_song.title)) 
                else:
                    current_song = await YTDLSource.create_source(ctx, current_song.title, loop=self.client.loop)
                    ctx.voice_client.play(current_song, after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
            except YTDLError as e:
                await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
        else:
            await asyncio.sleep(210)
            voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
            if not voice.is_playing():
                await ctx.voice_client.disconnect()

                songs = []
                repeating = False
                current_song = None

    def setup(client):
        client.add_cog(music(client))

cogs = [admin, general, music]

client = commands.Bot(command_prefix='!')

for i in range(len(cogs)):
    cogs[i].setup(client)

@client.event
async def change_status():
    await client.change_presence(activity=discord.Game(name="Fortnite"))

@client.event
async def on_ready():
    await change_status()
    print('Bot is online.')

async def voice_check(ctx, voice):
    if not voice:
        await ctx.send('Huh? I\'m not in a voice channel right now.')
        return False
    elif ctx.author.voice is None:
        await ctx.send("Ur not in a voice channel lmao.")
        return False
    elif ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send('Ur not in that voice channel. 🌚')
        return False
    else:
        return True

def cleanup():
    cache_path = ''
    file_list = os.listdir(cache_path)
    for file in file_list:
        if file.endswith('.webm'):
            os.remove(os.path.join(cache_path, file))

client.run(bot_token)