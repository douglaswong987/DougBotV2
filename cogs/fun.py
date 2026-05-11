import random
import asyncio
from datetime import datetime
import pytz
import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import tasks

INSULTS = [
    "you are so fucking STUPID",
    "your life is NOTHING",
    "i hate you",
    "you serve ZERO purpose",
    "you haven't showered in years",
    "idiot",
    "freak",
    "you're hard to look at",
    "are you naturally this dumb or do you have to put in effort",
    "i envy everyone you have never met",
    "i would unplug your life support to charge my phone",
    "you bring joy to everyone when you leave the room",
    "this is why people talk about you behind your back",
    "you are stealing my oxygen",
    "your mom",
    "this dick",
    "deez nuts",
    "your parents hate you",
    "i am inside your walls",
    "baka",
    "your cock is SO small",
]

BALL_CHOICES = [
    "it is certain", "it is decidedly so", "without a doubt",
    "yes, definitely", "you may rely on it", "as i see it, yes",
    "most likely", "outlook seems good", "yes",
    "reply hazy, try again", "ask again later", "better not tell you now",
    "cannot predict now", "concentrate and ask again",
    "don't count on it", "my reply is no", "my sources say no",
    "outlook not so good", "very doubtful",
]


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def cog_load(self):
        self.midnight_reset.start()

    def cog_unload(self):
        self.midnight_reset.cancel()

    @tasks.loop(hours=24)
    async def midnight_reset(self):
        async with self.bot.db.conn.execute(
            "SELECT guild_id, value FROM guild_config WHERE key='log_channel'"
        ) as cur:
            rows = await cur.fetchall()
        for row in rows:
            channel = self.bot.get_channel(int(row['value']))
            if channel:
                try:
                    await channel.send(
                        "🍆 **A new day has dawned.** The cocks have been reset. "
                        "Use `/cock` to claim your length for today."
                    )
                except discord.Forbidden:
                    pass

    @midnight_reset.before_loop
    async def before_midnight_reset(self):
        """Sleep until the next midnight PST before starting the 24h loop."""
        await self.bot.wait_until_ready()
        tz = pytz.timezone("US/Pacific")
        now = datetime.now(tz)
        from datetime import timedelta
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        delay = (tomorrow - now).total_seconds()
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Cock
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='cock', description="Generate your cock length for the day")
    async def cock(self, ctx: commands.Context):
        length = await self.db.get_cock_length(ctx.author.id, ctx.guild.id)
        if length is None:
            length = round(random.uniform(0.01, 13.00), 2)
            await self.db.set_cock_length(ctx.author.id, ctx.guild.id, length)

        if length >= 9.00:
            suffix = ' GOD DAMN 🥵🍆'
        elif length >= 6.50:
            suffix = ' OK we take those'
        elif length >= 4.00:
            suffix = " that's pretty average"
        else:
            suffix = ' hahahaha SMALL COCK 🤏'

        await ctx.send(f'{ctx.author.mention} your cock length is **{length} inches**.{suffix}')

    @commands.hybrid_command(name='cockcharts', description="Daily cock length leaderboard")
    async def cockcharts(self, ctx: commands.Context):
        today = datetime.now(pytz.timezone("US/Pacific")).strftime("%Y-%m-%d")
        rows = await self.db.get_cock_leaderboard(ctx.guild.id)

        embed = discord.Embed(
            title=f"🍆 Cock length leaderboard — {today}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/JfX7EKd.png")

        medals = ['🥇', '🥈', '🥉']
        if not rows:
            embed.description = "Nobody has rolled yet today. Use `/cock` to get started!"
        else:
            for i, row in enumerate(rows):
                member = ctx.guild.get_member(int(row['user_id']))
                name = member.display_name if member else f"<@{row['user_id']}>"
                medal = medals[i] if i < 3 else ''
                embed.add_field(
                    name=f"{i + 1}. {name} {medal}",
                    value=f"{row['length']} inches",
                    inline=False
                )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='meatking', description="Who has the biggest cock today?")
    async def meatking(self, ctx: commands.Context):
        rows = await self.db.get_meatking(ctx.guild.id)
        if not rows:
            await ctx.send("Nobody has rolled yet today. Use `/cock` to get started!")
            return
        length = rows[0]['length']
        if len(rows) == 1:
            member = ctx.guild.get_member(int(rows[0]['user_id']))
            name = member.mention if member else f"<@{rows[0]['user_id']}>"
            await ctx.send(f"👑 **MEAT KING**: {name} with **{length} inches** 🍆")
        else:
            names = ', '.join(
                ctx.guild.get_member(int(r['user_id'])).mention
                if ctx.guild.get_member(int(r['user_id'])) else f"<@{r['user_id']}>"
                for r in rows
            )
            await ctx.send(f"👑 **MEAT KINGS** (tied at **{length} inches**): {names} 🍆")

    @commands.hybrid_command(name='meatchud', description="Who has the smallest cock today?")
    async def meatchud(self, ctx: commands.Context):
        rows = await self.db.get_meatchud(ctx.guild.id)
        if not rows:
            await ctx.send("Nobody has rolled yet today. Use `/cock` to get started!")
            return
        length = rows[0]['length']
        if len(rows) == 1:
            member = ctx.guild.get_member(int(rows[0]['user_id']))
            name = member.mention if member else f"<@{rows[0]['user_id']}>"
            await ctx.send(f"🤏 **MEAT CHUD**: {name} with **{length} inches** 💀")
        else:
            names = ', '.join(
                ctx.guild.get_member(int(r['user_id'])).mention
                if ctx.guild.get_member(int(r['user_id'])) else f"<@{r['user_id']}>"
                for r in rows
            )
            await ctx.send(f"🤏 **MEAT CHUDS** (tied at **{length} inches**): {names} 💀")

    # ------------------------------------------------------------------
    # Dice / coin / 8ball
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='roll', description="Roll a number. Default 1–100, or specify a max (or min and max)")
    @app_commands.describe(upper="Upper bound (default 100)", lower="Lower bound (default 1)")
    async def roll(self, ctx: commands.Context, upper: int = 100, lower: int = 1):
        if lower >= upper:
            await ctx.send("Lower bound must be less than upper bound.", ephemeral=True)
            return
        result = random.randint(lower, upper)
        await ctx.send(f"🎲 DougBot rolls **{result}** (range {lower}–{upper})")

    @commands.hybrid_command(name='cointoss', description="Flip a coin")
    async def cointoss(self, ctx: commands.Context):
        result = random.choice(['**Heads** 🪙', '**Tails** 🪙'])
        await ctx.send(f"DougBot flips... {result}")

    @commands.hybrid_command(name='8ball', description="Ask the magic 8ball a question")
    @app_commands.describe(question="Your question")
    async def eightball(self, ctx: commands.Context, *, question: str):
        answer = random.choice(BALL_CHOICES)
        embed = discord.Embed(color=discord.Color.dark_purple())
        embed.add_field(name="🎱 Question", value=question, inline=False)
        embed.add_field(name="Answer", value=f"*{answer}*", inline=False)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Birthday
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Ignore anything that looks like a command
        if message.content.startswith("/") or message.content.startswith("!"):
            return

        # Birthday detection
        if 'happy birthday' in message.content.lower() and message.mentions:
            mentions = ', '.join(u.mention for u in message.mentions)
            await message.channel.send(f"HAPPY BIRTHDAY {mentions} 🎂🎉")
            return

        # Random insult logic — configurable targets
        if not message.guild:
            return

        db = self.bot.db

        # Special users always get their specific message and nothing else.
        special_msg = await db.get_insult_special(message.guild.id, message.author.id)
        if special_msg is not None:
            if random.random() <= 0.1:
                await message.channel.send(special_msg)
            return

        # General insult pool — users/roles configured by admins
        rolled = random.random()
        if rolled > 0.1:
            return

        target_user_ids = await db.get_insult_targets(message.guild.id)
        target_role_ids = await db.get_insult_roles(message.guild.id)

        author_role_ids = [r.id for r in message.author.roles]
        is_target = (
            message.author.id in target_user_ids
            or any(rid in target_role_ids for rid in author_role_ids)
        )

        if not is_target:
            return

        if rolled <= 0.0005:
            await message.channel.send("i love you")
        else:
            rows = await db.get_insults()
            pool = [r['message'] for r in rows] if rows else INSULTS
            await message.channel.send(random.choice(pool))


async def setup(bot):
    await bot.add_cog(Fun(bot))