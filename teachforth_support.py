"""Consent grants for one ticket. The token never goes into Discord."""

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("TEACHFORTH_DATA", "/var/lib/teachforth-helper"))
FILE = DATA / "support.json"


def load():
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("channels", {})
    data.setdefault("auto", {})
    return data


def save(data):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data), encoding="utf-8")
    try:
        FILE.chmod(0o600)
    except OSError:
        pass


def note_teacher(channel_id, teacher, recipient):
    data = load()
    row = data["channels"].get(str(channel_id)) or {}
    if row.get("grant"):
        return row
    row.update({"teacher": str(teacher), "recipient": str(recipient), "pending": True})
    data["channels"][str(channel_id)] = row
    save(data)
    return row


def teacher_for(channel_id):
    return str((load()["channels"].get(str(channel_id)) or {}).get("teacher") or "")


def remember(channel_id, row):
    data = load()
    data["channels"][str(channel_id)] = row
    save(data)


def consent(channel_id):
    row = load()["channels"].get(str(channel_id)) or {}
    if not row.get("grant"):
        return None
    return row


def forget(channel_id):
    data = load()
    data["channels"].pop(str(channel_id), None)
    save(data)


def auto_get(user_id):
    return dict(load()["auto"].get(str(user_id)) or {})


def auto_put(user_id, state):
    data = load()
    data["auto"][str(user_id)] = state
    save(data)


def auto_clear(user_id):
    data = load()
    data["auto"].pop(str(user_id), None)
    save(data)
