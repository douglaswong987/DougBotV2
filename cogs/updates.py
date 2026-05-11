import os
import discord
from discord.ext import commands
from anthropic import AsyncAnthropic


SUMMARY_PROMPT = """\
You are writing a Discord release announcement for a Discord bot called DougBot.

You will be given a list of git commit messages and a summary of which files changed.
Write a clean, friendly, human-readable summary of what changed in this release.

Rules:
- Group changes into: ✨ New Features, 🔧 Fixes, 🗑️ Removed, and 🧹 Improvements. Only include sections that are relevant.
- Each bullet point should be one concise sentence in plain English — no jargon, no commit hashes.
- Do not mention file names or technical implementation details unless they are meaningful to a user.
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
        branch = ref.replace('refs/heads/', '')

        commit_lines = [f"- {c.get('message', '').splitlines()[0]}" for c in commits]

        changed_files: set[str] = set()
        for c in commits:
            changed_files.update(c.get('added', []))
            changed_files.update(c.get('modified', []))
            changed_files.update(c.get('removed', []))

        commits_text = '\n'.join(commit_lines) or 'No commit messages'
        files_text = '\n'.join(sorted(changed_files)) or 'Unknown'

        try:
            response = await self.anthropic.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=600,
                messages=[{
                    'role': 'user',
                    'content': SUMMARY_PROMPT.format(commits=commits_text, files=files_text)
                }]
            )
            summary = response.content[0].text.strip()
            print('Claude summarization succeeded')
        except Exception as e:
            print(f'Claude summarization failed: {e}')
            summary = '\n'.join(commit_lines)

        embed = discord.Embed(
            title=f"🚀 DougBot updated — `{branch}`",
            description=summary,
            color=discord.Color.brand_green(),
            url=compare_url or None
        )
        embed.set_footer(text=f"Pushed by {pusher} • {len(commits)} commit(s) • {repo_name}")

        # Post to every guild's log channel
        async with self.bot.db.conn.execute(
            "SELECT guild_id, value FROM guild_config WHERE key='log_channel'"
        ) as cur:
            rows = await cur.fetchall()

        for row in rows:
            channel = self.bot.get_channel(int(row['value']))
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    print(f"Missing permissions to post to channel {row['value']}")


async def setup(bot):
    await bot.add_cog(Updates(bot))
