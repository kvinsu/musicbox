import random

from core.music_player import MusicPlayer, MusicQueue
from tests.fakes import make_track


def titles(queue: MusicQueue) -> list[str]:
    return [track.title for track in queue]


def test_queue_is_first_in_first_out():
    queue = MusicQueue()
    queue.enqueue([make_track('a'), make_track('b')])

    assert queue.dequeue().title == 'a'
    assert queue.dequeue().title == 'b'
    assert queue.dequeue() is None


def test_len_counts_waiting_tracks():
    queue = MusicQueue()
    assert len(queue) == 0

    queue.enqueue([make_track('a'), make_track('b')])

    assert len(queue) == 2


def test_remove_returns_track_at_index():
    queue = MusicQueue()
    queue.enqueue([make_track('a'), make_track('b'), make_track('c')])

    assert queue.remove(1).title == 'b'
    assert titles(queue) == ['a', 'c']


def test_remove_out_of_range_returns_none():
    queue = MusicQueue()
    queue.enqueue([make_track('a')])

    assert queue.remove(1) is None
    assert queue.remove(-1) is None
    assert titles(queue) == ['a']


def test_shuffle_reorders_queue(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda items: items.reverse())
    queue = MusicQueue()
    queue.enqueue([make_track('a'), make_track('b'), make_track('c')])

    queue.shuffle()

    assert titles(queue) == ['c', 'b', 'a']


def test_clear_empties_queue():
    queue = MusicQueue()
    queue.enqueue([make_track('a')])

    queue.clear()

    assert len(queue) == 0


def test_player_keeps_one_queue_per_guild_until_cleanup():
    player = MusicPlayer()
    first = player.get_queue(1)

    assert player.get_queue(1) is first
    assert player.get_queue(2) is not first

    player.cleanup(1)
    assert player.get_queue(1) is not first
