import asyncio
import base64
import os
import subprocess
import tempfile
from collections import deque
from dataclasses import dataclass
import re

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

_COOKIE_FILE = None

def _setup_cookies():
    global _COOKIE_FILE
    part1 = os.getenv('YOUTUBE_COOKIES_B64_1', '')
    part2 = os.getenv('YOUTUBE_COOKIES_B64_2', '')
    encoded = part1 + part2
    if not encoded:
        return
    encoded += "=" * (-len(encoded) % 4)
    data = base64.b64decode(encoded)
    tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
    tmp.write(data)
    tmp.flush()
    os.fsync(tmp.fileno())
    tmp.close()
    _COOKIE_FILE = tmp.name
    print(f"Cookie file written to {_COOKIE_FILE} ({len(data)} bytes)")

_setup_cookies()

_NODE_PATH = None

# Setup node via nodeenv if not available
def _setup_node():
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"node already available: {result.stdout.strip()}")
            return
    except FileNotFoundError:
        pass
    print("node not found, installing via nodeenv...")
    try:
        node_dir = '/tmp/node_env'
        subprocess.run(['nodeenv', node_dir, '--node=20.0.0', '--prebuilt'], check=True, capture_output=True)
        node_bin = f'{node_dir}/bin'
        os.environ['PATH'] = f"{node_bin}:{os.environ.get('PATH', '')}"
        global _NODE_PATH
        _NODE_PATH = f'{node_bin}/node'
        result = subprocess.run([_NODE_PATH, '--version'], capture_output=True, text=True)
        print(f"node installed: {result.stdout.strip()} at {_NODE_PATH}")
    except Exception as e:
        print(f"nodeenv install failed: {e}")

_setup_node()

# Find or install ffmpeg
def _find_ffmpeg():
    # Check common paths first
    for path in ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/nix/var/nix/profiles/default/bin/ffmpeg', '/tmp/ffmpeg/ffmpeg']:
        if os.path.isfile(path):
            print(f"ffmpeg found at: {path}")
            return path
    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        print(f"ffmpeg found at: {result.stdout.strip()}")
        return result.stdout.strip()
    # Use imageio-ffmpeg static binary
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"ffmpeg found via imageio at: {path}")
        return path
    except Exception as e:
        print(f"imageio_ffmpeg failed: {e}")
        return 'ffmpeg'

_FFMPEG_PATH = _find_ffmpeg()

# Test ffmpeg binary
def _test_ffmpeg(path):
    try:
        result = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"FFmpeg works: {version_line}")
            return True
        else:
            print(f"FFmpeg {path} failed version check: code {result.returncode}")
            return False
    except Exception as e:
        print(f"FFmpeg {path} test error: {e}")
        return False


if not _test_ffmpeg(_FFMPEG_PATH):
    # Try imageio as fallback
    try:
        import imageio_ffmpeg
        imageio_path = imageio_ffmpeg.get_ffmpeg_exe()
        if _test_ffmpeg(imageio_path):
            _FFMPEG_PATH = imageio_path
            print(f"Switched to imageio ffmpeg: {_FFMPEG_PATH}")
    except Exception as e:
        print(f"imageio fallback failed: {e}")

# Load opus - try common paths then find it
import ctypes.util, glob
def _load_opus():
    # Try standard names first
    for name in ['libopus.so.0', 'libopus.so', 'libopus']:
        try:
            discord.opus.load_opus(name)
            print(f"opus loaded: {name}")
            return
        except Exception:
            pass
    # Search filesystem
    for pattern in ['/usr/lib/*/libopus*', '/usr/lib/libopus*', '/nix/store/*/lib/libopus*', '/app/.venv/lib*/libopus*']:
        matches = glob.glob(pattern)
        if matches:
            try:
                discord.opus.load_opus(matches[0])
                print(f"opus loaded from: {matches[0]}")
                return
            except Exception:
                pass
    # Try to install via pip
    try:
        subprocess.run(['pip', 'install', 'opuslib', '--quiet'], check=True)
    except Exception:
        pass
    # Extract libopus.so from deb using pure Python
    try:
        import urllib.request, struct, io, gzip, tarfile
        deb_url = 'https://ftp.debian.org/debian/pool/main/o/opus/libopus0_1.3.1-3_amd64.deb'
        deb_data = urllib.request.urlopen(deb_url).read()

        # Parse ar archive format manually
        # ar format: global header (8 bytes) then entries
        pos = 8  # skip "!<arch>\n"
        data_tar = None
        while pos < len(deb_data):
            # Each entry: 60 byte header
            if pos + 60 > len(deb_data):
                break
            name = deb_data[pos:pos+16].decode('ascii').strip()
            size = int(deb_data[pos+48:pos+58].decode('ascii').strip())
            pos += 60
            content_bytes = deb_data[pos:pos+size]
            pos += size + (size % 2)  # pad to even
            if name.startswith('data.tar'):
                data_tar = (name, content_bytes)
                break

        if data_tar:
            name, content_bytes = data_tar
            if name.endswith('.gz'):
                fileobj = io.BytesIO(gzip.decompress(content_bytes))
            else:
                fileobj = io.BytesIO(content_bytes)
            with tarfile.open(fileobj=fileobj) as tar:
                for member in tar.getmembers():
                    if 'libopus.so' in member.name and not member.name.endswith('.a'):
                        f = tar.extractfile(member)
                        opus_path = '/tmp/libopus.so.0'
                        with open(opus_path, 'wb') as out:
                            out.write(f.read())
                        os.chmod(opus_path, 0o755)
                        discord.opus.load_opus(opus_path)
                        print(f"opus loaded from deb: {opus_path}")
                        return
    except Exception as e:
        print(f"opus deb extract failed: {e}")

_load_opus()

try:
    import yt_dlp_ejs
    print(f"yt-dlp-ejs found: {yt_dlp_ejs._version.__version__}")
except ImportError:
    print("yt-dlp-ejs NOT found")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': False,
    'no_warnings': False,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'remote_components': ['ejs:github'],
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -protocol_whitelist file,http,https,tcp,tls,crypto,hls,applehttp',
    'options': '-vn -f s16le -ar 48000 -ac 2',
}

IDLE_TIMEOUT = 600


@dataclass
class Track:
    title: str
    url: str
    webpage_url: str
    duration: int
    thumbnail: str | None
    uploader: str
    http_headers: dict = None
    local_file: str = None


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class NowPlayingView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label='⏭ Skip', style=discord.ButtonStyle.danger, row=1)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: discord.VoiceClient = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        vc.stop()
        await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)

    def add_related(self, related: list[dict]):
        if not related:
            return
        options = [
            discord.SelectOption(
                label=r['title'][:100],
                value=r['url'],
                description=r.get('uploader', '')[:100]
            )
            for r in related[:10]
        ]
        select = RelatedSelect(self.cog, self.guild_id, options)
        self.add_item(select)


class RelatedSelect(discord.ui.Select):
    def __init__(self, cog, guild_id: int, options: list[discord.SelectOption]):
        super().__init__(placeholder='Play a related song...', options=options, row=0)
        self.cog = cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        url = self.values[0]
        await interaction.response.defer()
        track = await fetch_track(url)
        if not track:
            await interaction.followup.send("Couldn't load that track.", ephemeral=True)
            return
        state = self.cog._state(self.guild_id)
        vc: discord.VoiceClient = interaction.guild.voice_client
        if not vc:
            await interaction.followup.send("Not in a voice channel.", ephemeral=True)
            return
        if vc.is_playing() or vc.is_paused():
            state.queue.append(track)
            embed = discord.Embed(title="Added to queue", description=f"[{track.title}]({track.webpage_url})", color=discord.Color.blurple())
            embed.add_field(name="Artist", value=track.uploader, inline=True)
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            embed.add_field(name="Position", value=f"#{len(state.queue)}", inline=True)
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            await interaction.followup.send(embed=embed)
        else:
            state.queue.append(track)
            self.cog._play_next(vc, state, self.guild_id)
            await interaction.followup.send("▶️ Playing now.")


async def fetch_related(webpage_url: str) -> list[dict]:
    loop = asyncio.get_event_loop()

    def _extract():
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlist_items': '1:11',
        }
        if _COOKIE_FILE:
            opts['cookiefile'] = _COOKIE_FILE
        # Get related via YouTube's watch page sidebar
        video_id = re.search(r'v=([a-zA-Z0-9_-]+)', webpage_url)
        if not video_id:
            return []
        related_url = f'https://www.youtube.com/watch?v={video_id.group(1)}&list=RD{video_id.group(1)}'
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(related_url, download=False)
                entries = info.get('entries', [])[1:11]  # skip first (current song)
                return [
                    {'title': e.get('title', 'Unknown'), 'url': f"https://www.youtube.com/watch?v={e['id']}", 'uploader': e.get('uploader') or e.get('channel', '')}
                    for e in entries if e.get('id')
                ]
        except Exception as e:
            print(f"Related fetch error: {e}")
            return []

    return await loop.run_in_executor(None, _extract)


async def fetch_playlist_and_enqueue(query: str, state, vc, cog, guild_id: int) -> int:
    """Fetch playlist entries flat, then download and enqueue one at a time. Returns track count."""
    loop = asyncio.get_event_loop()

    # Step 1: get flat list of video IDs quickly
    def _get_entries():
        opts = {
            'quiet': True,
            'extract_flat': True,
            'ignoreerrors': True,
        }
        if _COOKIE_FILE:
            opts['cookiefile'] = _COOKIE_FILE
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if not info or 'entries' not in info:
                return []
            return [e for e in info['entries'] if e and e.get('id')]

    entries = await loop.run_in_executor(None, _get_entries)
    if not entries:
        return 0

    # Step 2: download and enqueue one at a time
    started = False
    count = 0
    for entry in entries:
        url = f"https://www.youtube.com/watch?v={entry['id']}"
        try:
            track = await fetch_track(url)
            if not track or isinstance(track, list):
                await asyncio.sleep(1)
                continue
            state.queue.append(track)
            count += 1
            # Start playback only if truly idle
            if not started and vc.is_connected() and not vc.is_playing() and not vc.is_paused() and not state._playing:
                started = True
                cog._play_next(vc, state, guild_id)
            elif started and vc.is_connected() and not vc.is_playing() and not vc.is_paused() and not state._playing:
                # Bot went idle mid-playlist, kick it back
                cog._play_next(vc, state, guild_id)
            # Small delay to avoid hammering YouTube with 429s
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Playlist track error: {e}")
            await asyncio.sleep(1)
            continue

    return count


async def fetch_track(query: str) -> Track | None:
    yt_clean = re.match(r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)', query)
    if yt_clean:
        query = f'https://www.youtube.com/watch?v={yt_clean.group(1)}'

    loop = asyncio.get_event_loop()

    def _extract():
        opts = dict(YTDL_OPTIONS)
        if _COOKIE_FILE:
            opts['cookiefile'] = _COOKIE_FILE
        if _NODE_PATH:
            opts['js_runtimes'] = {'node': {'path': _NODE_PATH}}

        # Download to temp file so FFmpeg reads locally (avoids Railway network restrictions)
        import tempfile, uuid
        tmp_id = uuid.uuid4().hex
        tmp_path = f'/tmp/dougbot_{tmp_id}'

        dl_opts = dict(opts)
        dl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
        dl_opts['outtmpl'] = tmp_path + '_%(playlist_index)s.%(ext)s'
        dl_opts['quiet'] = True
        dl_opts['ffmpeg_location'] = _FFMPEG_PATH
        dl_opts['ignoreerrors'] = True

        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=True)
                # If playlist, return all entries
                if 'entries' in info:
                    import glob
                    results = []
                    for i, entry in enumerate(info['entries'], 1):
                        if not entry:
                            continue
                        entry_files = glob.glob(f'{tmp_path}_{i:02d}.*') or glob.glob(f'{tmp_path}_{i}.*')
                        if entry_files:
                            entry['_local_file'] = entry_files[0]
                        results.append(entry)
                    return {'_playlist': True, '_entries': results, 'title': info.get('title', 'Playlist')}
                import glob
                files = glob.glob(tmp_path + '.*')
                if files:
                    info['_local_file'] = files[0]
                return info
            except Exception as e:
                print(f"yt-dlp download error: {e}")
                return None

    info = await loop.run_in_executor(None, _extract)
    if not info:
        return None

    # Handle playlist
    if info.get('_playlist'):
        tracks = []
        for entry in info.get('_entries', []):
            local_file = entry.get('_local_file')
            tracks.append(Track(
                title=entry.get('title', 'Unknown'),
                url=local_file or entry.get('url', ''),
                webpage_url=entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                duration=entry.get('duration', 0),
                thumbnail=entry.get('thumbnail'),
                uploader=entry.get('uploader') or entry.get('channel', 'Unknown'),
                http_headers={},
                local_file=local_file,
            ))
        return tracks if tracks else None

    # Guard against None info (e.g. unavailable video with ignoreerrors)
    if not isinstance(info, dict):
        return None

    # Try to get a direct audio URL rather than HLS manifest
    url = info.get('url', '')
    http_headers = info.get('http_headers', {})
    formats = info.get('formats', [])
    # Prefer m4a then webm (non-HLS direct streams)
    for preferred_ext in ['m4a', 'webm', 'opus']:
        for fmt in formats:
            ext = fmt.get('ext', '')
            protocol = fmt.get('protocol', '')
            if ext == preferred_ext and 'hls' not in protocol and fmt.get('url'):
                url = fmt['url']
                http_headers = fmt.get('http_headers', http_headers)
                break
        else:
            continue
        break

    local_file = info.get('_local_file')

    return Track(
        title=info.get('title', 'Unknown'),
        url=local_file or url,
        webpage_url=info.get('webpage_url', ''),
        duration=info.get('duration', 0),
        thumbnail=info.get('thumbnail'),
        uploader=info.get('uploader') or info.get('channel', 'Unknown'),
        http_headers={} if local_file else http_headers,
        local_file=local_file,
    )


class GuildMusic:
    def __init__(self):
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.volume: float = 0.5
        self._idle_task: asyncio.Task | None = None
        self.now_playing_msg: discord.Message | None = None
        self.now_playing_channel: discord.TextChannel | None = None
        self._playing: bool = False

    def reset_idle(self, bot: commands.Bot, guild_id: int):
        if self._idle_task:
            self._idle_task.cancel()
        self._idle_task = bot.loop.create_task(self._idle_disconnect(bot, guild_id))

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
        if state._playing:
            return
        if not state.queue:
            state.current = None
            state._playing = False
            state.reset_idle(self.bot, guild_id)
            return

        state._playing = True
        track = state.queue.popleft()
        state.current = track

        ffmpeg_opts = {'options': '-vn'} if track.local_file else FFMPEG_OPTIONS
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(track.url, executable=_FFMPEG_PATH, **ffmpeg_opts),
            volume=state.volume
        )

        # Post Now Playing embed for this track
        async def _post_now_playing():
            if not state.now_playing_channel:
                return
            embed = discord.Embed(
                title="Now playing",
                description=f"[{track.title}]({track.webpage_url})",
                color=discord.Color.brand_green()
            )
            embed.add_field(name="Artist", value=track.uploader, inline=True)
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            view = NowPlayingView(self, guild_id)
            msg = await state.now_playing_channel.send(embed=embed, view=view)
            state.now_playing_msg = msg
            async def _add_related(m=msg, t=track, v=view):
                related = await fetch_related(t.webpage_url)
                if related and state.now_playing_msg == m:
                    v.add_related(related)
                    try:
                        await m.edit(view=v)
                    except Exception:
                        pass
            asyncio.ensure_future(_add_related())

        asyncio.run_coroutine_threadsafe(_post_now_playing(), self.bot.loop)

        finished_track = track

        local_file_to_delete = track.local_file

        def after(error):
            if error:
                print(f'Player error: {error}')
            state._playing = False
            # Clean up temp file
            if local_file_to_delete:
                try:
                    os.remove(local_file_to_delete)
                except Exception:
                    pass
            async def _on_finish():
                if state.now_playing_msg:
                    try:
                        played_embed = discord.Embed(
                            title="Played",
                            description=f"[{finished_track.title}]({finished_track.webpage_url})",
                            color=discord.Color.greyple()
                        )
                        played_embed.add_field(name="Artist", value=finished_track.uploader, inline=True)
                        played_embed.add_field(name="Duration", value=format_duration(finished_track.duration), inline=True)
                        if finished_track.thumbnail:
                            played_embed.set_thumbnail(url=finished_track.thumbnail)
                        await state.now_playing_msg.edit(embed=played_embed, view=None)
                    except Exception:
                        pass
                    state.now_playing_msg = None
            asyncio.run_coroutine_threadsafe(_on_finish(), self.bot.loop)
            self.bot.loop.call_soon_threadsafe(self._play_next, vc, state, guild_id)

        vc.play(source, after=after)
        state.cancel_idle()

    async def _load_playlist(self, query: str, state, vc, guild_id: int):
        count = await fetch_playlist_and_enqueue(query, state, vc, self, guild_id)
        if count == 0 and state.now_playing_channel:
            await state.now_playing_channel.send("❌ No tracks could be loaded from that playlist.")
        elif state.now_playing_channel:
            await state.now_playing_channel.send(f"✅ Finished loading **{count}** tracks from playlist.", delete_after=10)

    @commands.hybrid_command(name='play', description="Play a song from YouTube, SoundCloud, or Spotify")
    @app_commands.describe(query="Song name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer()

        vc = await self._get_voice(ctx)
        if not vc:
            return

        state = self._state(ctx.guild.id)
        state.now_playing_channel = ctx.channel

        # Detect playlist URLs and handle with streaming downloader
        is_playlist = ('list=' in query and 'watch?v=' not in query) or ('playlist?list=' in query)
        if is_playlist or (query.startswith('http') and 'list=' in query and 'watch?v=' not in query):
            await ctx.send("📋 Loading playlist... playback will start as tracks become ready.", delete_after=5)
            asyncio.ensure_future(self._load_playlist(query, state, vc, ctx.guild.id))
            return

        result = await fetch_track(query)

        if not result:
            await ctx.send("Could not find or load that track. Try a different search.", ephemeral=True)
            return

        # Handle playlist result from fetch_track (e.g. YouTube mix)
        if isinstance(result, list):
            was_playing = vc.is_playing() or vc.is_paused()
            for t in result:
                state.queue.append(t)
            embed = discord.Embed(title="📋 Playlist added to queue", color=discord.Color.blurple())
            embed.add_field(name="Tracks", value=str(len(result)), inline=True)
            embed.add_field(name="First track", value=f"[{result[0].title}]({result[0].webpage_url})", inline=True)
            await ctx.send(embed=embed)
            if not was_playing:
                self._play_next(vc, state, ctx.guild.id)
            return

        track = result

        if vc.is_playing() or vc.is_paused():
            state.queue.append(track)
            embed = discord.Embed(title="Added to queue", description=f"[{track.title}]({track.webpage_url})", color=discord.Color.blurple())
            embed.add_field(name="Artist", value=track.uploader, inline=True)
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            embed.add_field(name="Position", value=f"#{len(state.queue)}", inline=True)
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            await ctx.send(embed=embed)
        else:
            state.queue.append(track)
            self._play_next(vc, state, ctx.guild.id)
            await ctx.send("⏳ Loading...", delete_after=0)

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
            lines = '\n'.join(f"`{i+1}.` **{t.title}** — {t.uploader} `{format_duration(t.duration)}`" for i, t in enumerate(items))
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
        embed = discord.Embed(title="Now Playing", description=f"[{track.title}]({track.webpage_url})", color=discord.Color.blurple())
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