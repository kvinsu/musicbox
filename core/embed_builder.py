"""Reusable embed templates"""
import discord

class EmbedBuilder:
    @staticmethod
    def music_now_playing(song, requester) -> discord.Embed:
        """Create now-playing embed"""
        avatar_url = None
        try:
            avatar_url = str(requester.display_avatar.url)
        except Exception:
            pass
        
        duration = int(song.duration) if song.duration else 0

        embed = discord.Embed(
            title='🎧 Now Playing',
            description=song.title,
            url=song.url,
            color=discord.Color.blurple()
        )
        embed.add_field(name='Duration', value=EmbedBuilder._format_duration(duration))
        embed.add_field(name='Uploader', value=f'[{song.uploader}]({song.uploader_url})')
        embed.set_thumbnail(url=song.thumbnail)
        embed.set_footer(text=f'Requested by {requester}', icon_url=avatar_url)
        return embed
    
    @staticmethod
    def queue_list(queue, title='🎧 Queue') -> discord.Embed:
        """Create queue embed"""
        if not queue:
            return discord.Embed(title=title, description='Queue is empty', color=discord.Color.blurple())
        
        titles = [f'**{i}.** {track.title}' for i, track in enumerate(queue, 1)]
        total_duration = sum(int(track.duration) if track.duration else 0 for track in queue)
        
        embed = discord.Embed(
            title=title,
            description='\n'.join(titles[:10]),
            color=discord.Color.blurple()
        )
        embed.add_field(name='Total Duration', value=EmbedBuilder._format_duration(total_duration))
        
        if len(titles) > 10:
            embed.add_field(name='...and more', value=f'{len(titles) - 10} more songs')
        
        return embed
    
    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format seconds to readable duration"""
        if seconds == 0:
            return '/'
        
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        parts = []
        if days > 0:
            parts.append(f'{days}d')
        if hours > 0:
            parts.append(f'{hours}h')
        if minutes > 0:
            parts.append(f'{minutes}m')
        if secs > 0 or not parts:
            parts.append(f'{secs}s')
        
        return ' '.join(parts)