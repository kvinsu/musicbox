'''
Music cog, contains commands controlling music playback from YouTube
'''

import os
import asyncio
import functools
import logging
import random
import concurrent.futures
from collections import deque
from dataclasses import dataclass

import discord
from discord.ext import commands
import yt_dlp

logger = logging.getLogger("musicbot")

# shared executor, reuse across requests to avoid creating many threads
_YTDL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# maximum playlist items to enqueue (env PLAYLIST_MAX, default 50)
PLAYLIST_MAX = int(os.getenv("PLAYLIST_MAX", "100"))

class YTDLError(Exception):
    pass

@dataclass
class Track:
    info: dict

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
        self.duration = data.get('duration') or 0
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def create_info(cls, ctx: commands.Context, search: str, *, loop: asyncio.AbstractEventLoop = None):
        """
        Fast metadata-only extraction.
        Returns (infos, errors) where infos is a list of info-dicts (up to PLAYLIST_MAX)
        and errors is a list of strings describing skipped entries.
        """
        loop = loop or asyncio.get_event_loop()
        partial_extract = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        logger.info(f'Creating info for search: {search}')
        try:
            data = await loop.run_in_executor(_YTDL_EXECUTOR, partial_extract)
        except Exception as e:
            logger.exception("yt-dlp discovery failed")
            raise YTDLError(f"Couldn't find anything that matches `{search}`: {e}")

        if data is None:
            raise YTDLError(f"Couldn't find anything that matches `{search}`")
        
        infos = []
        errors = []

        if 'entries' in data:
            logger.info(f'Playlist detected')
            
            try:
                entries_list = list(data.get('entries') or [])
            except Exception as e:
                logger.warning(f'Failed to convert entries to list: {e}')
                entries_list = []

            entries = entries_list[:PLAYLIST_MAX]
            if not entries:
                raise YTDLError(f"Couldn't find any entries for playlist `{search}`")
            for entry in entries:
                if not entry:
                    # skip errornous entries
                    errors.append("Unknown/empty playlist entry")
                    continue

                infos.append(entry)
        else:
            logger.info(f'Single track detected')
            infos.append(data)

        logger.info(f'Created info for {len(infos)} item(s), {len(errors)} error(s)')
        return infos, errors
class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        # per-guild state
        self.queues = {}            # guild_id -> deque of sources
        self.now_playing = {}       # guild_id -> current source
        self.repeat_mode = {}       # guild_id -> bool
        self.locks = {}             # guild_id -> asyncio.Lock for safe access
        self._disconnect_tasks = {} # guild_id -> asyncio.Task for inactivity disconnect

    def get_lock(self, guild_id):
        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()
        return self.locks[guild_id]

    def get_queue(self, guild_id):
        """Get or create deque queue for guild (fast pops from left)."""
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
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
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)
        self.repeat_mode.pop(guild_id, None)
        # cancel disconnect task, if any
        t = self._disconnect_tasks.pop(guild_id, None)
        if t and not t.done():
            t.cancel()

    async def safe_send(self, ctx, message: str = None, embed: discord.Embed = None):
        """Send message safely, ignoring send failures"""
        try:
            if embed:
                await ctx.send(embed=embed)
            elif message:
                await ctx.send(message)
        except Exception as e:
            logger.debug(f'Failed to send message: {e}')

    async def send_to_channel(self, channel, message: str = None, embed: discord.Embed = None):
        """Send to a specific channel safely"""
        try:
            if embed:
                await channel.send(embed=embed)
            elif message:
                await channel.send(message)
        except Exception as e:
            logger.debug(f'Failed to send to channel: {e}')

    def make_after_callback(self, ctx):
        """Create callback that schedules async continuation"""
        def callback_wrapper(*args, **kwargs):
            exc = args[0] if args else kwargs.get('error', None)
            if exc:
                logger.error(f'FFmpeg/Player error in guild {ctx.guild.id}: {exc}')
            asyncio.run_coroutine_threadsafe(self._after_play(ctx, exc), self.client.loop)
        return callback_wrapper

    async def _after_play(self, ctx, exc):
        """Async continuation called after track ends or errors."""
        if exc:
            # If an error, log and attempt to continue to next
            await ctx.send(f'⚠️ Playback error: {exc}')
        # Immediately attempt to play next track
        await self.play_next(ctx)

    async def _schedule_disconnect(self, guild_id, voice, delay=300):
        """Disconnect if nothing starts playing within delay seconds."""
        try:
            await asyncio.sleep(delay)
            # only disconnect if nothing is playing
            if voice and not voice.is_playing() and (not self.get_queue(guild_id) or len(self.get_queue(guild_id)) == 0):
                await voice.disconnect()
                self.cleanup(guild_id)
                logger.info(f'Disconnected due to inactivity in guild {guild_id}')
        except asyncio.CancelledError:
            # Cancelled because playback resumed or manual disconnect
            pass

    async def voice_check(self, ctx, voice):
        """Check if bot and user are in same voice channel"""
        if not voice:
            await self.safe_send(ctx, '❌ I\'m not in a voice channel.')
            return False
        elif ctx.author.voice is None:
            await self.safe_send(ctx, '❌ You\'re not in a voice channel lmao.')
            return False
        elif voice.channel != ctx.author.voice.channel:
            await self.safe_send(ctx, '❌ Nice try, you\'re not in my voice channel :)')
            return False
        return True
    
    def get_item_title(self, item):
        """Extract title from YTDLSource or Track"""
        if hasattr(item, 'title'):
            return item.title
        elif isinstance(item, Track):
            return item.info.get('title', 'Unknown')
        return str(item)

    def get_item_duration(self, item):
        """Extract duration from YTDLSource or Track"""
        if hasattr(item, 'duration'):
            return getattr(item, 'duration', 0) or 0
        elif isinstance(item, Track):
            return item.info.get('duration') or 0
        return 0
    
    def queue_to_embed(self, queue, title='🎧 Queue'):
        """Convert queue to embed"""
        if not queue:
            return None

        titles = []
        total_duration = 0
        for i, song in enumerate(queue, 1):
            title_str = self.get_item_title(song)
            duration = self.get_item_duration(song)
            titles.append(f'**{i}.** {title_str}')
            try:
                total_duration += int(duration)
            except (ValueError, TypeError):
                pass

        embed = discord.Embed(
            title=title,
            description='\n'.join(titles[:10]),
            color=discord.Color.blurple()
        ).add_field(name='Total Duration', value=self.parse_duration(total_duration))
        
        if len(titles) > 10:
            embed.add_field(name='...and more', value=f'{len(titles) - 10} more songs')
        
        return embed
    
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

    async def _resolve_track_to_source(self, ctx, track_item):
        """
        Resolve a Track to a playable YTDLSource.
        Returns (source, error_msg) where one is None.
        """
        if not isinstance(track_item, Track):
            return track_item, None

        info = track_item.info
        webpage = info.get('webpage_url') or info.get('url') or (f"https://www.youtube.com/watch?v={info.get('id')}" if info.get('id') else None)
        
        if not webpage:
            return None, 'Unknown track entry'

        try:
            partial = functools.partial(YTDLSource.ytdl.extract_info, webpage, download=False)
            full = await asyncio.get_event_loop().run_in_executor(_YTDL_EXECUTOR, partial)
        except Exception as e:
            logger.warning(f"yt-dlp failed for {webpage}: {e}")
            return None, str(e)

        if full is None:
            return None, 'No info available'

        # handle playlist entries
        if 'entries' in full:
            entry = next((item for item in full.get('entries', []) if item), None)
            if not entry:
                return None, 'Empty playlist entry'
            full = entry

        full['requester'] = info.get('requester')
        full['channel'] = info.get('channel')

        try:
            url = full.get('url')
            if not url:
                raise RuntimeError('No playable url')
            ff = discord.FFmpegPCMAudio(url, **YTDLSource.ffmpeg_options)
            return YTDLSource(ff, data=full), None
        except Exception as e:
            logger.warning(f'Failed to create source: {e}')
            return None, str(e)

    @commands.command(help='Make the bot join your voice channel')
    async def join(self, ctx):
        if ctx.author.voice is None:
            await self.safe_send(ctx, '❌ You\'re not in a voice channel lmao.')
            return
        
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        else:
            await ctx.voice_client.move_to(channel)
        
        self.get_queue(ctx.guild.id)
        await ctx.message.add_reaction('👋')

    @commands.command(help='Make the bot leave the voice channel')
    async def leave(self, ctx):
        if not ctx.voice_client:
            await ctx.send('❌ Huh? I\'m not in a voice channel.')
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
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return
        
        voice.stop()
        await ctx.message.add_reaction('⏭️')

    @commands.command(help='Pause the current song')
    async def pause(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        if not voice.is_playing():
            await ctx.safe_send('❌ Nothing is playing.')
            return
        
        voice.pause()
        await ctx.message.add_reaction('⏸️')

    @commands.command(help='Resume the current song')
    async def resume(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_paused():
            await ctx.safe_send('❌ Nothing is paused.')
            return
        
        voice.resume()
        await ctx.message.add_reaction('▶️')

    @commands.command(help='Toggle repeat mode', aliases=['loop'])
    async def repeat(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing() or self.get_now_playing(ctx.guild.id) is None:
            await ctx.safe_send('❌ Nothing is playing.')
            return
        
        repeat_state = not self.is_repeat(ctx.guild.id)
        self.set_repeat(ctx.guild.id, repeat_state)
        await ctx.message.add_reaction('🔁')

    @commands.command(help='Shuffle the queue')
    async def shuffle(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.safe_send('❌ Queue is empty.')
            return

        qlist = list(queue)
        random.shuffle(qlist)
        self.queues[ctx.guild.id] = deque(qlist)
        await ctx.message.add_reaction('🔀')

    @commands.command(help='Stop playback and clear queue')
    async def stop(self, ctx):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing():
            await ctx.safe_send('❌ Nothing is playing.')
            return
        
        voice.stop()
        self.get_queue(ctx.guild.id).clear()
        await ctx.message.add_reaction('⏹️')

    @commands.command(help='Clear the queue')
    async def clear(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return
        
        queue.clear()
        await ctx.message.add_reaction('🗑️')

    @commands.command(help='Remove a song from the queue')
    async def remove(self, ctx, index: int):
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        
        queue = self.get_queue(ctx.guild.id)
        if not queue or index < 1 or index > len(queue):
            await ctx.safe_send('❌ Invalid index.')
            return

        # deque doesn't support pop at index; convert to list
        qlist = list(queue)
        removed = qlist.pop(index - 1)
        self.queues[ctx.guild.id] = deque(qlist)
        await self.safe_send(ctx, f'🎧 **Removed:** {self.get_item_title(removed)}')

    @commands.command(help='Show the current queue')
    async def queue(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await self.safe_send(ctx, '❌ Queue is empty.')
            return
        embed = self.queue_to_embed(queue)
        await self.safe_send(ctx, embed=embed)

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

    @commands.command(help='Play a song/playlist from YouTube')
    async def play(self, ctx, *, url):
        if ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel lmao.')
            return
        
        voice = ctx.voice_client
        if voice and voice.channel != ctx.author.voice.channel:
            await ctx.send('❌ Nice try, you\'re not in my voice channel :)')
            return
        
        if not voice:
            await ctx.invoke(self.join)
            voice = ctx.voice_client

        async with ctx.typing():
            try:
                infos, pre_errors = await YTDLSource.create_info(ctx, url, loop=self.client.loop)
            except YTDLError as e:
                await ctx.send(f'⚠️ {str(e)}')
                return

        # enqueue metadata-only Track objects
        queue = self.get_queue(ctx.guild.id)
        lock = self.get_lock(ctx.guild.id)
        enqueued = 0
        async with lock:
            for info in infos:
                # attach requester/channel so we can show/mention later
                info['requester'] = ctx.author
                info['channel'] = ctx.channel
                queue.append(Track(info=info))
                enqueued += 1

        # report any pre-scan errors, mostly for malformed playlist entries
        if pre_errors:
            sample = pre_errors[:5]
            more = len(pre_errors) - len(sample)
            msg_lines = [f'⚠️ Skipped {len(pre_errors)} playlist entry(ies) during scan:']
            msg_lines += [f'• {s}' for s in sample]
            if more > 0:
                msg_lines.append(f'...and {more} more.')
            await ctx.send("\n".join(msg_lines))

        # cancel scheduled disconnect
        dt = self._disconnect_tasks.pop(ctx.guild.id, None)
        if dt and not dt.done():
            dt.cancel()

        # start playback if idle
        if not voice.is_playing():
            await self.play_next(ctx)
            await ctx.send(f'🎧 **Enqueued:** {enqueued} track(s)')
        else:
            await ctx.send(f'🎧 **Enqueued:** {enqueued} track(s)')
                
    async def play_next(self, ctx):
        """Play the next song in queue; build playable source on-demand and skip bad items."""
        voice = ctx.voice_client
        if not voice:
            return

        guild_id = ctx.guild.id
        lock = self.get_lock(guild_id)
        # Loop until we successfully start playback or the queue is exhausted
        while True:
            async with lock:
                queue = self.get_queue(guild_id)
                if not queue:
                    # schedule disconnect
                    if guild_id not in self._disconnect_tasks or self._disconnect_tasks[guild_id].done():
                        self._disconnect_tasks[guild_id] = asyncio.create_task(self._schedule_disconnect(guild_id, voice, delay=300))
                    self.now_playing.pop(guild_id, None)
                    return

                next_item = queue.popleft()

            source, error = await self._resolve_track_to_source(ctx, next_item)
            if error:
                title = self.get_item_title(next_item)
                await self.safe_send(ctx, f'⚠️ Skipped `{title}`: {error}')
                continue

            self.set_now_playing(guild_id, source)
            try:
                voice.play(source, after=self.make_after_callback(ctx))
                await self.send_to_channel(source.channel, embed=self.create_embed(source, 'Now Playing'))
                return
            except Exception as e:
                logger.exception(f'Playback start failed: {e}')
                continue

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