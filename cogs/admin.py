"""Admin cog for owner-only commands"""

import discord
from discord.ext import commands
from config.settings import Config


class Admin(commands.Cog, name='admin'):    
    def __init__(self, client: commands.Bot) -> None:
        self.client = client
    
    @commands.command(
        hidden=True, 
        help='Shut down the bot completely', 
        aliases=['s', 'sleep']
    )
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown bot"""
        await ctx.message.add_reaction('💤')
        await self.client.close()

    @commands.command(
        hidden=True, 
        help='Get the bot invite link'
    )
    @commands.is_owner()
    async def invite(self, ctx: commands.Context) -> None:
        """Generate invite link"""
        invite_url = (
            f'https://discordapp.com/oauth2/authorize?'
            f'client_id={Config.BOT_ID}&permissions=8&scope=bot'
        )
        embed = discord.Embed(
            title='🎧 Invite Link',
            description=invite_url,
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.command(
        hidden=True, 
        help='List all servers the bot is in'
    )
    @commands.is_owner()
    async def servers(self, ctx: commands.Context) -> None:
        """List all guilds"""
        servers = list(self.client.guilds)
        servers_str = ', '.join([server.name for server in servers])
        await ctx.send(f'**Servers ({len(servers)}):** {servers_str}')


async def setup(client: commands.Bot) -> None:
    """Setup function for cog"""
    await client.add_cog(Admin(client))