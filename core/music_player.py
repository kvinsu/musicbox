"""Music player logic and queue management"""
from collections import deque
from dataclasses import dataclass
from typing import Optional, Deque
import asyncio

@dataclass
class Track:
    info: dict

class MusicQueue:
    """Per-guild music queue manager"""
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue: Deque[Track] = deque()
        self.now_playing: Optional[Track] = None
        self.repeat_mode: bool = False
        self.lock: asyncio.Lock = asyncio.Lock()
    
    async def enqueue(self, tracks: list[Track]):
        async with self.lock:
            self.queue.extend(tracks)
    
    async def dequeue(self) -> Optional[Track]:
        async with self.lock:
            if not self.queue:
                return None
            return self.queue.popleft()
    
    async def clear(self):
        async with self.lock:
            self.queue.clear()
    
    async def shuffle(self):
        async with self.lock:
            import random
            temp = list(self.queue)
            random.shuffle(temp)
            self.queue = deque(temp)
    
    async def remove(self, index: int) -> Optional[Track]:
        async with self.lock:
            if 0 <= index < len(self.queue):
                temp = list(self.queue)
                removed = temp.pop(index)
                self.queue = deque(temp)
                return removed
            return None
    
    def size(self) -> int:
        return len(self.queue)

class MusicPlayer:
    """Manages music queues across guilds"""
    def __init__(self):
        self.queues: dict[int, MusicQueue] = {}
    
    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(guild_id)
        return self.queues[guild_id]
    
    def cleanup(self, guild_id: int):
        self.queues.pop(guild_id, None)