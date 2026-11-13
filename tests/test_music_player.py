import random

from core.music_player import MusicPlayer, MusicQueue
from tests.fakes import make_track


async def test_queue_is_first_in_first_out():
    queue = MusicQueue(guild_id=1)
    await queue.enqueue([make_track('a'), make_track('b')])

    assert (await queue.dequeue()).title == 'a'
    assert (await queue.dequeue()).title == 'b'
    assert await queue.dequeue() is None


async def test_remove_returns_track_at_index():
    queue = MusicQueue(guild_id=1)
    await queue.enqueue([make_track('a'), make_track('b'), make_track('c')])

    removed = await queue.remove(1)

    assert removed.title == 'b'
    assert [t.title for t in queue.queue] == ['a', 'c']


async def test_remove_out_of_range_returns_none():
    queue = MusicQueue(guild_id=1)
    await queue.enqueue([make_track('a')])

    assert await queue.remove(1) is None
    assert await queue.remove(-1) is None
    assert queue.size() == 1


async def test_shuffle_reorders_queue(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda items: items.reverse())
    queue = MusicQueue(guild_id=1)
    await queue.enqueue([make_track('a'), make_track('b'), make_track('c')])

    await queue.shuffle()

    assert [t.title for t in queue.queue] == ['c', 'b', 'a']


async def test_clear_empties_queue():
    queue = MusicQueue(guild_id=1)
    await queue.enqueue([make_track('a')])

    await queue.clear()

    assert queue.size() == 0


def test_player_keeps_one_queue_per_guild_until_cleanup():
    player = MusicPlayer()
    first = player.get_queue(1)

    assert player.get_queue(1) is first
    assert player.get_queue(2) is not first

    player.cleanup(1)
    assert player.get_queue(1) is not first
