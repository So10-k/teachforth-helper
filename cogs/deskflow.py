"""TeachForth ticket flow.

Adapted from the public Modmail registry: claim, reminder, suggest, and rename.
Giveaways, countdowns, emote tools, and media logging are left out. They do not
belong on a school helpdesk.
"""

import json
import re
import time
from pathlib import Path

import discord
from discord.ext import commands, tasks

from core import checks
from core.models import PermissionLevel

DATA = Path("/var/lib/teachforth-helper/deskflow.json")
TOPICS = {
    "ide": "IDE",
    "github": "GitHub",
    "class": "Class",
    "account": "Account",
    "lesson": "Lesson",
    "other": "Other",
}
DURATION = re.compile(r"^(\d{1,4})([mhd])$")
COLOR = 0x7A1FA3


class DeskFlow(commands.Cog):
    """Sorting, soft claims, reminders, and suggestions."""

    def __init__(self, bot):
        self.bot = bot
        self.data = self._load()
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        perms = self.bot.config.get("command_permissions") or {}
        for name in ("sort", "queue", "claim", "unclaim", "remind", "idea", "decide"):
            current = perms.get(name) or []
            if -1 not in current and "-1" not in current:
                await self.bot.update_perms(name, -1)
                perms = self.bot.config.get("command_permissions") or {}

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot or member.guild != self.bot.modmail_guild:
            return
        embed = discord.Embed(
            title="Welcome to TeachForth",
            description="Message me here if you need a teacher. Say whether it is the IDE, GitHub, class, or your account. Never send a password or a login code.",
            color=COLOR,
        )
        embed.set_footer(text="TeachForth")
        try:
            await member.send(embed=embed)
        except discord.HTTPException:
            return

    @commands.command(name="sort")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def sort(self, ctx, topic: str = ""):
        """Sort this ticket. `.sort ide`, `github`, `class`, `account`, `lesson`, or `other`."""
        key = topic.strip().lower()
        if key not in TOPICS:
            return await ctx.send("Sort it as `ide`, `github`, `class`, `account`, `lesson`, or `other`.")
        label = TOPICS[key]
        channel = ctx.channel
        renamed = await self._place(channel, key, label)
        self.data.setdefault("sort", {})[str(channel.id)] = key
        self._save()
        embed = discord.Embed(
            title=f"Sorted · {label}",
            description="A teacher can filter the queue with `.queue`. The helpdesk groups these the same way.",
            color=COLOR,
        )
        embed.set_footer(text="TeachForth")
        if not renamed:
            embed.description = "I marked it, but I could not move the channel. I need Manage Channels for that."
        await ctx.send(embed=embed)

    @commands.command(name="queue")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def queue(self, ctx):
        """Show open tickets grouped by topic."""
        groups = {key: [] for key in (*TOPICS, "open")}
        for thread in list(self.bot.threads):
            channel = getattr(thread, "channel", None)
            if channel is None or not getattr(thread, "ready", False):
                continue
            key = self.data.get("sort", {}).get(str(channel.id)) or self._prefix(channel.name)
            recipient = getattr(thread, "recipient", None)
            who = getattr(recipient, "name", None) or channel.name
            groups.setdefault(key, []).append(f"{who} · {channel.mention}")
        embed = discord.Embed(title="Open tickets", color=COLOR)
        embed.set_footer(text="TeachForth")
        shown = False
        for key, rows in groups.items():
            if not rows:
                continue
            shown = True
            title = TOPICS.get(key, "Not sorted")
            embed.add_field(name=title, value="\n".join(rows[:8]), inline=False)
        if not shown:
            embed.description = "Nothing is open."
        await ctx.send(embed=embed)

    @commands.command(name="claim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def claim(self, ctx):
        """Take this ticket. Other teachers can still reply."""
        self.data.setdefault("claims", {})[str(ctx.channel.id)] = {
            "id": str(ctx.author.id),
            "name": ctx.author.display_name,
        }
        self._save()
        embed = discord.Embed(
            title="You have this",
            description=f"{ctx.author.display_name} is on it. Another teacher can still reply, or `.unclaim` it.",
            color=COLOR,
        )
        embed.set_footer(text="TeachForth")
        await ctx.send(embed=embed)

    @commands.command(name="unclaim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unclaim(self, ctx):
        """Let the ticket go back to the queue."""
        self.data.get("claims", {}).pop(str(ctx.channel.id), None)
        self._save()
        await ctx.send(embed=discord.Embed(title="Back in the queue", description="Anyone can take it.", color=COLOR))

    @commands.command(name="remind")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def remind(self, ctx, when: str, *, text: str):
        """Remind this channel. `.remind 20m check the project`."""
        match = DURATION.match(when.strip().lower())
        if not match or len(text) > 300:
            return await ctx.send("Use `.remind 20m check the project`. Minutes, hours, or days.")
        amount, unit = int(match.group(1)), match.group(2)
        seconds = amount * {"m": 60, "h": 3600, "d": 86400}[unit]
        if seconds < 60 or seconds > 14 * 86400:
            return await ctx.send("Pick a time between 1 minute and 14 days.")
        self.data.setdefault("reminders", []).append(
            {"at": time.time() + seconds, "channel": str(ctx.channel.id), "text": text, "by": ctx.author.display_name}
        )
        self._save()
        await ctx.send(embed=discord.Embed(title="I'll nudge this channel", description=text, color=COLOR))

    @commands.command(name="idea")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def idea(self, ctx, *, text: str):
        """Save a suggestion from this ticket."""
        if len(text) > 500:
            return await ctx.send("Keep the suggestion under 500 characters.")
        row = {
            "at": time.time(),
            "channel": str(ctx.channel.id),
            "by": ctx.author.display_name,
            "text": text,
            "status": "open",
        }
        self.data.setdefault("ideas", []).append(row)
        self.data["ideas"] = self.data["ideas"][-100:]
        self._save()
        embed = discord.Embed(title="Suggestion", description=text, color=COLOR)
        embed.set_footer(text="TeachForth · open")
        await ctx.send(embed=embed)

    @commands.command(name="decide")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def decide(self, ctx, choice: str, *, text: str = ""):
        """Accept or decline the latest suggestion. `.decide yes` or `.decide no`."""
        status = {"yes": "accepted", "accept": "accepted", "no": "declined", "deny": "declined"}.get(choice.lower())
        if not status:
            return await ctx.send("Use `.decide yes` or `.decide no`.")
        ideas = self.data.get("ideas") or []
        if not ideas:
            return await ctx.send("There is no suggestion yet.")
        ideas[-1]["status"] = status
        if text:
            ideas[-1]["note"] = text[:200]
        self._save()
        await ctx.send(embed=discord.Embed(title=f"Suggestion {status}", description=ideas[-1].get("text", ""), color=COLOR))

    @tasks.loop(seconds=30)
    async def tick(self):
        now = time.time()
        due = [item for item in self.data.get("reminders", []) if item.get("at", 0) <= now]
        if not due:
            return
        self.data["reminders"] = [item for item in self.data.get("reminders", []) if item.get("at", 0) > now]
        self._save()
        for item in due:
            channel = self.bot.get_channel(int(item.get("channel") or 0))
            if channel is None:
                continue
            embed = discord.Embed(title="Reminder", description=item.get("text") or "Check this ticket.", color=COLOR)
            embed.set_footer(text=f"TeachForth · {item.get('by') or 'staff'}")
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                continue

    @tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    async def _place(self, channel, key, label):
        base = self._bare(channel.name)
        name = f"{key}-{base}"[:100]
        category = await self._category(channel.guild, key, label)
        try:
            kwargs = {"name": name, "topic": f"TeachForth · {label}"}
            if category is not None:
                kwargs["category"] = category
            await channel.edit(**kwargs)
            return True
        except discord.HTTPException:
            return False

    async def _category(self, guild, key, label):
        saved = (self.data.get("categories") or {}).get(key)
        if saved:
            found = guild.get_channel(int(saved))
            if isinstance(found, discord.CategoryChannel):
                return found
        name = f"Help · {label}"
        found = discord.utils.get(guild.categories, name=name)
        if found is None:
            me = guild.me
            if me is None or not me.guild_permissions.manage_channels:
                return None
            main = self.bot.main_category
            overwrites = dict(main.overwrites) if main is not None else {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            try:
                found = await guild.create_category(name, overwrites=overwrites)
            except discord.HTTPException:
                return None
        self.data.setdefault("categories", {})[key] = found.id
        self._save()
        return found

    def _prefix(self, name):
        key = (name or "").split("-", 1)[0]
        return key if key in TOPICS else "open"

    def _bare(self, name):
        text = (name or "ticket").lower()
        key = text.split("-", 1)[0]
        if key in TOPICS and "-" in text:
            text = text.split("-", 1)[1]
        cleaned = re.sub(r"[^a-z0-9-]", "-", text).strip("-")
        return cleaned or "ticket"

    def _load(self):
        try:
            data = json.loads(DATA.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        data.setdefault("sort", {})
        data.setdefault("claims", {})
        data.setdefault("reminders", [])
        data.setdefault("ideas", [])
        data.setdefault("categories", {})
        return data

    def _save(self):
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(self.data), encoding="utf-8")
        try:
            DATA.chmod(0o600)
        except OSError:
            return


async def setup(bot):
    await bot.add_cog(DeskFlow(bot))
