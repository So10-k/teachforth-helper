"""Assign Discord roles from TeachForth website roles. Session lead is only for a live block."""

import json
import logging
import os
from pathlib import Path

import aiohttp
import discord

import teachforth_perms
import teachforth_portal

try:
    from core.models import getLogger

    logger = getLogger("cogs.teachforth")
except Exception:
    logger = logging.getLogger("cogs.teachforth")

ROLE_FOR = {
    "student": "TeachForth Student",
    "teacher": "TeachForth Teacher",
    "lead_teacher": "TeachForth Teacher",
    "chapter_lead": "TeachForth Chapter Lead",
    "admin": "TeachForth Admin",
}
SESSION = "TeachForth Session Lead"
SPECS = {
    "TeachForth Student": 0xC77DFF,
    "TeachForth Teacher": 0x7A1FA3,
    "TeachForth Chapter Lead": 0x5A189A,
    "TeachForth Admin": 0x3C096C,
    "TeachForth Session Lead": 0xE0AAFF,
}
STAFF_COMMANDS = ("teachforthlookup", "diagnostic", "projects", "project", "reports", "chapters", "helpmenusend")
COMMAND_LEVELS = teachforth_perms.command_levels()
STAFF_CATEGORY_ROLES = (
    "TeachForth Teacher",
    "TeachForth Chapter Lead",
    "TeachForth Admin",
    "TeachForth Session Lead",
)


def wanted_names(row):
    row = row or {}
    names = []
    base = ROLE_FOR.get(str(row.get("role") or ""))
    if base:
        names.append(base)
    if row.get("sessionLead") and base != "TeachForth Student":
        names.append(SESSION)
    return names


async def sync(bot):
    guild = bot.modmail_guild
    if guild is None:
        return
    me = guild.me
    if me is not None and not me.guild_permissions.manage_roles and not me.guild_permissions.administrator:
        logger.warning("Website roles were not assigned. The bot needs Manage Roles.")
        return
    phase = await class_phase()
    roles = await ensure_roles(guild)
    people = None
    if phase in {"on", "starting"}:
        status, data = await teachforth_portal.class_call("GET", "/api/discord/roster")
        if status == 200 and isinstance(data.get("people"), list):
            people = data["people"]
    elif phase == "off":
        people = cached_people()
    if people is None:
        logger.warning("Website roles were not assigned. Class phase was %s and no roster was available.", phase or "unknown")
        if phase == "off":
            await clear_session(roles.get(SESSION))
        return
    if phase == "off":
        for row in people:
            row["sessionLead"] = False
    people = {
        str(row.get("discordId")): row
        for row in people
        if str(row.get("discordId") or "").isdigit()
    }
    managed = {role.id for role in roles.values()}
    seen = set()
    changed = 0
    for discord_id, row in people.items():
        seen.add(int(discord_id))
        changed += await apply_account(bot, guild.id, discord_id, wanted_names(row), roles, managed)
    for member in list(guild.members):
        if member.bot or member.id in seen:
            continue
        if not any(role.id in managed for role in member.roles):
            continue
        changed += await apply_account(bot, guild.id, member.id, [], roles, managed)
    logger.info("TeachForth role sync finished. phase=%s accounts=%s changed=%s", phase, len(people), changed)
    teachforth_perms.apply_text(bot)
    await apply_levels(bot, roles)


async def apply_account(bot, guild_id, discord_id, names, roles, managed):
    want = {roles[name].id for name in names if name in roles}
    try:
        data = await bot.http.get_member(guild_id, int(discord_id))
    except discord.HTTPException:
        logger.warning("A linked account is not in the Discord server, so its role was not assigned.")
        return 0
    current = {int(role_id) for role_id in data.get("roles") or []}
    changed = 0
    for role_id in sorted(want - current):
        try:
            await bot.http.add_role(guild_id, int(discord_id), role_id, reason="TeachForth website role")
            changed += 1
        except discord.HTTPException:
            logger.warning("Could not add a TeachForth role. Move the bot role above the TeachForth roles.")
    for role_id in sorted((current & managed) - want):
        try:
            await bot.http.remove_role(guild_id, int(discord_id), role_id, reason="TeachForth website role")
            changed += 1
        except discord.HTTPException:
            logger.warning("Could not remove a TeachForth role. Move the bot role above the TeachForth roles.")
    return changed


async def ensure_roles(guild):
    found = {}
    for name, color in SPECS.items():
        role = discord.utils.get(guild.roles, name=name)
        if role is None:
            try:
                role = await guild.create_role(
                    name=name,
                    colour=discord.Colour(color),
                    hoist=name != "TeachForth Student",
                    mentionable=False,
                    reason="TeachForth website role",
                )
            except discord.HTTPException:
                logger.warning("Could not create %s", name)
                continue
        found[name] = role
    return found


async def clear_session(role):
    if role is None:
        return
    for member in list(role.members):
        try:
            await member.remove_roles(role, reason="Class is off")
        except discord.HTTPException:
            logger.info("Could not remove the session lead role")


async def apply_levels(bot, roles):
    levels = dict(bot.config.get("level_permissions") or {})
    desired = {"REGULAR": ["-1"]}
    admin = ids(roles, ["TeachForth Admin"])
    chapter = ids(roles, ["TeachForth Chapter Lead"])
    teachers = ids(roles, ["TeachForth Teacher", "TeachForth Session Lead"])
    if admin:
        desired["ADMINISTRATOR"] = admin
    if chapter:
        desired["MODERATOR"] = chapter
    if teachers:
        desired["SUPPORTER"] = teachers
    owners = [str(item) for item in (levels.get("OWNER") or [])]
    for owner_id in getattr(bot, "bot_owner_ids", []) or []:
        if str(owner_id) not in owners:
            owners.append(str(owner_id))
    if owners:
        desired["OWNER"] = owners
    changed = False
    for level, wanted in desired.items():
        current = [str(item) for item in levels.get(level) or []]
        if current != wanted:
            levels[level] = wanted
            changed = True
    if changed:
        bot.config["level_permissions"] = levels
        await bot.config.update()
        logger.info("Set Modmail permission levels from TeachForth roles.")
    overrides = dict(bot.config.get("override_command_level") or {})
    override_changed = False
    for name, level in COMMAND_LEVELS.items():
        if overrides.get(name) != level:
            overrides[name] = level
            override_changed = True
    if override_changed:
        bot.config["override_command_level"] = overrides
        await bot.config.update()
    perms = dict(bot.config.get("command_permissions") or {})
    stripped = False
    for name in STAFF_COMMANDS:
        current = list(perms.get(name) or [])
        if -1 in current:
            kept = [item for item in current if item != -1]
            if kept:
                perms[name] = kept
            else:
                perms.pop(name, None)
            stripped = True
    if stripped:
        bot.config["command_permissions"] = perms
        await bot.config.update()
    await apply_category(bot, roles)


async def apply_category(bot, roles):
    category = bot.main_category
    if category is None:
        return
    overwrites = dict(category.overwrites)
    changed = False
    for name in STAFF_CATEGORY_ROLES:
        role = roles.get(name)
        if role is None:
            continue
        current = overwrites.get(role)
        if current is not None and current.read_messages and current.send_messages:
            continue
        overwrites[role] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        )
        changed = True
    student = roles.get("TeachForth Student")
    if student is not None and student in overwrites:
        overwrites.pop(student)
        changed = True
    if not changed:
        return
    try:
        await category.edit(overwrites=overwrites, reason="TeachForth website roles")
    except discord.HTTPException:
        logger.warning("Could not open the help category to TeachForth staff roles.")


def cached_people():
    path = Path("/var/lib/teachforth-discord/roles.json")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(rows, dict):
        return None
    return [{"discordId": str(key), "role": value, "sessionLead": False} for key, value in rows.items()]


def ids(roles, names):
    return [str(roles[name].id) for name in names if name in roles]


async def class_phase():
    path = Path(os.environ.get("TEACHFORTH_POWER_SECRET", "/var/lib/teachforth-discord/power-secret"))
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not secret:
        return ""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "http://127.0.0.1:8791/api/internal/status",
                headers={"authorization": f"Bearer {secret}"},
            ) as res:
                if res.status != 200:
                    return ""
                data = await res.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return ""
    phase = str((data or {}).get("phase") or "")
    if (data or {}).get("running") and phase not in {"on", "starting", "off"}:
        return "on"
    return phase
