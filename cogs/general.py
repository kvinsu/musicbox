"""General cog with fun and utility commands"""

import asyncio
import random

import discord
import requests
from discord.ext import commands

from config.settings import Config

TENOR_SEARCH_URL = 'https://g.tenor.com/v1/search'
FALLBACK_GIFS = (
    'https://c.tenor.com/8nEtM-3oQ1sAAAAC/hug-cats.gif',
    'https://c.tenor.com/x4RluZcWrWwAAAAd/slap.gif',
    'https://c.tenor.com/Jpp7qo6lEHYAAAAd/mochi-cat.gif',
)
HUG_GIFS = (
    'https://c.tenor.com/OXCV_qL-V60AAAAC/mochi-peachcat-mochi.gif',
    'https://c.tenor.com/LadCBLn5HDQAAAAC/poke-hug.gif',
    'https://c.tenor.com/8nEtM-3oQ1sAAAAC/hug-cats.gif',
    'https://c.tenor.com/W-R9sPkk_IMAAAAC/come-here-hugs.gif',
    'https://c.tenor.com/GTlDCm4P4EsAAAAd/kitty-kitten.gif',
    'https://c.tenor.com/eAKshP8ZYWAAAAAC/cat-love.gif',
)


def _gif_embed(url: str, description: str | None = None) -> discord.Embed:
    embed = discord.Embed(description=description, color=discord.Color.blurple())
    embed.set_image(url=url)
    return embed


class General(commands.Cog, name='general'):
    sys_random = random.SystemRandom()

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.hybrid_command(name='help', help='Show bot commands')
    async def help_command(self, ctx: commands.Context, *, command: str | None = None) -> None:
        if command:
            cmd = self.client.get_command(command)
            if not cmd:
                await ctx.send(f'❌ Command `{command}` not found.')
                return

            embed = discord.Embed(
                title=f'🎧 Help: {cmd.name}',
                description=cmd.help or 'No description available',
                color=discord.Color.blurple(),
            )
            if cmd.aliases:
                embed.add_field(name='Aliases', value=', '.join(cmd.aliases), inline=False)
            if cmd.signature:
                embed.add_field(name='Usage', value=f'`{ctx.prefix}{cmd.name} {cmd.signature}`', inline=False)
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title='🎧 Bot Commands',
            description=f'Use `{ctx.prefix}help <command>` or `/help <command>` for more info on a command.',
            color=discord.Color.blurple(),
        )
        for cog_name, cog in self.client.cogs.items():
            if names := [f'`{cmd.name}`' for cmd in cog.get_commands() if not cmd.hidden]:
                embed.add_field(name=f'**{cog_name.title()}**', value=', '.join(names), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping', help='Show bot latency')
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.send(f'**Pong:** {round(self.client.latency * 1000)} ms')

    @commands.hybrid_command(name='hello', help='Greet the bot', aliases=['hi', 'hey'])
    async def hello(self, ctx: commands.Context) -> None:
        hello = self.sys_random.choice(['Hewo °‿‿°', 'Moin', 'Heyy ( ˘ ³˘)♥'])
        await ctx.send(f'{hello} {ctx.author.mention}')

    @commands.hybrid_command(name='about', help='Bot information', aliases=['info', 'stats'])
    async def about(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title='🎧 About me',
            description='A self-hosted YouTube music bot, type `/help` or `!help` to see all commands 😘',
            color=discord.Color.blurple(),
        )
        embed.add_field(name='Owner', value='Kevin#4854')
        embed.add_field(name='Servers', value=str(len(self.client.guilds)))
        embed.add_field(name='Library', value='discord.py')
        embed.add_field(name='GitHub', value='https://github.com/kvinsu/musicbox', inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='decide', help='Get a yes/no answer')
    async def decide(self, ctx: commands.Context, *, question: str) -> None:
        answer = self.sys_random.choice(
            [
                'Yes ʘ‿ʘ',
                'No ಠ_ಠ',
                'Sure (｡◕‿◕｡)',
                'Without a doubt, yes ♥‿♥',
                'Yeh, oke ( ˇ෴ˇ )',
                'no... (╯°□°）╯︵ ┻━┻',
                'no... 눈_눈',
                'no ;-;',
                'Nah ⊙_⊙',
                'Yas!!',
            ]
        )
        await ctx.send(f'**{answer}**')

    @commands.hybrid_command(name='hug', help='Hug someone')
    async def hug(self, ctx: commands.Context, user: discord.User | None = None) -> None:
        description = f'{ctx.author.mention} hugs {user.mention}!' if user else None
        await ctx.send(embed=_gif_embed(self.sys_random.choice(HUG_GIFS), description))

    @commands.hybrid_command(name='coinflip', help='Flip a coin (German)', aliases=['flip', 'coin'])
    async def coinflip(self, ctx: commands.Context) -> None:
        result = self.sys_random.choice(['Kopf', 'Zahl'])
        await ctx.send(f'{ctx.author.mention} hat gecoinflipped und **{result}** bekommen! ಠ‿ಠ')

    @commands.hybrid_command(name='lolcoinflip', help='LoL-themed coin flip (German)', aliases=['lolflip', 'lolcoin'])
    @commands.guild_only()
    async def lolcoinflip(self, ctx: commands.Context, *, username: str | None = None) -> None:
        result = self.sys_random.choice(
            [
                'wird feeden 🙃',
                'wird inten 😭',
                'hat carry boots an!! 😮 🥾',
                'ist sheesh drauf! 🤩',
                'es ist GG 🤗',
                'es ist ein ff angle 💀',
            ]
        )
        if not username:
            who = ctx.author.mention
        elif username.startswith('<@'):
            # Already a mention
            who = username
        elif member := ctx.guild.get_member_named(username):
            who = member.mention
        else:
            who = f'**{username}**'
        await ctx.send(f'{who} hat gecoinflipped und **{result}**')

    @commands.hybrid_command(
        name='fliflaflu',
        help='Rock-paper-scissors (German)',
        aliases=['enemenemiste', 'schnickschnackschnuck'],
    )
    async def fliflaflu(self, ctx: commands.Context) -> None:
        choice = self.sys_random.choice(['✂️ Schere', '🪨 Stein', '🧻 Papier'])
        await ctx.send(f'{ctx.author.mention} hat **{choice}** genommen!')

    @commands.hybrid_command(name='slap', help='Slap someone', aliases=['punch', 'hit'])
    async def slap(self, ctx: commands.Context, user: discord.User | None = None, *, reason: str | None = None) -> None:
        async with ctx.typing():
            gif = await self.get_random_gif('punch')
        description = None
        if user:
            description = f'{ctx.author.mention} slapped {user.mention}.'
            if reason:
                description += f' Reason: {reason}'
        await ctx.send(embed=_gif_embed(gif, description))

    @commands.hybrid_command(name='poke', help='Poke someone', aliases=['tap'])
    async def poke(self, ctx: commands.Context, user: discord.User, *, reason: str = '') -> None:
        async with ctx.typing():
            gif = await self.get_random_gif('poke')
        await ctx.send(embed=_gif_embed(gif, f'{user.mention} {reason}'))

    @commands.hybrid_command(
        name='roulette',
        help='Select random option from list divided by spaces',
        aliases=['select', 'choice'],
    )
    async def roulette(self, ctx: commands.Context, *, options: str) -> None:
        choices = options.split()
        embed = discord.Embed(title='🎲 Roulette', color=discord.Color.blurple())
        embed.add_field(name='Options', value=', '.join(choices), inline=False)
        embed.add_field(name='Selected', value=self.sys_random.choice(choices), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='gif', help='Fetch random GIF from Tenor')
    async def gif(self, ctx: commands.Context, *, search: str) -> None:
        async with ctx.typing():
            gif = await self.get_random_gif(search)
        await ctx.send(embed=_gif_embed(gif))

    async def get_random_gif(self, search_term: str) -> str:
        """Random Tenor result, or a built-in GIF without a token or when Tenor fails"""
        if not Config.TENOR_TOKEN:
            return self.sys_random.choice(FALLBACK_GIFS)

        try:
            # requests is blocking, keep it off the event loop
            response = await asyncio.to_thread(
                requests.get,
                TENOR_SEARCH_URL,
                params={'q': search_term, 'key': Config.TENOR_TOKEN, 'limit': 50},
                timeout=5,
            )
            gif = self.sys_random.choice(response.json()['results'])
            return gif['media'][0]['gif']['url']
        # Network errors, bad JSON, or a response shaped differently than expected
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return FALLBACK_GIFS[0]


async def setup(client: commands.Bot) -> None:
    await client.add_cog(General(client))
