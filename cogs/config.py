import discord
from discord.ext import commands
from discord import app_commands

from cogs.fun import INSULTS as DEFAULT_INSULTS


class Config(commands.Cog):
    """Admin commands for configuring DougBot behaviour."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ------------------------------------------------------------------
    # Log channel
    # ------------------------------------------------------------------

    @commands.hybrid_group(name='logs', description="Configure the log channel")
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @logs.command(name='set', description="Set the channel where DougBot logs events")
    @app_commands.describe(channel="The text channel to send logs to")
    @commands.has_permissions(administrator=True)
    async def logs_set(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.db.set_config(ctx.guild.id, 'log_channel', str(channel.id))
        await ctx.send(f"✅ Log channel set to {channel.mention}", ephemeral=True)

    @logs.command(name='clear', description="Stop sending logs (disable logging)")
    @commands.has_permissions(administrator=True)
    async def logs_clear(self, ctx: commands.Context):
        await self.db.delete_config(ctx.guild.id, 'log_channel')
        await ctx.send("✅ Log channel cleared. Logging is now disabled.", ephemeral=True)

    @logs.command(name='status', description="Show the current log channel")
    async def logs_status(self, ctx: commands.Context):
        channel_id = await self.db.get_config(ctx.guild.id, 'log_channel')
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await ctx.send(f"📋 Logs are being sent to {channel.mention}", ephemeral=True)
            else:
                await ctx.send(
                    "⚠️ A log channel was set but I can't find it (maybe it was deleted?).",
                    ephemeral=True
                )
        else:
            await ctx.send("📋 No log channel is configured.", ephemeral=True)

    # ------------------------------------------------------------------
    # Insult targets — users & roles
    # ------------------------------------------------------------------

    @commands.hybrid_group(name='insults', description="Configure DougBot's insult behaviour")
    @commands.has_permissions(administrator=True)
    async def insults(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @insults.command(name='adduser', description="Add a user to the random insult pool")
    @app_commands.describe(member="The user to add")
    @commands.has_permissions(administrator=True)
    async def insults_adduser(self, ctx: commands.Context, member: discord.Member):
        await self.db.add_insult_target(ctx.guild.id, member.id)
        await ctx.send(f"✅ {member.mention} added to insult targets.", ephemeral=True)

    @insults.command(name='removeuser', description="Remove a user from the insult pool")
    @app_commands.describe(member="The user to remove")
    @commands.has_permissions(administrator=True)
    async def insults_removeuser(self, ctx: commands.Context, member: discord.Member):
        await self.db.remove_insult_target(ctx.guild.id, member.id)
        await ctx.send(f"✅ {member.mention} removed from insult targets.", ephemeral=True)

    @insults.command(name='addrole', description="Add an entire role to the insult pool")
    @app_commands.describe(role="The role to add")
    @commands.has_permissions(administrator=True)
    async def insults_addrole(self, ctx: commands.Context, role: discord.Role):
        await self.db.add_insult_role(ctx.guild.id, role.id)
        await ctx.send(f"✅ Role {role.mention} added to insult targets.", ephemeral=True)

    @insults.command(name='removerole', description="Remove a role from the insult pool")
    @app_commands.describe(role="The role to remove")
    @commands.has_permissions(administrator=True)
    async def insults_removerole(self, ctx: commands.Context, role: discord.Role):
        await self.db.remove_insult_role(ctx.guild.id, role.id)
        await ctx.send(f"✅ Role {role.mention} removed from insult targets.", ephemeral=True)

    @insults.command(name='setspecial', description="Set an exclusive custom message for one user")
    @app_commands.describe(member="The user", message="The only message they will ever receive")
    @commands.has_permissions(administrator=True)
    async def insults_setspecial(self, ctx: commands.Context, member: discord.Member, *, message: str):
        await self.db.set_insult_special(ctx.guild.id, member.id, message)
        await ctx.send(
            f"✅ {member.mention} will now exclusively receive: *\"{message}\"*",
            ephemeral=True
        )

    @insults.command(name='clearspecial', description="Remove a user's exclusive message")
    @app_commands.describe(member="The user to clear")
    @commands.has_permissions(administrator=True)
    async def insults_clearspecial(self, ctx: commands.Context, member: discord.Member):
        await self.db.clear_insult_special(ctx.guild.id, member.id)
        await ctx.send(f"✅ Special message cleared for {member.mention}.", ephemeral=True)

    # ------------------------------------------------------------------
    # Insult dictionary
    # ------------------------------------------------------------------

    @insults.command(name='add', description="Add a new insult to the global dictionary")
    @app_commands.describe(message="The insult to add")
    @commands.has_permissions(administrator=True)
    async def insults_add(self, ctx: commands.Context, *, message: str):
        added = await self.db.add_insult(message)
        if added:
            count = await self.db.get_insult_count()
            await ctx.send(
                f"✅ Insult added. Dictionary now has **{count}** custom insult(s).",
                ephemeral=True
            )
        else:
            await ctx.send("⚠️ That insult already exists in the dictionary.", ephemeral=True)

    @insults.command(name='remove', description="Remove an insult from the dictionary by its ID")
    @app_commands.describe(insult_id="The ID shown in /insults dictionary")
    @commands.has_permissions(administrator=True)
    async def insults_remove(self, ctx: commands.Context, insult_id: int):
        removed = await self.db.remove_insult(insult_id)
        if not removed:
            await ctx.send(f"❌ No insult found with ID `{insult_id}`.", ephemeral=True)
            return
        count = await self.db.get_insult_count()
        if count == 0:
            await ctx.send(
                "✅ Insult removed. Dictionary is now empty — falling back to built-in defaults.",
                ephemeral=True
            )
        else:
            await ctx.send(
                f"✅ Insult removed. Dictionary now has **{count}** custom insult(s).",
                ephemeral=True
            )

    @insults.command(name='dictionary', description="View the full insult dictionary")
    async def insults_dictionary(self, ctx: commands.Context):
        rows = await self.db.get_insults()

        if not rows:
            lines = '\n'.join(f"> {i}" for i in DEFAULT_INSULTS)
            embed = discord.Embed(
                title="📖 Insult dictionary — using built-in defaults",
                description=(
                    "No custom insults added yet. These built-in insults are currently active:\n\n"
                    f"{lines}\n\n"
                    "Use `/insults add <message>` to build a custom dictionary."
                ),
                color=discord.Color.greyple()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        lines = '\n'.join(f"`{r['id']}` {r['message']}" for r in rows)
        # Truncate gracefully if somehow enormous
        if len(lines) > 3900:
            lines = lines[:3900] + '\n*... and more. Remove some to see the full list.*'
        embed = discord.Embed(
            title=f"📖 Custom insult dictionary ({len(rows)} insults)",
            description=lines,
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="Use /insults remove <id> to delete an insult")
        await ctx.send(embed=embed, ephemeral=True)

    @insults.command(name='list', description="Show insult targets, specials, and dictionary status")
    async def insults_list(self, ctx: commands.Context):
        user_ids = await self.db.get_insult_targets(ctx.guild.id)
        role_ids = await self.db.get_insult_roles(ctx.guild.id)
        specials = await self.db.get_all_insult_specials(ctx.guild.id)
        count = await self.db.get_insult_count()

        embed = discord.Embed(title="🎯 Insult configuration", color=discord.Color.dark_red())

        if user_ids:
            users = [
                (ctx.guild.get_member(uid) or discord.Object(uid)).mention
                if hasattr(ctx.guild.get_member(uid) or discord.Object(uid), 'mention')
                else f"<@{uid}>"
                for uid in user_ids
            ]
            embed.add_field(name="Users (random insults)", value='\n'.join(users), inline=False)
        else:
            embed.add_field(name="Users (random insults)", value="*None*", inline=False)

        if role_ids:
            roles = []
            for rid in role_ids:
                r = ctx.guild.get_role(rid)
                roles.append(r.mention if r else f"<@&{rid}>")
            embed.add_field(name="Roles (random insults)", value='\n'.join(roles), inline=False)
        else:
            embed.add_field(name="Roles (random insults)", value="*None*", inline=False)

        if specials:
            lines = []
            for row in specials:
                m = ctx.guild.get_member(int(row['user_id']))
                name = m.mention if m else f"<@{row['user_id']}>"
                lines.append(f"{name} → *\"{row['message']}\"*")
            embed.add_field(name="Special (exclusive message)", value='\n'.join(lines), inline=False)
        else:
            embed.add_field(name="Special (exclusive message)", value="*None*", inline=False)

        if count > 0:
            dict_status = f"**{count}** custom insult(s) active — use `/insults dictionary` to view"
        else:
            dict_status = f"*Empty — using {len(DEFAULT_INSULTS)} built-in defaults*"
        embed.add_field(name="Dictionary", value=dict_status, inline=False)

        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='dougbothelp', description="List all DougBot commands")
    async def dougbothelp(self, ctx: commands.Context):
        embed = discord.Embed(title="🤖 DougBot Commands", color=discord.Color.blurple())

        embed.add_field(name="🎉 Fun", value=(
            "`/cock` — Today's cock length\n"
            "`/cockcharts` — Daily leaderboard\n"
            "`/roll [max] [min]` — Roll a number\n"
            "`/cointoss` — Heads or tails\n"
            "`/8ball <question>` — Magic 8ball\n"
            "`/meatking` — The Meat King\n"
            "`/meatchud` — The Meat Chud\n"
            "`/fight <user1> <user2>` — FIGHT TO THE DEATH"
        ), inline=False)

        embed.add_field(name="🎉 Fun", value=(
            "`/play <link>` — Play music from Youtube, Spotify, Soundcloud\n"
            "`/skip` — Skips current song |\n"
            "`/stop` — Stops current play session\n"
            "`/pause` — Pause current song\n"
            "`/queue` — View current queue"
        ), inline=False)

        embed.add_field(name="⏰ Reminders", value=(
            "`/remindme <event> <duration>` — Set a reminder\n"
            "`/reminderslist` — Your active reminders\n"
            "`/cancelevent <id>` — Cancel one reminder\n"
            "`/cancelall` — Cancel all your reminders"
        ), inline=False)

        embed.add_field(name="🔧 Admin", value=(
            "`/purge <count>` — Delete messages\n"
            "`/logs set <#channel>` — Set log channel\n"
            "`/logs clear` — Disable logging\n"
            "`/logs status` — Show current log channel\n"
            "`/insults adduser @user` — Add user to random pool\n"
            "`/insults removeuser @user` — Remove user from pool\n"
            "`/insults addrole @role` — Add role to pool\n"
            "`/insults removerole @role` — Remove role from pool\n"
            "`/insults setspecial @user <msg>` — Exclusive message for one user\n"
            "`/insults clearspecial @user` — Remove exclusive message\n"
            "`/insults add <insult>` — Add to insult dictionary\n"
            "`/insults remove <id>` — Remove from dictionary by ID\n"
            "`/insults dictionary` — View full insult dictionary\n"
            "`/insults list` — Show all targets & config"
        ), inline=False)

        embed.add_field(name="📣 Release Notes", value=(
            "`/updates set <#channel>` — Set channel for release notes\n"
            "`/updates clear` — Disable release notes\n"
            "`/updates status` — Show current channel"
        ), inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Config(bot))
