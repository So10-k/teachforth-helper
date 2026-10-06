"""Admin database browser for the helpdesk. Secrets stay masked."""

import csv
import io
import json
import re
from urllib.parse import quote

from aiohttp import web

import teachforth_chat
import teachforth_portal
import teachforth_training

SECRET = re.compile(r"(?i)(password|token|secret|cookie|authorization|connection_uri|mongo_uri|session|hash)")
SOURCES = ("staff", "qualifications", "training", "mongo")


def is_admin(bot, user):
    user_id = str((user or {}).get("id") or "")
    if user_id and user_id in {str(item) for item in getattr(bot, "bot_owner_ids", []) or []}:
        return True
    if teachforth_portal.website_role(user_id) == "admin":
        return True
    member = teachforth_portal.staff_member(bot, user_id)
    return bool(member and any(role.name == "TeachForth Admin" for role in member.roles))


def mask(value, key=""):
    if SECRET.search(str(key or "")):
        return "••••" if value else value
    if isinstance(value, dict):
        return {str(k): mask(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(item, key) for item in value[:30]]
    text = value if isinstance(value, str) else value
    if isinstance(text, str):
        text = teachforth_portal.scrub(text)
        return text if len(text) <= 4000 else text[:4000] + "…"
    return value


def add_routes(app):
    app.add_routes([
        web.get("/data", page),
        web.post("/data/insert", insert),
        web.post("/data/save", save),
        web.post("/data/delete", delete),
        web.get("/data/export", export),
    ])


async def page(request):
    user = teachforth_portal.require_staff(request)
    bot = request.app["bot"]
    if not is_admin(bot, user):
        return web.Response(text=teachforth_portal.page("Database", "<div class='card'><p>Only an admin can open this.</p></div>", user.get("name")), content_type="text/html", status=403)
    src = request.query.get("src") or "staff"
    name = request.query.get("name") or ""
    q = (request.query.get("q") or "")[:120]
    rows, fields, note = await load_rows(bot, src, name, q)
    links = " ".join(f"<a class='button {'ghost' if src != item else ''}' href='/data?src={item}'>{item}</a>" for item in SOURCES)
    names = ""
    if src == "qualifications":
        names = " ".join(f"<a href='/data?src=qualifications&name={item}'>{item}</a>" for item in ("tickets", "users", "messages", "snapshots"))
    if src == "mongo":
        names = " ".join(f"<a href='/data?src=mongo&name={quote(item)}'>{teachforth_portal.e(item)}</a>" for item in await mongo_names(bot))
    head = "".join(f"<th>{teachforth_portal.e(field)}</th>" for field in fields)
    body = []
    for row in rows[:40]:
        cells = "".join(f"<td>{teachforth_portal.e(clip(row.get(field)))}</td>" for field in fields)
        body.append(f"<tr><td><form method='post' action='/data/save'>{hidden(user, src, name, row)}<button>Edit</button></form></td>{cells}</tr>")
    form = f"""
    {teachforth_portal.nav('data')}
    <div class="card"><h1>Database</h1><p>Helpdesk data. Tokens and passwords stay hidden.</p><p class="row">{links}</p>{names}</div>
    <div class="card"><form method="get" action="/data"><input type="hidden" name="src" value="{teachforth_portal.e(src)}"><input type="hidden" name="name" value="{teachforth_portal.e(name)}"><input name="q" value="{teachforth_portal.e(q)}" placeholder="Search"><button>Search</button></form>
      <p>{teachforth_portal.e(note)} <a href="/data/export?src={quote(src)}&name={quote(name)}">Export JSON</a></p>
      <div style="overflow:auto"><table><thead><tr><th></th>{head}</tr></thead><tbody>{''.join(body) or '<tr><td>No rows</td></tr>'}</tbody></table></div>
    </div>
    <div class="card"><h2>Insert</h2><form method="post" action="/data/insert">{token(user, src, name)}<label>JSON<textarea name="body" rows="6" placeholder='{{"id":"1","note":"hello"}}'></textarea></label><label><input type="checkbox" name="confirm" value="yes"> Save this row</label><button>Insert</button></form></div>
    """
    return web.Response(text=teachforth_portal.page("Database", form, user.get("name")), content_type="text/html")


async def insert(request):
    user, bot, form = await posted(request)
    if form.get("confirm") != "yes":
        raise web.HTTPBadRequest(text="Confirm the insert")
    try:
        row = json.loads(form.get("body") or "{}")
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text="That is not JSON")
    if not isinstance(row, dict):
        raise web.HTTPBadRequest(text="A row has to be an object")
    await mutate(bot, form.get("src"), form.get("name"), "insert", "", scrub_write(row))
    raise web.HTTPFound(back(form))


async def save(request):
    user, bot, form = await posted(request)
    src, name, key = form.get("src"), form.get("name"), form.get("key")
    if form.get("confirm") == "yes":
        values = {field: form.get(f"v:{field}") for field in form if field.startswith("v:") and form.get(field) != "••••"}
        values = {field[2:]: value for field, value in values.items()}
        await mutate(bot, src, name, "save", key, scrub_write(values))
        raise web.HTTPFound(back(form))
    rows, fields, _note = await load_rows(bot, src, name, "")
    row = next((item for item in rows if str(item.get("_key")) == str(key)), None)
    if not row:
        raise web.HTTPNotFound(text="Row not found")
    fields_html = "".join(
        f"<label>{teachforth_portal.e(field)}<textarea name='v:{teachforth_portal.e(field)}' rows='2'>{teachforth_portal.e(row.get(field) if not isinstance(row.get(field), (dict, list)) else json.dumps(row.get(field)))}</textarea></label>"
        for field in row if field != "_key"
    )
    body = f"""<div class='card'><h1>Edit</h1><form method='post' action='/data/save'>{hidden(user, src, name, row)}{fields_html}<label><input type='checkbox' name='confirm' value='yes'> Save this edit</label><button>Save</button></form>
      <form method='post' action='/data/delete'>{hidden(user, src, name, row)}<label><input type='checkbox' name='confirm' value='yes'> Delete this row</label><button>Delete</button></form></div>"""
    return web.Response(text=teachforth_portal.page("Edit", body, user.get("name")), content_type="text/html")


async def delete(request):
    user, bot, form = await posted(request)
    if form.get("confirm") != "yes":
        raise web.HTTPBadRequest(text="Confirm the delete")
    await mutate(bot, form.get("src"), form.get("name"), "delete", form.get("key"), {})
    raise web.HTTPFound(back(form))


async def export(request):
    user = teachforth_portal.require_staff(request)
    bot = request.app["bot"]
    if not is_admin(bot, user):
        raise web.HTTPForbidden(text="Only an admin can export this")
    src = request.query.get("src") or "staff"
    name = request.query.get("name") or ""
    rows, _fields, _note = await load_rows(bot, src, name, "")
    payload = json.dumps({"source": src, "name": name, "rows": rows[:500]}, indent=2, default=str)
    return web.Response(text=payload, content_type="application/json", headers={"content-disposition": f"attachment; filename={src or 'data'}.json"})


async def posted(request):
    user = teachforth_portal.require_staff(request)
    bot = request.app["bot"]
    if not is_admin(bot, user):
        raise web.HTTPForbidden(text="Only an admin can change this")
    form = await request.post()
    teachforth_portal.check_csrf(request, user, form)
    return user, bot, form


async def load_rows(bot, src, name, q):
    if src == "staff":
        rows = [{"_key": key, **mask(value)} if isinstance(value, dict) else {"_key": key, "value": mask(value, key)} for key, value in teachforth_portal.load_staff().items()]
        return filter_rows(rows, q), fields_of(rows), "Staff logins. Not Discord roles."
    if src == "qualifications":
        data = teachforth_chat.load()
        section = name or "tickets"
        rows = section_rows(data.get(section))
        return filter_rows(rows, q), fields_of(rows), f"qualifications.json · {section}. Add ?name=users, tickets, messages, or snapshots."
    if src == "training":
        rows = section_rows(teachforth_training.load().get("users"))
        return filter_rows(rows, q), fields_of(rows), "Training pathways."
    if src == "mongo":
        rows = await mongo_rows(bot, name or "logs", q)
        return rows, fields_of(rows), f"Mongo collection {name or 'logs'}."
    return [], ["_key"], "Unknown source"


def section_rows(value):
    if isinstance(value, dict):
        return [{"_key": key, **(mask(item) if isinstance(item, dict) else {"value": mask(item, key)})} for key, item in value.items()]
    if isinstance(value, list):
        return [{"_key": str(i), **(mask(item) if isinstance(item, dict) else {"value": mask(item)})} for i, item in enumerate(value)]
    return []


def filter_rows(rows, q):
    if not q:
        return rows
    needle = q.lower()
    return [row for row in rows if needle in json.dumps(row, default=str).lower()]


def fields_of(rows):
    fields = []
    for row in rows[:20]:
        for key in row:
            if key not in fields and key != "_key":
                fields.append(key)
    return fields[:12] or ["value"]


async def mongo_names(bot):
    db = getattr(getattr(bot, "api", None), "db", None)
    if db is None:
        return []
    try:
        return sorted(await db.list_collection_names())
    except Exception:
        return []


async def mongo_rows(bot, name, q):
    db = getattr(getattr(bot, "api", None), "db", None)
    if db is None or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name or ""):
        return []
    rows = []
    try:
        cursor = db[name].find({}).limit(200)
        async for doc in cursor:
            row = mask(dict(doc))
            row["_key"] = str(row.pop("_id", ""))
            if q and q.lower() not in json.dumps(row, default=str).lower():
                continue
            rows.append(row)
    except Exception:
        return []
    return rows


async def mutate(bot, src, name, action, key, values):
    if src == "staff":
        rows = teachforth_portal.load_staff()
        apply_dict(rows, action, key, values)
        teachforth_portal.save_staff(rows)
        return
    if src == "qualifications":
        section = name or "tickets"
        def change(data):
            bucket = data.setdefault(section, {})
            apply_dict(bucket, action, key, values)
        teachforth_chat.update(change)
        return
    if src == "training":
        data = teachforth_training.load()
        apply_dict(data.setdefault("users", {}), action, key, values)
        teachforth_training.save(data)
        return
    if src == "mongo":
        await mutate_mongo(bot, name or "logs", action, key, values)
        return
    raise web.HTTPBadRequest(text="Unknown source")


def apply_dict(bucket, action, key, values):
    if not isinstance(bucket, dict):
        raise web.HTTPBadRequest(text="That section is not a table of rows")
    if action == "delete":
        bucket.pop(str(key), None)
        return
    if action == "insert":
        row_key = str(values.get("id") or values.get("_key") or "")
        if not row_key:
            raise web.HTTPBadRequest(text="Give the row an id")
        bucket[row_key] = {k: v for k, v in values.items() if k not in {"id", "_key"}}
        return
    if str(key) not in bucket:
        raise web.HTTPNotFound(text="Row not found")
    current = bucket[str(key)]
    if not isinstance(current, dict):
        current = {"value": current}
    for field, value in values.items():
        if field == "_key" or value == "••••":
            continue
        current[field] = parse_value(value)
    bucket[str(key)] = current


async def mutate_mongo(bot, name, action, key, values):
    db = getattr(getattr(bot, "api", None), "db", None)
    if db is None or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        raise web.HTTPBadRequest(text="That collection is not available")
    oid = object_id(key)
    coll = db[name]
    if action == "delete":
        await coll.delete_one({"_id": oid})
        return
    clean = {k: parse_value(v) for k, v in values.items() if k not in {"_id", "_key"} and not SECRET.search(k) and v != "••••"}
    if action == "insert":
        if not clean:
            raise web.HTTPBadRequest(text="Nothing to insert")
        await coll.insert_one(clean)
        return
    if not clean:
        raise web.HTTPBadRequest(text="Nothing to update")
    result = await coll.update_one({"_id": oid}, {"$set": clean})
    if not result.matched_count:
        raise web.HTTPNotFound(text="Row not found")


def object_id(value):
    text = str(value or "")
    if re.fullmatch(r"[a-f0-9]{24}", text):
        try:
            from bson import ObjectId
            return ObjectId(text)
        except Exception:
            return text
    return text


def scrub_write(values):
    out = {}
    for key, value in (values or {}).items():
        if SECRET.search(str(key)) or value == "••••":
            continue
        out[str(key)[:80]] = value
    return out


def parse_value(value):
    text = str(value if value is not None else "")
    if text[:1] in "[{":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def clip(value):
    text = "" if value is None else (json.dumps(value) if isinstance(value, (dict, list)) else str(value))
    return text if len(text) <= 80 else text[:80] + "…"


def token(user, src, name):
    return f"<input type='hidden' name='csrf' value='{teachforth_portal.e(user.get('csrf'))}'><input type='hidden' name='src' value='{teachforth_portal.e(src)}'><input type='hidden' name='name' value='{teachforth_portal.e(name)}'>"


def hidden(user, src, name, row):
    return token(user, src, name) + f"<input type='hidden' name='key' value='{teachforth_portal.e(row.get('_key'))}'>"


def back(form):
    return f"/data?src={quote(str(form.get('src') or 'staff'))}&name={quote(str(form.get('name') or ''))}"


def csv_dump(rows):
    buf = io.StringIO()
    fields = ["_key", *fields_of(rows)]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
