"""Qualification routing for TeachForth tickets."""

import discord
from discord.ext import commands

import teachforth_chat
from core import checks
from core.models import PermissionLevel

COLOR = 0x3B6EF6


class Qualify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        teachforth_chat.attach(self.bot)

    @commands.group(name="qualification", aliases=["qualifications", "qualify"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def qualification(self, ctx):
        """Give staff a topic so only they see matching tickets."""
        lines = [
            "`.qualification add @user ide`",
            "`.qualification remove @user ide`",
            "`.qualification list`",
            "`.qualification list @user`",
            "",
            "Topics: " + ", ".join(sorted(teachforth_chat.TOPIC_IDS)),
            "A teacher only sees tickets for topics they hold. Admins see every ticket.",
        ]
        await ctx.send(embed=self._embed("Qualifications", "\n".join(lines)))

    @qualification.command(name="add")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def add(self, ctx, member: discord.Member, topic: str):
        """Give someone a qualification. Chapter lead or admin."""
        await self._set(ctx, member, topic, True)

    @qualification.command(name="remove")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def remove(self, ctx, member: discord.Member, topic: str):
        """Take a qualification away. Chapter lead or admin."""
        await self._set(ctx, member, topic, False)

    @qualification.command(name="list")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def list(self, ctx, member: discord.Member = None):
        """List qualifications. A teacher sees their own."""
        if member is not None and not await self._lead(ctx):
            return
        if member is None:
            rows = teachforth_chat.list_all()
            if not rows:
                return await ctx.send(embed=self._embed("Qualifications", "Nobody has one yet."))
            lines = []
            for discord_id, topics in list(rows.items())[:25]:
                person = ctx.guild.get_member(int(discord_id)) if ctx.guild else None
                name = getattr(person, "display_name", None) or discord_id
                shown = ", ".join(teachforth_chat.topic_label(item) for item in topics) or "none"
                lines.append(f"{name}: {shown}")
            return await ctx.send(embed=self._embed("Qualifications", "\n".join(lines)))
        topics = teachforth_chat.qualifications_for(member.id)
        shown = ", ".join(teachforth_chat.topic_label(item) for item in topics) or "None yet."
        await ctx.send(embed=self._embed(member.display_name, shown))

    async def _set(self, ctx, member, topic, present):
        topic = str(topic or "").strip().lower()
        if topic not in teachforth_chat.TOPIC_IDS:
            return await ctx.send(embed=self._embed("Qualification", "Use one of: " + ", ".join(sorted(teachforth_chat.TOPIC_IDS))))
        teachforth_chat.set_qualification(member.id, topic, present)
        await teachforth_chat.refresh_topic(self.bot, topic)
        verb = "can see" if present else "no longer sees"
        await ctx.send(embed=self._embed(
            "Qualification",
            f"{member.display_name} {verb} {teachforth_chat.topic_label(topic)} tickets.",
        ))

    async def _lead(self, ctx):
        rank = await teachforth_chat.staff_rank(self.bot, ctx.author.id)
        if rank in {"chapter", "admin"}:
            return True
        await ctx.send(embed=self._embed("Not allowed", "Listing someone else is for a chapter lead or admin."))
        return False

    def _embed(self, title, description):
        embed = discord.Embed(title=title[:256], description=description[:4000], color=COLOR)
        embed.set_footer(text="TeachForth Help")
        return embed


async def setup(bot):
    await bot.add_cog(Qualify(bot))
