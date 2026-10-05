"""Private desk training for a new teacher. Discord only."""

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

import teachforth_perms
import teachforth_training as training
from core import checks
from core.models import PermissionLevel
from core.thread import Thread

logger = logging.getLogger("teachforth.training")
COLOR = training.COLOR


class TrainButton(discord.ui.Button):
    def __init__(self, label, custom_id, style=discord.ButtonStyle.primary):
        super().__init__(label=label[:80], custom_id=custom_id[:100], style=style)

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Training")
        if cog is not None:
            await cog.handle(interaction)


def view_for(step, user_id, index):
    view = discord.ui.View(timeout=None)
    kind = step.get("kind")
    if kind == "quiz":
        for choice in step.get("choices") or []:
            style = discord.ButtonStyle.secondary
            view.add_item(TrainButton(choice["label"], f"tft:a:{user_id}:{index}:{choice['id']}", style))
    elif kind == "open":
        view.add_item(TrainButton("Open the practice ticket", f"tft:open:{user_id}", discord.ButtonStyle.primary))
    elif kind == "lab":
        view.add_item(TrainButton("Show the command", f"tft:show:{user_id}", discord.ButtonStyle.secondary))
        if step.get("where") != "sandbox":
            view.add_item(TrainButton("Open the practice ticket", f"tft:open:{user_id}", discord.ButtonStyle.primary))
    elif kind == "finish":
        view.add_item(TrainButton("Restore my access", f"tft:end:{user_id}", discord.ButtonStyle.success))
    return view if view.children else None


def stop_view(user_id):
    view = discord.ui.View(timeout=None)
    view.add_item(TrainButton("Stop and restore access", f"tft:stop:{user_id}", discord.ButtonStyle.danger))
    return view


def _typed(ctx):
    invoked = (getattr(ctx, "invoked_with", None) or "").lower()
    command = getattr(ctx.command, "name", "") or ""
    names = {command.lower()}
    names.update(item.lower() for item in (getattr(ctx.command, "aliases", None) or []))
    parent = getattr(getattr(ctx.command, "parent", None), "name", None)
    if parent:
        names.add(str(parent).lower())
    return bool(invoked) and invoked in names


async def guard(ctx):
    command = getattr(ctx.command, "name", "") or ""
    channel_id = getattr(ctx.channel, "id", 0)
    if training.is_sandbox(channel_id):
        return False
    if not training.is_ticket(channel_id):
        return True
    # Help lists every command by running its checks. Do not talk, and do not hide the list.
    if not _typed(ctx):
        return True
    if command in training.BLOCKED:
        await ctx.send("That command is blocked in a practice ticket. Finish the pathway, or a lead can run `.train end`.")
        return False
    if command == "helpmenusend":
        parts = (ctx.message.content or "").split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            await ctx.send("Run `.helpmenusend` with nothing after it. A type would start a real walk.")
            return False
    return True


class Training(commands.Cog):
    """A private category that teaches the Discord desk."""

    def __init__(self, bot):
        self.bot = bot
        self._seen = set()
        self._graded = set()
        self._calls = {}
        self._lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_check(guard)
        self.bot.before_invoke(self._remember)

    async def cog_unload(self):
        self.bot.remove_check(guard)
        if getattr(self.bot, "_before_invoke", None) == self._remember:
            self.bot._before_invoke = None

    @commands.Cog.listener()
    async def on_ready(self):
        await self._level()
        await self._rebind()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if not custom_id.startswith("tft:"):
            return
        await self.handle(interaction)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        content = message.content or ""
        kind = training._channel_kind(message.channel.id)
        if not kind:
            return
        name, rest = training.split_command(self._prefixes(), content)
        saved = self._calls.get(message.id)
        if saved and not name:
            name, rest = saved
        if kind == "sandbox":
            await self._grade_sandbox(message, name, rest)
            return
        await self._grade(message, name, rest)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        saved = self._calls.pop(getattr(ctx.message, "id", 0), None)
        if not saved:
            return
        await self._grade(ctx.message, saved[0], saved[1])

    @commands.group(name="train", invoke_without_command=True, usage="<user> [teacher|chapter|admin|session]")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def train(self, ctx, member: discord.Member = None, track: str = "teacher"):
        """Hide the server and open a private lesson for this person."""
        if member is None:
            return await ctx.send(
                "Use `.train @user teacher`, `.train @user chapter`, `.train @user admin`, or `.train @user session`."
            )
        if ctx.invoked_subcommand is not None:
            return
        picked = training.normalize_track(track)
        if not picked:
            return await ctx.send("Track is teacher, chapter, admin, or session.")
        await self._begin(ctx, member, picked)

    @train.command(name="end", usage="<user>")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def end(self, ctx, member: discord.Member = None):
        """Restore the roles and channels saved for this person."""
        if member is None:
            return await ctx.send("Use `.train end @user`.")
        await self._finish(ctx.guild, member.id, ctx.author, announce=ctx)

    @train.command(name="status")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def status(self, ctx):
        """Show who is in desk training."""
        rows = list(training.load().get("users", {}).values())
        if not rows:
            return await ctx.send(embed=self._embed("Desk training", "Nobody is in training."))
        lines = []
        for row in rows[:20]:
            step = training.step_at(int(row.get("step") or 0), row.get("track") or "teacher")
            title = step.get("title") if step else "Done"
            label = training.TRACKS.get(row.get("track") or "teacher", {}).get("label", "Teacher")
            lines.append(f"{row.get('name') or row.get('user_id')} · {label} · {title}")
        await ctx.send(embed=self._embed("Desk training", "\n".join(lines)))

    async def handle(self, interaction):
        if interaction.id in self._seen or interaction.response.is_done():
            return
        self._seen.add(interaction.id)
        custom_id = (interaction.data or {}).get("custom_id") or ""
        parts = custom_id.split(":")
        if len(parts) < 3 or not parts[2].isdigit():
            return
        user_id = int(parts[2])
        action = parts[1]
        if not await self._allowed(interaction, user_id):
            await self._say(interaction, "That training belongs to someone else.")
            return
        guild = interaction.guild or self.bot.modmail_guild
        row = training.get(user_id)
        if row is None:
            await self._say(interaction, "That training already ended.")
            return
        if action == "stop":
            view = discord.ui.View(timeout=None)
            view.add_item(TrainButton("Restore access now", f"tft:end:{user_id}", discord.ButtonStyle.danger))
            await self._say(interaction, "This puts their roles back and removes the training category.", view=view)
            return
        if action == "end":
            await interaction.response.defer()
            member = guild.get_member(user_id) if guild else None
            await self._finish(guild, user_id, interaction.user, announce=interaction)
            return
        if action == "show":
            step = training.step_at(int(row.get("step") or 0), row.get("track") or "teacher")
            shown = (step or {}).get("show") or "Stay on the pathway."
            where = "#training-sandbox" if (step or {}).get("where") == "sandbox" else "the practice ticket"
            await self._say(interaction, f"In {where}, run:\n`{shown}`")
            return
        if action == "open":
            await interaction.response.defer()
            await self._open_ticket(guild, row)
            return
        if action == "a" and len(parts) >= 5:
            await self._answer(interaction, guild, row, parts)
            return
        await self._say(interaction, "That button is not used anymore.")

    async def _begin(self, ctx, member, track="teacher"):
        if member.bot:
            return await ctx.send("Pick a person, not a bot.")
        if track == "admin" and not await self._admin(ctx.author):
            return await ctx.send("Admin training is for an admin.")
        if training.get(member.id):
            return await ctx.send(f"{member.display_name} is already in training. `.train end @{member.display_name}` restores them.")
        if await self.bot.is_owner(member) and not await self.bot.is_owner(ctx.author):
            return await ctx.send("Only the bot owner can train the bot owner.")
        if member.guild_permissions.administrator and not ctx.author.guild_permissions.administrator and not await self.bot.is_owner(ctx.author):
            return await ctx.send("An admin has to train an admin.")
        me = ctx.guild.me
        if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
            return await ctx.send("I need Manage Channels and Manage Roles before I can hide the server.")
        await ctx.send(f"Setting up a private desk for {member.display_name}. This can take a minute.")
        try:
            row = await self._isolate(ctx.guild, member, ctx.author, track)
        except discord.HTTPException as err:
            logger.exception("Training setup failed")
            return await ctx.send(f"I could not finish the private desk, so I put their access back. {err}")
        training.put(member.id, row)
        await self._level()
        await self._post_path(ctx.guild, row)
        link = f"https://discord.com/channels/{ctx.guild.id}/{row['path_id']}"
        try:
            await member.send(
                f"Your {training.TRACKS[track]['label']} training is open. Roles are saved, and the other channels are hidden.\n"
                f"Start here: {link}\n"
                "Read #training-info, then use the buttons in #training-pathway. Plan on about 30 minutes."
            )
        except discord.HTTPException:
            await ctx.send(f"I could not DM {member.display_name}. Send them this: {link}")
        await ctx.send(f"Training is open for {member.display_name}. `.train end {member.mention}` restores their access.")

    async def _isolate(self, guild, member, trainer, track="teacher"):
        role = await self._role(guild)
        original = [item.id for item in member.roles if not item.is_default() and item.id != role.id]
        category = None
        denied = []
        removed = []
        try:
            category = await guild.create_category(
                self._category_name(guild, member),
                overwrites=self._category_overwrites(guild, member, trainer, role),
                reason="TeachForth desk training",
            )
            info = await guild.create_text_channel(
                "training-info",
                category=category,
                overwrites={member: discord.PermissionOverwrite(read_messages=True, send_messages=False, add_reactions=False)},
                reason="TeachForth desk training",
            )
            pathway = await guild.create_text_channel(
                "training-pathway",
                category=category,
                overwrites={member: discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True)},
                reason="TeachForth desk training",
            )
            sandbox = None
            if training.TRACKS.get(track, {}).get("sandbox"):
                sandbox = await guild.create_text_channel(
                    "training-sandbox",
                    category=category,
                    overwrites={member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)},
                    reason="TeachForth desk training",
                )
                await sandbox.send(embed=self._embed(
                    "Sandbox",
                    "Commands here do not touch the live desk. Run the command from #training-pathway. A wrong reason stays wrong.",
                ))
            denied = await self._hide_elsewhere(guild, member, category.id)
            removed = await self._drop_roles(member)
            try:
                await member.add_roles(role, reason="TeachForth desk training")
            except discord.HTTPException:
                logger.warning("Could not add the training role")
            await info.send(embed=self._embed("How to use this", training.INFO), view=stop_view(member.id))
        except discord.HTTPException:
            await self._restore(guild, member, {"roles": original, "removed": removed, "denied": denied, "category_id": getattr(category, "id", 0), "ticket_id": 0, "old_channel_id": 0})
            raise
        return {
            "user_id": member.id,
            "name": member.display_name,
            "trainer_id": trainer.id,
            "track": track,
            "step": 0,
            "roles": original,
            "removed": removed,
            "denied": denied,
            "category_id": category.id,
            "info_id": info.id,
            "path_id": pathway.id,
            "sandbox_id": sandbox.id if sandbox is not None else 0,
            "path_message": 0,
            "ticket_id": 0,
            "old_channel_id": 0,
            "started": datetime.now(timezone.utc).isoformat(),
        }

    async def _hide_elsewhere(self, guild, member, keep_id):
        deny = discord.PermissionOverwrite(read_messages=False, send_messages=False, connect=False)
        changed = []
        for channel in list(guild.channels):
            if channel.id == keep_id or getattr(channel, "category_id", None) == keep_id:
                continue
            if not isinstance(channel, (discord.CategoryChannel, discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
                continue
            try:
                current = channel.overwrites_for(member)
                if current.read_messages is False and current.send_messages is False:
                    continue
                await channel.set_permissions(member, overwrite=deny, reason="TeachForth desk training")
                changed.append(channel.id)
            except discord.HTTPException:
                logger.info("Could not hide a channel from the trainee")
        return changed

    async def _drop_roles(self, member):
        removable = [
            role for role in member.roles
            if not role.is_default() and role.name != training.ROLE_NAME and role < member.guild.me.top_role
        ]
        if not removable:
            return []
        try:
            await member.remove_roles(*removable, reason="TeachForth desk training")
        except discord.HTTPException:
            logger.warning("Could not remove every saved role")
            return []
        return [role.id for role in removable]

    async def _open_ticket(self, guild, row):
        member = guild.get_member(int(row["user_id"])) if guild else None
        if member is None:
            return
        channel = guild.get_channel(int(row.get("ticket_id") or 0))
        if channel is None:
            category = guild.get_channel(int(row["category_id"]))
            overwrites = {
                member: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True,
                )
            }
            channel = await guild.create_text_channel(
                "practice-ticket",
                category=category,
                overwrites=overwrites,
                topic=f"User ID: {member.id}",
                reason="TeachForth practice ticket",
            )
            old = self.bot.threads.cache.get(member.id)
            old_channel = getattr(old, "channel", None)
            if old_channel is not None and old_channel.id != channel.id:
                row["old_channel_id"] = old_channel.id
            thread = Thread(self.bot.threads, member, channel)
            thread.ready = True
            self.bot.threads.cache[member.id] = thread
            row["ticket_id"] = channel.id
            training.put(member.id, row)
            await channel.send(embed=self._embed(
                "Practice ticket",
                "This is a real desk channel. You are also the student, so replies and the diagnostic prompt can arrive in your DMs.\n\n"
                "Run the command from #training-pathway here. Do not close this channel.",
            ))
        step = training.step_at(int(row.get("step") or 0), row.get("track") or "teacher")
        if step and step.get("kind") == "open":
            await self._advance(guild, row)
            return
        if step and step.get("show"):
            await channel.send(f"Current step: `{step['show']}`")

    async def _answer(self, interaction, guild, row, parts):
        index = int(parts[3]) if parts[3].isdigit() else -1
        if index != int(row.get("step") or 0):
            await self._say(interaction, "That card already moved on. Use the latest one in #training-pathway.")
            return
        step = training.step_at(index, row.get("track") or "teacher")
        choice = next((item for item in (step or {}).get("choices") or [] if item["id"] == parts[4]), None)
        if choice is None:
            await self._say(interaction, "That answer is not on this step.")
            return
        if not choice.get("ok"):
            await self._say(interaction, choice.get("why") or "Not that one. Read the card again.")
            return
        await interaction.response.defer()
        await self._advance(guild, row)

    async def _advance(self, guild, row):
        row["step"] = int(row.get("step") or 0) + 1
        training.put(row["user_id"], row)
        await self._post_path(guild, row)
        track = row.get("track") or "teacher"
        step = training.step_at(row["step"], track)
        target_id = int(row.get("sandbox_id") or 0) if step and step.get("where") == "sandbox" else int(row.get("ticket_id") or 0)
        channel = guild.get_channel(target_id) if guild else None
        if channel is not None and step and step.get("show"):
            await channel.send(embed=self._embed(step["title"], f"Run this here:\n`{step['show']}`"))

    async def _post_path(self, guild, row):
        channel = guild.get_channel(int(row.get("path_id") or 0))
        if channel is None:
            return
        track = row.get("track") or "teacher"
        steps = training.steps_for(track)
        step = training.step_at(int(row.get("step") or 0), track)
        if step is None:
            step = steps[-1]
        embed = self._embed(step["title"], step["body"])
        if step.get("prompt"):
            embed.add_field(name="Check", value=step["prompt"][:1024], inline=False)
        if step.get("show"):
            place = "#training-sandbox" if step.get("where") == "sandbox" else "the practice ticket"
            embed.add_field(name=f"Run this in {place}", value=f"`{step['show']}`", inline=False)
        embed.set_footer(text=f"{training.TRACKS[track]['label']} · step {int(row.get('step') or 0) + 1} of {len(steps)} · about {training.minutes_left(int(row.get('step') or 0), track)} min if you read")
        view = view_for(step, row["user_id"], int(row.get("step") or 0))
        message = None
        if row.get("path_message"):
            try:
                message = await channel.fetch_message(int(row["path_message"]))
            except discord.HTTPException:
                message = None
        if message is None:
            message = await channel.send(embed=embed, view=view)
            row["path_message"] = message.id
            training.put(row["user_id"], row)
        else:
            await message.edit(embed=embed, view=view)

    async def _finish(self, guild, user_id, actor, announce=None):
        row = training.get(user_id)
        if row is None:
            if announce is not None:
                await self._announce(announce, "That person is not in training.")
            return
        member = guild.get_member(int(user_id)) if guild else None
        restored = await self._restore(guild, member, row)
        if restored:
            training.pop(user_id)
        text = f"Training ended for {row.get('name') or user_id}. Saved roles were put back." if restored else (
            f"Training ended for {row.get('name') or user_id}, but I could not restore every role. A lead should check."
        )
        if member is not None:
            try:
                await member.send(text + " The other channels are visible again.")
            except discord.HTTPException:
                pass
        if announce is not None:
            await self._announce(announce, text)
        elif actor is not None:
            try:
                await actor.send(text)
            except discord.HTTPException:
                pass

    async def _restore(self, guild, member, row):
        ok = True
        if member is not None:
            roles = [guild.get_role(int(item)) for item in row.get("roles") or row.get("removed") or []]
            roles = [role for role in roles if role is not None and role < guild.me.top_role]
            if roles:
                try:
                    await member.add_roles(*roles, reason="TeachForth training ended")
                except discord.HTTPException:
                    ok = False
            training_role = discord.utils.get(guild.roles, name=training.ROLE_NAME)
            if training_role is not None and training_role in member.roles:
                try:
                    await member.remove_roles(training_role, reason="TeachForth training ended")
                except discord.HTTPException:
                    ok = False
            for channel_id in row.get("denied") or []:
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    continue
                try:
                    await channel.set_permissions(member, overwrite=None, reason="TeachForth training ended")
                except discord.HTTPException:
                    ok = False
            old_id = int(row.get("old_channel_id") or 0)
            old_channel = guild.get_channel(old_id) if old_id else None
            if old_channel is not None:
                restored = Thread(self.bot.threads, member, old_channel)
                restored.ready = True
                self.bot.threads.cache[member.id] = restored
            else:
                self.bot.threads.cache.pop(member.id, None)
        category = guild.get_channel(int(row.get("category_id") or 0))
        if category is not None:
            for child in list(getattr(category, "channels", [])):
                try:
                    await child.delete(reason="TeachForth training ended")
                except discord.HTTPException:
                    ok = False
            try:
                await category.delete(reason="TeachForth training ended")
            except discord.HTTPException:
                ok = False
        return ok

    async def _rebind(self):
        guild = self.bot.modmail_guild
        if guild is None:
            return
        for row in training.load().get("users", {}).values():
            channel = guild.get_channel(int(row.get("ticket_id") or 0))
            member = guild.get_member(int(row.get("user_id") or 0))
            if channel is None or member is None:
                continue
            thread = Thread(self.bot.threads, member, channel)
            thread.ready = True
            self.bot.threads.cache[member.id] = thread

    async def _allowed(self, interaction, user_id):
        if interaction.user.id == user_id or await self.bot.is_owner(interaction.user):
            return True
        names = {role.name for role in getattr(interaction.user, "roles", [])}
        return bool(names & {"TeachForth Admin", "TeachForth Chapter Lead"}) or interaction.user.guild_permissions.administrator

    async def _level(self):
        try:
            await self.bot.config.wait_until_ready()
        except Exception:
            return
        overrides = dict(self.bot.config.get("override_command_level") or {})
        changed = False
        for name in ("train", "train end", "train status"):
            if overrides.get(name) != "MODERATOR":
                overrides[name] = "MODERATOR"
                changed = True
        guild = self.bot.modmail_guild
        role = discord.utils.get(guild.roles, name=training.ROLE_NAME) if guild else None
        levels = dict(self.bot.config.get("level_permissions") or {})
        if role is not None:
            current = [str(item) for item in levels.get("SUPPORTER") or []]
            if str(role.id) not in current:
                current.append(str(role.id))
                levels["SUPPORTER"] = current
                self.bot.config["level_permissions"] = levels
                changed = True
        if changed:
            self.bot.config["override_command_level"] = overrides
            await self.bot.config.update()
        teachforth_perms.apply_text(self.bot)

    async def _role(self, guild):
        role = discord.utils.get(guild.roles, name=training.ROLE_NAME)
        if role is None:
            role = await guild.create_role(name=training.ROLE_NAME, colour=discord.Colour(COLOR), hoist=False, mentionable=False, reason="TeachForth desk training")
        return role

    def _category_overwrites(self, guild, member, trainer, role):
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True),
            role: discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True),
        }
        if trainer is not None and trainer != member:
            overwrites[trainer] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, read_message_history=True)
        for name in ("TeachForth Admin", "TeachForth Chapter Lead"):
            found = discord.utils.get(guild.roles, name=name)
            if found is not None:
                overwrites[found] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        return overwrites

    def _category_name(self, guild, member):
        base = f"Training · {member.display_name}"[:100]
        if discord.utils.get(guild.categories, name=base) is None:
            return base
        return f"{base[:88]} {str(member.id)[-4:]}"

    def _by_ticket(self, channel_id):
        return self._by_channel(channel_id)

    def _by_channel(self, channel_id):
        wanted = int(channel_id)
        for row in training.load().get("users", {}).values():
            if wanted in {int(row.get("ticket_id") or 0), int(row.get("sandbox_id") or 0)}:
                return row
        return None

    async def _admin(self, member):
        if await self.bot.is_owner(member):
            return True
        if getattr(member.guild_permissions, "administrator", False):
            return True
        return any(role.name == "TeachForth Admin" for role in getattr(member, "roles", []))

    def _prefixes(self):
        raw = getattr(self.bot, "prefix", ".") or "."
        if isinstance(raw, (list, tuple)):
            return tuple(item for item in raw if item) + (".",)
        return (str(raw), ".")

    async def _remember(self, ctx):
        content = ctx.message.content or ""
        name, rest = training.split_command(self._prefixes(), content)
        if not name and ctx.command is not None:
            name = ctx.command.name
        self._calls[ctx.message.id] = (name, rest)
        if len(self._calls) > 200:
            for key in list(self._calls)[:100]:
                self._calls.pop(key, None)

    async def _grade_sandbox(self, message, name, rest):
        row = self._by_channel(message.channel.id)
        if row is None or int(row["user_id"]) != message.author.id:
            return
        step = training.step_at(int(row.get("step") or 0), row.get("track") or "teacher")
        on_lab = bool(step and step.get("where") == "sandbox")
        if not name and not on_lab:
            return
        result = training.grade(step, name, rest) if on_lab else "no"
        if message.id in self._graded:
            return
        if result != "no":
            self._graded.add(message.id)
        await message.channel.send(training.sandbox_reply(name, result, step))
        if result == "pass":
            await self._advance(message.guild, row)

    async def _grade(self, message, name, rest):
        async with self._lock:
            if message.id in self._graded:
                return
            row = self._by_channel(message.channel.id)
            if row is None or int(row.get("user_id") or 0) != message.author.id:
                return
            step = training.step_at(int(row.get("step") or 0), row.get("track") or "teacher")
            result = training.grade(step, name, rest)
            if result == "no":
                return
            self._graded.add(message.id)
            if len(self._graded) > 400:
                self._graded = set(list(self._graded)[-200:])
        if result == "short":
            await message.channel.send(step.get("short") or "That command needs a real sentence after it.")
            return
        if result == "extra":
            await message.channel.send(step.get("extra") or "Run that command with nothing after it.")
            return
        if result == "abuse":
            await message.channel.send(step.get("abuse_why") or "That is the abuse this step is about.")
            return
        await message.channel.send("That counted. The pathway moved on.")
        await self._advance(message.guild, row)

    async def _say(self, interaction, text, view=None):
        kwargs = {"ephemeral": True}
        if view is not None:
            kwargs["view"] = view
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, **kwargs)
            else:
                await interaction.response.send_message(text, **kwargs)
        except discord.HTTPException:
            logger.debug("Could not answer a training button.", exc_info=True)

    async def _announce(self, target, text):
        try:
            if isinstance(target, discord.Interaction):
                if target.response.is_done():
                    await target.followup.send(text)
                else:
                    await target.response.send_message(text)
                return
            await target.send(text)
        except discord.HTTPException:
            logger.debug("Could not announce the training result.", exc_info=True)

    def _embed(self, title, description):
        embed = discord.Embed(title=str(title)[:256], description=str(description)[:4000], color=COLOR)
        embed.set_footer(text="TeachForth desk training")
        return embed


async def setup(bot):
    await bot.add_cog(Training(bot))
