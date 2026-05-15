import discord
import wavelink
from discord.ext import commands
from discord import app_commands


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        node = wavelink.Node(
            uri='wss://dougbot-lavalink-production.up.railway.app',
            password='youshallnotpass',
        )
        await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)

    async def _get_player(self, ctx: commands.Context) -> wavelink.Player | None:
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first.", ephemeral=True)
            return None

        player: wavelink.Player = ctx.guild.voice_client

        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                player.autoplay = wavelink.AutoPlayMode.disabled
            except Exception as e:
                await ctx.send(f"Couldn't connect to your voice channel: {e}", ephemeral=True)
                return None

        return player

    @commands.hybrid_command(name='play', description="Play a song from YouTube, SoundCloud, or Spotify")
    @app_commands.describe(query="Song name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer()

        player = await self._get_player(ctx)
        if not player:
            return

        tracks = await wavelink.Playable.search(query)
        if not tracks:
            await ctx.send("No results found. Try a different search.", ephemeral=True)
            return

        if isinstance(tracks, wavelink.Playlist):
            for track in tracks.tracks:
                await player.queue.put_wait(track)
            await ctx.send(f"📋 Added **{len(tracks.tracks)}** tracks from **{tracks.name}** to the queue.")
            if not player.playing:
                await player.play(player.queue.get())
        else:
            track = tracks[0]
            if player.playing:
                await player.queue.put_wait(track)
                await ctx.send(f"➕ Added to queue: **{track.title}** by {track.author}")
            else:
                await ctx.send(f"▶️ Now playing: **{track.title}** by {track.author}")
                await player.play(track)

    @commands.hybrid_command(name='skip', description="Skip the current song")
    async def skip(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.playing:
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        await player.skip(force=True)
        await ctx.send("⏭️ Skipped.")

    @commands.hybrid_command(name='pause', description="Pause or resume playback")
    async def pause(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        if player.paused:
            await player.pause(False)
            await ctx.send("▶️ Resumed.")
        else:
            await player.pause(True)
            await ctx.send("⏸️ Paused.")

    @commands.hybrid_command(name='stop', description="Stop playback and clear the queue")
    async def stop(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await ctx.send("⏹️ Stopped and disconnected.")

    @commands.hybrid_command(name='queue', description="Show the current queue")
    async def queue(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or (not player.playing and player.queue.is_empty):
            await ctx.send("The queue is empty.", ephemeral=True)
            return

        embed = discord.Embed(title="🎵 Queue", color=discord.Color.blurple())

        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{player.current.title}** by {player.current.author}",
                inline=False
            )

        if not player.queue.is_empty:
            upcoming = list(player.queue)[:10]
            lines = '\n'.join(
                f"{i + 1}. **{t.title}** by {t.author}"
                for i, t in enumerate(upcoming)
            )
            if len(player.queue) > 10:
                lines += f"\n*...and {len(player.queue) - 10} more*"
            embed.add_field(name="Up Next", value=lines, inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='nowplaying', description="Show what's currently playing")
    async def nowplaying(self, ctx: commands.Context):
        player: wavelink.Player = ctx.guild.voice_client
        if not player or not player.current:
            await ctx.send("Nothing is playing right now.", ephemeral=True)
            return

        track = player.current
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{track.title}**",
            color=discord.Color.blurple(),
            url=track.uri
        )
        embed.add_field(name="Artist", value=track.author, inline=True)
        if track.length:
            minutes, seconds = divmod(track.length // 1000, 60)
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='volume', description="Set the playback volume (0-100)")
    @app_commands.describe(level="Volume level (0-100)")
    async def volume(self, ctx: commands.Context, level: int):
        player: wavelink.Player = ctx.guild.voice_client
        if not player:
            await ctx.send("Nothing is playing.", ephemeral=True)
            return
        if not 0 <= level <= 100:
            await ctx.send("Volume must be between 0 and 100.", ephemeral=True)
            return
        await player.set_volume(level)
        await ctx.send(f"🔊 Volume set to **{level}%**")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player:
            return
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f'Lavalink node connected: {payload.node.uri}')


async def setup(bot):
    await bot.add_cog(Music(bot))
