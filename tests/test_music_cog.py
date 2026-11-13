import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import Config
from tests.fakes import FakeSource, FakeVoice, eventually, make_track
from utils.errors import YTDLError


def queued_titles(cog) -> list[str]:
    return [t.title for t in cog.player.get_queue(1)]


def playing_title(voice: FakeVoice) -> str | None:
    return voice.source.title if voice.source else None


@pytest.fixture
def channel() -> MagicMock:
    """Text channel the tracks were requested from"""
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


def enqueue(cog, *titles, channel=None):
    cog.player.get_queue(1).enqueue([make_track(t, channel=channel) for t in titles])


class TestPlayNext:
    async def test_starts_next_track_and_announces_it(self, cog, ctx, voice, channel, created_sources):
        enqueue(cog, 'a', 'b', channel=channel)

        await cog.play_next(ctx)

        assert playing_title(voice) == 'a'
        assert cog.player.get_queue(1).now_playing is voice.source
        assert queued_titles(cog) == ['b']
        channel.send.assert_awaited_once()
        assert channel.send.await_args.kwargs['embed'].description == 'a'

    async def test_finished_track_advances_from_player_thread(self, cog, ctx, voice, created_sources):
        enqueue(cog, 'a', 'b')
        await cog.play_next(ctx)

        # discord.py calls `after` from the audio player thread
        await asyncio.to_thread(voice.finish)

        await eventually(lambda: playing_title(voice) == 'b')
        assert queued_titles(cog) == []

    async def test_concurrent_calls_start_one_track_and_keep_the_rest(self, cog, ctx, voice, created_sources):
        enqueue(cog, 'a', 'b', 'c')

        # The after-play callback and /play both calling play_next while idle
        await asyncio.gather(cog.play_next(ctx), cog.play_next(ctx))

        assert voice.play_calls == 1
        assert playing_title(voice) == 'a'
        assert queued_titles(cog) == ['b', 'c']

    async def test_does_nothing_while_paused(self, cog, ctx, voice, created_sources):
        voice.source = FakeSource({'title': 'current'})
        voice.pause()
        enqueue(cog, 'a')

        await cog.play_next(ctx)

        assert playing_title(voice) == 'current'
        assert queued_titles(cog) == ['a']

    async def test_play_failure_does_not_drain_queue(self, cog, ctx, created_sources):
        ctx.voice_client = FakeVoice(play_error=RuntimeError('voice websocket closed'))
        enqueue(cog, 'a', 'b', 'c')

        await cog.play_next(ctx)

        assert ctx.voice_client.play_calls == 1
        assert queued_titles(cog) == ['b', 'c']

    async def test_skips_tracks_that_fail_to_load(self, cog, ctx, voice, monkeypatch):
        async def create_source(track):
            if track.title == 'broken':
                raise YTDLError('unavailable')
            return FakeSource(track.info)

        monkeypatch.setattr('cogs.music.YTDLSource.create_source', create_source)
        enqueue(cog, 'broken', 'ok')

        await cog.play_next(ctx)

        assert playing_title(voice) == 'ok'
        assert 'Skipped `broken`' in ctx.channel.send.await_args_list[0].args[0]
        ctx.send.assert_not_awaited()

    async def test_repeat_replays_current_track(self, cog, ctx, voice, created_sources):
        queue = cog.player.get_queue(1)
        queue.repeat_mode = True
        queue.now_playing = FakeSource({'title': 'current', 'webpage_url': 'https://youtu.be/current'})
        enqueue(cog, 'next')

        await cog.play_next(ctx)

        assert playing_title(voice) == 'current'
        assert queued_titles(cog) == ['next']

    async def test_broken_repeat_track_falls_back_to_queue(self, cog, ctx, voice, monkeypatch):
        attempts = []

        async def create_source(track):
            if track.title == 'current':
                attempts.append(track)
                assert len(attempts) == 1, 'broken repeat track was retried'
                raise YTDLError('gone')
            return FakeSource(track.info)

        monkeypatch.setattr('cogs.music.YTDLSource.create_source', create_source)
        queue = cog.player.get_queue(1)
        queue.repeat_mode = True
        queue.now_playing = FakeSource({'title': 'current'})
        enqueue(cog, 'next')

        await cog.play_next(ctx)

        assert playing_title(voice) == 'next'

    async def test_empty_queue_schedules_inactivity_disconnect(self, cog, ctx):
        await cog.play_next(ctx)

        assert not cog._disconnect_tasks[1].done()


class TestPlayCommand:
    @pytest.fixture
    def search(self, monkeypatch):
        search = AsyncMock(return_value=([make_track('a')], []))
        monkeypatch.setattr('cogs.music.YTDLSource.search', search)
        return search

    async def test_replies_and_starts_playback_when_idle(self, cog, ctx, search, monkeypatch):
        monkeypatch.setattr(cog, 'play_next', AsyncMock())

        await cog.play.callback(cog, ctx, song='a')

        ctx.send.assert_awaited_once_with('🎧 **Enqueued:** 1 track(s)')
        cog.play_next.assert_awaited_once_with(ctx)
        assert queued_titles(cog) == ['a']

    async def test_joins_the_callers_channel_first(self, cog, ctx, voice, search, monkeypatch):
        monkeypatch.setattr(cog, 'play_next', AsyncMock())
        ctx.voice_client = None

        async def join(command):
            ctx.voice_client = voice

        ctx.invoke.side_effect = join

        await cog.play.callback(cog, ctx, song='a')

        ctx.invoke.assert_awaited_once_with(cog.join)
        cog.play_next.assert_awaited_once_with(ctx)

    async def test_only_enqueues_while_paused(self, cog, ctx, voice, search, monkeypatch):
        voice.source = FakeSource({'title': 'current'})
        voice.pause()
        monkeypatch.setattr(cog, 'play_next', AsyncMock())

        await cog.play.callback(cog, ctx, song='a')

        cog.play_next.assert_not_awaited()
        assert queued_titles(cog) == ['a']

    async def test_replies_when_nothing_was_found(self, cog, ctx, search, monkeypatch):
        search.return_value = ([], [])
        monkeypatch.setattr(cog, 'play_next', AsyncMock())

        await cog.play.callback(cog, ctx, song='nothing')

        ctx.send.assert_awaited_once_with('❌ No playable tracks found.')
        cog.play_next.assert_not_awaited()

    async def test_cancels_pending_inactivity_disconnect(self, cog, ctx, search, monkeypatch):
        monkeypatch.setattr(cog, 'play_next', AsyncMock())
        pending = asyncio.create_task(asyncio.sleep(60))
        cog._disconnect_tasks[1] = pending

        await cog.play.callback(cog, ctx, song='a')
        await asyncio.sleep(0)

        assert pending.cancelled()


class TestControls:
    async def start(self, cog, ctx, *titles):
        enqueue(cog, *titles)
        await cog.play_next(ctx)

    async def test_skip_plays_next_track(self, cog, ctx, voice, created_sources):
        await self.start(cog, ctx, 'a', 'b')

        await cog.skip.callback(cog, ctx)

        await eventually(lambda: playing_title(voice) == 'b')
        ctx.send.assert_awaited_once_with('⏭️ Skipped.')

    async def test_skip_with_repeat_moves_to_next_track(self, cog, ctx, voice, created_sources):
        await self.start(cog, ctx, 'a', 'b')
        cog.player.get_queue(1).repeat_mode = True

        await cog.skip.callback(cog, ctx)

        await eventually(lambda: playing_title(voice) == 'b')

    async def test_skip_works_while_paused(self, cog, ctx, voice, created_sources):
        await self.start(cog, ctx, 'a', 'b')
        voice.pause()

        await cog.skip.callback(cog, ctx)

        await eventually(lambda: playing_title(voice) == 'b')

    async def test_stop_with_repeat_ends_playback(self, cog, ctx, voice, created_sources):
        await self.start(cog, ctx, 'a', 'b')
        cog.player.get_queue(1).repeat_mode = True

        await cog.stop.callback(cog, ctx)

        # The after-play callback finds nothing left and schedules the inactivity disconnect
        await eventually(lambda: 1 in cog._disconnect_tasks)
        assert voice.source is None
        assert voice.play_calls == 1
        assert queued_titles(cog) == []

    async def test_remove_uses_one_based_index(self, cog, ctx):
        enqueue(cog, 'a', 'b', 'c')

        await cog.remove.callback(cog, ctx, 2)

        assert queued_titles(cog) == ['a', 'c']
        ctx.send.assert_awaited_once_with('🗑️ **Removed:** b')

    @pytest.mark.parametrize('index', [0, 4])
    async def test_remove_rejects_out_of_range_index(self, cog, ctx, index):
        enqueue(cog, 'a', 'b', 'c')

        await cog.remove.callback(cog, ctx, index)

        assert queued_titles(cog) == ['a', 'b', 'c']
        ctx.send.assert_awaited_once_with('❌ Invalid index.')

    async def test_controls_require_the_same_voice_channel(self, cog, ctx, voice, created_sources):
        await self.start(cog, ctx, 'a')
        ctx.author.voice.channel = object()

        await cog.skip.callback(cog, ctx)

        assert playing_title(voice) == 'a'
        ctx.send.assert_awaited_once_with("❌ You're not in my voice channel.")


class TestDisconnects:
    @pytest.fixture(autouse=True)
    def no_delay(self, monkeypatch):
        monkeypatch.setattr(Config, 'DISCONNECT_TIMEOUT', 0)

    async def test_inactivity_disconnects_idle_client(self, cog, voice):
        queue = cog.player.get_queue(1)

        await cog._disconnect_when_idle(1, voice)

        voice.disconnect.assert_awaited_once()
        assert cog.player.get_queue(1) is not queue

    async def test_inactivity_ignores_stale_client(self, cog):
        stale = FakeVoice(connected=False)
        queue = cog.player.get_queue(1)

        await cog._disconnect_when_idle(1, stale)

        stale.disconnect.assert_not_awaited()
        assert cog.player.get_queue(1) is queue

    async def test_leave_cancels_pending_inactivity_disconnect(self, cog, ctx, voice):
        pending = asyncio.create_task(asyncio.sleep(60))
        cog._disconnect_tasks[1] = pending

        await cog.leave.callback(cog, ctx)
        await asyncio.sleep(0)

        voice.disconnect.assert_awaited_once()
        assert pending.cancelled()

    async def test_bot_leaving_voice_drops_guild_state(self, cog):
        queue = cog.player.get_queue(1)
        queue.repeat_mode = True
        member = cog.client.user
        member.guild.id = 1

        await cog.on_voice_state_update(member, MagicMock(), MagicMock(channel=None))

        assert cog.player.get_queue(1) is not queue

    async def test_leaves_when_alone_in_channel(self, cog, voice):
        member = MagicMock()
        member.guild.id = 1
        member.guild.voice_client = voice
        voice.channel = MagicMock(members=[cog.client.user])

        await cog.on_voice_state_update(member, MagicMock(), MagicMock())

        voice.disconnect.assert_awaited_once()


async def test_after_play_logs_instead_of_raising(cog, ctx, monkeypatch, caplog):
    monkeypatch.setattr(cog, 'play_next', AsyncMock(side_effect=RuntimeError('boom')))

    with caplog.at_level(logging.ERROR, logger='musicbot'):
        await cog._after_play(ctx, RuntimeError('ffmpeg died'))

    ctx.channel.send.assert_awaited_once_with('⚠️ Playback error: ffmpeg died')
    assert 'Failed to continue playback in guild 1' in caplog.text
