"""IDE live chat, qualification routing, and device-consent diagnostics.

The browser never sees the Discord secret. The class IDE proxies here.
Cookie values, passwords, and session tokens are not stored or forwarded.
"""

import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import discord
from aiohttp import web

import teachforth_plugins
import teachforth_portal
import teachforth_support

logger = logging.getLogger("teachforth.chat")
DATA = teachforth_portal.DATA
STORE = DATA / "qualifications.json"
COLOR = 0x3B6EF6
STAFF_ROLES = {"TeachForth Teacher", "TeachForth Chapter Lead", "TeachForth Admin", "TeachForth Session Lead"}
LEAD_ROLES = {"TeachForth Chapter Lead", "TeachForth Admin"}
HIDE_ROLES = {"TeachForth Teacher", "TeachForth Chapter Lead", "TeachForth Session Lead", "TeachForth Student"}
STAFF_WEBSITE = {"teacher", "lead_teacher", "chapter_lead", "admin"}
LEAD_WEBSITE = {"chapter_lead", "admin"}
TOPICS = (
    ("ide", "IDE", "The editor, files, or running code"),
    ("github", "GitHub", "GitHub, commits, or a repository"),
    ("class", "Class", "Joining class or the live session"),
    ("account", "Account", "Sign-in, roles, or the Discord link"),
    ("homework", "Homework", "An assignment or a lesson"),
    ("general", "Something else", "A question that does not fit"),
)
TOPIC_IDS = {item[0] for item in TOPICS}
CATEGORIES = {key: f"Help · {label}" for key, label, _blurb in TOPICS}
WIDGET_COMMANDS = (
    ("help", "student", "Commands you can run in this chat.", ""),
    ("reply", "teacher", "Send this to the student. They see your name.", "<message>"),
    ("areply", "teacher", "Send this without your name.", "<message>"),
    ("note", "teacher", "Staff note. The student does not see it.", "<message>"),
    ("close", "teacher", "Close this ticket.", "[message]"),
    ("claim", "teacher", "Take this ticket.", ""),
    ("diagnostic", "teacher", "Ask them to share browser and device details.", ""),
    ("projects", "teacher", "Projects for the account that consented.", ""),
    ("project view", "teacher", "Show a project in this chat.", "<id>"),
    ("project create", "teacher", "Make a project for the consented account.", "[blank|python|web] [title]"),
    ("reports", "teacher", "Reports for the consented account. Staff only.", ""),
    ("chapters", "teacher", "Chapters for the consented account.", ""),
    ("helpmenusend", "teacher", "Walk them through a fix. No type lists the walks.", "[type]"),
    ("queue", "teacher", "Open tickets you are qualified to see.", ""),
    ("qualification list", "teacher", "Qualifications on this desk.", "[user]"),
    ("qualification add", "chapter lead", "Give a staff member a qualification.", "<user> <topic>"),
    ("qualification remove", "chapter lead", "Take a qualification away.", "<user> <topic>"),
)
_lock = threading.Lock()
_hits = {}
_attached = set()


def topic_label(topic):
    for key, label, _blurb in TOPICS:
        if key == topic:
            return label
    return "Help"


def topic_blurb(topic):
    for key, _label, blurb in TOPICS:
        if key == topic:
            return blurb
    return ""


def now():
    return datetime.now(timezone.utc).isoformat()


def load():
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("users", {})
    data.setdefault("tickets", {})
    data.setdefault("messages", [])
    data.setdefault("snapshots", {})
    return data


def save(data):
    DATA.mkdir(parents=True, exist_ok=True)
    temp = STORE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(STORE)


def update(mutator):
    with _lock:
        data = load()
        mutator(data)
        save(data)
        return data


def clean_text(text, limit=1800):
    value = teachforth_portal.scrub(text)
    value = re.sub(r"(?i)\b(cookie|token|password|authorization)\s*[:=]\s*\S+", "[removed]", value)
    return value.strip()[:limit]


def snowflake(value):
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{17,20}", text) else ""


def sanitize_diagnostics(raw):
    if not isinstance(raw, dict):
        return None
    try:
        blob = json.dumps(raw).lower()
    except (TypeError, ValueError):
        return None
    if any(part in blob for part in ("document.cookie", "password", "sessionid", "github_pat_", "ghp_")):
        return None
    text_fields = {
        "browser": 40,
        "platform": 40,
        "language": 24,
        "timezone": 48,
        "screen": 20,
        "viewport": 20,
        "userAgent": 180,
    }
    out = {}
    for key, limit in text_fields.items():
        value = clean_text(raw.get(key), limit)
        if value:
            out[key] = value
    for key in ("cookiesEnabled", "online", "touch", "doNotTrack"):
        if key in raw:
            out[key] = bool(raw.get(key))
    for key in ("cores", "memoryGb"):
        try:
            number = int(raw.get(key))
        except (TypeError, ValueError):
            continue
        if 0 < number < 128:
            out[key] = number
    languages = raw.get("languages")
    if isinstance(languages, list):
        out["languages"] = [clean_text(item, 24) for item in languages[:4] if clean_text(item, 24)]
    return out or None


def format_diagnostics(info):
    info = info or {}
    yes = {True: "yes", False: "no"}
    lines = []
    if info.get("browser"):
        lines.append(f"Browser: {info['browser']}")
    if info.get("platform"):
        lines.append(f"Device: {info['platform']}")
    if info.get("language"):
        lines.append(f"Language: {info['language']}")
    if info.get("timezone"):
        lines.append(f"Timezone: {info['timezone']}")
    if info.get("screen"):
        lines.append(f"Screen: {info['screen']}")
    if info.get("viewport"):
        lines.append(f"Viewport: {info['viewport']}")
    if "cookiesEnabled" in info:
        lines.append(f"Cookies enabled: {yes[bool(info['cookiesEnabled'])]}")
    if "online" in info:
        lines.append(f"Online: {yes[bool(info['online'])]}")
    if "touch" in info:
        lines.append(f"Touch: {yes[bool(info['touch'])]}")
    if "doNotTrack" in info:
        lines.append(f"Do not track: {yes[bool(info['doNotTrack'])]}")
    if info.get("cores"):
        lines.append(f"CPU cores: {info['cores']}")
    if info.get("memoryGb"):
        lines.append(f"Device memory: {info['memoryGb']} GB")
    if info.get("userAgent"):
        lines.append(f"Agent: {info['userAgent']}")
    return "\n".join(lines) or "No device details."


def topic_for(channel_id):
    return str((load()["tickets"].get(str(channel_id)) or {}).get("topic") or "")


def qualifications_for(discord_id):
    rows = load()["users"].get(str(discord_id)) or []
    return [item for item in rows if item in TOPIC_IDS]


def set_qualification(discord_id, topic, present):
    discord_id = snowflake(discord_id)
    topic = str(topic or "").strip().lower()
    if not discord_id or topic not in TOPIC_IDS:
        return False

    def change(data):
        current = [item for item in data["users"].get(discord_id) or [] if item in TOPIC_IDS]
        if present and topic not in current:
            current.append(topic)
        if not present:
            current = [item for item in current if item != topic]
        if current:
            data["users"][discord_id] = current
        else:
            data["users"].pop(discord_id, None)

    update(change)
    return True


def list_all():
    return {str(key): list(value) for key, value in load()["users"].items()}


def remember_ticket(channel_id, recipient_id, topic, consent, diagnostics):
    channel_id = str(channel_id)
    recipient_id = str(recipient_id)

    def change(data):
        row = dict(data["tickets"].get(channel_id) or {})
        row.update({
            "topic": topic,
            "recipient": recipient_id,
            "consent": bool(consent),
            "pending": False,
            "diagnostics": diagnostics or {},
            "at": row.get("at") or now(),
        })
        data["tickets"][channel_id] = row
        if diagnostics:
            data["snapshots"][recipient_id] = {"at": now(), "diagnostics": diagnostics}

    update(change)


def mark_pending(channel_id, recipient_id, pending):
    def change(data):
        row = dict(data["tickets"].get(str(channel_id)) or {})
        row["recipient"] = str(recipient_id)
        row["pending"] = bool(pending)
        row["consent"] = True if pending else row.get("consent")
        data["tickets"][str(channel_id)] = row

    update(change)


def ticket_row(channel_id):
    return dict(load()["tickets"].get(str(channel_id)) or {})


def recent_snapshot(discord_id, minutes=30):
    row = (load()["snapshots"].get(str(discord_id)) or {})
    stamp = row.get("at") or ""
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if age.total_seconds() > minutes * 60:
        return None
    return sanitize_diagnostics(row.get("diagnostics"))


def log_message(entry):
    entry = dict(entry)
    entry.setdefault("id", secrets.token_hex(8))
    entry.setdefault("at", now())
    entry["text"] = clean_text(entry.get("text") or "", 2000)

    def change(data):
        messages = data["messages"]
        discord_id = str(entry.get("discordId") or "")
        if discord_id and any(str(item.get("discordId") or "") == discord_id for item in messages[-240:]):
            return
        messages.append(entry)
        data["messages"] = messages[-800:]

    update(change)
    return entry


def messages_for(channel_id, staff):
    rows = []
    for item in load()["messages"]:
        if str(item.get("channelId") or "") != str(channel_id):
            continue
        if not staff and item.get("side") == "note":
            continue
        rows.append(public_message(item))
    return rows[-60:]


def messages_for_person(recipient_id, staff):
    rows = []
    for item in load()["messages"]:
        if str(item.get("recipientId") or "") != str(recipient_id):
            continue
        if not staff and item.get("side") == "note":
            continue
        rows.append(public_message(item))
    return rows[-60:]


def public_message(item):
    return {
        "id": item.get("id"),
        "channelId": str(item.get("channelId") or ""),
        "author": item.get("author") or "TeachForth",
        "side": item.get("side") or "staff",
        "text": item.get("text") or "",
        "cards": item.get("cards") or [],
        "at": item.get("at") or "",
    }


def card(title, body, fields=None, buttons=None, tone="info"):
    return {
        "title": clean_text(title, 120) or "TeachForth",
        "body": clean_text(body, 1800),
        "fields": [
            {"name": clean_text(field.get("name"), 40), "value": clean_text(field.get("value"), 500)}
            for field in (fields or [])[:8]
            if field.get("name") and field.get("value")
        ],
        "buttons": [
            {"id": clean_text(button.get("id"), 40), "label": clean_text(button.get("label"), 40)}
            for button in (buttons or [])[:6]
            if button.get("id") and button.get("label")
        ],
        "tone": tone if tone in {"info", "good", "warn"} else "info",
    }


def limited(key, count, window):
    now_at = time.time()
    hits = [stamp for stamp in _hits.get(key, []) if now_at - stamp < window]
    if len(hits) >= count:
        _hits[key] = hits
        return True
    hits.append(now_at)
    _hits[key] = hits
    return False


def same_secret(request):
    given = request.headers.get("x-teachforth-discord", "")
    expected = teachforth_portal.class_secret()
    if not expected or not given:
        return False
    left = hashlib.sha256(expected.encode()).digest()
    right = hashlib.sha256(given.encode()).digest()
    return hmac.compare_digest(left, right)


def guild_of(bot):
    return getattr(bot, "modmail_guild", None)


async def member_of(bot, discord_id):
    guild = guild_of(bot)
    if guild is None or not snowflake(discord_id):
        return None
    member = guild.get_member(int(discord_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(discord_id))
    except (discord.HTTPException, discord.NotFound):
        return None


def role_names(member):
    if member is None:
        return set()
    return {role.name for role in getattr(member, "roles", [])}


async def website_role(discord_id):
    status, data = await teachforth_portal.class_call("GET", f"/api/discord/profile?discordId={discord_id}")
    if status != 200:
        return ""
    return str(data.get("role") or "")


async def staff_rank(bot, discord_id):
    member = await member_of(bot, discord_id)
    names = role_names(member)
    site = await website_role(discord_id)
    owner = int(discord_id) in set(getattr(bot, "bot_owner_ids", []) or [])
    if owner or "TeachForth Admin" in names or site == "admin":
        return "admin"
    if "TeachForth Chapter Lead" in names or site == "chapter_lead":
        return "chapter"
    if names & STAFF_ROLES or site in STAFF_WEBSITE:
        return "teacher"
    return ""


async def can_see(bot, discord_id, topic):
    if topic not in TOPIC_IDS:
        return True
    rank = await staff_rank(bot, discord_id)
    if rank == "admin":
        return True
    return topic in qualifications_for(discord_id)


def allow_overwrite():
    return discord.PermissionOverwrite(
        view_channel=True,
        read_messages=True,
        send_messages=True,
        read_message_history=True,
        embed_links=True,
        attach_files=True,
    )


def deny_overwrite():
    return discord.PermissionOverwrite(view_channel=False, read_messages=False, send_messages=False)


async def topic_category(guild, topic):
    name = CATEGORIES.get(topic)
    if not name or guild is None:
        return None
    found = discord.utils.get(guild.categories, name=name)
    if found is not None:
        return found
    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        return None
    overwrites = {
        guild.default_role: deny_overwrite(),
        me: allow_overwrite(),
    }
    for role in guild.roles:
        if role.name == "TeachForth Admin":
            overwrites[role] = allow_overwrite()
        elif role.name in HIDE_ROLES:
            overwrites[role] = deny_overwrite()
    try:
        return await guild.create_category(name, overwrites=overwrites, reason="TeachForth qualification")
    except discord.HTTPException:
        logger.info("Could not create the %s category", name)
        return None


def qualified_members(guild, topic):
    if guild is None:
        return []
    wanted = {discord_id for discord_id, topics in list_all().items() if topic in topics}
    found = []
    for discord_id in wanted:
        member = guild.get_member(int(discord_id))
        if member is not None:
            found.append(member)
    return found


async def route_channel(bot, channel, topic, recipient):
    if channel is None or topic not in TOPIC_IDS or recipient is None:
        return False
    guild = channel.guild
    me = guild.me if guild else None
    if me is None or not me.guild_permissions.manage_channels:
        return False
    overwrites = {
        guild.default_role: deny_overwrite(),
        me: allow_overwrite(),
    }
    for role in guild.roles:
        if role.name == "TeachForth Admin":
            overwrites[role] = allow_overwrite()
        elif role.name in HIDE_ROLES:
            overwrites[role] = deny_overwrite()
    for member in qualified_members(guild, topic):
        overwrites[member] = allow_overwrite()
    for owner_id in set(getattr(bot, "bot_owner_ids", []) or []):
        member = guild.get_member(int(owner_id))
        if member is not None:
            overwrites[member] = allow_overwrite()
    slug = re.sub(r"[^a-z0-9]+", "", str(getattr(recipient, "name", "student")).lower())[:18] or "student"
    kwargs = {
        "name": f"{topic}-{slug}"[:90],
        "overwrites": overwrites,
        "topic": f"User ID: {recipient.id}",
        "reason": "TeachForth qualification routing",
    }
    category = await topic_category(guild, topic)
    if category is not None:
        kwargs["category"] = category
    try:
        await channel.edit(**kwargs)
    except discord.HTTPException:
        logger.info("Could not route ticket %s", channel.id)
        return False
    return True


async def refresh_topic(bot, topic):
    for thread in list(getattr(bot, "threads", [])):
        channel = getattr(thread, "channel", None)
        if channel is None or topic_for(channel.id) != topic:
            continue
        await route_channel(bot, channel, topic, getattr(thread, "recipient", None))


async def find_thread(bot, user=None, channel_id=""):
    if channel_id and snowflake(channel_id):
        for thread in list(bot.threads):
            channel = getattr(thread, "channel", None)
            if channel is not None and channel.id == int(channel_id):
                return thread
        return None
    if user is None:
        return None
    try:
        thread = await bot.threads.find(recipient=user)
    except Exception:
        logger.info("Could not find a thread for %s", getattr(user, "id", ""))
        return None
    channel = getattr(thread, "channel", None)
    if thread is None or channel is None:
        return None
    return thread


async def open_thread(bot, user):
    existing = await find_thread(bot, user=user)
    if existing is not None:
        return existing, False
    thread = await bot.threads.find_or_create(user)
    await thread.wait_until_ready()
    return thread, True


def footer(kind):
    return f"tf-widget · {kind}"


async def send_embed(channel, embed):
    embed.set_footer(text=footer("desk"))
    return await channel.send(embed=embed)


async def post_opening(channel, name, topic, message, diagnostics, consent):
    embed = discord.Embed(title="New IDE chat", description=clean_text(message, 1800) or "Opened from the IDE.", color=COLOR)
    embed.add_field(name="Student", value=clean_text(name, 80) or "Student", inline=True)
    embed.add_field(name="Topic", value=topic_label(topic), inline=True)
    if consent and diagnostics:
        embed.add_field(name="Device details", value=format_diagnostics(diagnostics)[:1000], inline=False)
        embed.set_footer(text=footer("They allowed device details. Cookie values were not sent."))
    else:
        embed.set_footer(text=footer("They did not share device details."))
    return await channel.send(embed=embed)


def commands_for(rank):
    order = {"student": 0, "teacher": 1, "chapter": 2, "admin": 3}
    have = order.get(rank or "student", 0)
    rows = []
    for name, need, help_text, usage in WIDGET_COMMANDS:
        required = 2 if need == "chapter lead" else 1 if need == "teacher" else 0
        if have >= required:
            rows.append({"name": name, "usage": usage, "help": help_text, "level": need})
    return rows


def command_cards():
    lines = [f"`.{name}` {usage} — {help_text}" for name, _need, help_text, usage in WIDGET_COMMANDS if _need == "student"]
    staff = [f"`.{name}` {usage} — {help_text}" for name, need, help_text, usage in WIDGET_COMMANDS if need != "student"]
    return [
        card("In this chat", "\n".join(lines), tone="info"),
        card("Teachers", "\n".join(staff[:8]), tone="info"),
        card("Routing", "\n".join(staff[8:]) or "Qualification commands are for a chapter lead.", tone="info"),
    ]


async def inbox(bot, viewer_id):
    groups = {key: [] for key, _label, _blurb in TOPICS}
    other = []
    for thread in list(bot.threads):
        channel = getattr(thread, "channel", None)
        recipient = getattr(thread, "recipient", None)
        if channel is None or recipient is None or not getattr(thread, "ready", False):
            continue
        topic = topic_for(channel.id)
        if topic and not await can_see(bot, viewer_id, topic):
            continue
        last = ""
        for item in reversed(load()["messages"]):
            if str(item.get("channelId") or "") == str(channel.id) and item.get("text"):
                last = item["text"][:120]
                break
        row = {
            "channelId": str(channel.id),
            "name": getattr(recipient, "name", "Student"),
            "topic": topic or "open",
            "label": topic_label(topic) if topic else "Open",
            "preview": last,
            "claimed": ticket_row(channel.id).get("claimed") or "",
        }
        if topic in groups:
            groups[topic].append(row)
        else:
            other.append(row)
    ordered = []
    for key, label, _blurb in TOPICS:
        if groups[key]:
            ordered.append({"id": key, "label": label, "tickets": groups[key]})
    if other:
        ordered.append({"id": "open", "label": "Not routed", "tickets": other})
    return ordered


async def session_payload(bot, user, rank, channel_id=""):
    thread = await visible(bot, user.id, snowflake(channel_id), rank) if snowflake(channel_id) else await find_thread(bot, user=user)
    channel = getattr(thread, "channel", None)
    channel_id = str(channel.id) if channel is not None else ""
    row = ticket_row(channel_id) if channel_id else {}
    staff = rank in {"teacher", "chapter", "admin"}
    messages = messages_for(channel_id, staff) if channel_id else messages_for_person(user.id, False)
    payload = {
        "ok": True,
        "name": getattr(user, "display_name", None) or getattr(user, "name", "Student"),
        "staff": staff,
        "rank": rank or "student",
        "topics": [{"id": key, "label": label, "blurb": blurb} for key, label, blurb in TOPICS],
        "qualifications": qualifications_for(user.id) if staff else [],
        "commands": commands_for(rank or "student"),
        "conversation": {
            "open": channel is not None,
            "channelId": channel_id,
            "topic": row.get("topic") or "",
            "label": topic_label(row.get("topic") or ""),
            "pendingDiagnostic": bool(row.get("pending")),
            "messages": messages,
        },
    }
    if staff:
        payload["inbox"] = await inbox(bot, user.id)
    return payload


async def visible(bot, actor_id, channel_id, rank):
    thread = await find_thread(bot, channel_id=channel_id)
    if thread is None or getattr(thread, "recipient", None) is None:
        return None
    recipient_id = str(thread.recipient.id)
    if recipient_id == str(actor_id):
        return thread
    if rank not in {"teacher", "chapter", "admin"}:
        return None
    topic = topic_for(thread.channel.id)
    if topic and not await can_see(bot, actor_id, topic):
        return None
    return thread


async def run_support(bot, thread, author, name, rest):
    cog = bot.get_cog("Diagnostic")
    row = teachforth_support.consent(thread.channel.id)
    if cog is None:
        return [card("Unavailable", "Diagnostics are not loaded.", tone="warn")]
    if not row or str(row.get("recipient")) != str(thread.recipient.id):
        return [card("Need consent", "Ask them for the support code from their profile, then run this again.", tone="warn")]

    class Ctx:
        channel = thread.channel
        bot = None

        async def send(self, content=None, embed=None, embeds=None, **_kwargs):
            return None

    Ctx.bot = bot
    ctx = Ctx()
    ctx.author = author
    if name == "projects":
        status, data = await cog._read(row, thread.channel, "/api/discord/support/projects")
        if status != 200:
            return [card("Projects", data.get("error") or "Class did not answer.", tone="warn")]
        lines = [
            f"{item.get('id')} · {item.get('title')} · {item.get('language')}"
            for item in data.get("projects") or []
        ]
        return [card("Projects", "\n".join(lines) or "No projects on this account.")]
    if name == "project":
        parts = rest.split(None, 2)
        action = parts[0].lower() if parts else ""
        if action == "view" and len(parts) > 1 and parts[1].isdigit():
            status, data = await cog._read(row, thread.channel, "/api/discord/support/project", {"id": int(parts[1])})
            if status != 200:
                return [card("Project", data.get("error") or "That project did not open.", tone="warn")]
            project = data.get("project") or {}
            files = data.get("files") or []
            fields = [
                {"name": item.get("path") or "file", "value": clean_text(item.get("content") or "", 500) or "Empty"}
                for item in files[:4]
            ]
            await thread.channel.send(embed=cog._embed(project.get("title") or "Project", f"ID {project.get('id')}"))
            return [card(project.get("title") or "Project", project.get("githubUrl") or "Opened in the ticket.", fields)]
        if action == "create":
            spec = rest.split(None, 1)[1] if len(rest.split(None, 1)) > 1 else ""
            template, title = cog._parse_create(spec)
            status, data = await teachforth_portal.class_call("POST", "/api/discord/support/project", {
                "grant": row["grant"],
                "channelId": str(thread.channel.id),
                "teacherDiscordId": str(author.id),
                "title": title,
                "template": template,
            })
            if status not in {200, 201}:
                return [card("Project", data.get("error") or "That project was not created.", tone="warn")]
            project = data.get("project") or {}
            return [card("Project created", f"{project.get('id')} · {project.get('title') or title}")]
        return [card("Project", "Use .project view ID or .project create blank.")]
    if name in {"reports", "chapters"}:
        status, data = await cog._read(row, thread.channel, f"/api/discord/support/{name}")
        if status != 200:
            return [card(name.title(), data.get("error") or "Class did not answer.", tone="warn")]
        if name == "chapters":
            lines = [f"{item.get('name')} · {item.get('place') or 'no place'}" for item in data.get("chapters") or []]
            return [card("Chapters", "\n".join(lines) or "No chapter on this account.")]
        rows = data.get("reports") or []
        if not rows:
            return [card("Reports", "None yet.")]
        return [
            card(f"{item.get('author') or 'Report'} · {item.get('block') or ''}", clean_text(item.get("body") or "No note.", 800))
            for item in rows[:4]
        ]
    return [card("Unknown", "That command is not in this chat.")]


async def run_command(bot, thread, author, rank, text):
    raw = text.strip()
    if raw[:1] in "./":
        raw = raw[1:]
    parts = raw.split(None, 1)
    if not parts:
        return [card("Commands", "Type .help")]
    name = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    if name == "project" and rest:
        name = "project"
    needed = "student"
    for command, level, _help, _usage in WIDGET_COMMANDS:
        if command == name or (name == "project" and command.startswith("project")) or (name == "qualification" and command.startswith("qualification")):
            needed = level
            break
    rank_order = {"student": 0, "teacher": 1, "chapter": 2, "admin": 3, "": 0}
    need_order = 2 if needed == "chapter lead" else 1 if needed == "teacher" else 0
    if rank_order.get(rank, 0) < need_order:
        return [card("Not allowed", "That is for a teacher, chapter lead, or admin.", tone="warn")]
    if name == "help":
        lines = [f".{item['name']} {item['usage']} — {item['help']}".strip() for item in commands_for(rank or "student")]
        return [card("Commands", "\n".join(lines))]
    if name == "qualification":
        return await qualification_command(bot, author, rank, rest)
    if name == "queue":
        groups = await inbox(bot, author.id)
        if not groups:
            return [card("Queue", "No open tickets you can see.")]
        return [card(group["label"], "\n".join(f"{item['name']} · {item['preview'] or 'No preview'}" for item in group["tickets"][:8]) or "None") for group in groups]
    if thread is None or thread.channel is None:
        return [card("No ticket", "Open a conversation first.", tone="warn")]
    if name in {"reply", "areply"}:
        if not rest:
            return [card("Reply", "Write the message after .reply")]
        title = "TeachForth" if name == "areply" else (getattr(author, "display_name", None) or author.name)
        embed = discord.Embed(description=clean_text(rest), color=0x7A1FA3)
        embed.set_author(name=title)
        embed.set_footer(text=footer("reply"))
        await thread.channel.send(embed=embed)
        try:
            await thread.recipient.send(embed=discord.Embed(description=clean_text(rest), color=0x7A1FA3).set_author(name=title))
        except discord.HTTPException:
            return [card("Not delivered", "I could not DM them. The reply is in the ticket.", tone="warn")]
        log_message({
            "discordId": "",
            "channelId": str(thread.channel.id),
            "recipientId": str(thread.recipient.id),
            "author": title,
            "side": "staff",
            "text": rest,
        })
        return [card("Sent", rest)]
    if name == "note":
        if not rest:
            return [card("Note", "Write the note after .note")]
        embed = discord.Embed(description=clean_text(rest), color=0x5865F2)
        embed.set_author(name=f"Note ({author.name})")
        embed.set_footer(text=footer("Internal Note"))
        await thread.channel.send(embed=embed)
        log_message({
            "channelId": str(thread.channel.id),
            "recipientId": str(thread.recipient.id),
            "author": author.name,
            "side": "note",
            "text": rest,
        })
        return [card("Note saved", "The student does not see this.", tone="info")]
    if name == "close":
        await thread.close(closer=author, message=clean_text(rest, 300) or "Closed from the IDE chat.")
        return [card("Closed", "This ticket is closing.", tone="good")]
    if name == "claim":
        def change(data):
            row = dict(data["tickets"].get(str(thread.channel.id)) or {})
            row["claimed"] = str(author.id)
            data["tickets"][str(thread.channel.id)] = row
        update(change)
        await send_embed(thread.channel, discord.Embed(description=f"{author.name} claimed this ticket.", color=COLOR))
        return [card("Claimed", f"{author.display_name} has this ticket.", tone="good")]
    if name == "diagnostic":
        await request_diagnostic(bot, thread, author)
        return [card("Asked", "They can allow device details in Discord or in the IDE chat.")]
    if name == "helpmenusend":
        return await start_walk(bot, thread, rest)
    if name in {"projects", "project", "reports", "chapters"}:
        return await run_support(bot, thread, author, name, rest)
    return [card("Discord only", f"`.{name}` runs in the Discord ticket, not in this chat.", tone="warn")]


async def qualification_command(bot, author, rank, rest):
    parts = rest.split()
    action = parts[0].lower() if parts else "list"
    if action == "list":
        target = parts[1] if len(parts) > 1 else ""
        target_id = snowflake(re.sub(r"\D", "", target)) if target else str(author.id)
        if target and rank not in {"chapter", "admin"}:
            return [card("Not allowed", "Listing someone else is for a chapter lead or admin.", tone="warn")]
        topics = qualifications_for(target_id)
        if target_id == str(author.id) and not target:
            shown = ", ".join(topic_label(item) for item in topics) or "None yet."
            return [card("Your qualifications", shown)]
        lines = []
        source = {target_id: topics} if target else list_all()
        for discord_id, items in list(source.items())[:20]:
            member = await member_of(bot, discord_id)
            label = getattr(member, "display_name", None) or discord_id
            lines.append(f"{label}: {', '.join(topic_label(item) for item in items) or 'none'}")
        return [card("Qualifications", "\n".join(lines) or "Nobody has one yet.")]
    if action not in {"add", "remove"} or len(parts) < 3:
        return [card("Qualification", ".qualification add @user ide\n.qualification remove @user ide\n.qualification list")]
    if rank not in {"chapter", "admin"}:
        return [card("Not allowed", "Adding a qualification is for a chapter lead or admin.", tone="warn")]
    target_id = snowflake(re.sub(r"\D", "", parts[1]))
    topic = parts[2].lower()
    if not target_id or topic not in TOPIC_IDS:
        return [card("Qualification", "Use a person and one of: " + ", ".join(sorted(TOPIC_IDS)), tone="warn")]
    set_qualification(target_id, topic, action == "add")
    await refresh_topic(bot, topic)
    verb = "added" if action == "add" else "removed"
    return [card("Qualification", f"{topic_label(topic)} {verb}. Matching tickets are visible only to qualified staff and admins.", tone="good")]


async def start_walk(bot, thread, kind):
    cog = bot.get_cog("Diagnostic")
    if cog is None:
        return [card("Walks", "Automated help is not loaded.", tone="warn")]
    picked = cog._kind(kind)
    if not picked:
        lines = [f".helpmenusend {item['id']} — {item['label']}" for item in teachforth_plugins.PLUGINS]
        return [card("Automated helpers", "\n".join(lines))]
    moved, previous = await cog._move(thread.channel, "Automated")
    state = teachforth_plugins.begin(picked, "", await cog._fill(thread))
    state["automated"] = True
    state["channel"] = str(thread.channel.id)
    state["previous"] = previous
    teachforth_support.auto_put(thread.recipient.id, state)
    await cog._show(thread, state)
    spec = teachforth_plugins.prompt(state)
    where = "Moved to Automated." if moved else "The walk started."
    return [card(spec.get("title") or "Walk", (spec.get("body") or "") + "\n\n" + where, buttons=walk_buttons(spec))]


def walk_buttons(spec):
    buttons = []
    select = (spec or {}).get("select") or {}
    for item in select.get("options") or []:
        buttons.append({"id": f"step:{item.get('id')}", "label": item.get("label") or "Choose"})
    for item in (spec or {}).get("buttons") or []:
        buttons.append({"id": str(item.get("id") or "").replace("tfa:", "").replace("tfp:", ""), "label": item.get("label") or "Next"})
    return buttons


async def walk_click(bot, thread, action):
    cog = bot.get_cog("Diagnostic")
    if cog is None or thread is None:
        return [card("Walk", "That walk is not running.", tone="warn")]
    state = teachforth_support.auto_get(thread.recipient.id)
    if action in {"fixed", "tfa:fixed"}:
        await cog._finish(thread, state, "They said that fixed it.")
        return [card("Fixed", "A teacher has the steps they tried.", tone="good")]
    if action in {"restart", "tfa:restart"}:
        teachforth_support.auto_clear(thread.recipient.id)
        return [card("Stopped", "The walk stopped.")]
    if action in {"still", "tfa:still"}:
        kind, _payload = teachforth_plugins.apply_still(state)
    elif action.startswith("step:"):
        kind, _payload = teachforth_plugins.apply_choice(state, action.split(":", 1)[1])
    else:
        return [card("Walk", "Use the buttons on the latest step.")]
    await cog._after(thread, state, kind)
    spec = teachforth_plugins.prompt(teachforth_support.auto_get(thread.recipient.id))
    if not spec:
        return [card("Walk", "The walk moved on.")]
    return [card(spec.get("title") or "Next", spec.get("body") or "", buttons=walk_buttons(spec))]


async def request_diagnostic(bot, thread, author):
    recipient = thread.recipient
    teachforth_support.note_teacher(thread.channel.id, author.id, recipient.id)
    mark_pending(thread.channel.id, recipient.id, True)
    embed = discord.Embed(
        title="Share device details?",
        description=(
            "Your teacher asked to see the browser and device for this ticket.\n\n"
            "Allowing sends the browser name, device, language, timezone, screen size, "
            "and whether cookies are enabled.\n\n"
            "Cookie values, passwords, and sign-in tokens are not sent.\n\n"
            "Allow here, or allow it in the TeachForth IDE chat. "
            "The details are added to this ticket."
        ),
        color=COLOR,
    )
    embed.set_footer(text="TeachForth Help")
    view = bot.get_cog("Diagnostic")
    discord_view = view.consent_view() if view is not None and hasattr(view, "consent_view") else None
    try:
        await recipient.send(embed=embed, view=discord_view)
    except discord.HTTPException:
        await thread.channel.send(embed=discord.Embed(description="I could not DM them. They can allow it in the IDE chat.", color=COLOR))
    await send_embed(thread.channel, discord.Embed(description=f"{author.name} asked for device details.", color=COLOR))


async def grant_from_discord(bot, user, allowed, locale=""):
    thread = await find_thread(bot, user=user)
    if thread is None or thread.channel is None:
        return "Open a ticket first, then allow device details."
    if not allowed:
        def change(data):
            row = dict(data["tickets"].get(str(thread.channel.id)) or {})
            row["pending"] = False
            row["consent"] = False
            data["tickets"][str(thread.channel.id)] = row
        update(change)
        await send_embed(thread.channel, discord.Embed(title="Device details", description="They did not share device details.", color=COLOR))
        return "You did not share device details."
    snapshot = recent_snapshot(user.id)
    mark_pending(thread.channel.id, user.id, snapshot is None)
    if snapshot:
        await attach_diagnostics(bot, thread, snapshot, "Discord")
        return "Shared. Your teacher can see the device details on this ticket."
    lines = "They allowed device details from Discord."
    if locale:
        lines += f"\nDiscord locale: {clean_text(locale, 24)}"
    lines += "\nBrowser details attach from the IDE chat. Cookie values are not sent."
    await send_embed(thread.channel, discord.Embed(title="Device details", description=lines, color=COLOR))
    return "Allowed. Open the IDE chat so the browser details can attach. Cookie values are not sent."


async def attach_diagnostics(bot, thread, diagnostics, source):
    info = sanitize_diagnostics(diagnostics)
    if not info:
        return False
    remember_ticket(thread.channel.id, thread.recipient.id, topic_for(thread.channel.id) or "general", True, info)
    embed = discord.Embed(title="Device details", description=format_diagnostics(info)[:4000], color=COLOR)
    embed.set_footer(text=footer(f"Allowed from {source}. Cookie values were not sent."))
    await thread.channel.send(embed=embed)
    log_message({
        "channelId": str(thread.channel.id),
        "recipientId": str(thread.recipient.id),
        "author": "TeachForth",
        "side": "card",
        "text": "Device details were shared with the teacher.",
        "cards": [card("Device details", format_diagnostics(info), tone="good")],
    })
    return True


async def accept_json(request):
    if not same_secret(request):
        return None, web.json_response({"error": "Sign in first"}, status=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return body, None


async def actor_user(bot, body):
    discord_id = snowflake(body.get("discordId"))
    if not discord_id:
        return None, web.json_response({"error": "Link Discord first."}, status=400)
    try:
        user = await bot.get_or_fetch_user(int(discord_id))
    except (discord.HTTPException, discord.NotFound):
        user = None
    if user is None:
        return None, web.json_response({"error": "That Discord account is not available."}, status=404)
    return user, None


async def widget_session(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    if limited(f"read:{user.id}", 120, 600):
        return web.json_response({"error": "Slow down a moment."}, status=429)
    rank = await staff_rank(bot, user.id)
    return web.json_response(await session_payload(bot, user, rank, body.get("channelId")))


async def open_from(bot, user, body):
    topic = str(body.get("topic") or "general").lower()
    if topic not in TOPIC_IDS:
        topic = "general"
    message = clean_text(body.get("message") or body.get("text") or "")
    if not message:
        return {"error": "Write a message first.", "status": 400}
    consent = bool(body.get("consent"))
    diagnostics = sanitize_diagnostics(body.get("diagnostics")) if consent else None
    try:
        thread, _created = await open_thread(bot, user)
    except (discord.HTTPException, RuntimeError):
        return None
    if thread is None or thread.channel is None:
        return None
    await route_channel(bot, thread.channel, topic, user)
    remember_ticket(thread.channel.id, user.id, topic, consent, diagnostics)
    sent = await post_opening(thread.channel, body.get("name") or user.name, topic, message, diagnostics, consent)
    log_message({
        "discordId": str(sent.id),
        "channelId": str(thread.channel.id),
        "recipientId": str(user.id),
        "author": user.name,
        "side": "student",
        "text": message,
    })
    if diagnostics:
        log_message({
            "channelId": str(thread.channel.id),
            "recipientId": str(user.id),
            "author": "TeachForth",
            "side": "note",
            "text": "Device details",
            "cards": [card("Device details", format_diagnostics(diagnostics), tone="good")],
        })
        log_message({
            "channelId": str(thread.channel.id),
            "recipientId": str(user.id),
            "author": "TeachForth",
            "side": "card",
            "text": "You shared device details with your teacher. Cookie values were not sent.",
        })
    rank = await staff_rank(bot, user.id)
    return await session_payload(bot, user, rank)


async def widget_open(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    if limited(f"send:{user.id}", 20, 600):
        return web.json_response({"error": "Slow down a moment."}, status=429)
    try:
        payload = await open_from(bot, user, body)
    except (discord.HTTPException, RuntimeError):
        return web.json_response({"error": "I could not open a ticket. Message the TeachForth bot in Discord."}, status=502)
    if payload is None:
        return web.json_response({"error": "The helpdesk is still starting."}, status=503)
    if payload.get("error") and "conversation" not in payload:
        return web.json_response({"error": payload["error"]}, status=payload.get("status") or 400)
    return web.json_response(payload)


async def widget_send(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    if limited(f"send:{user.id}", 40, 600):
        return web.json_response({"error": "Slow down a moment."}, status=429)
    rank = await staff_rank(bot, user.id)
    text = clean_text(body.get("text") or body.get("message") or "", 2000)
    if not text:
        return web.json_response({"error": "Write a message first."}, status=400)
    channel_id = snowflake(body.get("channelId"))
    thread = await visible(bot, user.id, channel_id, rank) if channel_id else await find_thread(bot, user=user)
    if text[:1] in "./":
        cards = await run_command(bot, thread, user, rank, text)
        if thread is not None and thread.channel is not None:
            log_message({
                "channelId": str(thread.channel.id),
                "recipientId": str(thread.recipient.id),
                "author": "TeachForth",
                "side": "card" if rank else "card",
                "text": cards[0]["title"] if cards else "Command",
                "cards": cards,
            })
        return web.json_response({"ok": True, "cards": cards, "conversation": (await session_payload(bot, user, rank))["conversation"]})
    if thread is None or thread.channel is None:
        payload = await open_from(bot, user, body)
        if payload is None:
            return web.json_response({"error": "I could not open a ticket. Message the TeachForth bot in Discord."}, status=502)
        if payload.get("error") and "conversation" not in payload:
            return web.json_response({"error": payload["error"]}, status=payload.get("status") or 400)
        return web.json_response(payload)
    recipient_id = str(thread.recipient.id)
    if recipient_id == str(user.id):
        state = teachforth_support.auto_get(user.id)
        if state.get("automated") and state.get("awaiting") == "text":
            kind, _payload = teachforth_plugins.apply_text(state, text)
            cog = bot.get_cog("Diagnostic")
            cards = [card("Sent", "A teacher has that answer.")]
            if cog is not None:
                await cog._after(thread, state, kind)
                spec = teachforth_plugins.prompt(state)
                if spec:
                    cards = [card(spec.get("title") or "Next", spec.get("body") or "", buttons=walk_buttons(spec))]
            return web.json_response({"ok": True, "cards": cards, "conversation": (await session_payload(bot, user, rank))["conversation"]})
        embed = discord.Embed(description=text, color=0xC77DFF)
        embed.set_author(name=f"{user.name} · IDE chat")
        embed.set_footer(text=footer("student"))
        sent = await thread.channel.send(embed=embed)
        log_message({
            "discordId": str(sent.id),
            "channelId": str(thread.channel.id),
            "recipientId": recipient_id,
            "author": user.name,
            "side": "student",
            "text": text,
        })
    else:
        embed = discord.Embed(description=text, color=0x7A1FA3)
        embed.set_author(name=getattr(user, "display_name", None) or user.name)
        embed.set_footer(text=footer("reply"))
        await thread.channel.send(embed=embed)
        try:
            await thread.recipient.send(embed=discord.Embed(description=text, color=0x7A1FA3).set_author(name=embed.author.name))
        except discord.HTTPException:
            pass
        log_message({
            "channelId": str(thread.channel.id),
            "recipientId": recipient_id,
            "author": embed.author.name,
            "side": "staff",
            "text": text,
        })
    return web.json_response(await session_payload(bot, user, rank))


async def widget_diagnostics(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    thread = await find_thread(bot, user=user)
    if thread is None or thread.channel is None:
        return web.json_response({"error": "Open a ticket first."}, status=404)
    if not body.get("consent"):
        await grant_from_discord(bot, user, False)
        return web.json_response({"ok": True})
    info = sanitize_diagnostics(body.get("diagnostics"))
    if not info:
        return web.json_response({"error": "Those details were not usable."}, status=400)
    await attach_diagnostics(bot, thread, info, "the IDE")
    rank = await staff_rank(bot, user.id)
    return web.json_response(await session_payload(bot, user, rank))


async def widget_walk(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    thread = await find_thread(bot, user=user)
    cards = await walk_click(bot, thread, str(body.get("action") or ""))
    if thread is not None and thread.channel is not None:
        log_message({
            "channelId": str(thread.channel.id),
            "recipientId": str(thread.recipient.id),
            "author": "TeachForth",
            "side": "card",
            "text": cards[0]["title"] if cards else "Walk",
            "cards": cards,
        })
    return web.json_response({"ok": True, "cards": cards})


async def widget_qualify(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    rank = await staff_rank(bot, user.id)
    cards = await qualification_command(
        bot,
        user,
        rank,
        " ".join([
            str(body.get("action") or "list"),
            str(body.get("targetId") or ""),
            str(body.get("topic") or ""),
        ]).strip(),
    )
    return web.json_response({"ok": True, "cards": cards, "qualifications": qualifications_for(user.id)})


async def widget_thread(request):
    body, error = await accept_json(request)
    if error:
        return error
    bot = request.app["bot"]
    user, error = await actor_user(bot, body)
    if error:
        return error
    rank = await staff_rank(bot, user.id)
    thread = await visible(bot, user.id, snowflake(body.get("channelId")), rank)
    if thread is None or thread.channel is None:
        return web.json_response({"error": "That ticket is not open."}, status=404)
    topic = topic_for(thread.channel.id)
    return web.json_response({
        "ok": True,
        "conversation": {
            "open": True,
            "channelId": str(thread.channel.id),
            "topic": topic,
            "label": topic_label(topic),
            "pendingDiagnostic": bool(ticket_row(thread.channel.id).get("pending")),
            "messages": messages_for(thread.channel.id, rank in {"teacher", "chapter", "admin"}),
        },
    })


def add_routes(app):
    app.router.add_post("/widget/session", widget_session)
    app.router.add_post("/widget/open", widget_open)
    app.router.add_post("/widget/send", widget_send)
    app.router.add_post("/widget/thread", widget_thread)
    app.router.add_post("/widget/diagnostics", widget_diagnostics)
    app.router.add_post("/widget/walk", widget_walk)
    app.router.add_post("/widget/qualify", widget_qualify)


def attach(bot):
    if id(bot) in _attached:
        return
    _attached.add(id(bot))

    async def on_discord_message(message):
        await mirror(bot, message)

    bot.add_listener(on_discord_message, "on_message")


async def mirror(bot, message):
    channel = getattr(message, "channel", None)
    if not isinstance(channel, discord.TextChannel):
        return
    if message.embeds:
        footer_text = message.embeds[0].footer.text if message.embeds[0].footer else ""
        if footer_text and "tf-widget" in footer_text:
            return
    try:
        thread = await bot.threads.find(channel=channel)
    except Exception:
        return
    if thread is None or getattr(thread, "recipient", None) is None:
        return
    entry = entry_from_message(message, thread)
    if entry:
        log_message(entry)


def entry_from_message(message, thread):
    recipient = thread.recipient
    channel_id = str(message.channel.id)
    recipient_id = str(recipient.id)
    if message.embeds:
        embed = message.embeds[0]
        footer_text = (embed.footer.text or "") if embed.footer else ""
        if "tf-widget" in footer_text:
            return None
        text = embed.description or embed.title or ""
        if not text and embed.fields:
            text = "\n".join(f"{field.name}: {field.value}" for field in embed.fields[:6])
        if not text:
            return None
        internal = "note" in footer_text.lower()
        color = embed.color.value if embed.color else 0
        side = "note" if internal else "student" if color in {0xC77DFF, 0xF1C40F} else "staff"
        author = getattr(recipient, "name", "Student") if side == "student" else (
            embed.author.name if embed.author else message.author.display_name
        )
        return {
            "discordId": str(message.id),
            "channelId": channel_id,
            "recipientId": recipient_id,
            "author": author,
            "side": side,
            "text": text,
        }
    text = message.content or ""
    if not text or text.startswith("."):
        return None
    side = "student" if message.author.id == recipient.id else "staff"
    return {
        "discordId": str(message.id),
        "channelId": channel_id,
        "recipientId": recipient_id,
        "author": message.author.display_name,
        "side": side,
        "text": text,
    }
