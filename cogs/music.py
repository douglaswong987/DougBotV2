import asyncio
import base64
import os
import tempfile
from collections import deque
from dataclasses import dataclass

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

_COOKIE_FILE = None

def _setup_cookies():
    global _COOKIE_FILE
    encoded = os.getenv('YOUTUBE_COOKIES_B64')
    if not encoded:
        return
    data = base64.b64decode(encoded)
    tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
    tmp.write(data)
    tmp.close()
    _COOKIE_FILE = tmp.name

_setup_cookies()

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'cookiefile': _COOKIE_FILE,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

IDLE_TIMEOUT = 600  # 10 minutes in seconds


@dataclass
class Track:
    title: str
    url: str
    webpage_url: str
    duration: int
    thumbnail: str | None
    uploader: str


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def fetch_track(query: str) -> Track | None:
    # Strip playlist/radio params from YouTube URLs so yt-dlp loads the single video
    import re
    yt_clean = re.match(r'(https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+)', query)
    if yt_clean:
        query = yt_clean.group(1)

    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info
            except Exception:
                return None

    info = await loop.run_in_executor(None, _extract)
    if not info:
        return None

    return Track(
        title=info.get('title', 'Unknown'),
        url=info.get('url', ''),
        webpage_url=info.get('webpage_url', ''),
        duration=info.get('duration', 0),
        thumbnail=info.get('thumbnail'),
        uploader=info.get('uploader') or info.get('channel', 'Unknown'),
    )


class GuildMusic:
    def __init__(self):
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.volume: float = 0.5
        self._idle_task: asyncio.Task | None = None

    def reset_idle(self, bot: commands.Bot, guild_id: int):
        if self._idle_task:
            self._idle_task.cancel()
        self._idle_task = bot.loop.create_task(
            self._idle_disconnect(bot, guild_id)
        )

    def cancel_idle(self):
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None

    async def _idle_disconnect(self, bot: commands.Bot, guild_id: int):
        await asyncio.sleep(IDLE_TIMEOUT)
        guild = bot.get_guild(guild_id)
        if guild and guild.voice_client:
            self.queue.clear()
            self.current = None
            await guild.voice_client.disconnect()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._states: dict[int, GuildMusic] = {}

    def _state(self, guild_id: int) -> GuildMusic:
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusic()
        return self._states[guild_id]

    async def _get_voice(self, ctx: commands.Context) -> discord.VoiceClient | None:
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first.", ephemeral=True)
            return None
        vc: discord.VoiceClient = ctx.guild.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()
        elif vc.channel != ctx.author.voice.channel:
            await vc.move_to(ctx.author.voice.channel)
        return vc

    def _play_next(self, vc: discord.VoiceClient, state: GuildMusic, guild_id: int):
        if not state.queue:
            state.current = None
            state.reset_idle(self.bot, guild_id)
            return

        track = state.queue.popleft()
        state.current = track

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTIONS),
            volume=state.volume
        )

        def after(error):
            if error:
                print(f'Player error: {error}')
            self.bot.loop.call_soon_threadsafe(
                self._play_next, vc, state, guild_id
            )

        vc.play(source, after=after)
        state.cancel_idle()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='play', description="Play a song from YouTube, SoundCloud, or Spotify")
    @app_commands.describe(query="Song name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer()

        vc = await self._get_voice(ctx)
        if not vc:
            return

        track = await fetch_track(query)

        if not track:
            await ctx.send("Could not find or load that track. Try a different search.", ephemeral=True)
            return

        state = self._state(ctx.guild.id)

        if vc.is_playing() or vc.is_paused():
            state.queue.append(track)
            embed = discord.Embed(
                title="Added to queue",
                description=f"**{track.title}**",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Artist", value=track.uploader, inline=True)
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            embed.add_field(name="Position", value=f"#{len(state.queue)}", inline=True)
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            await ctx.send(embed=embed)
        else:
            state.queue.append(track)
            self._play_next(vc, state, ctx.guild.id)
            embed = discord.Embed(
                title="Now playing",
                description=f"**{track.title}**",
                color=discord.Color.brand_green(),
                url=track.webpage_url
            )
            embed.add_field(name="Artist", value=track.uploader, inline=True)
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            if track.thumbnail:
                embed.set_thumbnail(url=track.webpage_url)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name='skip', description="Skip the current song")
    async def skip(self, ctx: commands.Context):
        vc: discord.VoiceClient = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        vc.stop()
        await ctx.send("Skipped.")

    @commands.hybrid_command(name='pause', description="Pause or resume playback")
    async def pause(self, ctx: commands.Context):
        vc: discord.VoiceClient = ctx.guild.voice_client
        if not vc:
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        if vc.is_paused():
            vc.resume()
            await ctx.send("Resumed.")
        elif vc.is_playing():
            vc.pause()
            await ctx.send("Paused.")
        else:
            await ctx.send("Nothing is playing.", ephemeral=True)

    @commands.hybrid_command(name='stop', description="Stop playback, clear the queue, and disconnect")
    async def stop(self, ctx: commands.Context):
        vc: discord.VoiceClient = ctx.guild.voice_client
        if not vc:
            await ctx.send("Not in a voice channel.", ephemeral=True)
            return
        state = self._state(ctx.guild.id)
        state.queue.clear()
        state.current = None
        state.cancel_idle()
        vc.stop()
        await vc.disconnect()
        await ctx.send("Stopped and disconnected.")

    @commands.hybrid_command(name='queue', description="Show the current queue")
    async def queue(self, ctx: commands.Context):
        state = self._state(ctx.guild.id)
        vc: discord.VoiceClient = ctx.guild.voice_client

        if not vc or (not vc.is_playing() and not vc.is_paused() and not state.queue):
            await ctx.send("The queue is empty.", ephemeral=True)
            return

        embed = discord.Embed(title="Queue", color=discord.Color.blurple())

        if state.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{state.current.title}** — {state.current.uploader} `{format_duration(state.current.duration)}`",
                inline=False
            )

        if state.queue:
            items = list(state.queue)[:10]
            lines = '\n'.join(
                f"`{i + 1}.` **{t.title}** — {t.uploader} `{format_duration(t.duration)}`"
                for i, t in enumerate(items)
            )
            if len(state.queue) > 10:
                lines += f"\n*...and {len(state.queue) - 10} more*"
            embed.add_field(name="Up Next", value=lines, inline=False)
        else:
            embed.add_field(name="Up Next", value="*Queue is empty*", inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='nowplaying', description="Show what's currently playing")
    async def nowplaying(self, ctx: commands.Context):
        state = self._state(ctx.guild.id)
        vc: discord.VoiceClient = ctx.guild.voice_client

        if not vc or not state.current:
            await ctx.send("Nothing is playing right now.", ephemeral=True)
            return

        track = state.current
        embed = discord.Embed(
            title="Now Playing",
            description=f"**{track.title}**",
            color=discord.Color.blurple(),
            url=track.webpage_url
        )
        embed.add_field(name="Artist", value=track.uploader, inline=True)
        embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='volume', description="Set the playback volume (0-100)")
    @app_commands.describe(level="Volume level (0-100)")
    async def volume(self, ctx: commands.Context, level: int):
        if not 0 <= level <= 100:
            await ctx.send("Volume must be between 0 and 100.", ephemeral=True)
            return
        state = self._state(ctx.guild.id)
        state.volume = level / 100
        vc: discord.VoiceClient = ctx.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = state.volume
        await ctx.send(f"Volume set to **{level}%**")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))