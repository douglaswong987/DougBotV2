import asyncio
import discord
from discord.ext import commands
from discord import app_commands


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def get_log_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = await self.db.get_config(guild_id, 'log_channel')
        if not channel_id:
            return None
        channel = self.bot.get_channel(int(channel_id))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def send_log(self, guild_id: int, embed: discord.Embed):
        channel = await self.get_log_channel(guild_id)
        if channel:
            await channel.send(embed=embed)

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='purge', description="Delete a number of messages from this channel (admin only)")
    @app_commands.describe(count="Number of messages to delete")
    @commands.has_permissions(administrator=True)
    async def purge(self, ctx: commands.Context, count: int):
        if count < 1 or count > 500:
            await ctx.send("Please provide a number between 1 and 500.", ephemeral=True)
            return

        confirm_msg = await ctx.send(
            f"⚠️ Are you sure you want to delete **{count}** messages? "
            f"Reply with `confirm` within 15 seconds to proceed."
        )

        def check(m):
            return (
                m.content.lower() == 'confirm'
                and m.channel == ctx.channel
                and m.author == ctx.author
            )

        try:
            reply = await self.bot.wait_for('message', check=check, timeout=15.0)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Confirmation timed out. Nothing deleted.")
            return

        await reply.delete()
        await confirm_msg.delete()

        deleted = await ctx.channel.purge(limit=count)
        notice = await ctx.channel.send(f"🗑️ Deleted **{len(deleted)}** messages.")
        await asyncio.sleep(5)
        await notice.delete()

    # ------------------------------------------------------------------
    # Log events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(
            title=f"✏️ Message edited in {before.channel.mention}",
            color=discord.Color.gold()
        )
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        embed.add_field(name="Before", value=before.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "*empty*", inline=False)
        await self.send_log(before.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title=f"👋 {member.name} joined the server!",
            description=f"Welcome, {member.mention}!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title=f"👋 {member.name} left the server",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel = self.bot.get_channel(payload.channel_id)
        msg = payload.cached_message

        # Ignore bot messages
        if msg and msg.author.bot:
            return

        embed = discord.Embed(
            title=f"🗑️ Message deleted in {channel.mention if channel else 'unknown channel'}",
            color=discord.Color.red()
        )

        if msg:
            embed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
            embed.description = msg.content[:2048] or "*no text content*"
        else:
            embed.description = "*Message not in cache — content unavailable*"

        await self.send_log(payload.guild_id, embed)


async def setup(bot):
    await bot.add_cog(Moderation(bot))