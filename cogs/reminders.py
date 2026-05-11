import uuid
import asyncio
from datetime import datetime, timezone
import discord
from discord.ext import commands, tasks
from discord import app_commands

import re

DURATION_RE = re.compile(
    r'^(\d+)\s*(minute|hour|day|week|month|year)s?$', re.IGNORECASE
)

UNIT_SECONDS = {
    'minute': 60,
    'hour':   3600,
    'day':    86400,
    'week':   604800,
    'month':  2592000,
    'year':   31536000,
}


def parse_duration(text: str) -> int | None:
    """Return duration in seconds, or None if unparseable."""
    m = DURATION_RE.match(text.strip())
    if not m:
        return None
    return int(m.group(1)) * UNIT_SECONDS[m.group(2).lower()]


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._active: dict[str, asyncio.Task] = {}

    @property
    def db(self):
        return self.bot.db

    async def cog_load(self):
        """Re-schedule any unfired reminders that survived a restart."""
        rows = await self.db.get_pending_reminders()
        for row in rows:
            self._schedule(row['id'], row['user_id'], row['fire_at'])

    def _schedule(self, reminder_id: str, user_id: str, fire_at_iso: str):
        task = self.bot.loop.create_task(
            self._fire_reminder(reminder_id, int(user_id), fire_at_iso)
        )
        self._active[reminder_id] = task

    async def _fire_reminder(self, reminder_id: str, user_id: int, fire_at_iso: str):
        fire_at = datetime.fromisoformat(fire_at_iso)
        now = datetime.now(timezone.utc)
        delay = (fire_at - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

        # Fetch from DB to make sure it wasn't cancelled
        rows = await self.db.get_pending_reminders()
        reminder = next((r for r in rows if r['id'] == reminder_id), None)
        if not reminder:
            return

        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(
                f"⏰ **Reminder:** {reminder['event_name']}\n"
                f"This reminder has fired! Hope you didn't forget. 🔔"
            )
        except discord.Forbidden:
            pass  # User has DMs closed
        finally:
            await self.db.mark_reminder_fired(reminder_id)
            self._active.pop(reminder_id, None)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='remindme', description="Set a reminder")
    @app_commands.describe(
        event="What to remind you about",
        duration="How long from now (e.g. '2 hours', '30 minutes', '1 day')"
    )
    async def remindme(self, ctx: commands.Context, event: str, *, duration: str):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(
                "❌ Invalid duration format.\n"
                "Examples: `30 minutes`, `2 hours`, `1 day`, `1 week`",
                ephemeral=True
            )
            return

        now = datetime.now(timezone.utc)
        fire_at = datetime(
            now.year, now.month, now.day,
            now.hour, now.minute, now.second,
            tzinfo=timezone.utc
        )
        fire_at = fire_at.replace(second=fire_at.second + seconds)
        from datetime import timedelta
        fire_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        reminder_id = str(uuid.uuid4())[:8]

        await self.db.add_reminder(
            reminder_id, ctx.author.id, ctx.guild.id,
            event, fire_at.isoformat()
        )
        self._schedule(reminder_id, str(ctx.author.id), fire_at.isoformat())

        embed = discord.Embed(
            title="✅ Reminder set!",
            description=(
                f"**Event:** {event}\n"
                f"**Fires:** {discord.utils.format_dt(fire_at, 'R')}\n"
                f"**ID:** `{reminder_id}`"
            ),
            color=discord.Color.brand_green()
        )
        embed.set_footer(text="I'll DM you when it fires. Use /reminderslist to see all reminders.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reminderslist', description="List your active reminders")
    async def reminderslist(self, ctx: commands.Context):
        rows = await self.db.get_user_reminders(ctx.author.id)
        if not rows:
            await ctx.send("You have no active reminders.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🗓️ Your active reminders",
            color=discord.Color.blue()
        )
        for row in rows:
            fire_at = datetime.fromisoformat(row['fire_at'])
            embed.add_field(
                name=f"`{row['id']}` — {row['event_name']}",
                value=f"Fires {discord.utils.format_dt(fire_at, 'R')}",
                inline=False
            )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='cancelevent', description="Cancel a reminder by ID")
    @app_commands.describe(reminder_id="The reminder ID shown in /reminderslist")
    async def cancelevent(self, ctx: commands.Context, reminder_id: str):
        deleted = await self.db.delete_reminder(reminder_id, ctx.author.id)
        if not deleted:
            await ctx.send(
                "❌ Reminder not found or doesn't belong to you.",
                ephemeral=True
            )
            return

        # Cancel the in-memory task
        task = self._active.pop(reminder_id, None)
        if task:
            task.cancel()

        await ctx.send(f"✅ Reminder `{reminder_id}` cancelled.", ephemeral=True)

    @commands.hybrid_command(name='cancelall', description="Cancel all your active reminders")
    async def cancelall(self, ctx: commands.Context):
        count = await self.db.delete_all_user_reminders(ctx.author.id)
        if count == 0:
            await ctx.send("You have no active reminders to cancel.", ephemeral=True)
            return

        # Cancel all in-memory tasks for this user
        rows = await self.db.get_user_reminders(ctx.author.id)
        fired_ids = {r['id'] for r in rows}
        for rid in list(self._active.keys()):
            if rid not in fired_ids:
                task = self._active.pop(rid, None)
                if task:
                    task.cancel()

        embed = discord.Embed(
            title="🚫 Reminders cancelled",
            description=f"Cancelled **{count}** reminder(s).",
            color=discord.Color.brand_red()
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Reminders(bot))
