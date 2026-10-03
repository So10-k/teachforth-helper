"""Student ticket intake. Shared by the bot and the helpdesk."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.environ.get("TEACHFORTH_DATA", "/var/lib/teachforth-helper"))
FILE = DATA / "intake.json"
COLOR = 0x7A1FA3

TOPICS = (
    ("ide", "The IDE"),
    ("login", "Signing in"),
    ("github", "GitHub"),
    ("work", "Lost work"),
    ("lesson", "A lesson"),
    ("other", "Something else"),
)
TOPIC_IDS = {key for key, _label in TOPICS}

ARTICLES = {
    "ide": (
        "The IDE",
        "A blank or spinning page is usually the class computer, not your project.\n"
        "1. Close the old tab and open the class link from the TeachForth site again.\n"
        "2. If it says class is off, you did not break it. A teacher has to start it.\n"
        "3. If the editor is empty, wait 20 seconds and refresh once. Do not open a second copy.",
    ),
    "login": (
        "Signing in",
        "The class site signs you in with Discord. There is no separate password.\n"
        "1. Use the Login button on the class site.\n"
        "2. If it loops, close every TeachForth tab and try once more.\n"
        "3. A school browser sometimes blocks the popup. Try the same link in Chrome.",
    ),
    "github": (
        "GitHub",
        "GitHub is how your code stays yours after class.\n"
        "1. In the IDE, open your account and connect GitHub. Approve only the TeachForth app.\n"
        "2. Do not send a password or token in this chat. A teacher does not need one.\n"
        "3. If it already says connected and a push failed, tell us the project name.",
    ),
    "work": (
        "Lost work",
        "Your project lives on the class computer, and on GitHub if you connected it.\n"
        "1. Do not start a new project. Open the same one from the IDE home.\n"
        "2. If class was off, the last save is the one committed before it stopped.\n"
        "3. A teacher can look the project up once this ticket is open. We need its name.",
    ),
    "lesson": (
        "A lesson",
        "Being stuck is a normal ticket. A teacher can open your project from here.\n"
        "Have the lesson name and the last thing you tried. You do not need a perfect error message.",
    ),
    "other": (
        "Something else",
        "Tell us what you were trying to do, then what happened. A teacher reads that before they reply.",
    ),
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    users = data.get("users")
    return users if isinstance(users, dict) else {}


def save(users):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")


def get(user_id):
    return dict(load().get(str(user_id)) or {})


def put(user_id, state):
    users = load()
    users[str(user_id)] = state
    save(users)


def clear(user_id):
    users = load()
    users.pop(str(user_id), None)
    save(users)


def topic_label(key):
    for item, label in TOPICS:
        if item == key:
            return label
    return "Help"


def guess_topic(text):
    low = (text or "").lower()
    words = {
        "ide": ("ide", "editor", "codespace", "blank", "page", "crash"),
        "login": ("login", "sign in", "signin", "oauth", "password"),
        "github": ("github", "repo", "push", "sync"),
        "work": ("lost", "gone", "deleted", "save", "project disappeared"),
        "lesson": ("lesson", "chapter", "stuck", "homework", "exercise"),
    }
    for key, hints in words.items():
        if any(hint in low for hint in hints):
            return key
    return ""


def means_fixed(text):
    low = (text or "").lower()
    return any(part in low for part in ("fixed", "it worked", "that worked", "never mind", "nevermind", "all good", "solved"))


def means_teacher(text):
    low = (text or "").lower()
    return any(part in low for part in ("teacher", "still", "didn't", "did not", "nope", "not fixed", "need help"))


def brief_lines(state):
    topic = topic_label(state.get("topic"))
    tried = state.get("article") and "Shown. They still need a teacher." or "Not shown."
    return [
        ("Topic", topic),
        ("First message", state.get("first") or "No text."),
        ("Trying to", state.get("trying") or "Not answered."),
        ("What happened", state.get("happened") or "Not answered."),
        ("Self-help", tried),
        ("Class", state.get("class_line") or "Not checked."),
    ]


def card_html(user_id, escape):
    state = get(user_id)
    if not state or not state.get("topic"):
        return ""
    rows = "".join(
        f"<p><b>{escape(name)}</b><br>{escape(text)}</p>" for name, text in brief_lines(state)
    )
    return f'<div class="card"><h2>What they told us</h2>{rows}</div>'
