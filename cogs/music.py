"""Music cog with commands for playback control"""

import asyncio
import logging
from typing import Optional
import discord
from discord.ext import commands

from core.ytdl_source import YTDLSource, Track
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
        # Nothing awaits this coroutine, so log failures instead of losing them
        try:
            if exc:
                await ctx.channel.send(f'⚠️ Playback error: {exc}')
            await self.play_next(ctx)
        except Exception:
            logger.exception(f'Failed to continue playback in guild {ctx.guild.id}')

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
            # A stale client's disconnect() would unregister the guild's newer voice client
            if voice and voice.is_connected() and not voice.is_playing():
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
            await ctx.send('❌ I\'m not in a voice channel.')
            return False
        elif not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel.')
            return False
        elif voice.channel != ctx.author.voice.channel:
            await ctx.send('❌ You\'re not in my voice channel.')
            return False
        return True

    @commands.hybrid_command(name='join', help='Make the bot join your voice channel')
    @commands.guild_only()
    async def join(self, ctx: commands.Context) -> None:
        """Join user's voice channel"""
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await ctx.send('❌ You\'re not in a voice channel.')
            return

        channel = ctx.author.voice.channel
        # Defer slash interactions, connecting can exceed Discord's 3s limit
        async with ctx.typing():
            if ctx.voice_client is None:
                await channel.connect()
            else:
                await ctx.voice_client.move_to(channel)

        # Initialize queue for guild
        self.player.get_queue(ctx.guild.id)
        await ctx.send('👋')

    @commands.hybrid_command(name='leave', help='Make the bot leave the voice channel')
    @commands.guild_only()
    async def leave(self, ctx: commands.Context) -> None:
        """Leave voice channel and cleanup"""
        if not ctx.voice_client:
            await ctx.send('❌ I\'m not in a voice channel.')
            return

        # Defer slash interactions, disconnecting waits on the gateway
        async with ctx.typing():
            await ctx.voice_client.disconnect()
        self.player.cleanup(ctx.guild.id)
        # Cancel disconnect task
        dt = self._disconnect_tasks.pop(ctx.guild.id, None)
        if dt and not dt.done():
            dt.cancel()
        await ctx.send('👋')

    @commands.hybrid_command(name='skip', help='Skip the current song')
    @commands.guild_only()
    async def skip(self, ctx: commands.Context) -> None:
        """Skip current track"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing() and not voice.is_paused():
            await ctx.send('❌ Nothing is playing.')
            return

        # Otherwise repeat mode would replay the skipped track
        self.player.get_queue(ctx.guild.id).now_playing = None
        voice.stop()
        await ctx.send('⏭️ Skipped.')

    @commands.hybrid_command(name='pause', help='Pause the current song')
    @commands.guild_only()
    async def pause(self, ctx: commands.Context) -> None:
        """Pause playback"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        if not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return

        voice.pause()
        await ctx.send('⏸️ Paused.')

    @commands.hybrid_command(name='resume', help='Resume the current song')
    @commands.guild_only()
    async def resume(self, ctx: commands.Context) -> None:
        """Resume playback"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_paused():
            await ctx.send('❌ Nothing is paused.')
            return

        voice.resume()
        await ctx.send('▶️ Resuming...')

    @commands.hybrid_command(name='repeat', help='Toggle repeat mode', aliases=['loop'])
    @commands.guild_only()
    async def repeat(self, ctx: commands.Context) -> None:
        """Toggle repeat mode"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if (not voice.is_playing() and not voice.is_paused()) or queue.now_playing is None:
            await ctx.send('❌ Nothing is playing.')
            return

        queue.repeat_mode = not queue.repeat_mode
        status = 'ON' if queue.repeat_mode else 'OFF'
        await ctx.send(f'🔁 Repeat mode **{status}**')

    @commands.hybrid_command(name='shuffle', help='Shuffle the queue')
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle queue"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await ctx.send('❌ Queue is empty.')
            return

        await queue.shuffle()
        await ctx.send('🔀 Queue shuffled.')

    @commands.hybrid_command(name='stop', help='Stop playback and clear queue')
    @commands.guild_only()
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear queue"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return
        if not voice.is_playing() and not voice.is_paused():
            await ctx.send('❌ Nothing is playing.')
            return

        # Empty the queue and drop repeat first, the after-play callback would otherwise continue
        queue = self.player.get_queue(ctx.guild.id)
        queue.repeat_mode = False
        await queue.clear()
        voice.stop()
        await ctx.send('⏹️ Stopped playback and cleared the queue.')

    @commands.hybrid_command(name='clear', help='Clear the queue')
    @commands.guild_only()
    async def clear(self, ctx: commands.Context) -> None:
        """Clear the queue"""
        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await ctx.send('❌ Queue is empty.')
            return

        await queue.clear()
        await ctx.send('🗑️ Cleared the queue.')

    @commands.hybrid_command(name='remove', help='Remove a song from the queue')
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, index: int) -> None:
        """Remove track from queue by index"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0 or index < 1 or index > queue.size():
            await ctx.send('❌ Invalid index.')
            return

        removed = await queue.remove(index - 1)
        if removed:
            await ctx.send(f'🗑️ **Removed:** {removed.title}')
        else:
            await ctx.send('❌ Failed to remove track.')

    @commands.hybrid_command(name='queue', help='Show the current queue')
    @commands.guild_only()
    async def queue(self, ctx: commands.Context) -> None:
        """Display queue"""
        queue = self.player.get_queue(ctx.guild.id)
        if queue.size() == 0:
            await ctx.send('❌ Queue is empty.')
            return

        # Convert deque to list for embed builder
        queue_list = list(queue.queue)
        embed = EmbedBuilder.queue_list(queue_list)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='nowplaying', help='Show the currently playing song', aliases=['np'])
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context) -> None:
        """Show currently playing track"""
        voice = ctx.voice_client
        if not await self.voice_check(ctx, voice):
            return

        queue = self.player.get_queue(ctx.guild.id)
        if not queue.now_playing or (not voice.is_playing() and not voice.is_paused()):
            await ctx.send('❌ Nothing is playing.')
            return

        source = queue.now_playing
        embed = EmbedBuilder.music_now_playing(source, source.data.get('requester'))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='play', help='Play a song or playlist from YouTube')
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, song: str) -> None:
        """Play track or playlist"""
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
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
                tracks, errors = await YTDLSource.search(song, loop=self.client.loop)
            except YTDLError as e:
                await ctx.send(f'⚠️ {str(e)}')
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
            await ctx.send('\n'.join(msg_lines))

        if not tracks:
            await ctx.send('❌ No playable tracks found.')
            return

        # Cancel disconnect task
        dt = self._disconnect_tasks.pop(ctx.guild.id, None)
        if dt and not dt.done():
            dt.cancel()

        # Always reply here, slash commands need a response and play_next only posts to the channel
        await ctx.send(f'🎧 **Enqueued:** {len(tracks)} track(s)')

        # Start playback if idle, a paused track still owns the player
        if not voice.is_playing() and not voice.is_paused():
            await self.play_next(ctx)

    async def play_next(self, ctx: commands.Context) -> None:
        """Play next song; skip bad items"""
        voice = ctx.voice_client
        if not voice:
            return

        guild_id = ctx.guild.id
        queue = self.player.get_queue(guild_id)

        # The after-play callback and /play can race here, only one may start a track
        async with queue.play_lock:
            if not voice.is_connected() or voice.is_playing() or voice.is_paused():
                return

            while True:
                if queue.repeat_mode and queue.now_playing is not None:
                    track = Track(info=dict(queue.now_playing.data))
                else:
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
                    await ctx.channel.send(f'⚠️ Skipped `{track.title}`: {e}')
                    # Don't retry a broken repeat track forever
                    queue.now_playing = None
                    continue

                # Play; failures here aren't track specific (e.g. disconnected), so don't drain the queue
                try:
                    voice.play(source, after=self.make_after_callback(ctx))
                except Exception as e:
                    logger.exception(f'Playback start failed: {e}')
                    return

                # Set now playing
                queue.now_playing = source

                channel = source.data.get('channel')
                requester = source.data.get('requester')
                if channel:
                    await channel.send(
                        embed=EmbedBuilder.music_now_playing(source, requester)
                    )
                return

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Auto-disconnect when alone in voice channel"""
        if member == self.client.user:
            # Kicked or disconnected elsewhere, don't resume a stale queue on the next join
            if after.channel is None:
                self.player.cleanup(member.guild.id)
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