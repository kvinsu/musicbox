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

    @commands.command(hidden=True, aliases=['commandlist', 'commands'])
    async def _help(self, ctx: commands.Context) -> None:
        """Show help"""
        await ctx.send_help()

    @commands.command(help='Show bot latency')
    async def ping(self, ctx: commands.Context) -> None:
        """Show ping"""
        await ctx.send(f'**Pong:** {round(self.client.latency * 1000)} ms')

    @commands.command(help='Greet the bot', aliases=['hi', 'hey'])
    async def hello(self, ctx: commands.Context) -> None:
        """Say hello"""
        hellos = [
            'Hewo °‿‿°', 'Moin', 'Heyy ( ˘ ³˘)♥'
        ]
        hello = self.sys_random.choice(hellos)
        await ctx.send(f'{hello} {ctx.message.author.mention}')
    
    @commands.command(help='Bot information', aliases=['info', 'stats'])
    async def about(self, ctx: commands.Context) -> None:
        """Show bot info"""
        servers = self.client.guilds
        embed = discord.Embed(
            title='🎧 About me',
            description='A YouTube music bot hosted 24/7.',
            color=discord.Color.blurple()
        )
        embed.add_field(name='Owner', value='Kevin#4854')
        embed.add_field(name='Servers', value=f'{len(servers)}')
        embed.add_field(name='Library', value='discord.py')
        embed.add_field(
            name='GitHub',
            value='https://github.com/kvinsu/discord_musicbot',
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(help='Get a yes/no answer')
    async def decide(self, ctx: commands.Context, *, question: commands.clean_content) -> None:
        """Answer with yes or no"""
        responses = [
            'Yes ʘ‿ʘ', 'No ಠ_ಠ', 'Sure (｡◕‿◕｡)', 
            'Without a doubt, yes ♥‿♥', 'Yeh, oke ( ˇ෴ˇ )',
            'no... (╯°□°）╯︵ ┻━┻', 'no... 눈_눈',
            'senpai, pls no ;-;', 'Nah ⊙_⊙', 'Yas!!'
        ]
        answer = self.sys_random.choice(responses)
        await ctx.send(f'**{answer}**')

    @commands.command(help='Hug someone')
    async def hug(self, ctx: commands.Context, username: Optional[str] = None) -> None:
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

        if username:
            mentions_matches = ['<@!', '>']
            if all(x in username for x in mentions_matches):
                embed.description = f'{ctx.author.mention} hugs {username}!'
            else:
                member = ctx.guild.get_member_named(username)
                if member:
                    embed.description = f'{ctx.author.mention} hugs {member.mention}!'
            
        await ctx.send(embed=embed)

    @commands.command(
        help='Flip a coin (German)', 
        aliases=["flip", "coin"]
    )
    async def coinflip(self, ctx: commands.Context) -> None:
        """Coin flip"""
        coinsides = ['Kopf', 'Zahl']
        result = self.sys_random.choice(coinsides)
        await ctx.send(
            f'{ctx.author.mention} hat gecoinflipped und **{result}** bekommen! ಠ‿ಠ'
        )

    @commands.command(
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

    @commands.command(
        help='Rock-paper-scissors (German)', 
        aliases=["enemenemiste", "schnickschnackschnuck"]
    )
    async def fliflaflu(self, ctx: commands.Context) -> None:
        """Rock paper scissors"""
        options = ['✂️ Schere', '🪨 Stein', '🧻 Papier']
        choice = self.sys_random.choice(options)
        await ctx.send(f'{ctx.author.mention} hat **{choice}** genommen!')

    @commands.command(
        help='Slap someone', 
        aliases=['punch', 'hit']
    )
    async def slap(self, ctx: commands.Context, *, username: Optional[str] = None) -> None:
        """Send slap GIF"""
        slap_gif = self.get_random_gif('punch')
        
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=slap_gif)

        if username:
            mentions_matches = ['<@!', '>']
            if all(x in username for x in mentions_matches):
                embed.description = f'{ctx.author.mention} slapped {username}!'
            else:
                member = ctx.guild.get_member_named(username)
                if member:
                    embed.description = f'{ctx.author.mention} slapped {member.mention}!'
                else:
                    embed.description = f'{ctx.author.mention} slapped **{username}**!'

        await ctx.send(embed=embed)

    @commands.command(
        help='Select random option from list', 
        aliases=["select", "choice"]
    )
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

    @commands.command(help='Generate dere-type personality')
    async def dere(self, ctx: commands.Context, *, username: str) -> None:
        """Dere type generator"""
        dere_types = {
            'bakadere': 'is very clumsy and stupid | more often than not, they lack common sense',
            'dandere': 'quiet, silent and asocial | come across as emotionless at times | will suddenly become talkative, sweet, and cute when alone with the right person | actually just shy',
            'darudere': 'often very lazy and dull | will usually ignore others and do whatever they want unless someone they care about asks them to do something or needs their help',
            'deredere': 'very sweet and energetic | usually cheerful and happy | tend to spread joyfulness to others',
            'hinedere': 'has cynical world views | cold-hearted | highly arrogant | has a soft side deep down that may reveal itself once their love interest breaks through',
            'hiyakasudere': 'likes to tease and flirt | sarcastic, mischievous, or at least playful',
            'kamidere': 'feels superior compared to others | highly arrogant, overconfident and proud | aren\'t afraid to speak their minds and show everyone how right they are | stubborn | narcissistic',
            'kanedere': 'attracted to others with money or status | gold digger',
            'kuudere': 'calm and collected on the outside | never panics | shows little emotion | tends to be a leader | often cold, blunt, and cynical | very caring on the inside, at least when it comes to the ones they love',
            'tsundere': 'usually stern, cold or hostile to the person they like and even others | occasionally showing the warm, loving feelings hidden inside | shy, nervous, insecure | can\'t help acting badly in front of their crush',
            'undere': 'says yes to pretty much everything the one they love says | easily manipulated'
        }

        dere_type, dere_info = self.sys_random.choice(list(dere_types.items()))

        mentions_matches = ['<@!', '>']
        if all(x in username for x in mentions_matches):
            username_display = username
        else:
            member = ctx.guild.get_member_named(username)
            username_display = member.mention if member else username

        embed = discord.Embed(
            title='💞 Dere-type Generator',
            description=f'**Person:** {username_display}\n**Type:** {dere_type}\n\n{dere_info}',
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.command(help='Fetch random GIF from Tenor')
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