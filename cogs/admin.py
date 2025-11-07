'''
Admin cog, contains commands designed purely for the owner
'''

import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# get bot id
load_dotenv()
bot_id = os.getenv("BOT_ID")

class admin(commands.Cog, name='admin'):
    def __init__(self, client):
        self.client = client
    
    @commands.command(hidden=True, help='Shuts down the bot completely.', aliases=['s', 'sleep'])
    @commands.is_owner()
    async def shutdown(self, ctx):
        await ctx.message.add_reaction('💤')
        await self.client.close()

    @commands.command(hidden=True, help='Returns an invite link of the bot to a server.')
    @commands.is_owner()
    async def invite(self, ctx):
        embed = (discord.Embed( title='🎧 Invite Link', 
                                description='https://discordapp.com/oauth2/authorize?client_id={}&permissions=8&scope=bot'.format(bot_id), 
                                color=discord.Color.blurple()))
        await ctx.send(embed=embed)

    @commands.command(hidden=True, help='Gets all servers the bot is currently in.')
    @commands.is_owner()
    async def servers(self, ctx):
        servers = list(self.client.guilds)
        servers_to_string = ', '.join([server.name for server in servers])
        await ctx.send(f'Servers: {servers_to_string}')


def setup(client):
    client.add_cog(admin(client))