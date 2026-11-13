"""Reusable embed templates"""

from collections.abc import Sequence

import discord

from core.ytdl_source import Track, YTDLSource


class EmbedBuilder:
    @staticmethod
    def music_now_playing(song: YTDLSource, requester: discord.abc.User | None) -> discord.Embed:
        """Create now-playing embed"""
        embed = discord.Embed(
            title='🎧 Now Playing',
            description=song.title,
            url=song.url,
            color=discord.Color.blurple(),
        )
        embed.add_field(name='Duration', value=EmbedBuilder._format_duration(song.duration))
        uploader = f'[{song.uploader}]({song.uploader_url})' if song.uploader_url else song.uploader
        embed.add_field(name='Uploader', value=uploader or 'Unknown')
        embed.set_thumbnail(url=song.thumbnail)
        if requester:
            embed.set_footer(text=f'Requested by {requester}', icon_url=requester.display_avatar.url)
        return embed

    @staticmethod
    def queue_list(tracks: Sequence[Track], title: str = '🎧 Queue') -> discord.Embed:
        """Create queue embed showing the first ten tracks"""
        if not tracks:
            return discord.Embed(title=title, description='Queue is empty', color=discord.Color.blurple())

        lines = [f'**{i}.** {track.title}' for i, track in enumerate(tracks[:10], 1)]
        embed = discord.Embed(title=title, description='\n'.join(lines), color=discord.Color.blurple())
        total = sum(track.duration for track in tracks)
        embed.add_field(name='Total Duration', value=EmbedBuilder._format_duration(total))
        if len(tracks) > 10:
            embed.add_field(name='...and more', value=f'{len(tracks) - 10} more songs')
        return embed

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format seconds like '1h 2m 3s', or '/' when unknown"""
        if not seconds:
            return '/'

        minutes, secs = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f'{days}d')
        if hours:
            parts.append(f'{hours}h')
        if minutes:
            parts.append(f'{minutes}m')
        if secs or not parts:
            parts.append(f'{secs}s')
        return ' '.join(parts)
