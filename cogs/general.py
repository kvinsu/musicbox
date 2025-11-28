"""General cog with fun and utility commands"""

import random
from typing import Optional
import discord
from discord.ext import commands
import requests
from config.settings import Config


class General(commands.Cog, name='general'):    
    # Improve random generator
    sys_random = random.SystemRandom()

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.hybrid_command(name='help', help='Show bot commands')
    async def help_command(self, ctx: commands.Context, *, command: Optional[str] = None) -> None:
        """Show help for commands"""
        if command:
            # Show help for specific command
            cmd = self.client.get_command(command)
            if cmd:
                embed = discord.Embed(
                    title=f'🎧 Help: {cmd.name}',
                    description=cmd.help or 'No description available',
                    color=discord.Color.blurple()
                )
                if cmd.aliases:
                    embed.add_field(name='Aliases', value=', '.join(cmd.aliases), inline=False)
                if cmd.signature:
                    embed.add_field(name='Usage', value=f'`{ctx.prefix}{cmd.name} {cmd.signature}`', inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f'❌ Command `{command}` not found.')
            return
        
        # Show all commands grouped by cog
        embed = discord.Embed(
            title='🎧 Bot Commands',
            description=f'Use `{ctx.prefix}help <command>` or `/help <command>` for more info on a command.',
            color=discord.Color.blurple()
        )
        
        for cog_name, cog in self.client.cogs.items():
            # Get commands from this cog (excluding hidden ones)
            cog_commands = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            if cog_commands:
                command_list = ', '.join([f'`{cmd.name}`' for cmd in cog_commands])
                embed.add_field(
                    name=f'**{cog_name.title()}**',
                    value=command_list,
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping', help='Show bot latency')
    async def ping(self, ctx: commands.Context) -> None:
        """Show ping"""
        await ctx.send(f'**Pong:** {round(self.client.latency * 1000)} ms')

    @commands.hybrid_command(name='hello', help='Greet the bot', aliases=['hi', 'hey'])
    async def hello(self, ctx: commands.Context) -> None:
        """Say hello"""
        hellos = [
            'Hewo °‿‿°', 'Moin', 'Heyy ( ˘ ³˘)♥'
        ]
        hello = self.sys_random.choice(hellos)
        await ctx.send(f'{hello} {ctx.author.mention}')
    
    @commands.hybrid_command(name='about', help='Bot information', aliases=['info', 'stats'])
    async def about(self, ctx: commands.Context) -> None:
        """Show bot info"""
        servers = self.client.guilds
        embed = discord.Embed(
            title='🎧 About me',
            description='A self-hosted YouTube music bot, type `/help` or `!help` to see all commands 😘',
            color=discord.Color.blurple()
        )
        embed.add_field(name='Owner', value='Kevin#4854')
        embed.add_field(name='Servers', value=f'{len(servers)}')
        embed.add_field(name='Library', value='discord.py')
        embed.add_field(
            name='GitHub',
            value='https://github.com/kvinsu/musicbox',
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='decide', help='Get a yes/no answer')
    async def decide(self, ctx: commands.Context, *, question: str) -> None:
        """Answer with yes or no"""
        responses = [
            'Yes ʘ‿ʘ', 'No ಠ_ಠ', 'Sure (｡◕‿◕｡)', 
            'Without a doubt, yes ♥‿♥', 'Yeh, oke ( ˇ෴ˇ )',
            'no... (╯°□°）╯︵ ┻━┻', 'no... 눈_눈',
            'no ;-;', 'Nah ⊙_⊙', 'Yas!!'
        ]
        answer = self.sys_random.choice(responses)
        await ctx.send(f'**{answer}**')

    @commands.hybrid_command(name='hug', help='Hug someone')
    async def hug(self, ctx: commands.Context, user: Optional[discord.User] = None) -> None:
        """Send hug GIF"""
        hugs = [
            'https://c.tenor.com/OXCV_qL-V60AAAAC/mochi-peachcat-mochi.gif',
            'https://c.tenor.com/LadCBLn5HDQAAAAC/poke-hug.gif',
            'https://c.tenor.com/8nEtM-3oQ1sAAAAC/hug-cats.gif',
            'https://c.tenor.com/W-R9sPkk_IMAAAAC/come-here-hugs.gif',
            'https://c.tenor.com/GTlDCm4P4EsAAAAd/kitty-kitten.gif',
            'https://c.tenor.com/eAKshP8ZYWAAAAAC/cat-love.gif'
        ]
        
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=self.sys_random.choice(hugs))

        if user:
            embed.description = f'{ctx.author.mention} hugs {user.mention}!'
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='coinflip', help='Flip a coin (German)', aliases=["flip", "coin"])
    async def coinflip(self, ctx: commands.Context) -> None:
        """Coin flip"""
        coinsides = ['Kopf', 'Zahl']
        result = self.sys_random.choice(coinsides)
        await ctx.send(
            f'{ctx.author.mention} hat gecoinflipped und **{result}** bekommen! ಠ‿ಠ'
        )

    @commands.hybrid_command(
        name='lolcoinflip',
        help='LoL-themed coin flip (German)', 
        aliases=["lolflip", "lolcoin"]
    )
    async def lolcoinflip(
        self, 
        ctx: commands.Context, 
        *, 
        username: Optional[str] = None
    ) -> None:
        """LoL coin flip"""
        coinsides = [
            'wird feeden 🙃', 'wird inten 😭', 
            'hat carry boots an!! 😮 🥾', 'ist sheesh drauf! 🤩',
            'es ist GG 🤗', 'es ist ein ff angle 💀'
        ]
        result = self.sys_random.choice(coinsides)
        
        if not username:
            await ctx.send(f'{ctx.author.mention} hat gecoinflipped und **{result}**')
        else:
            mentions_matches = ['<@!', '>']
            if all(x in username for x in mentions_matches):
                await ctx.send(f'{username} hat gecoinflipped und **{result}**')
            else:
                member = ctx.guild.get_member_named(username)
                if member:
                    await ctx.send(f'{member.mention} hat gecoinflipped und **{result}**')
                else:
                    await ctx.send(f'**{username}** hat gecoinflipped und **{result}**')

    @commands.hybrid_command(name='fliflaflu', help='Rock-paper-scissors (German)', aliases=["enemenemiste", "schnickschnackschnuck"])
    async def fliflaflu(self, ctx: commands.Context) -> None:
        """Rock paper scissors"""
        options = ['✂️ Schere', '🪨 Stein', '🧻 Papier']
        choice = self.sys_random.choice(options)
        await ctx.send(f'{ctx.author.mention} hat **{choice}** genommen!')

    @commands.hybrid_command(name='slap', help='Slap someone', aliases=['punch', 'hit'])
    async def slap(self, ctx: commands.Context, user: Optional[discord.User] = None, reason: str = "None") -> None:
        """Send slap GIF"""
        slap_gif = self.get_random_gif('punch')
        
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=slap_gif)

        if user:
            embed.description = f'{ctx.author.mention} slapped {user.mention}. Reason: {reason}'

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='poke', help='Poke someone', aliases=['tap'])
    async def poke(self, ctx: commands.Context, user: discord.User, *, reason: Optional[str] = "") -> None:
        """Send poke GIF"""
        poke_gif = self.get_random_gif('poke')
        
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=poke_gif)

        if user:
            embed.description = f'{user.mention} {reason}'

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='roulette', help='Select random option from list', aliases=["select", "choice"])
    async def roulette(self, ctx: commands.Context, *, options: str) -> None:
        """Random selection"""
        parsed_list = list(options.split(" "))
        list_to_string = ', '.join(parsed_list)

        embed = discord.Embed(
            title='🎲 Roulette',
            color=discord.Color.blurple()
        )
        embed.add_field(name='Options', value=f'{list_to_string}', inline=False)
        embed.add_field(
            name='Selected', 
            value=f'{self.sys_random.choice(parsed_list)}', 
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='gif', help='Fetch random GIF from Tenor')
    async def gif(self, ctx: commands.Context, *, search: str) -> None:
        """Fetch GIF"""
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=self.get_random_gif(search))
        await ctx.send(embed=embed)

    def get_random_gif(self, search_term: str) -> str:
        """Get random GIF from Tenor or fallback"""
        # If no TENOR_TOKEN provided, fallback to a small curated list
        if not Config.TENOR_TOKEN:
            fallback = [
                'https://c.tenor.com/8nEtM-3oQ1sAAAAC/hug-cats.gif',
                'https://c.tenor.com/x4RluZcWrWwAAAAd/slap.gif',
                'https://c.tenor.com/Jpp7qo6lEHYAAAAd/mochi-cat.gif'
            ]
            return self.sys_random.choice(fallback)

        try:
            url = (
                f'https://g.tenor.com/v1/search?'
                f'q={search_term}&key={Config.TENOR_TOKEN}&limit=50'
            )
            response = requests.get(url, timeout=5)
            data = response.json()
            gif = self.sys_random.choice(data.get('results', []))
            return gif['media'][0]['gif']['url']
        except Exception:
            # Any fetch issues -> fallback
            return 'https://c.tenor.com/8nEtM-3oQ1sAAAAC/hug-cats.gif'

  
async def setup(client: commands.Bot) -> None:
    """Setup function for cog"""
    await client.add_cog(General(client))