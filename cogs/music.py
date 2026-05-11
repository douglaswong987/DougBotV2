import os
import discord
import wavelink
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        node = wavelink.Node(
            uri=os.getenv('LAVALINK_URL'),
            password=os.getenv('LAVALINK_PW'),
        )
        await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)