import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database
from webhook import start_webhook

load_dotenv()

intents = discord.Intents.all()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.db = None


@bot.event
async def on_ready():
    bot.db = await Database.create()
    await bot.load_extension('cogs.fun')
    await bot.load_extension('cogs.reminders')
    await bot.load_extension('cogs.moderation')
    await bot.load_extension('cogs.config')
    await bot.load_extension('cogs.updates')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.playing, name='with his meat')
    )
    print(f'Logged in as {bot.user.name}')


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


async def main():
    async with bot:
        await start_webhook(bot)
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            raise ValueError('DISCORD_TOKEN not set in .env')
        await bot.start(token)


if __name__ == '__main__':
    asyncio.run(main())
