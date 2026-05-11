import os
import asyncio
import threading
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database
from webhook import run_webhook_server

load_dotenv()

print(f"DISCORD_TOKEN set: {bool(os.getenv('DISCORD_TOKEN'))}")
print(f"ANTHROPIC_API_KEY set: {bool(os.getenv('ANTHROPIC_API_KEY'))}")
print(f"WEBHOOK_SECRET set: {bool(os.getenv('WEBHOOK_SECRET'))}")

intents = discord.Intents.all()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='\x00', intents=intents)
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



if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError('DISCORD_TOKEN not set in .env')

    # Run webhook server in a background thread — completely isolated from the bot's event loop
    webhook_thread = threading.Thread(
        target=run_webhook_server,
        args=(bot,),
        daemon=True  # dies automatically when the main process exits
    )
    webhook_thread.start()

    bot.run(token)
