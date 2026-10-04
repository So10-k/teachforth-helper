"""TeachForth names for Modmail permission levels, commands, and arguments."""

import discord

from core.models import PermissionLevel

LEVELS = (
    ("OWNER", "Owner", "Bot owner. `.perms`, config, and plugins."),
    ("ADMINISTRATOR", "Admin", "TeachForth Admin. Can start class and use every desk command."),
    ("MODERATOR", "Chapter Lead", "TeachForth Chapter Lead. Can block and move tickets."),
    ("SUPPORTER", "Teacher", "TeachForth Teacher and the current session lead."),
    ("REGULAR", "Student", "Everyone. Help and about only."),
)
ALIASES = {
    "owner": "OWNER",
    "5": "OWNER",
    "admin": "ADMINISTRATOR",
    "administrator": "ADMINISTRATOR",
    "4": "ADMINISTRATOR",
    "chapter lead": "MODERATOR",
    "chapterlead": "MODERATOR",
    "chapter-lead": "MODERATOR",
    "moderator": "MODERATOR",
    "mod": "MODERATOR",
    "3": "MODERATOR",
    "teacher": "SUPPORTER",
    "session lead": "SUPPORTER",
    "sessionlead": "SUPPORTER",
    "session-lead": "SUPPORTER",
    "supporter": "SUPPORTER",
    "responder": "SUPPORTER",
    "2": "SUPPORTER",
    "student": "REGULAR",
    "regular": "REGULAR",
    "everyone": "REGULAR",
    "1": "REGULAR",
}
# Internal Modmail key, help, usage. Usage is what `.help command` shows after the prefix.
COMMANDS = {
    "help": ("REGULAR", "Show the commands your role can run.", "[command]"),
    "about": ("REGULAR", "About this TeachForth bot.", ""),
    "login": ("SUPPORTER", "Register a teacher for the helpdesk. A student cannot register.", "[code]"),
    "roles": ("REGULAR", "Refresh your website role on Discord. Admins can refresh everyone.", "[all]"),
    "reply": ("SUPPORTER", "Send this to the student. They see your name.", "<message>"),
    "areply": ("SUPPORTER", "Send this to the student without your name.", "<message>"),
    "preply": ("SUPPORTER", "Send this to the student with no embed.", "<message>"),
    "close": ("SUPPORTER", "Close this ticket. Delay looks like 30m or 2h.", "[after] [message]"),
    "note": ("SUPPORTER", "Staff note. The student does not see it.", "<message>"),
    "snippet": ("SUPPORTER", "Send a saved reply. `snippet add <name> <text>` saves one.", "[name]"),
    "logs": ("SUPPORTER", "Read a past ticket. Defaults to this student.", "[student]"),
    "contact": ("SUPPORTER", "Open a ticket with someone.", "<user> [message]"),
    "claim": ("SUPPORTER", "Take this ticket. Replies stay open.", ""),
    "unclaim": ("SUPPORTER", "Release this ticket.", ""),
    "notify": ("SUPPORTER", "Ping someone when this student writes again.", "[user or role]"),
    "subscribe": ("SUPPORTER", "Follow this ticket.", "[user or role]"),
    "diagnostic": ("SUPPORTER", "Ask the student to share browser and device details. Cookie values are not sent.", ""),
    "qualification": ("SUPPORTER", "Route tickets by topic. Add and remove are for a chapter lead.", "add|remove|list"),
    "qualification add": ("MODERATOR", "Give a staff member a qualification.", "<user> <ide|github|class|account|homework|general>"),
    "qualification remove": ("MODERATOR", "Take a qualification away.", "<user> <topic>"),
    "qualification list": ("SUPPORTER", "List qualifications. A teacher sees their own.", "[user]"),
    "projects": ("SUPPORTER", "List projects for the account that consented in this ticket.", ""),
    "project": ("SUPPORTER", "View or create a project for the consented account.", "view <id>"),
    "project view": ("SUPPORTER", "Show that project's files in this staff channel.", "<id>"),
    "project create": ("SUPPORTER", "Make a project. Language is blank, python, or web.", "[blank|python|web] [title]"),
    "reports": ("SUPPORTER", "Reports for the consented account. Staff channel only.", ""),
    "chapters": ("SUPPORTER", "Chapters for the consented account.", ""),
    "helpmenusend": ("SUPPORTER", "Walk the student through a fix. No type lists the walks.", "[type]"),
    "teachforthlookup": ("SUPPORTER", "Account, reports, and history. In a ticket, the student is the default.", "[name]"),
    "sort": ("SUPPORTER", "Move this ticket into a topic category.", "<topic>"),
    "queue": ("SUPPORTER", "Show open tickets.", ""),
    "block": ("MODERATOR", "Stop desk messages from someone. Chapter lead or admin.", "<user> [duration] [reason]"),
    "unblock": ("MODERATOR", "Allow desk messages again.", "<user>"),
    "move": ("MODERATOR", "Move this ticket to another category.", "<category>"),
    "alias": ("MODERATOR", "Make a short name for a command.", "<name> <command>"),
    "activity": ("ADMINISTRATOR", "Set the bot status.", "<text>"),
    "enable": ("ADMINISTRATOR", "Open the desk to new tickets.", ""),
    "disable": ("ADMINISTRATOR", "Pause the desk.", ""),
    "permissions": ("OWNER", "See and edit who can run each command.", ""),
    "permissions override": ("OWNER", "Change the level one command requires.", "<command> <student|teacher|chapter lead|admin|owner>"),
    "permissions add": ("OWNER", "Give a role a level. Quote a two-word level.", "level <level> <role>"),
    "permissions remove": ("OWNER", "Take a level off a role or undo an override.", "level <level> <role>"),
    "permissions get": ("OWNER", "See a level, a command, or every override.", "level <level>"),
    "config": ("OWNER", "Change bot settings. Owner only.", ""),
    "plugin": ("OWNER", "Install or remove a plugin. Owner only.", ""),
}
DENIAL = {
    "login": "Helpdesk registration is for a teacher, chapter lead, or admin.",
    "roles": "Refreshing everyone is for an admin. `.roles` refreshes only you.",
    "block": "Blocking is for a chapter lead or an admin.",
    "unblock": "Unblocking is for a chapter lead or an admin.",
    "move": "Moving a ticket is for a chapter lead or an admin.",
    "diagnostic": "Diagnostics are for a teacher, the session lead, a chapter lead, or an admin.",
    "permissions": "Changing permissions is owner only.",
}
COGS = {
    "Modmail": "Tickets. Teachers write back. Chapter leads can block and move.",
    "Utility": "Help, about, and `.perms`.",
    "Diagnostic": "Support-code lookup after the student consents.",
    "TeachForth": "Helpdesk registration and account lookup.",
    "DeskFlow": "Sorting, claiming, and the queue.",
}


def label(level):
    name = getattr(level, "name", str(level or "")).upper()
    for key, shown, _who in LEVELS:
        if key == name:
            return shown
    return name.title() or "that role"


def parse_level(name):
    key = ALIASES.get(str(name or "").strip().lower())
    if key is None:
        key = str(name or "").strip().upper()
    try:
        return PermissionLevel[key]
    except KeyError:
        return PermissionLevel.INVALID


def command_levels():
    return {name: level for name, (level, _help, _usage) in COMMANDS.items()}


def denial(command_name, level):
    specific = DENIAL.get(command_name)
    if specific:
        return specific
    shown = label(level)
    if shown == "Teacher":
        return "That is for a teacher, the session lead, a chapter lead, or an admin."
    if shown == "Student":
        return "Link your account, then try `/help`."
    return f"That is for a {shown.lower()}."


def names_line():
    return "student, teacher, chapter lead, admin, owner"


def matrix_embed(color):
    embed = discord.Embed(
        title="TeachForth permissions",
        color=color,
        description=(
            "Levels come from the website role. Session lead is not its own level: "
            "they use Teacher commands, and only the live session lead or an admin can use `/home`."
        ),
    )
    for key, shown, who in LEVELS:
        rank = int(PermissionLevel[key])
        embed.add_field(name=f"{shown} [{rank}]", value=who, inline=False)
    embed.add_field(
        name="Commands",
        value=(
            "`reply <message>` · `close [30m] [message]` · `note <message>` · `contact <user> [message]`\n"
            "`diagnostic` · `qualification add <user> <topic>` · `projects` · `project view <id>`\n"
            "`block <user> [duration] [reason]` · `move <category>` · `helpmenusend [type]`"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Levels: {names_line()}. Quote two-word levels.")
    return embed


def apply_text(bot):
    prefix = bot.prefix or "."
    for name, (_level, help_text, usage) in COMMANDS.items():
        command = bot.get_command(name)
        if command is None:
            continue
        command.help = help_text
        command.brief = help_text
        if usage:
            command.usage = usage
    for name, text in COGS.items():
        cog = bot.get_cog(name)
        if cog is not None:
            cog.description = text
    bot.teachforth_prefix = prefix
