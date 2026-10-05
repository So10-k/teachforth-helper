"""Private Discord desk training. The website is a later session."""

import json
import re
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


CHAPTER_STEPS = [
    {
        "id": "powers",
        "kind": "quiz",
        "minutes": 3,
        "title": "What a chapter lead can newly do",
        "body": (
            "A teacher can reply, note, claim, ask for device details, and read tickets they are qualified for. "
            "A chapter lead can also block, unblock, move a ticket, and give or take a qualification.\n\n"
            "You still cannot pause the desk, change the bot's settings, or train an admin. "
            "Those stay with an admin. More buttons is not more freedom. It is more ways to hurt a student by accident.\n\n"
            "The sandbox in this category will accept the commands and show what they would do. "
            "The live desk does not change."
        ),
        "prompt": "Which of these is new for a chapter lead?",
        "choices": [
            {"id": "reply", "label": ".reply", "ok": False, "why": "Teachers already reply. The new powers are block, move, and qualifications."},
            {"id": "block", "label": "Block, move, and qualifications", "ok": True, "why": ""},
            {"id": "disable", "label": "Pause the whole desk", "ok": False, "why": "Pausing the desk is an admin command. A chapter lead does not get it."},
            {"id": "config", "label": "Change bot config", "ok": False, "why": "Config is owner only. A chapter lead does not touch it."},
        ],
    },
    {
        "id": "abuse-block",
        "kind": "quiz",
        "minutes": 3,
        "title": "A block is not a mood",
        "body": (
            "`.block` stops a person from opening desk messages. Use it for harassment, spam, or a repeat of the same abuse after a warning. "
            "Always include a duration and a reason another lead could defend.\n\n"
            "Abuse looks like: blocking someone because they were slow, confused, or frustrating. "
            "Abuse looks like a block with no reason, or a reason of \"annoying.\" "
            "That is you using a safety tool as a mute button.\n\n"
            "If a student is stuck, the tool is a reply or a note. Not a block."
        ),
        "prompt": "A student is slow and keeps asking the same question. What do you do?",
        "choices": [
            {"id": "block", "label": "Block them for the rest of class", "ok": False, "why": "Being slow is not abuse. A block here is you punishing a student for needing help."},
            {"id": "note", "label": "Reply once more, then leave a note", "ok": True, "why": ""},
            {"id": "close", "label": "Close the ticket with no note", "ok": False, "why": "Closing hides the need. It does not meet it."},
            {"id": "forever", "label": "Block them with no duration", "ok": False, "why": "A block without a duration and a specific reason is not a decision. It is a dump."},
        ],
    },
    {
        "id": "do-block",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 3,
        "title": "Block the practice student",
        "body": (
            "In #training-sandbox, block the practice student for a limited time, with a reason you would say out loud to another lead.\n\n"
            "\"Annoying\" does not count. A time like `2h` or `30m` has to be in the command. "
            "The sandbox will not block anyone on the live desk."
        ),
        "command": "block",
        "aliases": ["block"],
        "min_rest": 24,
        "need_time": True,
        "abuse": ["annoying", "slow", "stupid", "whatever", "bored", "hate"],
        "show": ".block @Practice 2h Insults in the ticket after being asked to stop",
        "short": "Include a duration like 2h or 30m, and a specific reason. The live desk did not change.",
        "abuse_why": "That reason is a mood, not a harm. Say what they did, and for how long. Nobody was blocked.",
        "done": "Sandbox only. Nobody was blocked. On the live desk that command would stop their messages for the time you named, and the reason would be on the record.",
    },
    {
        "id": "do-unblock",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 2,
        "title": "Take the block off",
        "body": (
            "A block is temporary unless you have a reason to renew it. "
            "When the time is up, or when a lead agrees it was wrong, `.unblock` puts the desk back.\n\n"
            "Leaving a block on because you forgot is also a mistake. "
            "Run the unblock in the sandbox. There is nothing to add after the person."
        ),
        "command": "unblock",
        "aliases": ["unblock"],
        "min_rest": 3,
        "show": ".unblock @Practice",
        "short": "Name the person: `.unblock @Practice`.",
        "done": "Sandbox only. Nobody was unblocked on the live desk. This is how you undo a block you would not defend.",
    },
    {
        "id": "qual-abuse",
        "kind": "quiz",
        "minutes": 3,
        "title": "A qualification is access, not a favor",
        "body": (
            "`.qualification add` lets that teacher see every open ticket in that topic. "
            "IDE, GitHub, class, account, homework, or general.\n\n"
            "Give it when they can actually help that topic. "
            "Do not give it because they asked, because they are your friend, or so the queue looks smaller.\n\n"
            "Taking one away is the same kind of decision. "
            "You are changing who can read a student's help request."
        ),
        "prompt": "A friend wants the account qualification so they can see more tickets. What do you do?",
        "choices": [
            {"id": "add", "label": "Add it. They are staff.", "ok": False, "why": "Staff is not a reason to read account tickets. Access follows the work they can do."},
            {"id": "no", "label": "No, unless they cover that topic", "ok": True, "why": ""},
            {"id": "all", "label": "Give them every topic", "ok": False, "why": "Every topic is the admin view. You do not hand that out as a favor."},
            {"id": "self", "label": "Give it to yourself instead", "ok": False, "why": "Adding yourself so you can browse tickets is the same abuse."},
        ],
    },
    {
        "id": "do-qual",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 3,
        "title": "Give one topic, not all of them",
        "body": (
            "In the sandbox, give @Practice the ide qualification. One topic. "
            "The command is `.qualification add @Practice ide`.\n\n"
            "The live qualification list does not change. "
            "If you add every topic, this step will not move."
        ),
        "command": "qualification",
        "aliases": ["qualification", "qualify"],
        "min_rest": 8,
        "need": ["add", "ide"],
        "forbid_all": True,
        "show": ".qualification add @Practice ide",
        "short": "Use `.qualification add @Practice ide`. One topic.",
        "done": "Sandbox only. @Practice did not gain live access. On the real desk that teacher would start seeing IDE tickets.",
    },
    {
        "id": "move-abuse",
        "kind": "quiz",
        "minutes": 3,
        "title": "Move is for the right people, not to hide",
        "body": (
            "`.move` puts the ticket in another category so the right qualification sees it. "
            "It is not a way to get a hard student out of your view.\n\n"
            "Abuse looks like moving a ticket into a category nobody watches, "
            "or moving it because the student complained about you.\n\n"
            "If you are the wrong person, say so in a note, then move it to the topic that matches. "
            "Do not move it into silence."
        ),
        "prompt": "The student is upset with you. What is the abuse?",
        "choices": [
            {"id": "note", "label": "A note, then a move to the right topic", "ok": False, "why": "That is the honest handoff. The abuse is hiding the ticket."},
            {"id": "hide", "label": "Moving it where nobody looks", "ok": True, "why": ""},
            {"id": "reply", "label": "Replying with what you tried", "ok": False, "why": "A reply is the work. Hiding the channel is the abuse."},
            {"id": "ask", "label": "Asking another lead to take it", "ok": False, "why": "Asking for help is fine. Burying the ticket is not."},
        ],
    },
    {
        "id": "do-move",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 2,
        "title": "Move the practice ticket",
        "body": (
            "Run `.move IDE` in the sandbox. "
            "That is the category a real IDE ticket would sit in. "
            "The live channels do not move."
        ),
        "command": "move",
        "aliases": ["move"],
        "min_rest": 2,
        "show": ".move IDE",
        "short": "Name the category: `.move IDE`.",
        "done": "Sandbox only. No live ticket moved. On the real desk the qualified IDE teachers would be the ones who see it.",
    },
    {
        "id": "duty",
        "kind": "quiz",
        "minutes": 3,
        "title": "You answer for the tools",
        "body": (
            "A chapter lead is who other teachers copy. "
            "If you block lightly, they will block lightly. If you hand out qualifications as favors, the tickets stop being private.\n\n"
            "Before you run block, move, or qualification, you should be able to tell an admin the reason in one sentence. "
            "If you cannot, you do not run it.\n\n"
            "The sandbox let you feel the commands. The live desk will not forgive a careless one."
        ),
        "prompt": "You are about to block someone and you cannot explain why. What do you do?",
        "choices": [
            {"id": "run", "label": "Run it, and write the reason later", "ok": False, "why": "Later is how a bad block becomes a record with no defense."},
            {"id": "stop", "label": "Do not run it", "ok": True, "why": ""},
            {"id": "short", "label": "Use a one-word reason", "ok": False, "why": "A one-word reason is a sign you do not have one."},
            {"id": "friend", "label": "Ask a friend to run it for you", "ok": False, "why": "Handing the abuse to someone else is still the abuse."},
        ],
    },
    {
        "id": "done",
        "kind": "finish",
        "minutes": 1,
        "title": "Restore the server",
        "body": (
            "You practiced block, unblock, a single qualification, and a move. None of those touched the live desk.\n\n"
            "On the real desk, each of those commands changes what a student can do or who can read them. "
            "Press Restore when you can say that out loud."
        ),
    },
]

ADMIN_STEPS = [
    {
        "id": "see",
        "kind": "quiz",
        "minutes": 3,
        "title": "You can see every ticket",
        "body": (
            "An admin sees every open ticket, not only the topics they hold. "
            "You can pause the desk, set the bot status, refresh everyone's website role, and start class.\n\n"
            "That is not a perk. A ticket can hold a student's name, their class, a device card, and a support code. "
            "Opening one because you are curious is reading their help request without a reason.\n\n"
            "The sandbox will run the admin commands as a drill. The live desk stays as it is."
        ),
        "prompt": "Why can an admin see every ticket?",
        "choices": [
            {"id": "fun", "label": "So they can browse when class is quiet", "ok": False, "why": "Quiet is not a reason to read a student's request."},
            {"id": "duty", "label": "So a stuck ticket is never invisible", "ok": True, "why": ""},
            {"id": "rank", "label": "Rank should see more than teachers", "ok": False, "why": "Rank is not the point. Coverage is."},
            {"id": "logs", "label": "So they can copy logs into a group chat", "ok": False, "why": "Logs stay in the ticket. Copying them out is a leak."},
        ],
    },
    {
        "id": "curious",
        "kind": "quiz",
        "minutes": 3,
        "title": "Curiosity is a kind of abuse",
        "body": (
            "Abuse at this level is quiet. You open a ticket you are not working. "
            "You refresh roles to see if someone got demoted. You set the bot status to a joke during class. "
            "You pause the desk because the queue annoys you.\n\n"
            "None of those look like a ban. All of them use a tool the students cannot see, for you instead of them.\n\n"
            "If you would not tell the student and a chapter lead what you just did, do not do it."
        ),
        "prompt": "Which of these is abuse?",
        "choices": [
            {"id": "cover", "label": "Opening a ticket that has had no reply", "ok": False, "why": "An unanswered ticket is the reason you can see all of them."},
            {"id": "browse", "label": "Opening one because the name is familiar", "ok": True, "why": ""},
            {"id": "note", "label": "Leaving a note for the teacher who has it", "ok": False, "why": "A note is the work. Browsing is not."},
            {"id": "ask", "label": "Asking a lead before you disable the desk", "ok": False, "why": "Asking is the restraint. Disabling to clear your own queue is the abuse."},
        ],
    },
    {
        "id": "pause",
        "kind": "quiz",
        "minutes": 3,
        "title": "Pausing the desk stops new help",
        "body": (
            "`.disable` tells new students the desk is not accepting threads. "
            "People already in a ticket may be paused too, depending on the setting. "
            "`.enable` opens it again.\n\n"
            "You disable it when the desk is broken, or when a lead has decided help is closed. "
            "You do not disable it to make the queue empty, to punish a class, or to go to lunch.\n\n"
            "During a live class, a paused desk means a student in trouble has nowhere to write."
        ),
        "prompt": "Class is on, and the queue is long. Do you disable the desk?",
        "choices": [
            {"id": "yes", "label": "Yes. Catch up, then enable it", "ok": False, "why": "A long queue is a staffing problem. Pausing hides new students."},
            {"id": "no", "label": "No. Claim one, and ask for help", "ok": True, "why": ""},
            {"id": "joke", "label": "Disable it and set a joke status", "ok": False, "why": "That is two abuses at once. The desk is not a toy."},
            {"id": "later", "label": "Disable it and tell nobody", "ok": False, "why": "A silent pause is how a student thinks they were ignored."},
        ],
    },
    {
        "id": "do-disable",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 3,
        "title": "See the pause, without pausing",
        "body": (
            "Run `.disable` in #training-sandbox. "
            "Read the reply. The live desk will stay open. "
            "This step exists so you feel how small the command is, and how wide the effect is.\n\n"
            "Do not run it in any other channel. There it is real."
        ),
        "command": "disable",
        "aliases": ["disable"],
        "show": ".disable",
        "done": "Sandbox only. The live desk is still open. On the real desk, new students would have been told help is closed.",
    },
    {
        "id": "do-enable",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 2,
        "title": "Open it back up",
        "body": (
            "A pause you do not reverse is a closed door. "
            "Run `.enable` in the sandbox. "
            "On a live desk you would also tell the leads, in words, that help is open again."
        ),
        "command": "enable",
        "aliases": ["enable"],
        "show": ".enable",
        "done": "Sandbox only. The live desk was never paused. The habit is: if you close it, you are the one who opens it, and you say so.",
    },
    {
        "id": "do-activity",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 2,
        "title": "Set a status a student can read",
        "body": (
            "`.activity` is the bot's status. Students see it. "
            "In the sandbox, set one you would leave up during class.\n\n"
            "A joke, a meme, or an empty flex does not count. "
            "The live status will not change."
        ),
        "command": "activity",
        "aliases": ["activity"],
        "min_rest": 8,
        "abuse": ["lol", "lmao", "joke", "meme", "haha"],
        "show": ".activity Watching TeachForth help",
        "short": "Write a status a student could read during class.",
        "abuse_why": "That status is for you, not for a student who needs help. The live status did not change.",
        "done": "Sandbox only. The live bot status did not change. A real `.activity` is public. Write it as if a student is reading it.",
    },
    {
        "id": "roles-lab",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 3,
        "title": "Refreshing roles is not a punishment",
        "body": (
            "`.roles all` asks the website who everyone is, and puts those Discord roles back. "
            "It is how a missed sync gets fixed. It is not how you demote someone you are annoyed with.\n\n"
            "Run `.roles all` in the sandbox. "
            "Nobody's live roles will move."
        ),
        "command": "roles",
        "aliases": ["roles", "refetch"],
        "need": ["all"],
        "show": ".roles all",
        "short": "The admin form is `.roles all`. A single `.roles` only refreshes you.",
        "done": "Sandbox only. No roles were rewritten. On the live desk this pulls the website roster. It does not invent a demotion.",
    },
    {
        "id": "leak",
        "kind": "quiz",
        "minutes": 3,
        "title": "What you must not carry out of a ticket",
        "body": (
            "A support code, a device card, a student's files, and the text of their ticket stay in that ticket. "
            "You do not paste them into a staff group, a personal DM, or a screenshot channel.\n\n"
            "Cookie values are never in the card. If you see something that looks like a password or a token, you do not repeat it. "
            "You tell the student to rotate it, and you do not store it in a note.\n\n"
            "Admin access is how a leak gets large. One paste reaches every person you sent it to."
        ),
        "prompt": "A device card is useful to another teacher who is not on the ticket. What do you do?",
        "choices": [
            {"id": "paste", "label": "Paste the card into staff chat", "ok": False, "why": "Staff chat is not the ticket. That is a leak."},
            {"id": "add", "label": "Have them open the ticket, or leave a note", "ok": True, "why": ""},
            {"id": "dm", "label": "DM them the support code", "ok": False, "why": "A support code is consent for that ticket, not a key you can forward."},
            {"id": "shot", "label": "Send a screenshot", "ok": False, "why": "A screenshot is the same leak, with extra pixels."},
        ],
    },
    {
        "id": "done",
        "kind": "finish",
        "minutes": 1,
        "title": "Restore the server",
        "body": (
            "You paused and reopened a fake desk, set a status, and refreshed roles, all inside the sandbox. "
            "The live bot did none of it.\n\n"
            "An admin command is small to type and wide to undo. "
            "Press Restore when you are ready to have the rest of the server back."
        ),
    },
]

SESSION_STEPS = [
    {
        "id": "not-promo",
        "kind": "quiz",
        "minutes": 3,
        "title": "Session lead is not a promotion",
        "body": (
            "The session lead is the teacher running this live block. "
            "You still use teacher commands. You do not gain block, move, or qualifications because class is on.\n\n"
            "Only the current session lead, or an admin, can use `/home` for the class computer. "
            "That is the power. It starts and stops the room the students are in. "
            "It is not a badge, and it ends when the block ends.\n\n"
            "This training does not open the website. It teaches the restraint around that button."
        ),
        "prompt": "Class is on, and you are the session lead. What did you gain?",
        "choices": [
            {"id": "block", "label": "Chapter lead commands", "ok": False, "why": "Session lead does not include block, move, or qualifications."},
            {"id": "home", "label": "The live class controls, for this block", "ok": True, "why": ""},
            {"id": "admin", "label": "Admin, until you log off", "ok": False, "why": "You are not an admin. `/home` is the class computer, not the desk."},
            {"id": "forever", "label": "The role until someone takes it", "ok": False, "why": "It is for this block. When class is off, the role comes off."},
        ],
    },
    {
        "id": "home",
        "kind": "quiz",
        "minutes": 3,
        "title": "The class computer is the room",
        "body": (
            "`/home` is how the live session lead, or an admin, starts and stops class. "
            "Students are in that IDE. Stopping it closes their room.\n\n"
            "You start it when the block starts. You stop it when the block is actually over and students have had a chance to save. "
            "You do not restart it to show a friend. You do not hand the role to someone who is not teaching.\n\n"
            "If you are unsure whether class should end, it should not end yet."
        ),
        "prompt": "A friend wants to press stop so they can see the screen. What do you do?",
        "choices": [
            {"id": "hand", "label": "Hand them the session lead role", "ok": False, "why": "The role is the person teaching this block, not a spectator pass."},
            {"id": "no", "label": "No. Stopping class is not a demo", "ok": True, "why": ""},
            {"id": "stop", "label": "Stop it for a minute", "ok": False, "why": "A minute is enough to kick every student out of the room."},
            {"id": "later", "label": "Stop it and say you will restart", "ok": False, "why": "A promise to restart does not unsaved work that was open."},
        ],
    },
    {
        "id": "early",
        "kind": "quiz",
        "minutes": 3,
        "title": "Ending early is abuse",
        "body": (
            "Abuse here does not look like a ban. It looks like ending class because you are tired, "
            "while students are still in the IDE. It looks like telling them the IDE is down when you stopped it. "
            "It looks like leaving the computer on all night because you forgot.\n\n"
            "You are trusted with the room. "
            "Tired is a reason to ask another teacher to take the block, not a reason to shut the door."
        ),
        "prompt": "You are tired, and three students are still working. What do you do?",
        "choices": [
            {"id": "stop", "label": "Stop class and tell them it crashed", "ok": False, "why": "That is a lie plus a closed room. Both are abuses."},
            {"id": "ask", "label": "Ask another teacher to take the block", "ok": True, "why": ""},
            {"id": "leave", "label": "Leave, and leave class running", "ok": False, "why": "An unattended class computer is how it stays on past the block."},
            {"id": "block", "label": "Block the students so the queue is quiet", "ok": False, "why": "You cannot block as a session lead, and the queue is not why you are tired."},
        ],
    },
    {
        "id": "handoff",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 4,
        "title": "Write the handoff",
        "body": (
            "If you have to leave the block, the next person needs a note, not a vibe. "
            "In #training-sandbox, run `.note` with who is still working, what is broken, and whether class should stay up.\n\n"
            "A few words do not count. "
            "This does not write a live note. It checks that you know what a handoff contains."
        ),
        "command": "note",
        "aliases": ["note"],
        "min_rest": 40,
        "show": ".note Two students still in the IDE. Class should stay up. GitHub link failed for one. I did not stop class.",
        "short": "Name who is still working, what is stuck, and whether class stays up. A short note does not hand the room off.",
        "done": "Sandbox only. No live note was saved. That is the note you leave before you ask someone to take the block.",
    },
    {
        "id": "queue-lab",
        "kind": "lab",
        "where": "sandbox",
        "minutes": 2,
        "title": "Look at the work, not the power",
        "body": (
            "Session lead does not skip the queue. "
            "Run `.queue` in the sandbox. "
            "On a live desk this lists the tickets you are allowed to see as a teacher, not every ticket in the server."
        ),
        "command": "queue",
        "aliases": ["queue"],
        "show": ".queue",
        "done": "Sandbox only. The live queue was not opened. You still see teacher tickets, not the admin view.",
    },
    {
        "id": "no-block",
        "kind": "quiz",
        "minutes": 3,
        "title": "Do not borrow a power you do not have",
        "body": (
            "If a student is rude, you reply, you note it, and you ask a chapter lead. "
            "You do not try `.block` because the role feels bigger tonight. "
            "You do not try `.disable` because the queue is loud.\n\n"
            "The sandbox will refuse those as live commands. "
            "If you type them here, read why they do not belong to this role. They will not move the pathway."
        ),
        "prompt": "A student is rude in a ticket during your block. What do you do?",
        "choices": [
            {"id": "block", "label": "Block them yourself", "ok": False, "why": "You do not have that command for a reason. A chapter lead decides a block."},
            {"id": "note", "label": "Note it, and ask a chapter lead", "ok": True, "why": ""},
            {"id": "disable", "label": "Disable the desk", "ok": False, "why": "One rude ticket is not a reason to close help for the class."},
            {"id": "stop", "label": "Stop class", "ok": False, "why": "The room is not a mute button."},
        ],
    },
    {
        "id": "done",
        "kind": "finish",
        "minutes": 1,
        "title": "Restore the server",
        "body": (
            "You are still a teacher, with the class computer for this block only. "
            "You practiced a handoff and the queue. You did not gain chapter lead tools.\n\n"
            "Press Restore. Your saved roles and the hidden channels come back."
        ),
    },
]

TRACKS = {
    "teacher": {"label": "Teacher", "steps": STEPS, "sandbox": False},
    "chapter": {"label": "Chapter lead", "steps": CHAPTER_STEPS, "sandbox": True},
    "admin": {"label": "Admin", "steps": ADMIN_STEPS, "sandbox": True},
    "session": {"label": "Session lead", "steps": SESSION_STEPS, "sandbox": True},
}
TRACK_ALIASES = {
    "teacher": "teacher",
    "desk": "teacher",
    "chapter": "chapter",
    "chapterlead": "chapter",
    "chapter-lead": "chapter",
    "admin": "admin",
    "administrator": "admin",
    "session": "session",
    "sessionlead": "session",
    "session-lead": "session",
}


def normalize_track(value):
    key = re.sub(r"[\s_]+", "", str(value or "").strip().lower())
    return TRACK_ALIASES.get(key, "")


def steps_for(track):
    return TRACKS.get(track or "teacher", TRACKS["teacher"])["steps"]


def active_ids():
    return {int(key) for key in load().get("users", {}) if str(key).isdigit()}


def is_ticket(channel_id):
    return _channel_kind(channel_id) == "ticket"


def is_sandbox(channel_id):
    return _channel_kind(channel_id) == "sandbox"


def _channel_kind(channel_id):
    wanted = int(channel_id or 0)
    if not wanted:
        return ""
    for row in load().get("users", {}).values():
        if int(row.get("ticket_id") or 0) == wanted:
            return "ticket"
        if int(row.get("sandbox_id") or 0) == wanted:
            return "sandbox"
    return ""


def sandbox_reply(name, result, step):
    if not name:
        return "The sandbox hears commands. Start with a dot."
    if result == "abuse":
        return (step or {}).get("abuse_why") or "That is the abuse this step is about. The live desk did not change."
    if result == "short":
        return (step or {}).get("short") or "That is missing a part. The live desk did not change."
    if result == "extra":
        return (step or {}).get("extra") or "Take off the extra words. The live desk did not change."
    if result == "pass":
        return (step or {}).get("done") or "Sandbox only. The live desk did not change. That counted."
    if name in {"block", "unblock", "disable", "enable", "move"} and (step or {}).get("id") == "no-block":
        return "Session lead does not get that command. Asking a chapter lead is the step. The live desk did not change."
    return f"Sandbox only. `.{name}` did not touch the live desk. Run the command on the pathway."


def grade(step, name, rest):
    if not step or step.get("kind") != "lab":
        return "no"
    if name not in set(step.get("aliases") or []):
        return "no"
    if step.get("bare") and rest:
        return "extra"
    low = rest.lower()
    if any(word in low for word in (step.get("abuse") or [])):
        return "abuse"
    if step.get("need_time") and not re.search(r"\b\d+\s*[mhd]\b", low):
        return "short"
    if step.get("need") and not all(part in low for part in step["need"]):
        return "short"
    if step.get("forbid_all"):
        found = [topic for topic in ("ide", "github", "class", "account", "homework", "general") if re.search(rf"\b{topic}\b", low)]
        if len(found) > 1:
            return "abuse"
        if len(found) != 1:
            return "short"
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


def step_at(index, track="teacher"):
    steps = steps_for(track)
    if index < 0 or index >= len(steps):
        return None
    return steps[index]


def minutes_left(index, track="teacher"):
    return sum(int(step.get("minutes") or 1) for step in steps_for(track)[index:])
