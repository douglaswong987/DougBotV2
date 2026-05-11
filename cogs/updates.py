import os
import discord
from discord.ext import commands
from discord import app_commands
from anthropic import AsyncAnthropic


SUMMARY_PROMPT = """\
You are writing a Discord release announcement for a Discord bot called DougBot.

You will be given a list of git commit messages and a summary of which files changed.
Write a clean, friendly, human-readable summary of what changed in this release.

Rules:
- Group changes into: ✨ New Features, 🔧 Fixes, 🗑️ Removed, and 🧹 Improvements. Only include sections that are relevant.
- Each bullet point should be one concise sentence in plain English — no jargon, no commit hashes.
- Do not mention file names or technical implementation details unless they're meaningful to a user.
- Keep the total response under 400 words.
- Do not include a title or header — just the grouped bullet points.
- If the changes are minor or unclear, write a single short paragraph instead of bullet points.

Commits:
{commits}

Files changed:
{files}
"""


class Updates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.anthropic = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    @property
    def db(self):
        return self.bot.db

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.hybrid_group(name='updates', description="Configure release note announcements")
    @commands.has_permissions(administrator=True)
    async def updates(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @updates.command(name='set', description="Set the channel where release notes are posted")
    @app_commands.describe(channel="The text channel to post release notes to")
    @commands.has_permissions(administrator=True)
    async def updates_set(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.db.set_config(ctx.guild.id, 'updates_channel', str(channel.id))
        await ctx.send(f"✅ Release notes will be posted to {channel.mention}", ephemeral=True)

    @updates.command(name='clear', description="Stop posting release notes")
    @commands.has_permissions(administrator=True)
    async def updates_clear(self, ctx: commands.Context):
        await self.db.delete_config(ctx.guild.id, 'updates_channel')
        await ctx.send("✅ Release notes disabled.", ephemeral=True)

    @updates.command(name='status', description="Show where release notes are being posted")
    async def updates_status(self, ctx: commands.Context):
        channel_id = await self.db.get_config(ctx.guild.id, 'updates_channel')
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await ctx.send(f"📣 Release notes are posting to {channel.mention}", ephemeral=True)
            else:
                await ctx.send("⚠️ A channel was set but I can't find it (maybe deleted?).", ephemeral=True)
        else:
            await ctx.send("📣 No updates channel configured.", ephemeral=True)

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------

    async def handle_release(self, data: dict):
        """Called by webhook.py when a push to main arrives."""
        ref = data.get('ref', '')
        if ref != 'refs/heads/main':
            return

        commits = data.get('commits', [])
        if not commits:
            return

        repo_name = data.get('repository', {}).get('full_name', 'unknown/repo')
        compare_url = data.get('compare', '')
        pusher = data.get('pusher', {}).get('name', 'Someone')
        head_commit = data.get('head_commit', {})
        branch = ref.replace('refs/heads/', '')

        # Build commit summary for Claude
        commit_lines = []
        for c in commits:
            msg = c.get('message', '').split('\n')[0]  # first line only
            commit_lines.append(f"- {msg}")

        # Collect changed files across all commits (deduplicated)
        changed_files: set[str] = set()
        for c in commits:
            changed_files.update(c.get('added', []))
            changed_files.update(c.get('modified', []))
            changed_files.update(c.get('removed', []))

        commits_text = '\n'.join(commit_lines) or 'No commit messages'
        files_text = '\n'.join(sorted(changed_files)) or 'Unknown'

        # Ask Claude for a summary
        try:
            response = await self.anthropic.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=600,
                messages=[{
                    'role': 'user',
                    'content': SUMMARY_PROMPT.format(
                        commits=commits_text,
                        files=files_text
                    )
                }]
            )
            summary = response.content[0].text.strip()
        except Exception as e:
            print(f'Claude summarization failed: {e}')
            summary = '\n'.join(commit_lines)  # fall back to raw commits

        # Build the embed
        embed = discord.Embed(
            title=f"🚀 DougBot updated — `{branch}`",
            description=summary,
            color=discord.Color.brand_green(),
            url=compare_url or discord.Embed.Empty
        )
        embed.set_footer(text=f"Pushed by {pusher} • {len(commits)} commit(s) • {repo_name}")

        # Post to every guild that has an updates channel configured
        async with self.bot.db.conn.execute(
            "SELECT guild_id, value FROM guild_config WHERE key='updates_channel'"
        ) as cur:
            rows = await cur.fetchall()

        for row in rows:
            channel = self.bot.get_channel(int(row['value']))
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    print(f"Missing permissions to post to channel {row['value']} in guild {row['guild_id']}")


async def setup(bot):
    await bot.add_cog(Updates(bot))
