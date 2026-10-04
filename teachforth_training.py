"""Private Discord desk training. The website is a later session."""

import json
from pathlib import Path

import teachforth_portal

STORE = teachforth_portal.DATA / "training.json"
ROLE_NAME = "TeachForth Training"
COLOR = 0x5A189A
BLOCKED = {"close", "disable", "block", "unblock", "move", "contact", "snooze", "delete"}

INFO = (
    "This category is only yours until training ends. The rest of the server is hidden, "
    "and your roles are saved.\n\n"
    "How this works\n"
    "• Read #training-pathway. The buttons are the lesson.\n"
    "• You cannot type in this channel or in #training-pathway.\n"
    "• A wrong answer stays put and tells you why.\n"
    "• When a step names a command, open the practice ticket and run that command there.\n"
    "• The pathway moves on by itself when the command lands. You do not press a done button.\n"
    "• Do not close the practice ticket. `.close` is blocked there on purpose.\n"
    "• In the practice ticket you are also the student, so a reply or a diagnostic prompt can arrive in your DMs. That is the student side.\n"
    "• This session is the Discord desk only. The website and the IDE chat are a later session.\n"
    "• Plan on about 30 minutes if you read. Rushing the buttons will not teach the desk.\n\n"
    "If you get stuck, a chapter lead or an admin can run `.train end @you`. "
    "The Stop button below restores your roles and channels."
)

STEPS = [
    {
        "id": "arrive",
        "kind": "quiz",
        "minutes": 2,
        "title": "A ticket starts in a DM",
        "body": (
            "A student does not open a staff channel. They message this bot, or a teacher uses `.contact`.\n\n"
            "The bot then creates a channel. That channel is the ticket. The topic holds their user ID. "
            "That is how `.reply`, `.note`, and `.diagnostic` know who the ticket belongs to.\n\n"
            "If you type in the ticket with no command, the student does not see it. "
            "The channel is the staff desk, not the conversation they are reading.\n\n"
            "Your job is to notice a new ticket, say you have it, and find out what they were doing. "
            "You are not grading them, and you are not asking for a password."
        ),
        "prompt": "Where does a new student request start?",
        "choices": [
            {"id": "channel", "label": "They create the staff channel", "ok": False, "why": "Students never create the staff channel. The bot does that after they write in."},
            {"id": "dm", "label": "They message the bot", "ok": True, "why": ""},
            {"id": "general", "label": "They post in a public channel", "ok": False, "why": "Public channels are not the desk. The request starts in a DM with the bot."},
            {"id": "lead", "label": "A lead assigns an empty channel", "ok": False, "why": "A lead can open a ticket with `.contact`, but a student request starts when they message the bot."},
        ],
    },
    {
        "id": "sides",
        "kind": "quiz",
        "minutes": 2,
        "title": "Two sides of one ticket",
        "body": (
            "You see a channel. The student sees a DM with the bot.\n\n"
            "`.reply` sends your words to that DM and shows your name. "
            "`.areply` sends them without your name. `.preply` sends plain text, still without the staff channel around it.\n\n"
            "A normal message, a `.note`, and a command error stay on the staff side. "
            "If you are not sure the student saw it, look for the bot's confirmation in the ticket. Do not assume.\n\n"
            "In this practice you will be both sides. When you `.reply`, the student copy can arrive in your own DMs. Read it. That is what they see."
        ),
        "prompt": "You type \"try again\" in the ticket with no command. Who sees it?",
        "choices": [
            {"id": "student", "label": "The student, in their DM", "ok": False, "why": "A plain message stays in the staff channel. `.reply` is what sends it."},
            {"id": "staff", "label": "Staff in that channel only", "ok": True, "why": ""},
            {"id": "server", "label": "Everyone in the server", "ok": False, "why": "The ticket is not a public channel. Other people see it only if their role or qualification allows it."},
            {"id": "deleted", "label": "Nobody. It gets deleted", "ok": False, "why": "The bot does not delete a plain staff message. It also does not send it to the student."},
        ],
    },
    {
        "id": "who",
        "kind": "quiz",
        "minutes": 3,
        "title": "Who is allowed to see it",
        "body": (
            "Teachers are not all looking at the same queue. A ticket has a topic: ide, github, class, account, homework, or general.\n\n"
            "A teacher sees a topic only if they hold that qualification. "
            "An admin sees every ticket. A chapter lead sees a topic when nobody is qualified for it, so it is not left unseen.\n\n"
            "`.qualification list` shows what you hold. Adding or removing one is for a chapter lead: "
            "`.qualification add @user ide`.\n\n"
            "The next teacher may not be you. Write so a stranger can continue. "
            "Past work is the point of the ticket, not a private memory."
        ),
        "prompt": "You hold the ide qualification, and you are not an admin. Which new tickets can you see?",
        "choices": [
            {"id": "all", "label": "Every open ticket", "ok": False, "why": "Every open ticket is the admin view. A teacher sees the topics they hold."},
            {"id": "ide", "label": "IDE tickets", "ok": True, "why": ""},
            {"id": "claimed", "label": "Only tickets you claimed", "ok": False, "why": "A claim marks that you have it. It is not the thing that reveals the ticket."},
            {"id": "chapter", "label": "Only your chapter's tickets", "ok": False, "why": "The desk routes by qualification, not by which chapter the student sits in."},
        ],
    },
    {
        "id": "first",
        "kind": "quiz",
        "minutes": 2,
        "title": "The first reply",
        "body": (
            "The first reply has three jobs: they know a person has them, they know what to do next, and they are not scared.\n\n"
            "Say you have it. Ask one concrete question. \"What did you click, and what do you see now?\" is enough. "
            "Do not send a list of five fixes. Do not ask for a password, a token, or a cookie value.\n\n"
            "If the IDE is down, say so and tell them a lead is checking the class computer. "
            "Do not tell them to keep refreshing for ten minutes with no news.\n\n"
            "Short is better than clever. They may be on a shared laptop, and class time is moving."
        ),
        "prompt": "The student says \"it crashed.\" What is the first reply?",
        "choices": [
            {"id": "restart", "label": "Tell them to restart the laptop", "ok": False, "why": "You do not know what crashed. A restart can also throw away unsaved work."},
            {"id": "ask", "label": "Ask what they clicked and what they see", "ok": True, "why": ""},
            {"id": "password", "label": "Ask them to paste the login", "ok": False, "why": "Never ask for a password, a token, or a cookie value. Not in a ticket, and not in DMs."},
            {"id": "close", "label": "Close it and wait for a lead", "ok": False, "why": "Closing hides the request. If you are stuck, leave it open and ask a lead in the ticket."},
        ],
    },
    {
        "id": "open",
        "kind": "open",
        "minutes": 1,
        "title": "Open the practice ticket",
        "body": (
            "The next steps happen in a real ticket in this category. Press the button. Do not create one by hand.\n\n"
            "You will be the staff member and the practice student. "
            "`.reply` and `.diagnostic` can DM you. Read those DMs. That is the student side of the desk.\n\n"
            "Leave the ticket open until the pathway says training is done. `.close` will be refused there."
        ),
    },
    {
        "id": "reply",
        "kind": "lab",
        "minutes": 3,
        "title": "Send a reply they can see",
        "body": (
            "Go to the practice ticket and run the command below. Nothing else will move this step.\n\n"
            "Use a full sentence. A single word does not count. "
            "After it sends, check your DMs. The student copy should be there, with your name on it.\n\n"
            "If the DM does not arrive, the ticket will still say whether the command ran. "
            "A closed DM is a real desk problem. You would then tell them to open DMs, and you would keep the ticket."
        ),
        "command": "reply",
        "aliases": ["reply"],
        "min_rest": 12,
        "show": ".reply Hey, I have this. What did you click, and what do you see now?",
        "short": "Write a real sentence after `.reply`. A word or two does not count.",
    },
    {
        "id": "anon",
        "kind": "quiz",
        "minutes": 2,
        "title": "Named, unnamed, plain",
        "body": (
            "`.reply` is the normal one. The student sees your name, so the next message has a person attached to it.\n\n"
            "`.areply` is the same send, without your name. Use it when a lead asked for an unnamed reply, not because you are unsure.\n\n"
            "`.preply` drops the embed and sends plain text. Use it when an embed would get in the way, not as a habit.\n\n"
            "Do not use an unnamed reply to hide a guess. If you are unsure, say so in a named reply, or ask a lead in a `.note`."
        ),
        "prompt": "When should you use `.areply`?",
        "choices": [
            {"id": "always", "label": "On every ticket", "ok": False, "why": "The normal reply shows your name. Unnamed is the exception."},
            {"id": "asked", "label": "When a lead asked for no name", "ok": True, "why": ""},
            {"id": "unsure", "label": "When you are unsure", "ok": False, "why": "If you are unsure, say so, or write a note and ask a lead. Do not hide the reply."},
            {"id": "angry", "label": "When the student is frustrated", "ok": False, "why": "A frustrated student needs a person, not an unnamed message."},
        ],
    },
    {
        "id": "note",
        "kind": "lab",
        "minutes": 2,
        "title": "Write a note the student never sees",
        "body": (
            "`.note` is for the next teacher. The student does not get a DM. A plain message is easy to miss. A note stays with the ticket.\n\n"
            "Write what you observed and what is still unknown. "
            "\"Student says Run did nothing. I have not seen the screen yet.\" is a note. "
            "\"idk\" is not.\n\n"
            "Run it in the practice ticket. This step moves when the note is long enough to help the next person."
        ),
        "command": "note",
        "aliases": ["note"],
        "min_rest": 12,
        "show": ".note Student says Run did nothing. I asked what they see. Still unknown.",
        "short": "A note needs a real observation, not a word or two.",
    },
    {
        "id": "claim",
        "kind": "lab",
        "minutes": 2,
        "title": "Claim it, do not hide it",
        "body": (
            "`.claim` tells other staff you have this ticket. It does not remove their access. "
            "An admin can still see it. A qualified teacher can still see it.\n\n"
            "Claim when you are actually working it. `.unclaim` when you have to leave and nobody is waiting on you specifically.\n\n"
            "Run `.claim` in the practice ticket. There is nothing to add after the command."
        ),
        "command": "claim",
        "aliases": ["claim"],
        "min_rest": 0,
        "show": ".claim",
    },
    {
        "id": "handoff",
        "kind": "quiz",
        "minutes": 2,
        "title": "The next teacher is a stranger",
        "body": (
            "Teachers are picked by who is free. The person who had this student last week may be in another session.\n\n"
            "Your note is the handoff. Your claim is only a flag. "
            "If you close the ticket, the next person loses the thread of what was tried.\n\n"
            "Write the note as if you will not be here to explain it. "
            "Include the command you suggested and whether the student said it worked."
        ),
        "prompt": "Another teacher has this student tomorrow. What helps them most?",
        "choices": [
            {"id": "dms", "label": "They can scroll your personal DMs", "ok": False, "why": "Your personal DMs are not the ticket. The next teacher cannot see them."},
            {"id": "note", "label": "A note of what you tried and what is unknown", "ok": True, "why": ""},
            {"id": "lock", "label": "Your claim locks everyone else out", "ok": False, "why": "A claim does not hide the ticket. It only says you have it."},
            {"id": "fresh", "label": "Close it so they start fresh", "ok": False, "why": "Closing throws away the record. Leave it open and leave a note."},
        ],
    },
    {
        "id": "diagnostic",
        "kind": "lab",
        "minutes": 4,
        "title": "Ask before you guess the device",
        "body": (
            "`.diagnostic` asks the student to share this browser and device. "
            "Allowing sends the browser name, device, language, timezone, screen size, and whether cookies are enabled.\n\n"
            "Cookie values, passwords, and sign-in tokens are not sent. Do not ask them to paste those. "
            "If they press Not now, you keep helping without the details.\n\n"
            "Run `.diagnostic` in the practice ticket. The prompt should arrive in your DMs, because you are the practice student. "
            "You can press Not now. The command itself is what this step checks.\n\n"
            "This does not train the website widget. If they allow it there later, the same rule holds: no cookie values."
        ),
        "command": "diagnostic",
        "aliases": ["diagnostic"],
        "min_rest": 0,
        "show": ".diagnostic",
    },
    {
        "id": "consent",
        "kind": "quiz",
        "minutes": 2,
        "title": "Consent is a stop sign",
        "body": (
            "The prompt is the ask. Their button is the answer. You do not get a second, quieter way to collect the same thing.\n\n"
            "If they allow it, the ticket gets a device card. You use it to see Chrome versus a phone, not to sign in as them.\n\n"
            "If they refuse, say that is fine and ask what they see. "
            "Do not run the command in a loop. Do not ask for a screenshot of cookies, a password, or `document.cookie`.\n\n"
            "A support code is a separate consent, from their profile, for account lookup. "
            "You do not invent one, and you do not take one from another ticket."
        ),
        "prompt": "They press Not now on the device prompt. What do you do?",
        "choices": [
            {"id": "cookie", "label": "Ask them to paste document.cookie", "ok": False, "why": "Cookie values are never collected. Not now means you stop asking for device details."},
            {"id": "help", "label": "Keep helping without device details", "ok": True, "why": ""},
            {"id": "close", "label": "Close the ticket", "ok": False, "why": "A refusal is not a reason to close. Keep the ticket and ask what they see."},
            {"id": "again", "label": "Run .diagnostic until they allow it", "ok": False, "why": "Once is the ask. Repeating it is pressure. Continue without the card."},
        ],
    },
    {
        "id": "projects",
        "kind": "lab",
        "minutes": 2,
        "title": "Look up work only after consent",
        "body": (
            "After a support code is redeemed on this ticket, `.projects`, `.reports`, `.chapters`, and `.project view` can read that account. "
            "The code is the consent. It lasts for this ticket, not for every future one.\n\n"
            "This practice ticket has no code. Run `.projects` anyway. "
            "The reply should say there is no consent. That message is the lesson. Do not paste a real student's code in here.\n\n"
            "If a live ticket has no code, you ask them to press Support code, or to copy the one from their profile. You do not look them up from memory."
        ),
        "command": "projects",
        "aliases": ["projects"],
        "min_rest": 0,
        "show": ".projects",
    },
    {
        "id": "walks",
        "kind": "lab",
        "minutes": 3,
        "title": "A walk is a procedure, not a guess",
        "body": (
            "`.helpmenusend` with nothing after it lists the walks: page, login, editor, crash, work, github, lesson, error, pair, start, link, and feedback.\n\n"
            "A type starts that walk and can move the ticket into an automated category. "
            "The student gets one step at a time. You stay in the ticket and watch what they pick.\n\n"
            "In this practice, run `.helpmenusend` with nothing after it. "
            "A type is blocked here so you do not start a real walk by accident.\n\n"
            "Use a walk when the problem matches one. Do not send three walks at once. "
            "If none match, stay in the ticket and reply yourself."
        ),
        "command": "helpmenusend",
        "aliases": ["helpmenusend"],
        "bare": True,
        "min_rest": 0,
        "show": ".helpmenusend",
        "extra": "Run `.helpmenusend` with nothing after it. A type would start a real walk.",
    },
    {
        "id": "queue",
        "kind": "lab",
        "minutes": 2,
        "title": "The queue is the work you can see",
        "body": (
            "`.queue` lists open tickets you are allowed to see. It is not a scoreboard, and it is not every ticket in the server.\n\n"
            "Use it at the start of a block and when you finish one student. "
            "Pick a ticket you are qualified for. Claim it if you are taking it.\n\n"
            "Run `.queue` in the practice ticket. Then come back to this channel. The pathway moves on its own."
        ),
        "command": "queue",
        "aliases": ["queue"],
        "min_rest": 0,
        "show": ".queue",
    },
    {
        "id": "close",
        "kind": "quiz",
        "minutes": 2,
        "title": "Close only when the work is done",
        "body": (
            "`.close` ends the ticket. `.close 30m` waits, then closes. You can add a short message after the delay.\n\n"
            "Close when the student is unstuck, or when they say they are done. "
            "Do not close because your block ended, because you are unsure, or because the queue looks long.\n\n"
            "If you have to leave, write a `.note` and leave the ticket open. `.unclaim` if someone else should take it.\n\n"
            "Do not run `.close` in the practice ticket. It is blocked so the rest of the lesson still has a channel."
        ),
        "prompt": "Your class block is over, and the student still needs help. What do you do?",
        "choices": [
            {"id": "close", "label": "Close it so it leaves your queue", "ok": False, "why": "Closing ends the record. Your queue being empty is not the goal."},
            {"id": "note", "label": "Leave a note and leave the ticket open", "ok": True, "why": ""},
            {"id": "delete", "label": "Delete the channel", "ok": False, "why": "Do not delete a ticket channel by hand. Close is the desk's end, and this one is not ready to close."},
            {"id": "new", "label": "Tell them to open a new ticket tomorrow", "ok": False, "why": "A new ticket drops the notes. Leave this one open."},
        ],
    },
    {
        "id": "done",
        "kind": "finish",
        "minutes": 1,
        "title": "Restore the server",
        "body": (
            "That is the desk. You can open a ticket, reply so the student sees it, leave a note, claim it, ask for device details without cookie values, "
            "refuse a lookup that has no consent, list the walks, and read your queue.\n\n"
            "The website and the IDE chat are not part of this session.\n\n"
            "Press Restore. Your saved roles come back, the hidden channels open again, and this category is removed. "
            "A chapter lead can do the same with `.train end @you`."
        ),
    },
]


def active_ids():
    return {int(key) for key in load().get("users", {}) if str(key).isdigit()}


def is_ticket(channel_id):
    wanted = int(channel_id or 0)
    if not wanted:
        return False
    for row in load().get("users", {}).values():
        if int(row.get("ticket_id") or 0) == wanted:
            return True
    return False


def grade(step, name, rest):
    if not step or step.get("kind") != "lab":
        return "no"
    if name not in set(step.get("aliases") or []):
        return "no"
    if step.get("bare") and rest:
        return "extra"
    if len(rest) < int(step.get("min_rest") or 0):
        return "short"
    return "pass"


def split_command(prefix, content):
    text = str(content or "").strip()
    prefixes = prefix if isinstance(prefix, (list, tuple)) else (prefix or ".",)
    used = next((item for item in prefixes if item and text.startswith(item)), "")
    if not used:
        return "", ""
    body = text[len(used):].strip()
    name, _, rest = body.partition(" ")
    return name.lower(), rest.strip()


def load():
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}
    if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
        return {"users": {}}
    return data


def save(data):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STORE)


def get(user_id):
    return load().get("users", {}).get(str(user_id))


def put(user_id, row):
    data = load()
    data.setdefault("users", {})[str(user_id)] = row
    save(data)


def pop(user_id):
    data = load()
    row = data.get("users", {}).pop(str(user_id), None)
    save(data)
    return row


def step_at(index):
    if index < 0 or index >= len(STEPS):
        return None
    return STEPS[index]


def minutes_left(index):
    return sum(int(step.get("minutes") or 1) for step in STEPS[index:])
