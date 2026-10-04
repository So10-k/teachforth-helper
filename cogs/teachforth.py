"""TeachForth commands on top of the Modmail desk."""

import logging
import re

import discord
from discord.ext import commands, tasks
from discord.http import Route

import teachforth_portal
import teachforth_roles
from core import checks
from core.models import PermissionLevel

logger = logging.getLogger("teachforth")
SNOWFLAKE = re.compile(r"\d{17,20}")
COPY = {
    "thread_creation_contact_title": ("New Thread", "New help request"),
    "thread_creation_self_contact_response": ("You have opened a Modmail thread.", "You opened a TeachForth help thread."),
    "thread_creation_contact_response": ("{creator.name} has opened a Modmail thread.", "{creator.name} opened a help thread."),
    "thread_move_response": ("This thread has been moved.", "This conversation moved."),
    "disabled_new_thread_response": ("We are not accepting new threads.", "Help is closed right now."),
    "disabled_current_thread_response": ("We are not accepting any messages.", "Help is paused right now."),
    "thread_creation_menu_dropdown_placeholder": (
        "Select an option to contact the staff team.",
        "What do you need help with?",
    ),
    "anon_username": (None, "TeachForth"),
    "anon_tag": ("Response", "TeachForth"),
    "mod_tag": (None, "TeachForth"),
    "mod_color": (0x2ECC71, "0x7a1fa3"),
    "recipient_color": (0xF1C40F, "0xc77dff"),
    "private_added_to_group_response": (
        "{moderator.name} has added you to a Modmail thread.",
        "{moderator.name} added you to a TeachForth help thread.",
    ),
    "private_added_to_group_description_anon": (
        "A moderator has added you to a Modmail thread.",
        "A teacher added you to a TeachForth help thread.",
    ),
    "public_added_to_group_response": (
        "{moderator.name} has added {users} to the Modmail thread.",
        "{moderator.name} added {users} to this TeachForth thread.",
    ),
    "public_added_to_group_description_anon": (
        "A moderator has added {users} to the Modmail thread.",
        "A teacher added {users} to this TeachForth thread.",
    ),
    "private_removed_from_group_response": (
        "{moderator.name} has removed you from the Modmail thread.",
        "{moderator.name} removed you from the TeachForth help thread.",
    ),
    "private_removed_from_group_description_anon": (
        "A moderator has removed you from the Modmail thread.",
        "A teacher removed you from the TeachForth help thread.",
    ),
    "public_removed_from_group_response": (
        "{moderator.name} has removed {users} from the Modmail thread.",
        "{moderator.name} removed {users} from this TeachForth thread.",
    ),
    "public_removed_from_group_description_anon": (
        "A moderator has removed {users} from the Modmail thread.",
        "A teacher removed {users} from this TeachForth thread.",
    ),
    "confirm_thread_response": (
        "Click the button to confirm thread creation which will directly contact the moderators.",
        "Click the button to send this to a TeachForth teacher.",
    ),
}
SNIPPETS = {
    "greeting": "Hey, a TeachForth teacher has this. Tell me what you're stuck on.",
    "hours": "Class hours are on the board. If the IDE is down, a lead can start it.",
    "github": "Your code stays in GitHub. Open the IDE and connect GitHub from the account menu if it isn't linked yet.",
    "ide": "Open the IDE from the class link. If it will not load, say what you see and a lead will check the server.",
}


class TeachForth(commands.Cog):
    """Registration, slash forwarding, and IDE lookup."""

    def __init__(self, bot):
        self.bot = bot
        self._hinted = set()

    @commands.Cog.listener()
    async def on_ready(self):
        await teachforth_portal.start(self.bot)
        await self.ensure_desk()
        if not self.role_sync.is_running():
            self.role_sync.start()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.application_command:
            return
        if interaction.command is not None or interaction.response.is_done():
            return
        name = (interaction.data or {}).get("name") or ""
        if not name:
            return
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.HTTPException:
            return
        status, payload = await teachforth_portal.slash_answer(self._slash_body(interaction))
        body = payload if status == 200 and isinstance(payload, dict) else {
            "embeds": [{"title": "That got stuck", "description": "Try again in a minute.", "color": 0x7A1FA3}],
            "flags": 64,
        }
        try:
            await self.bot.http.request(
                Route(
                    "PATCH",
                    "/webhooks/{application_id}/{interaction_token}/messages/@original",
                    application_id=interaction.application_id,
                    interaction_token=interaction.token,
                ),
                json=body,
            )
        except discord.HTTPException:
            logger.warning("Slash followup failed for %s", name)

    @commands.command(name="login", usage="[code]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def login(self, ctx, code: str = ""):
        """Register a teacher for the helpdesk. A student cannot register."""
        if ctx.guild is None:
            return await ctx.send("Run that in the TeachForth server.")
        app = getattr(self.bot, "_teachforth_app", None)
        if app is None:
            return await ctx.send("The helpdesk is still starting. Try again in a few seconds.")
        status, data = teachforth_portal.accept_registration(
            app,
            ctx.author.id,
            ctx.author.display_name,
            code,
            getattr(ctx.author.guild_permissions, "value", 0),
        )
        if status != 200:
            return await ctx.send(data.get("error") or "That didn't register.")
        if data.get("code"):
            return await ctx.send(
                f"You're registered. Helpdesk code: `{data['code']}`\nPaste it at {teachforth_portal.PUBLIC}"
            )
        await ctx.send(data.get("message") or "You're registered.")

    @commands.command(name="teachforthlookup", aliases=["tflookup"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def teachforthlookup(self, ctx, *, query: str = ""):
        """In a ticket, show that person's IDE account, reports, and history."""
        target, text = self._lookup_target(ctx, query)
        if not target and not text:
            return await ctx.send("Run this in a ticket, or give a name, mention, or Discord ID.")
        status, data = await teachforth_portal.ide_lookup(ctx.author.id, target=target, query=text)
        person = self._discord_person(ctx, target)
        embeds = teachforth_portal.dossier_embeds(status, data, person)
        await ctx.send(embeds=embeds[:10])

    def _lookup_target(self, ctx, query):
        text = (query or "").strip()
        match = SNOWFLAKE.search(text)
        if match and (text.startswith("<@") or text == match.group(0)):
            return match.group(0), ""
        if text:
            return "", text
        for item in list(getattr(self.bot, "threads", [])):
            channel = getattr(item, "channel", None)
            recipient = getattr(item, "recipient", None)
            if channel and channel.id == ctx.channel.id and recipient is not None:
                return str(recipient.id), ""
        return "", ""

    def _discord_person(self, ctx, target):
        if not target:
            return None
        user = ctx.guild.get_member(int(target)) if ctx.guild else None
        return user or self.bot.get_user(int(target))

    def _slash_body(self, interaction):
        user = interaction.user
        account = {
            "id": str(user.id),
            "username": user.name,
            "global_name": user.global_name or user.name,
        }
        member = {
            "permissions": str(getattr(interaction.permissions, "value", 0)),
            "user": account,
        }
        return {
            "type": 2,
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
            "channel_id": str(interaction.channel_id) if interaction.channel_id else None,
            "member": member if interaction.guild_id else None,
            "user": account,
            "data": interaction.data,
        }

    async def ensure_desk(self):
        try:
            await self.bot.config.wait_until_ready()
            changed = False
            for key, (old, new) in COPY.items():
                if self.bot.config.get(key) == old:
                    self.bot.config[key] = new
                    changed = True
            snippets = dict(self.bot.config.get("snippets") or {})
            for name, value in SNIPPETS.items():
                if name not in snippets:
                    snippets[name] = value
                    changed = True
            if changed:
                self.bot.config["snippets"] = snippets
                await self.bot.config.update()
            if not self.bot.config.get("level_permissions"):
                await self.bot.update_perms(PermissionLevel.REGULAR, -1)
                for owner_id in self.bot.bot_owner_ids:
                    await self.bot.update_perms(PermissionLevel.OWNER, int(owner_id))
                guild = self.bot.modmail_guild
                if guild is not None:
                    for role in self._staff_roles(guild):
                        await self.bot.update_perms(PermissionLevel.SUPPORTER, role.id)
            if self.bot.config.get("thread_creation_menu_enabled"):
                self.bot.config["thread_creation_menu_enabled"] = False
                await self.bot.config.update()
            await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name="TeachForth help")
            )
            await self.ensure_category()
        except Exception:
            logger.exception("TeachForth desk setup did not finish")

    async def ensure_category(self):
        guild = self.bot.modmail_guild
        if guild is None or self.bot.main_category is not None:
            return
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            logger.warning("Desk category was not created. The bot needs Manage Channels.")
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        for role in self._staff_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, read_message_history=True
            )
        for owner_id in self.bot.bot_owner_ids:
            member = guild.get_member(int(owner_id))
            if member is not None:
                overwrites[member] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_messages=True
                )
        try:
            category = await guild.create_category(name="TeachForth Help", overwrites=overwrites)
            log_channel = await guild.create_text_channel(name="help-logs", category=category)
        except discord.Forbidden:
            logger.warning("Desk category was not created. The bot needs Manage Channels.")
            return
        self.bot.config["main_category_id"] = category.id
        self.bot.config["log_channel_id"] = log_channel.id
        await self.bot.config.update()
        await log_channel.send("Help logs land here. Tickets open under TeachForth Help.")

    @tasks.loop(minutes=2)
    async def role_sync(self):
        try:
            await teachforth_roles.sync(self.bot)
        except Exception:
            logger.exception("Website role sync failed")

    @role_sync.before_loop
    async def role_sync_ready(self):
        await self.bot.wait_until_ready()

    def _staff_roles(self, guild):
        words = ("teacher", "staff", "mod", "helper", "lead", "admin")
        roles = []
        for role in guild.roles:
            if role.is_default():
                continue
            name = role.name.lower()
            if role.permissions.administrator or role.permissions.manage_messages or any(word in name for word in words):
                roles.append(role)
        return roles


async def setup(bot):
    await bot.add_cog(TeachForth(bot))
