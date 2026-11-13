"""Music cog with commands for playback control"""

import asyncio
import logging

import discord
from discord.ext import commands

from config.settings import Config
from core.embed_builder import EmbedBuilder
from core.music_player import MusicPlayer, MusicQueue
from core.ytdl_source import Track, YTDLSource
from utils.errors import YTDLError

logger = logging.getLogger('musicbot')


def is_active(voice: discord.VoiceClient) -> bool:
    """Playing or paused; is_playing() alone is False while paused"""
    return voice.is_playing() or voice.is_paused()


class Music(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client
        self.player = MusicPlayer()
        self._disconnect_tasks: dict[int, asyncio.Task] = {}

    def _queue(self, ctx: commands.Context) -> MusicQueue:
        return self.player.get_queue(ctx.guild.id)

    def make_after_callback(self, ctx: commands.Context):
        """Callback for voice.play(); discord.py calls it from the audio player thread"""

        def after(error: Exception | None) -> None:
            if error:
                logger.error(f'FFmpeg/Player error in guild {ctx.guild.id}: {error}')
            asyncio.run_coroutine_threadsafe(self._after_play(ctx, error), self.client.loop)

        return after

    async def _after_play(self, ctx: commands.Context, error: Exception | None) -> None:
        # Nothing awaits this coroutine, so log failures instead of losing them
        try:
            if error:
                await ctx.channel.send(f'⚠️ Playback error: {error}')
            await self.play_next(ctx)
        except Exception:
            logger.exception(f'Failed to continue playback in guild {ctx.guild.id}')

    def _start_disconnect_timer(self, guild_id: int, voice: discord.VoiceClient) -> None:
        task = self._disconnect_tasks.get(guild_id)
        if task is None or task.done():
            self._disconnect_tasks[guild_id] = asyncio.create_task(self._disconnect_when_idle(guild_id, voice))

    def _cancel_disconnect_timer(self, guild_id: int) -> None:
        if task := self._disconnect_tasks.pop(guild_id, None):
            task.cancel()

    async def _disconnect_when_idle(self, guild_id: int, voice: discord.VoiceClient) -> None:
        """Leave voice if nothing starts playing within DISCONNECT_TIMEOUT seconds"""
        await asyncio.sleep(Config.DISCONNECT_TIMEOUT)
        # A stale client's disconnect() would unregister the guild's newer voice client
        if voice.is_connected() and not is_active(voice) and not self.player.get_queue(guild_id):
            await voice.disconnect()
            self.player.cleanup(guild_id)
            logger.info(f'Disconnected due to inactivity in guild {guild_id}')

    async def _voice_for(self, ctx: commands.Context) -> discord.VoiceClient | None:
        """The bot's voice client if the author is in the same channel, otherwise reply why not"""
        voice = ctx.voice_client
        if not voice:
            await ctx.send("❌ I'm not in a voice channel.")
        elif not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await ctx.send("❌ You're not in a voice channel.")
        elif voice.channel != ctx.author.voice.channel:
            await ctx.send("❌ You're not in my voice channel.")
        else:
            return voice
        return None

    @commands.hybrid_command(name='join', help='Make the bot join your voice channel')
    @commands.guild_only()
    async def join(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await ctx.send("❌ You're not in a voice channel.")
            return

        channel = ctx.author.voice.channel
        # Defer slash interactions, connecting can exceed Discord's 3s limit
        async with ctx.typing():
            if ctx.voice_client is None:
                await channel.connect()
            else:
                await ctx.voice_client.move_to(channel)
        await ctx.send('👋')

    @commands.hybrid_command(name='leave', help='Make the bot leave the voice channel')
    @commands.guild_only()
    async def leave(self, ctx: commands.Context) -> None:
        voice = ctx.voice_client
        if not voice:
            await ctx.send("❌ I'm not in a voice channel.")
            return

        # Defer slash interactions, disconnecting waits on the gateway
        async with ctx.typing():
            await voice.disconnect()
        self.player.cleanup(ctx.guild.id)
        self._cancel_disconnect_timer(ctx.guild.id)
        await ctx.send('👋')

    @commands.hybrid_command(name='skip', help='Skip the current song')
    @commands.guild_only()
    async def skip(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        if not is_active(voice):
            await ctx.send('❌ Nothing is playing.')
            return

        # Otherwise repeat mode would replay the skipped track
        self._queue(ctx).now_playing = None
        voice.stop()
        await ctx.send('⏭️ Skipped.')

    @commands.hybrid_command(name='pause', help='Pause the current song')
    @commands.guild_only()
    async def pause(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        if not voice.is_playing():
            await ctx.send('❌ Nothing is playing.')
            return

        voice.pause()
        await ctx.send('⏸️ Paused.')

    @commands.hybrid_command(name='resume', help='Resume the current song')
    @commands.guild_only()
    async def resume(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        if not voice.is_paused():
            await ctx.send('❌ Nothing is paused.')
            return

        voice.resume()
        await ctx.send('▶️ Resuming...')

    @commands.hybrid_command(name='repeat', help='Toggle repeat mode', aliases=['loop'])
    @commands.guild_only()
    async def repeat(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        queue = self._queue(ctx)
        if not is_active(voice) or queue.now_playing is None:
            await ctx.send('❌ Nothing is playing.')
            return

        queue.repeat_mode = not queue.repeat_mode
        await ctx.send(f'🔁 Repeat mode **{"ON" if queue.repeat_mode else "OFF"}**')

    @commands.hybrid_command(name='shuffle', help='Shuffle the queue')
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context) -> None:
        if not await self._voice_for(ctx):
            return
        queue = self._queue(ctx)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return

        queue.shuffle()
        await ctx.send('🔀 Queue shuffled.')

    @commands.hybrid_command(name='stop', help='Stop playback and clear queue')
    @commands.guild_only()
    async def stop(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        if not is_active(voice):
            await ctx.send('❌ Nothing is playing.')
            return

        # Empty the queue and drop repeat first, the after-play callback would otherwise continue
        queue = self._queue(ctx)
        queue.repeat_mode = False
        queue.clear()
        voice.stop()
        await ctx.send('⏹️ Stopped playback and cleared the queue.')

    @commands.hybrid_command(name='clear', help='Clear the queue')
    @commands.guild_only()
    async def clear(self, ctx: commands.Context) -> None:
        queue = self._queue(ctx)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return

        queue.clear()
        await ctx.send('🗑️ Cleared the queue.')

    @commands.hybrid_command(name='remove', help='Remove a song from the queue')
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, index: int) -> None:
        if not await self._voice_for(ctx):
            return
        removed = self._queue(ctx).remove(index - 1)
        if removed is None:
            await ctx.send('❌ Invalid index.')
            return

        await ctx.send(f'🗑️ **Removed:** {removed.title}')

    @commands.hybrid_command(name='queue', help='Show the current queue')
    @commands.guild_only()
    async def show_queue(self, ctx: commands.Context) -> None:
        queue = self._queue(ctx)
        if not queue:
            await ctx.send('❌ Queue is empty.')
            return

        await ctx.send(embed=EmbedBuilder.queue_list(list(queue)))

    @commands.hybrid_command(name='nowplaying', help='Show the currently playing song', aliases=['np'])
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context) -> None:
        voice = await self._voice_for(ctx)
        if not voice:
            return
        source = self._queue(ctx).now_playing
        if source is None or not is_active(voice):
            await ctx.send('❌ Nothing is playing.')
            return

        await ctx.send(embed=EmbedBuilder.music_now_playing(source, source.requester))

    @commands.hybrid_command(name='play', help='Play a song or playlist from YouTube')
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, song: str) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
            await ctx.send("❌ You're not in a voice channel.")
            return

        voice = ctx.voice_client
        if voice and voice.channel != ctx.author.voice.channel:
            await ctx.send("❌ You're not in my voice channel.")
            return
        if not voice:
            await ctx.invoke(self.join)
            voice = ctx.voice_client

        async with ctx.typing():
            try:
                tracks, errors = await YTDLSource.search(song)
            except YTDLError as e:
                await ctx.send(f'⚠️ {e}')
                return

        for track in tracks:
            track.info['requester'] = ctx.author
            track.info['channel'] = ctx.channel
        self._queue(ctx).enqueue(tracks)

        if errors:
            await ctx.send(self._skipped_message(errors))
        if not tracks:
            await ctx.send('❌ No playable tracks found.')
            return

        self._cancel_disconnect_timer(ctx.guild.id)
        # Always reply here, slash commands need a response and play_next only posts to the channel
        await ctx.send(f'🎧 **Enqueued:** {len(tracks)} track(s)')

        # Start playback if idle, a paused track still owns the player
        if not is_active(voice):
            await self.play_next(ctx)

    @staticmethod
    def _skipped_message(errors: list[str]) -> str:
        lines = [f'⚠️ Skipped {len(errors)} entry(ies):', *(f'• {error}' for error in errors[:5])]
        if len(errors) > 5:
            lines.append(f'...and {len(errors) - 5} more.')
        return '\n'.join(lines)

    async def play_next(self, ctx: commands.Context) -> None:
        """Start the next track (or the current one again in repeat mode), skipping tracks that fail to load"""
        voice = ctx.voice_client
        if not voice:
            return

        queue = self._queue(ctx)
        # The after-play callback and /play can race here, only one may start a track
        async with queue.play_lock:
            if not voice.is_connected() or is_active(voice):
                return

            while True:
                if queue.repeat_mode and queue.now_playing is not None:
                    track = Track(info=dict(queue.now_playing.data))
                else:
                    track = queue.dequeue()
                    if track is None:
                        self._start_disconnect_timer(ctx.guild.id, voice)
                        return

                try:
                    source = await YTDLSource.create_source(track)
                except YTDLError as e:
                    logger.warning(f'Failed to create source: {e}')
                    await ctx.channel.send(f'⚠️ Skipped `{track.title}`: {e}')
                    # Don't retry a broken repeat track forever
                    queue.now_playing = None
                    continue

                # Failures here aren't track specific (e.g. disconnected), so don't drain the queue
                try:
                    voice.play(source, after=self.make_after_callback(ctx))
                except Exception:
                    logger.exception('Playback start failed')
                    return

                queue.now_playing = source
                if source.channel:
                    await source.channel.send(embed=EmbedBuilder.music_now_playing(source, source.requester))
                return

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Drop state when the bot leaves voice, and leave when nobody else is left"""
        if member == self.client.user:
            # Kicked or disconnected elsewhere, don't resume a stale queue on the next join
            if after.channel is None:
                self.player.cleanup(member.guild.id)
            return

        voice = member.guild.voice_client
        if voice and voice.channel and len(voice.channel.members) == 1:
            await voice.disconnect()
            self.player.cleanup(member.guild.id)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Music(client))
