"""Music cog with commands for playback control"""

import asyncio
import logging
from typing import Optional
import discord
from discord.ext import commands

from core.ytdl_source import YTDLSource
from core.music_player import MusicPlayer
from core.embed_builder import EmbedBuilder
from utils.errors import YTDLError
from config.settings import Config

logger = logging.getLogger("musicbot")


class Music(commands.Cog):    
    def __init__(self, client: commands.Bot) -> None:
        self.client = client
        self.player = MusicPlayer()
        self._disconnect_tasks: dict[int, asyncio.Task] = {}

    async def safe_send(
        self, 
        ctx: commands.Context, 
        message: Optional[str] = None, 
        embed: Optional[discord.Embed] = None
    ) -> None:
        """Send message safely, ignoring send failures"""
        try:
            if embed:
                await ctx.send(embed=embed)
            elif message:
                await ctx.send(message)
        except Exception as e:
            logger.debug(f'Failed to send message: {e}')

    async def send_to_channel(
        self, 
        channel: discord.TextChannel, 
        message: Optional[str] = None, 
        embed: Optional[discord.Embed] = None
    ) -> None:
        """Send to a specific channel safely"""
        try:
            if embed:
                await channel.send(embed=embed)
            elif message:
                await channel.send(message)
        except Exception as e:
            logger.debug(f'Failed to send to channel: {e}')

    def make_after_callback(self, ctx: commands.Context):
        """Create callback that schedules async continuation"""
        def callback_wrapper(*args, **kwargs) -> None:
            exc = args[0] if args else kwargs.get('error', None)
            if exc:
                logger.error(f'FFmpeg/Player error in guild {ctx.guild.id}: {exc}')
            asyncio.run_coroutine_threadsafe(self._after_play(ctx, exc), self.client.loop)
        return callback_wrapper

    async def _after_play(self, ctx: commands.Context, exc: Optional[Exception]) -> None:
        """Async continuation called after track ends"""
        if exc:
            await self.safe_send(ctx, f'⚠️ Playback error: {exc}')
        await self.play_next(ctx)

    async def _schedule_disconnect(
        self, 
        guild_id: int, 
        voice: discord.VoiceClient, 
        delay: Optional[int] = None
    ) -> None:
        """Disconnect if nothing starts playing within delay seconds"""
        delay = delay or Config.DISCONNECT_TIMEOUT
        try:
            await asyncio.sleep(delay)
            if voice and not voice.is_playing():
                queue = self.player.get_queue(guild_id)
                if queue.size() == 0:
                    await voice.disconnect()
                    self.player.cleanup(guild_id)
                    logger.info(f'Disconnected due to inactivity in guild {guild_id}')
        except asyncio.CancelledError:
            pass

    async def voice_check(self, ctx: commands.Context, voice: Optional[discord.VoiceClient]) -> bool:
        """Check if bot and user are in same voice channel"""
        if not voice:
            await self.safe_send(ctx, '❌ I\'m not in a voice channel.')
            return False
        elif not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await self.safe_send(ctx, '❌ You\'re not in a voice channel.')
            return False
        elif voice.channel != ctx.author.voice.channel:
            await self.safe_send(ctx, '❌ You\'re not in my voice channel.')
            return False
        return True

    @commands.command(help='Make the bot join your voice channel')
    async def join(self, ctx: commands.Context) -> None:
        """Join user's voice channel"""
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await self.safe_send(ctx, '❌ You\'re not in a voice channel.')
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        else:
            await ctx.voice_client.move_to(channel)

        # Initialize queue for guild
        self.player.get_queue(ctx.guild.id)
        await ctx.message.add_reaction('👋')

    @commands.command(help='Make the bot leave the voice channel')
    async def leave(self, ctx: commands.Context) -> None:
        """Leave voice channel and cleanup"""
        if not ctx.voice_client:
            await self.safe_send(ctx, '❌ I\'m not in a voice channel.')
            return

        await ctx.voice_client.disconnect()
        self.player.cleanup(ctx.guild.id)
        # Cancel disconnect task
        dt = self._disconnect_tasks.pop(ctx.guild.id, None)
        if dt and not dt.done():
            dt.cancel()
        await ctx.message.add_reaction('👋')

    @commands.command(help='Skip the current song')
    async def skip(self, ctx: commands.Context) -> None:
        """Skip current track"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing():
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return

        voice.stop()
        await ctx.message.add_reaction('⏭️')

    @commands.command(help='Pause the current song')
    async def pause(self, ctx: commands.Context) -> None:
        """Pause playback"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        if not voice.is_playing():
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return

        voice.pause()
        await ctx.message.add_reaction('⏸️')

    @commands.command(help='Resume the current song')
    async def resume(self, ctx: commands.Context) -> None:
        """Resume playback"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_paused():
            await self.safe_send(ctx, '❌ Nothing is paused.')
            return

        voice.resume()
        await ctx.message.add_reaction('▶️')

    @commands.command(help='Toggle repeat mode', aliases=['loop'])
    async def repeat(self, ctx: commands.Context) -> None:
        """Toggle repeat mode"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if not voice.is_playing() or queue.now_playing is None:
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return

        queue.repeat_mode = not queue.repeat_mode
        status = 'ON' if queue.repeat_mode else 'OFF'
        await self.safe_send(ctx, f'🔁 Repeat mode **{status}**')

    @commands.command(help='Shuffle the queue')
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle queue"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await self.safe_send(ctx, '❌ Queue is empty.')
            return

        await queue.shuffle()
        await ctx.message.add_reaction('🔀')

    @commands.command(help='Stop playback and clear queue')
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear queue"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing():
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return

        voice.stop()
        queue = self.player.get_queue(ctx.guild.id)
        await queue.clear()
        await ctx.message.add_reaction('⏹️')

    @commands.command(help='Clear the queue')
    async def clear(self, ctx: commands.Context) -> None:
        """Clear the queue"""
        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await self.safe_send(ctx, '❌ Queue is empty.')
            return

        await queue.clear()
        await ctx.message.add_reaction('🗑️')

    @commands.command(help='Remove a song from the queue')
    async def remove(self, ctx: commands.Context, index: int) -> None:
        """Remove track from queue by index"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0 or index < 1 or index > queue.size():
            await self.safe_send(ctx, '❌ Invalid index.')
            return

        removed = await queue.remove(index - 1)
        if removed:
            await self.safe_send(ctx, f'🎧 **Removed:** {removed.title}')
        else:
            await self.safe_send(ctx, '❌ Failed to remove track.')

    @commands.command(help='Show the current queue')
    async def queue(self, ctx: commands.Context) -> None:
        """Display queue"""
        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await self.safe_send(ctx, '❌ Queue is empty.')
            return

        # Convert deque to list for embed builder
        queue_list = list(queue.queue)
        embed = EmbedBuilder.queue_list(queue_list)
        await self.safe_send(ctx, embed=embed)

    @commands.command(help='Show the currently playing song', aliases=['np'])
    async def nowplaying(self, ctx: commands.Context) -> None:
        """Show currently playing track"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if not queue.now_playing or not voice.is_playing():
            await self.safe_send(ctx, '❌ Nothing is playing.')
            return

        source = queue.now_playing
        embed = EmbedBuilder.music_now_playing(source, source.info.get('requester'))
        await self.safe_send(ctx, embed=embed)

    @commands.command(help='Play a song/playlist from YouTube')
    async def play(self, ctx: commands.Context, *, url: str) -> None:
        """Play track or playlist"""
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await self.safe_send(ctx, '❌ You\'re not in a voice channel.')
            return

        voice = ctx.voice_client
        if voice and voice.channel != ctx.author.voice.channel:
            await self.safe_send(ctx, '❌ You\'re not in my voice channel.')
            return

        if not voice:
            await ctx.invoke(self.join)
            voice = ctx.voice_client

        async with ctx.typing():
            try:
                tracks, errors = await YTDLSource.search(url, loop=self.client.loop)
            except YTDLError as e:
                await self.safe_send(ctx, f'⚠️ {str(e)}')
                return

        # Attach requester/channel to each track
        for track in tracks:
            track.info['requester'] = ctx.author
            track.info['channel'] = ctx.channel

        # Enqueue tracks
        queue = self.player.get_queue(ctx.guild.id)
        await queue.enqueue(tracks)

        # Report skipped entries
        if errors:
            sample = errors[:5]
            more = len(errors) - len(sample)
            msg_lines = [f'⚠️ Skipped {len(errors)} entry(ies):']
            msg_lines += [f'• {s}' for s in sample]
            if more > 0:
                msg_lines.append(f'...and {more} more.')
            await self.safe_send(ctx, '\n'.join(msg_lines))

        # Cancel disconnect task
        dt = self._disconnect_tasks.pop(ctx.guild.id, None)
        if dt and not dt.done():
            dt.cancel()

        # Start playback if idle
        if not voice.is_playing():
            await self.play_next(ctx)
        else:
            await self.safe_send(ctx, f'🎧 **Enqueued:** {len(tracks)} track(s)')

    async def play_next(self, ctx: commands.Context) -> None:
        """Play next song; skip bad items"""
        voice = ctx.voice_client
        if not voice:
            return

        guild_id = ctx.guild.id
        queue = self.player.get_queue(guild_id)

        while True:
            track = await queue.dequeue()
            if not track:
                # Schedule disconnect
                if guild_id not in self._disconnect_tasks or self._disconnect_tasks[guild_id].done():
                    self._disconnect_tasks[guild_id] = asyncio.create_task(
                        self._schedule_disconnect(guild_id, voice)
                    )
                return

            # Try to create playable source
            try:
                source = await YTDLSource.create_source(track, loop=self.client.loop)
            except YTDLError as e:
                logger.warning(f"Failed to create source: {e}")
                await self.safe_send(ctx, f'⚠️ Skipped `{track.title}`: {e}')
                continue

            # Set now playing
            queue.now_playing = source

            # Play
            try:
                voice.play(source, after=self.make_after_callback(ctx))
                channel = source.data.get('channel')
                requester = source.data.get('requester')
                if channel:
                    await self.send_to_channel(
                        channel,
                        embed=EmbedBuilder.music_now_playing(source, requester)
                    )
                return
            except Exception as e:
                logger.exception(f'Playback start failed: {e}')
                continue

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, 
        member: discord.Member, 
        before: discord.VoiceState, 
        after: discord.VoiceState
    ) -> None:
        """Auto-disconnect when alone in voice channel"""
        if member == self.client.user:
            return

        voice = member.guild.voice_client
        if not voice or not voice.channel:
            return

        if len(voice.channel.members) == 1:
            await voice.disconnect()
            self.player.cleanup(member.guild.id)


async def setup(client: commands.Bot) -> None:
    """Setup function for cog"""
    await client.add_cog(Music(client))