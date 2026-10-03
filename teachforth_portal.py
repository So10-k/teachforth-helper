"""TeachForth helpdesk. Staff register in Discord, then sign in here."""

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

DATA = Path(os.environ.get("TEACHFORTH_DATA", "/var/lib/teachforth-helper"))
HOST = os.environ.get("TEACHFORTH_PORTAL_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEACHFORTH_PORTAL_PORT", "8795"))
PUBLIC = os.environ.get("TEACHFORTH_PORTAL_URL", "https://teachforthhelp.samsprojects.xyz").rstrip("/")
APP_ID = os.environ.get("TEACHFORTH_APP_ID", "1555983675810652301")
TOKEN_RE = re.compile(r"(?i)\b(?:ghp_|github_pat_|sk-|xox[baprs]-|MT[A-Za-z0-9_-]{20,})[A-Za-z0-9_-]{8,}")

_started = False


def scrub(text):
    return TOKEN_RE.sub("[removed]", str(text or ""))


def _read(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return default


def session_key():
    path = DATA / "session.key"
    if not path.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf-8")
        path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()


def staff_path():
    return DATA / "staff.json"


def load_staff():
    try:
        data = json.loads(staff_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_staff(rows):
    DATA.mkdir(parents=True, exist_ok=True)
    staff_path().write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    staff_path().chmod(0o600)


def sign(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    mac = hmac.new(session_key().encode(), raw, hashlib.sha256).hexdigest()
    return f"{raw.hex()}.{mac}"


def unsign(token, max_age=60 * 60 * 12):
    try:
        raw_hex, mac = str(token or "").split(".", 1)
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        return None
    expected = hmac.new(session_key().encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if time.time() - float(payload.get("iat") or 0) > max_age:
        return None
    return payload


def e(value):
    return html.escape(scrub(value), quote=True)


def page(title, body, user=""):
    who = f"<span>{e(user)}</span>" if user else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · TeachForth</title>
<style>
:root {{ color-scheme: light; --ink:#241433; --muted:#6d5b80; --line:#eadff3; --purple:#7a1fa3; --bg:#f7f2fb; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font:16px/1.5 "Segoe UI", sans-serif; color:var(--ink); background:radial-gradient(1200px 500px at 10% -10%, #f3e6ff, transparent), var(--bg); }}
header {{ display:flex; justify-content:space-between; align-items:center; padding:22px 28px; }}
a {{ color:var(--purple); }}
main {{ width:min(880px, calc(100% - 32px)); margin:0 auto 48px; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:18px; padding:22px; margin:14px 0; box-shadow:0 10px 30px #7a1fa308; }}
h1 {{ font-size:32px; line-height:1.15; margin:0 0 8px; }}
h2 {{ font-size:18px; margin:0 0 8px; }}
p {{ color:var(--muted); }}
label {{ display:block; font-size:13px; margin:12px 0 6px; }}
input, textarea, select {{ width:100%; border:1px solid var(--line); border-radius:12px; padding:12px; font:inherit; }}
button, .button {{ display:inline-block; border:0; border-radius:999px; background:var(--purple); color:#fff; padding:11px 16px; text-decoration:none; cursor:pointer; }}
.ghost {{ background:#fff; color:var(--purple); border:1px solid var(--line); }}
.row {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
.msg {{ padding:12px 0; border-top:1px solid var(--line); }}
.msg b {{ display:block; }}
.err {{ color:#8d1d3b; }}
footer {{ color:var(--muted); font-size:13px; padding:0 28px 28px; }}
</style>
</head>
<body>
<header><strong>TeachForth Help</strong>{who}</header>
<main>{body}</main>
<footer>TeachForth Desk is a modified Modmail. <a href="https://github.com/So10-k/teachforth-helper">Source</a> is offered under AGPL-3.0.</footer>
</body>
</html>"""


def staff_member(bot, user_id):
    guild = bot.guild
    if guild is None:
        return None
    return guild.get_member(int(user_id))


def allowed(bot, user_id, permissions=""):
    if str(user_id) in {str(item) for item in bot.bot_owner_ids}:
        return True
    member = staff_member(bot, user_id)
    if member is not None:
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild or perms.manage_messages:
            return True
    try:
        bits = int(permissions or "0")
    except ValueError:
        bits = 0
    if bits & (0x8 | 0x20 | 0x2000):
        return True
    roles = {}
    try:
        roles = json.loads(Path("/var/lib/teachforth-discord/roles.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        roles = {}
    return roles.get(str(user_id)) in {"admin", "chapter_lead", "lead_teacher", "teacher"}


def issue_code(app, kind, discord_id=""):
    code = secrets.token_hex(3).upper()
    app["codes"][code] = {"kind": kind, "discord_id": str(discord_id), "exp": time.time() + 600, "approved": False}
    return code


def live_code(app, code):
    row = app["codes"].get(str(code or "").strip().upper())
    if not row or row["exp"] < time.time():
        return None
    return row


def register_user(app, discord_id, name):
    rows = load_staff()
    rows[str(discord_id)] = {"name": scrub(name)[:80], "at": datetime.now(timezone.utc).isoformat()}
    save_staff(rows)
    return rows[str(discord_id)]


def session_for(discord_id, name):
    return sign({"id": str(discord_id), "name": scrub(name)[:80], "csrf": secrets.token_hex(16), "iat": time.time()})


def current(request):
    return unsign(request.cookies.get("tf_help", ""))


def require_staff(request):
    user = current(request)
    if not user or str(user.get("id")) not in load_staff():
        raise web.HTTPFound("/")
    return user


def check_csrf(request, user, form):
    if not hmac.compare_digest(str(form.get("csrf") or ""), str(user.get("csrf") or "")):
        raise web.HTTPForbidden(text="Page expired. Refresh and try again.")


def fake_message(member, channel, text):
    from types import SimpleNamespace

    return SimpleNamespace(
        content=text,
        attachments=[],
        stickers=[],
        author=member,
        channel=channel,
        guild=channel.guild,
        id=0,
        created_at=datetime.now(timezone.utc),
        embeds=[],
        reference=None,
        mention_everyone=False,
        mentions=[],
        role_mentions=[],
        channel_mentions=[],
    )


async def login_page(request):
    user = current(request)
    if user and str(user.get("id")) in load_staff():
        raise web.HTTPFound("/desk")
    secret = _read(DATA / "oauth-secret")
    oauth = ""
    if secret:
        oauth = '<p><a class="button" href="/oauth/start">Login with Discord</a></p>'
    else:
        oauth = "<p>Discord OAuth is waiting on a client secret. Until then, register with <code>/login</code> or <code>.login</code> and paste the code.</p>"
    body = f"""
    <div class="card">
      <h1>Helpdesk</h1>
      <p>Teachers answer students here and in Discord. Register once in the server, then come back.</p>
      {oauth}
      <form method="post" action="/login/code">
        <label for="code">Code from /login</label>
        <input id="code" name="code" autocomplete="one-time-code" maxlength="12" required>
        <p class="row"><button type="submit">Sign in</button> <a class="button ghost" href="/login/device">I am in Discord</a></p>
      </form>
    </div>
    <div class="card">
      <h2>Register</h2>
      <p>In the TeachForth server, run <code>/login</code>. Or run <code>.login CODE</code> with the code from the Discord button. That registers this account.</p>
    </div>"""
    return web.Response(text=page("Sign in", body), content_type="text/html")


async def device_page(request):
    code = issue_code(request.app, "browser")
    body = f"""
    <div class="card">
      <h1>Finish in Discord</h1>
      <p>Run this in the TeachForth server. It registers you and signs this browser in.</p>
      <p><code>.login {e(code)}</code></p>
      <p id="state">Waiting for Discord…</p>
    </div>
    <script>
    async function poll() {{
      const res = await fetch("/login/poll?code={e(code)}");
      if (res.ok) location.href = "/desk";
      else setTimeout(poll, 2000);
    }}
    poll();
    </script>"""
    response = web.Response(text=page("Register", body), content_type="text/html")
    response.set_cookie("tf_pending", code, max_age=600, httponly=True, secure=True, samesite="Lax")
    return response


async def poll(request):
    row = live_code(request.app, request.query.get("code"))
    if not row or not row.get("approved") or not row.get("discord_id"):
        return web.Response(status=204)
    response = web.Response(status=204)
    response.set_cookie("tf_help", session_for(row["discord_id"], row.get("name") or "Teacher"), max_age=60 * 60 * 12, httponly=True, secure=True, samesite="Lax", path="/")
    request.app["codes"].pop(str(request.query.get("code")).upper(), None)
    return response


async def paste_login(request):
    form = await request.post()
    row = live_code(request.app, form.get("code"))
    if not row or row["kind"] != "paste" or not row.get("discord_id"):
        return web.Response(text=page("Sign in", '<div class="card"><p class="err">That code is old or not yours. Run /login again.</p></div>'), content_type="text/html", status=400)
    response = web.HTTPFound("/desk")
    response.set_cookie("tf_help", session_for(row["discord_id"], row.get("name") or "Teacher"), max_age=60 * 60 * 12, httponly=True, secure=True, samesite="Lax", path="/")
    request.app["codes"].pop(str(form.get("code")).upper(), None)
    return response


async def oauth_start(request):
    if not _read(DATA / "oauth-secret"):
        raise web.HTTPFound("/")
    state = secrets.token_urlsafe(18)
    request.app["states"][state] = time.time() + 600
    url = (
        "https://discord.com/oauth2/authorize?client_id="
        + APP_ID
        + "&response_type=code&scope=identify&prompt=consent&state="
        + state
        + "&redirect_uri="
        + quote(PUBLIC + "/oauth/callback", safe="")
    )
    raise web.HTTPFound(url)


async def oauth_callback(request):
    state = request.query.get("state", "")
    if request.app["states"].pop(state, 0) < time.time():
        return web.Response(text=page("Sign in", '<div class="card"><p class="err">That login expired. Try again.</p></div>'), content_type="text/html", status=400)
    secret = _read(DATA / "oauth-secret")
    if not secret:
        raise web.HTTPFound("/")
    async with request.app["bot"].session.post(
        "https://discord.com/api/v10/oauth2/token",
        data={
            "client_id": APP_ID,
            "client_secret": secret,
            "grant_type": "authorization_code",
            "code": request.query.get("code", ""),
            "redirect_uri": PUBLIC + "/oauth/callback",
        },
    ) as res:
        token = await res.json(content_type=None)
        if res.status != 200:
            return web.Response(text=page("Sign in", '<div class="card"><p class="err">Discord did not accept that login.</p></div>'), content_type="text/html", status=400)
    async with request.app["bot"].session.get(
        "https://discord.com/api/v10/users/@me",
        headers={"authorization": f"Bearer {token.get('access_token', '')}"},
    ) as res:
        user = await res.json(content_type=None)
    discord_id = str(user.get("id") or "")
    if discord_id not in load_staff():
        return web.Response(
            text=page("Register first", '<div class="card"><h1>Not registered</h1><p>Discord knows you, but the helpdesk does not yet. Run <code>/login</code> or <code>.login</code> in the server, then come back.</p></div>'),
            content_type="text/html",
            status=403,
        )
    response = web.HTTPFound("/desk")
    response.set_cookie("tf_help", session_for(discord_id, user.get("global_name") or user.get("username") or "Teacher"), max_age=60 * 60 * 12, httponly=True, secure=True, samesite="Lax", path="/")
    return response


def accept_registration(app, discord_id, name, code="", permissions=""):
    discord_id = str(discord_id or "")
    if not re.fullmatch(r"\d{17,20}", discord_id):
        return 400, {"error": "That account is not valid."}
    if not allowed(app["bot"], discord_id, permissions):
        return 403, {"error": "Only teachers and admins can register."}
    register_user(app, discord_id, name or "Teacher")
    row = live_code(app, code) if code else None
    if code and row and row["kind"] == "browser":
        row.update({"approved": True, "discord_id": discord_id, "name": name})
        return 200, {"ok": True, "message": "Registered. The browser you started from is signed in."}
    if code and not row:
        return 400, {"error": "That code expired. Open the helpdesk and start again."}
    paste = issue_code(app, "paste", discord_id)
    app["codes"][paste]["name"] = name
    return 200, {"ok": True, "code": paste, "message": f"Registered. Your helpdesk code is {paste}. It lasts 10 minutes."}


async def register(request):
    if request.remote not in {"127.0.0.1", "::1"}:
        return web.json_response({"error": "Local only"}, status=403)
    expected = _read(DATA / "internal-secret")
    given = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(given, f"Bearer {expected}"):
        return web.json_response({"error": "Sign in first"}, status=401)
    body = await request.json()
    status, payload = accept_registration(
        request.app,
        body.get("discordId"),
        body.get("name") or "Teacher",
        body.get("code") or "",
        body.get("permissions") or "",
    )
    return web.json_response(payload, status=status)


async def desk(request):
    user = require_staff(request)
    bot = request.app["bot"]
    rows = []
    for thread in list(bot.threads):
        if not getattr(thread, "ready", False) or thread.channel is None:
            continue
        recipient = getattr(thread, "recipient", None)
        name = getattr(recipient, "name", None) or str(getattr(thread, "id", "Student"))
        rows.append(f'<p><a href="/thread/{int(thread.channel.id)}"><strong>{e(name)}</strong></a> · open</p>')
    listing = "\n".join(rows) or "<p>No open conversations. A student message in Discord will show up here.</p>"
    body = f'<div class="card"><h1>Open</h1>{listing}</div><div class="card"><p class="row"><a class="button ghost" href="/logs">Old logs</a> <a class="button ghost" href="/logout">Sign out</a></p></div>'
    return web.Response(text=page("Desk", body, user.get("name")), content_type="text/html")


async def thread_page(request):
    user = require_staff(request)
    bot = request.app["bot"]
    channel_id = int(request.match_info["channel_id"])
    thread = None
    for item in list(bot.threads):
        if item.channel and item.channel.id == channel_id:
            thread = item
            break
    if thread is None:
        return web.Response(text=page("Missing", '<div class="card"><p>That conversation is closed or gone.</p></div>'), content_type="text/html", status=404)
    messages = []
    async for message in thread.channel.history(limit=40, oldest_first=False):
        who = message.author.display_name
        text = scrub(message.content or "")
        if not text and message.embeds:
            text = scrub(message.embeds[0].description or message.embeds[0].title or "")
        if text:
            messages.append(f'<div class="msg"><b>{e(who)}</b>{e(text)}</div>')
    messages.reverse()
    csrf = e(user.get("csrf"))
    body = f"""
    <div class="card"><h1>{e(getattr(thread.recipient, 'name', 'Student'))}</h1>{''.join(messages) or '<p>No messages yet.</p>'}</div>
    <div class="card">
      <form method="post" action="/thread/{channel_id}/reply">
        <input type="hidden" name="csrf" value="{csrf}">
        <label for="reply">Reply</label>
        <textarea id="reply" name="message" maxlength="1800" required></textarea>
        <p class="row"><button type="submit">Send</button></p>
      </form>
      <form method="post" action="/thread/{channel_id}/note">
        <input type="hidden" name="csrf" value="{csrf}">
        <label for="note">Staff note</label>
        <textarea id="note" name="message" maxlength="1800" required></textarea>
        <p><button class="ghost" type="submit">Save note</button></p>
      </form>
      <form method="post" action="/thread/{channel_id}/close">
        <input type="hidden" name="csrf" value="{csrf}">
        <label for="close">Close</label>
        <input id="close" name="message" maxlength="500" placeholder="Optional note for the student">
        <p><button class="ghost" type="submit">Close</button></p>
      </form>
    </div>"""
    return web.Response(text=page("Conversation", body, user.get("name")), content_type="text/html")


async def thread_action(request):
    user = require_staff(request)
    form = await request.post()
    check_csrf(request, user, form)
    bot = request.app["bot"]
    channel_id = int(request.match_info["channel_id"])
    thread = next((item for item in list(bot.threads) if item.channel and item.channel.id == channel_id), None)
    if thread is None:
        return web.Response(status=404, text="Missing")
    member = staff_member(bot, user["id"]) or bot.get_user(int(user["id"]))
    if member is None:
        return web.Response(text=page("Not in server", '<div class="card"><p>Join the TeachForth server first.</p></div>'), content_type="text/html", status=403)
    text = scrub(form.get("message") or "")[:1800]
    action = request.match_info["action"]
    try:
        if action == "reply":
            await thread.reply(fake_message(member, thread.channel, text), content=text)
        elif action == "note":
            await thread.note(fake_message(member, thread.channel, text), persistent=True)
        elif action == "close":
            await thread.close(closer=member, message=text or None, silent=not text)
        else:
            return web.Response(status=404, text="Missing")
    except Exception:
        return web.Response(text=page("Not sent", '<div class="card"><p class="err">That did not send. Try again from the Discord thread.</p></div>'), content_type="text/html", status=500)
    raise web.HTTPFound("/desk" if action == "close" else f"/thread/{channel_id}")


async def logs_page(request):
    user = require_staff(request)
    bot = request.app["bot"]
    rows = []
    try:
        cursor = bot.api.logs.find({}).sort("_id", -1).limit(30)
        async for doc in cursor:
            key = doc.get("key") or ""
            recipient = (doc.get("recipient") or {}).get("name") or "Student"
            if re.fullmatch(r"[0-9a-f]{6,32}", str(key)):
                rows.append(f'<p><a href="/logs/{e(key)}">{e(recipient)}</a></p>')
    except Exception:
        rows = []
    body = f'<div class="card"><h1>Logs</h1>{"".join(rows) or "<p>No closed logs yet.</p>"}</div>'
    return web.Response(text=page("Logs", body, user.get("name")), content_type="text/html")


async def log_page(request):
    user = require_staff(request)
    key = request.match_info["key"]
    if not re.fullmatch(r"[0-9a-f]{6,32}", key):
        return web.Response(status=404, text="Missing")
    doc = await request.app["bot"].api.logs.find_one({"key": key})
    if not doc:
        return web.Response(text=page("Missing", '<div class="card"><p>That log is gone.</p></div>'), content_type="text/html", status=404)
    messages = []
    for message in doc.get("messages") or []:
        author = (message.get("author") or {}).get("name") or "Someone"
        kind = message.get("type") or ""
        if kind == "note":
            author = f"{author} · note"
        messages.append(f'<div class="msg"><b>{e(author)}</b>{e(message.get("content") or "")}</div>')
    body = f'<div class="card"><h1>Log</h1>{"".join(messages) or "<p>Empty.</p>"}</div>'
    return web.Response(text=page("Log", body, user.get("name")), content_type="text/html")


async def logout(request):
    response = web.HTTPFound("/")
    response.del_cookie("tf_help", path="/")
    return response


async def health(_request):
    return web.json_response({"ok": True})


def build_app(bot):
    app = web.Application()
    app["bot"] = bot
    app["codes"] = {}
    app["states"] = {}
    app.add_routes([
        web.get("/", login_page),
        web.get("/login/device", device_page),
        web.get("/login/poll", poll),
        web.post("/login/code", paste_login),
        web.get("/oauth/start", oauth_start),
        web.get("/oauth/callback", oauth_callback),
        web.post("/internal/register", register),
        web.get("/desk", desk),
        web.get("/thread/{channel_id}", thread_page),
        web.post("/thread/{channel_id}/{action}", thread_action),
        web.get("/logs", logs_page),
        web.get("/logs/{key}", log_page),
        web.get("/logout", logout),
        web.get("/health", health),
    ])
    return app


async def start(bot):
    global _started
    if _started:
        return
    _started = True
    DATA.mkdir(parents=True, exist_ok=True)
    app = build_app(bot)
    bot._teachforth_app = app
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
