'''
Music cog, contains commands controlling music playback from YouTube
'''

import asyncio
import functools

import discord
from discord.ext import commands

import random
import concurrent.futures
import threading
import time

# fork of ytdl, more patched and maintained
import yt_dlp

# ignore unnecessary bug reports
yt_dlp.utils.bug_reports_message = lambda: ''

class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
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
        # bind to ipv4 since ipv6 addresses cause issues sometimes
        'source_address': '0.0.0.0'
    }

    # prevent termination of FFMPEG executable due to corrupt packages
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
        'options': '-vn'
    }

    ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
    
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data
        self.requester = data.get('requester')
        self.channel = data.get('channel')

        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        # prevents this method from opening too many stale threads (especially when playing playlists)
        executor = concurrent.futures.ThreadPoolExecutor(10)

        # first extraction: determine song type
        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(executor, partial)

        if data is None:
            raise YTDLError(f'Couldn\'t find anything that matches `{search}`')

        playlist_detected = False
        if 'entries' not in data:
            # search song via keyword or url
            process_info = [data]
        else:
            # search song via yt playlist
            playlist_detected = True
            await ctx.send('🎧 **Processing playlist.** This may take a while...')
            process_info = [entry for entry in data['entries']]

            if not process_info:
                raise YTDLError(f'Couldn\'t find anything that matches `{search}`')

        sources = []
        for entry in process_info:
            # differentiation necessary, as yt playlists have different dict_keys
            if playlist_detected == False:
                webpage_url = entry['webpage_url']
            else:
                webpage_url = entry['url']

            # second extraction: actual audio processing + retrieval of other keys (thumbnail, duration etc.)
            partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
            data = await loop.run_in_executor(executor, partial)
            # TODO: case playlist: throws Errno 11: Resource temporarily not available after ~29th song
            # print(f'{threading.active_count()} Threads active.')

            if data is None:
                raise YTDLError(f'Couldn\'t fetch `{webpage_url}`')

            if 'entries' not in data:
                info = data
            else:
                info = None
                while info is None:
                    try:
                        info = data['entries'].pop(0)
                    except IndexError:
                        raise YTDLError(f'Couldn\'t retrieve any matches for `{webpage_url}`')

            # add user + channel info to dict
            info['requester'] = ctx.author
            info['channel'] = ctx.channel
            sources.append(cls(discord.FFmpegPCMAudio(info['url'], **cls.ffmpeg_options), data=info))

        return sources


repeating = {}
songs = {}
current_song = {}

class Music(commands.Cog):
    def __init__(self, client):
        self.client = client

    #TODO: spotify support (if possible?)
    
    @commands.command(help='This command makes the bot join the voice channel')
    async def join(self, ctx):
        global songs, current_song, repeating

        if ctx.author.voice is None:
            await ctx.send('❌ Ur not in a voice channel lmao.')
        else:
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect()
            else:
                await ctx.voice_client.move_to(voice_channel)
            
            # init
            songs[ctx.guild.id] = []
            current_song[ctx.guild.id] = None
            repeating[ctx.guild.id] = False
    
    @commands.command(help='This command makes the bot leave the voice channel')
    async def leave(self, ctx):
        global songs, repeating, current_song
        
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        else:
            await ctx.voice_client.disconnect()
            await ctx.message.add_reaction('👋')

            songs[ctx.guild.id] = []
            repeating[ctx.guild.id] = False
            current_song[ctx.guild.id] = None

    @commands.command(help='This command skips the current song')
    async def skip(self, ctx):
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('❌ Nothing to skip.')
            return
        else:
            ctx.voice_client.stop()
            if(repeating[ctx.guild.id]):
                await ctx.send('🎧 **Skipped. Still in repeat mode tho!**')
            else:
                await ctx.send('🎧 **Skipped.**')

    @commands.command(help='This command pauses the current song')
    async def pause(self, ctx):
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('❌ Nothing to pause.')
            return
        else:
            voice.pause()
            await ctx.message.add_reaction('⏸️')

    @commands.command(help='This command resumes the current song')
    async def resume(self, ctx):
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not voice.is_paused():
            await ctx.send('❌ Nothing is paused.')
            return
        else:
            voice.resume()
            await ctx.message.add_reaction('▶️')

    @commands.command(help='This command sets the repeat mode of the player',aliases=['loop'])
    async def repeat(self, ctx):
        global repeating

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not voice.is_playing() or current_song[ctx.guild.id] == None:
            await ctx.send('❌ Nothing to repeat.')
            return
        else:
            repeating[ctx.guild.id] = not repeating[ctx.guild.id]
            if repeating[ctx.guild.id]:
                await ctx.send('🎧 **Repeat mode ON**')
            else:
                await ctx.send('🎧 **Repeat mode OFF**')

    @commands.command(help='This command shuffles the current queue')
    async def shuffle(self, ctx):
        global songs

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not songs[ctx.guild.id]:
            await ctx.send('❌ Queue is empty, nothing to shuffle.')
            return
        else:
            random.shuffle(songs[ctx.guild.id])
            await ctx.send('🎧 **Queue shuffled.** Check via ``!queue``.')

    @commands.command(help='This command stops the current song and empties the queue')
    async def stop(self, ctx):
        global songs, current_song, repeating

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not voice.is_playing():
            await ctx.send('❌ Nothing to stop.')
            return
        else:
            songs[ctx.guild.id] = []
            current_song[ctx.guild.id] = None
            repeating[ctx.guild.id] = False
            
            voice.stop()
            await ctx.send('🎧 **Stopped and queue cleared.**')

    @commands.command(help='This command clears the current queue')
    async def clear(self, ctx):
        global songs, current_song

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not songs[ctx.guild.id]:
            await ctx.send('❌ Queue is empty, nothing to clear.')
            return
        else:
            songs[ctx.guild.id] = []
            await ctx.send('🎧 **Queue cleared.**')

    @commands.command(name='remove', help='This command removes a specific song from the current queue')
    async def _remove(self, ctx, index: int):
        global songs

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if not await self.voice_check(ctx, voice):
            return
        elif not songs[ctx.guild.id]:
            await ctx.send('❌ Queue is empty, nothing to remove.')
            return
        else:
            if index > 0 and index <= len(songs[ctx.guild.id]):
                tmp = songs[ctx.guild.id][index - 1]
                del(songs[ctx.guild.id][index - 1])
                await ctx.send(f'🎧 **Removed:** {tmp.title}')
            else:
                await ctx.send('❌ Invalid index. Check for it via ``!queue``.')

    @commands.command(help='This command displays the current queue')
    async def queue(self, ctx):
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        
        if not await self.voice_check(ctx, voice):
            return
        elif not songs[ctx.guild.id]:
            await ctx.send('❌ Queue is empty, nothing to show.')
            return
        else:
            titles = [song.title for song in songs[ctx.guild.id]]
            enum_titles = []

            for idx, val in enumerate(titles, start=1):
                enum_titles.append(f'**{idx}.** {val}')

            durations = [song.duration for song in songs[ctx.guild.id]]
            total_duration = sum(durations)

            try:
                embed = (discord.Embed(title='🎧  Current Queue',
                                    description='\n'.join(enum_titles),
                                    color=discord.Color.blurple())
                                    .add_field(name='Total time', value=self.parse_duration(duration=total_duration))
                                    )
                await ctx.send(embed=embed)
            except:
                await ctx.send('❌ Too many songs to display!')
                embed = (discord.Embed(title='🎧  Current Queue',
                                    description=f'{len(titles)} songs enqueued.',
                                    color=discord.Color.blurple())
                                    .add_field(name='Total time', value=self.parse_duration(duration=total_duration))
                                    )
                await ctx.send(embed=embed)

    # TODO: Add time left / progress bar?
    @commands.command(help='This command displays the current song', aliases=['np'])
    async def nowplaying(self, ctx):
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)

        if not await self.voice_check(ctx, voice):
            return
        elif current_song[ctx.guild.id] == None or not voice.is_playing():
            await ctx.send('❌ Nothing is being played right now.')
        else:
            await ctx.send(embed=self.create_play_embed(ctx=ctx, song=None))

    @commands.command(help='This command plays songs or adds them to the current queue')
    async def play(self, ctx, *, url):
        global songs, current_song, repeating

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if ctx.author.voice is None:
            await ctx.send("❌ Ur not in a voice channel lmao.")
            return
        elif voice and ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.send('❌ Ur not in that voice channel. 🌚')
            return

        if not voice:
            await ctx.invoke(self.client.get_command('join'))

        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if voice:
            sources = await YTDLSource.create_source(ctx, search=url, loop=self.client.loop)
            try:
                songs[ctx.guild.id].extend(sources)
            except:
                songs[ctx.guild.id] = sources

            if not voice.is_playing():
                try:
                    current_song[ctx.guild.id] = songs[ctx.guild.id].pop(0)
                    ctx.voice_client.play(current_song[ctx.guild.id], after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
                    if len(sources) > 1:
                        await ctx.send(f'🎧 **Enqueued:** {len(sources)} songs')
                    await ctx.send(embed=self.create_play_embed(ctx=ctx, song=None))
                except YTDLError as e:
                    await ctx.send(f'⚠️ An error occurred while processing this request: {str(e)}')
            else:
                if len(sources) > 1:
                    await ctx.send(f'🎧 **Enqueued:** {len(sources)} songs')
                else:
                    await ctx.send(embed=self.create_play_embed(ctx=ctx, song=sources[0]))

    async def play_next(self, ctx):
        global songs, current_song, repeating

        if songs[ctx.guild.id] or repeating[ctx.guild.id]:
            try:
                if not repeating[ctx.guild.id]:
                    current_song[ctx.guild.id] = songs[ctx.guild.id].pop(0)
                    ctx.voice_client.play(current_song[ctx.guild.id], after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
                    await current_song[ctx.guild.id].channel.send(f'🎧 **Now playing:** {current_song[ctx.guild.id].title}') 
                else:
                    repeated_song = await YTDLSource.create_source(ctx, current_song[ctx.guild.id].url, loop=self.client.loop)
                    current_song[ctx.guild.id] = repeated_song[0]
                    ctx.voice_client.play(current_song[ctx.guild.id], after=lambda e: print('Player error: %s' % e) if e else asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.client.loop))
            except YTDLError as e:
                await ctx.send(f'⚠️ An error occurred while processing this request: {str(e)}')
        else:
            # inactivity disconnect after 3 minutes
            await asyncio.sleep(210)
            voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
            if not voice.is_playing():
                await ctx.voice_client.disconnect()

                songs[ctx.guild.id] = []
                repeating[ctx.guild.id] = False
                current_song[ctx.guild.id] = None

    # create song overview embed
    def create_play_embed(self, ctx, song):
        if song == None:
            headline = '🎧  Now playing'
            song = current_song[ctx.guild.id]
        else:
            headline = '🎧  Added to queue'

        # prevent embed breaking when playing LIVE video
        if song.duration == '':
            duration = '/'
        else:
            duration = song.duration

        # Safe avatar url for discord.py v2
        avatar_url = None
        try:
            avatar_url = str(getattr(getattr(song.requester, "display_avatar", None), "url", None))
        except Exception:
            avatar_url = None

        embed = (discord.Embed(title=headline,
                               description=f'{song.title}',
                               color=discord.Color.blurple())
                 .add_field(name='Duration', value=self.parse_duration(duration))
                 .add_field(name='Channel', value=f'[{song.uploader}]({song.uploader_url})')
                 .add_field(name='URL', value=f'[YouTube]({song.url})')
                 .set_thumbnail(url=song.thumbnail)
                 .set_footer(text=f'Requested by {song.requester}', icon_url=avatar_url))
        return embed

    # check voice_states of member and bot
    async def voice_check(self, ctx, voice):
        if not voice:
            await ctx.send('❌ Huh? I\'m not in a voice channel right now.')
            return False
        elif ctx.author.voice is None:
            await ctx.send("❌ Ur not in a voice channel lmao.")
            return False
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.send('❌ Ur not in that voice channel. 🌚')
            return False
        else:
            return True

    # calculate durations for song/queue
    @staticmethod
    def parse_duration(duration):
        if duration == '/':
            return '/'
        
        duration = int(duration)
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append(f'{days} days')
        if hours > 0:
            duration.append(f'{hours} hours')
        if minutes > 0:
            duration.append(f'{minutes} minutes')
        if seconds > 0:
            duration.append(f'{seconds} seconds')

        return ', '.join(duration)

    # auto-disconnect when alone in channel
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        global songs, current_song, repeating

        voice_state = member.guild.voice_client
        if voice_state is None:
            return 

        # TODO: Bugged - leaves voice channel if ANY channel in guild has 1 member
        if len(voice_state.channel.members) == 1:
            songs[member.guild.id] = []
            current_song[member.guild.id] = None
            repeating[member.guild.id] = False

            await voice_state.disconnect()


async def setup(client):
    await client.add_cog(Music(client))
