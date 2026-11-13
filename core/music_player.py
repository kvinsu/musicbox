"""Per-guild queue state"""

import asyncio
import random
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator

from core.ytdl_source import Track, YTDLSource


class MusicQueue:
    """Tracks waiting to play in one guild, plus the one playing now.

    Queue operations never await, so they are atomic on the event loop and
    need no lock of their own.
    """

    def __init__(self) -> None:
        self._tracks: deque[Track] = deque()
        self.now_playing: YTDLSource | None = None
        self.repeat_mode = False
        # Held while picking and starting the next track, which spans awaits
        self.play_lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._tracks)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._tracks)

    def enqueue(self, tracks: Iterable[Track]) -> None:
        self._tracks.extend(tracks)

    def dequeue(self) -> Track | None:
        return self._tracks.popleft() if self._tracks else None

    def clear(self) -> None:
        self._tracks.clear()

    def shuffle(self) -> None:
        random.shuffle(self._tracks)

    def remove(self, index: int) -> Track | None:
        """Remove and return the track at a zero-based index, if there is one"""
        if not 0 <= index < len(self._tracks):
            return None
        track = self._tracks[index]
        del self._tracks[index]
        return track


class MusicPlayer:
    """Queues for every guild the bot plays in"""

    def __init__(self) -> None:
        self.queues: defaultdict[int, MusicQueue] = defaultdict(MusicQueue)

    def get_queue(self, guild_id: int) -> MusicQueue:
        return self.queues[guild_id]

    def cleanup(self, guild_id: int) -> None:
        self.queues.pop(guild_id, None)
