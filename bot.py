import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database

load_dotenv()

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='!', intents=intents)
bot.db = None


async def setup_hook():
    bot.db = await Database.create()
    await bot.load_extension('cogs.fun')
    await bot.load_extension('cogs.reminders')
    await bot.load_extension('cogs.moderation')
    await bot.load_extension('cogs.config')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')

bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.playing, name='with his meat')
    )
    print(f'Logged in as {bot.user.name}')


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError('DISCORD_TOKEN not set in .env')
    bot.run(token)
