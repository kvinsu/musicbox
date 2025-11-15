'''
Music cog, contains commands controlling music playback from YouTube
'''

import asyncio
import functools
import logging
import random
import concurrent.futures

import discord
from discord.ext import commands
import yt_dlp

logger = logging.getLogger("musicbot")

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
        'source_address': '0.0.0.0',
        'socket_timeout': 30
    }

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
        'options': '-vn -q:a 5'
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
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.AbstractEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(executor, partial)

        if data is None:
            raise YTDLError(f'Couldn\'t find anything that matches `{search}`')

        playlist_detected = 'entries' in data
        if playlist_detected:
            await ctx.send('🎧 **Processing playlist.** This may take a while...')
            process_info = data.get('entries', [])
            if not process_info:
                raise YTDLError(f'Couldn\'t find anything that matches `{search}`')
        else:
            process_info = [data]

        sources = []
        for entry in process_info:
            webpage_url = entry.get('url') if playlist_detected else entry.get('webpage_url')
            
            partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
            data = await loop.run_in_executor(executor, partial)

            if data is None:
                raise YTDLError(f'Couldn\'t fetch `{webpage_url}`')

            info = data if 'entries' not in data else data['entries'][0]
            info['requester'] = ctx.author
            info['channel'] = ctx.channel
            
            try:
                sources.append(cls(discord.FFmpegPCMAudio(info['url'], **cls.ffmpeg_options), data=info))
            except Exception as e:
                logger.warning(f'Failed to create source for {info.get("title")}: {e}')
                continue

        if not sources:
            raise YTDLError(f'Couldn\'t process any sources from `{search}`')
        return sources


class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.queues = {}  # guild_id -> list of sources
        self.now_playing = {}  # guild_id -> current source
        self.repeat_mode = {}  # guild_id -> bool

    def get_queue(self, guild_id):
        """Get or create queue for guild"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def get_now_playing(self, guild_id):
        return self.now_playing.get(guild_id)

    def set_now_playing(self, guild_id, source):
        self.now_playing[guild_id] = source

    def is_repeat(self, guild_id):
        return self.repeat_mode.get(guild_id, False)

    def set_repeat(self, guild_id, value):
        self.repeat_mode[guild_id] = value

    def cleanup(self, guild_id):
        """Clean up guild state"""
        if guild_id in self.queues:
            del self.queues[guild_id]
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
        if guild_id in self.repeat_mode:
            del self.repeat_mode[guild_id]

    def make_after_callback(self, ctx):
        """Create after callback with error handling"""
        async def after_callback(error):
            if error:
                logger.error(f'Player error in {ctx.guild.id}: {error}')
            else:
                await self.play_next(ctx)
        
        def callback_wrapper(exc):
            if exc:
                logger.error(f'FFmpeg error: {exc}')
                asyncio.run_coroutine_threadsafe(after_callback(exc), self.client.loop)
            else:
                asyncio.run_coroutine_threadsafe(after_callback(None), self.client.loop)
        
        return callback_wrapper

    @commands.command(help='Make the bot join your voice channel')
    async def join(self, ctx):
        if ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel.')
            return
        
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        else:
            await ctx.voice_client.move_to(channel)
        
        self.get_queue(ctx.guild.id)
        await ctx.send(f'🎧 **Joined {channel.name}**')

    @commands.command(help='Make the bot leave the voice channel')
    async def leave(self, ctx):
        if not ctx.voice_client:
            await ctx.send('❌ I\'m not in a voice channel.')
            return
        
        await ctx.voice_client.disconnect()
        self.cleanup(ctx.guild.id)
        await ctx.message.add_reaction('👋')

    @commands.command(help='Skip the current song')
    async def skip(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return
        
        voice.stop()
        await ctx.send('⏭️ **Skipped**')

    @commands.command(help='Pause the current song')
    async def pause(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return
        
        voice.pause()
        await ctx.message.add_reaction('⏸️')

    @commands.command(help='Resume the current song')
    async def resume(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_paused():
            await ctx.send('❌ Nothing is paused.')
            return
        
        voice.resume()
        await ctx.message.add_reaction('▶️')

    @commands.command(help='Toggle repeat mode', aliases=['loop'])
    async def repeat(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_playing() or self.get_now_playing(ctx.guild.id) is None:
            await ctx.send('❌ Nothing is playing.')
            return
        
        repeat_state = not self.is_repeat(ctx.guild.id)
        self.set_repeat(ctx.guild.id, repeat_state)
        status = '**ON**' if repeat_state else '**OFF**'
        await ctx.send(f'🎧 Repeat mode {status}')

    @commands.command(help='Shuffle the queue')
    async def shuffle(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return
        
        random.shuffle(queue)
        await ctx.send('🎧 **Queue shuffled**')

    @commands.command(help='Stop playback and clear queue')
    async def stop(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return
        
        voice.stop()
        self.get_queue(ctx.guild.id).clear()
        await ctx.send('⏹️ **Stopped**')

    @commands.command(help='Clear the queue')
    async def clear(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return
        
        queue.clear()
        await ctx.send('🎧 **Queue cleared**')

    @commands.command(help='Remove a song from the queue')
    async def remove(self, ctx, index: int):
        queue = self.get_queue(ctx.guild.id)
        if not queue or index < 1 or index > len(queue):
            await ctx.send('❌ Invalid index.')
            return
        
        removed = queue.pop(index - 1)
        await ctx.send(f'🎧 **Removed:** {removed.title}')

    @commands.command(help='Show the current queue')
    async def queue(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return
        
        titles = [f'**{i}.** {song.title}' for i, song in enumerate(queue, 1)]
        total_duration = sum(song.duration for song in queue if song.duration)
        
        try:
            embed = discord.Embed(
                title='🎧 Queue',
                description='\n'.join(titles[:10]),
                color=discord.Color.blurple()
            ).add_field(name='Total Duration', value=self.parse_duration(total_duration))
            
            if len(titles) > 10:
                embed.add_field(name='...and more', value=f'{len(titles) - 10} more songs')
            
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f'Queue embed error: {e}')
            await ctx.send(f'🎧 **{len(queue)} songs in queue**')

    @commands.command(help='Show the currently playing song', aliases=['np'])
    async def nowplaying(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        song = self.get_now_playing(ctx.guild.id)
        if not song or not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return
        
        await ctx.send(embed=self.create_embed(song, 'Now Playing'))

    @commands.command(help='Play a song from YouTube')
    async def play(self, ctx, *, url):
        if ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel.')
            return
        
        voice = ctx.voice_client
        if voice and voice.channel != ctx.author.voice.channel:
            await ctx.send('❌ You\'re not in my voice channel.')
            return
        
        if not voice:
            await ctx.invoke(self.join)
            voice = ctx.voice_client
        
        async with ctx.typing():
            try:
                sources = await YTDLSource.create_source(ctx, url, loop=self.client.loop)
            except YTDLError as e:
                await ctx.send(f'⚠️ {str(e)}')
                return
        
        queue = self.get_queue(ctx.guild.id)
        queue.extend(sources)
        
        if not voice.is_playing():
            await self.play_next(ctx)
        else:
            await ctx.send(f'🎧 **Added {len(sources)} song(s) to queue**')

    async def play_next(self, ctx):
        """Play the next song in queue"""
        voice = ctx.voice_client
        queue = self.get_queue(ctx.guild.id)
        
        if not queue:
            if voice and voice.is_playing():
                voice.stop()
            # Disconnect after 5 minutes of inactivity
            await asyncio.sleep(300)
            if voice and not voice.is_playing():
                await voice.disconnect()
                self.cleanup(ctx.guild.id)
            return
        
        try:
            if self.is_repeat(ctx.guild.id) and self.get_now_playing(ctx.guild.id):
                # Re-fetch the current song for repeat
                current = self.get_now_playing(ctx.guild.id)
                sources = await YTDLSource.create_source(ctx, current.url, loop=self.client.loop)
                source = sources[0]
            else:
                source = queue.pop(0)
            
            self.set_now_playing(ctx.guild.id, source)
            voice.play(source, after=self.make_after_callback(ctx))
            await source.channel.send(embed=self.create_embed(source, 'Now Playing'))
        except YTDLError as e:
            logger.error(f'Play error: {e}')
            await ctx.send(f'⚠️ Playback error: {str(e)}')
            await self.play_next(ctx)
        except Exception as e:
            logger.exception(f'Unexpected play error: {e}')
            await self.play_next(ctx)

    def create_embed(self, song, title=''):
        """Create a formatted embed for a song"""
        duration = song.duration if song.duration else '/'
        
        avatar_url = None
        try:
            avatar_url = str(song.requester.display_avatar.url)
        except Exception:
            pass
        
        embed = discord.Embed(
            title=f'🎧 {title}',
            description=song.title,
            url=song.url,
            color=discord.Color.blurple()
        )
        embed.add_field(name='Duration', value=self.parse_duration(duration))
        embed.add_field(name='Uploader', value=f'[{song.uploader}]({song.uploader_url})')
        embed.set_thumbnail(url=song.thumbnail)
        embed.set_footer(text=f'Requested by {song.requester}', icon_url=avatar_url)
        
        return embed

    async def voice_check(self, ctx, voice):
        """Check if bot and user are in same voice channel"""
        if not voice:
            await ctx.send('❌ I\'m not in a voice channel.')
            return False
        elif ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel.')
            return False
        elif voice.channel != ctx.author.voice.channel:
            await ctx.send('❌ You\'re not in my voice channel.')
            return False
        return True

    @staticmethod
    def parse_duration(duration):
        """Parse duration in seconds to readable format"""
        if duration == '/' or duration == 0:
            return '/'
        
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            return '/'
        
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        parts = []
        if days > 0:
            parts.append(f'{days}d')
        if hours > 0:
            parts.append(f'{hours}h')
        if minutes > 0:
            parts.append(f'{minutes}m')
        if seconds > 0 or not parts:
            parts.append(f'{seconds}s')
        
        return ' '.join(parts)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect when alone in voice channel"""
        if member == self.client.user:
            return
        
        voice = member.guild.voice_client
        if not voice or not voice.channel:
            return
        
        if len(voice.channel.members) == 1:
            await voice.disconnect()
            self.cleanup(member.guild.id)


async def setup(client):
    await client.add_cog(Music(client))