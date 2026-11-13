"""Admin cog for owner-only commands"""

import discord
from discord.ext import commands


class Admin(commands.Cog, name='admin'):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.hybrid_command(
        name='shutdown',
        hidden=True,
        help='Shut down the bot completely',
        aliases=['s', 'sleep'],
    )
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        await ctx.send('💤 Shutting down...')
        await self.client.close()

    @commands.hybrid_command(name='invite', hidden=True, help='Get the bot invite link')
    @commands.is_owner()
    async def invite(self, ctx: commands.Context) -> None:
        url = discord.utils.oauth_url(self.client.application_id, permissions=discord.Permissions(administrator=True))
        embed = discord.Embed(title='🎧 Invite Link', description=url, color=discord.Color.blurple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='servers', hidden=True, help='List all servers the bot is in')
    @commands.is_owner()
    async def servers(self, ctx: commands.Context) -> None:
        names = ', '.join(guild.name for guild in self.client.guilds)
        await ctx.send(f'🎧 **Servers ({len(self.client.guilds)}):** {names}', ephemeral=True)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Admin(client))
