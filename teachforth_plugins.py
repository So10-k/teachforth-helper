"""Classroom troubleshooters. Students walk these before a teacher is pulled in."""

CLASS_URL = "https://74-248-20-108.sslip.io"

PLUGINS = [
    {
        "id": "page",
        "label": "Page won't load",
        "blurb": "Blank page, spinning tab, or a message that class is off.",
        "hints": ("blank", "won't load", "wont load", "spinning", "class is off", "page", "white screen"),
        "intro": "I checked class before asking you to refresh.\n{class_line}",
        "steps": [
            {
                "id": "see",
                "ask": "What do you see?",
                "choices": [
                    {
                        "id": "blank",
                        "label": "Blank or spinning",
                        "fix": "{class_line}\n\nClose the old tab. Open {url} once. Do not use a Codespaces bookmark. If class is off, refreshing will not bring the editor back.",
                        "suggest": "Confirm they opened the class link, not Codespaces. If class is on and it is still blank, ask for a screenshot.",
                    },
                    {
                        "id": "says-off",
                        "label": "It says class is off",
                        "fix": "{class_line}\n\nIf class is actually off, you did not break it. A teacher has to start it. If class is on, that tab is stale. Close it and open {url}.",
                        "suggest": "If class is off and they need it, start class. If class is on, they had a stale tab.",
                        "priority": "low",
                    },
                    {"id": "login", "label": "Stuck on login", "switch": "login"},
                    {
                        "id": "empty",
                        "label": "Editor is empty",
                        "fix": "The page loaded. Wait 20 seconds, then refresh once. Do not open a second copy of the project. Your files are on the class computer, not in the tab.",
                        "more": "still-empty",
                        "suggest": "Editor shell loaded but files did not. Ask which project, then open it from their account.",
                    },
                    {
                        "id": "old",
                        "label": "Old tab or bookmark",
                        "fix": "Old bookmarks often open Codespaces. That is the thing that crashed laptops. Close it. The editor is {url} while class is on.",
                        "suggest": "They were on an old link. Send them the class link if it is still failing.",
                    },
                ],
            },
            {
                "id": "still-empty",
                "ask": "After one refresh, what is on the page?",
                "choices": [
                    {"id": "files", "label": "Still no files", "open": True, "suggest": "Open their project from the IDE account. Do not tell them to make a new one."},
                    {"id": "error", "label": "There is an error", "switch": "error"},
                    {"id": "back", "label": "It came back", "fix": "Good. Stay in that tab. Send status later if it drops again."},
                ],
            },
        ],
    },
    {
        "id": "login",
        "label": "Can't sign in",
        "blurb": "Discord login missing, looping, or the wrong account.",
        "hints": ("login", "sign in", "signin", "password", "oauth", "loop"),
        "intro": "The editor signs you in with Discord. There is no separate password.\n{class_line}",
        "steps": [
            {
                "id": "where",
                "ask": "Where did it stop?",
                "choices": [
                    {
                        "id": "no-button",
                        "label": "No Login button",
                        "fix": "{class_line}\n\nYou are probably on the org site, or class is off. The editor is {url}. Look for Login with Discord.",
                        "suggest": "Check the URL they opened. The org site is not the editor.",
                    },
                    {
                        "id": "popup",
                        "label": "Popup was blocked",
                        "fix": "The school browser blocked Discord. Allow popups for {url}, or try Chrome. Do not type a password into a random box.",
                        "suggest": "School browser blocked the Discord popup. They should not be asked for a password.",
                    },
                    {
                        "id": "wrong",
                        "label": "Wrong Discord account",
                        "fix": "Sign out of Discord in the browser, then log in with the Discord you use in class. A teacher never needs your password. Account check: {github}. {projects}.",
                        "suggest": "They may be on a different Discord than the linked IDE account.",
                    },
                    {
                        "id": "loop",
                        "label": "It loops after Allow",
                        "fix": "Close every TeachForth tab. Open {url} once. Press Login once. Pressing it again makes the loop worse.",
                        "more": "loop-after",
                        "suggest": "Login loop. Ask if they have two Discord sessions or a school extension blocking cookies.",
                    },
                    {
                        "id": "empty",
                        "label": "In, but no projects",
                        "fix": "You are signed in. {projects}. {github}. If the list is empty, this Discord may not be the one linked to your class account. Do not make a new project yet.",
                        "suggest": "Signed in but no projects. Compare Discord IDs before they create a duplicate.",
                    },
                ],
            },
            {
                "id": "loop-after",
                "ask": "After closing the tabs and trying once, what happened?",
                "choices": [
                    {"id": "worked", "label": "It worked", "fix": "Stay in that tab. You do not need to log in again today."},
                    {"id": "still", "label": "Still looping", "open": True, "suggest": "Login still loops after one clean try. Check cookies, a second Discord account, and whether class is on."},
                ],
            },
        ],
    },
    {
        "id": "editor",
        "label": "Editor is stuck",
        "blurb": "The page is up, but you cannot type, run, or see files.",
        "hints": ("can't type", "cant type", "won't run", "wont run", "frozen", "cursor"),
        "intro": "The editor is up, so this is not a class-off problem.\n{class_line}",
        "steps": [
            {
                "id": "what",
                "ask": "What is stuck?",
                "choices": [
                    {
                        "id": "type",
                        "label": "I cannot type",
                        "fix": "Click inside the editor. Press Esc to close a popup. Click the file name in the list, then click the code. A lesson panel can steal the cursor.",
                        "suggest": "Cursor was not in the editor, or a modal was open.",
                    },
                    {
                        "id": "run",
                        "label": "Run does nothing",
                        "fix": "Use the Run button once. If it says the port is in use, stop the old run, then start one. Do not open a second copy.",
                        "more": "run-after",
                        "suggest": "Run failed. Ask for the exact message. Port-in-use means an old run is still up.",
                    },
                    {
                        "id": "frozen",
                        "label": "The tab froze",
                        "fix": "Refresh once. Your files are on the class computer. If the laptop fan is loud, close other tabs. This is not Codespaces.",
                        "suggest": "Tab froze. Confirm the project is still on their account before they start over.",
                    },
                    {"id": "files", "label": "Files disappeared", "switch": "work"},
                ],
            },
            {
                "id": "run-after",
                "kind": "text",
                "ask": "Paste what Run said",
                "hint": "A sentence or the red text is enough.",
                "then": "decode",
            },
        ],
    },
    {
        "id": "crash",
        "label": "Laptop is struggling",
        "blurb": "Fan, freeze, or a Codespaces tab eating the computer.",
        "hints": ("crash", "fan", "slow", "freeze", "laptop", "codespace", "hot"),
        "intro": "Your code runs on the class computer. The laptop only shows a browser tab.\n{class_line}",
        "steps": [
            {
                "id": "what",
                "ask": "What is the computer doing?",
                "choices": [
                    {
                        "id": "fan",
                        "label": "Fan is loud",
                        "fix": "Close extra tabs. Keep one tab on {url}. Do not open Codespaces. That old setup ran the editor on your laptop.",
                        "suggest": "Laptop was doing too much. Make sure they are on the class link, not Codespaces.",
                    },
                    {
                        "id": "freeze",
                        "label": "It froze",
                        "fix": "Force-quit the browser if you have to. Open {url} again and pick the same project. Do not create a new one. {projects}",
                        "suggest": "Laptop froze. Open the existing project. Do not let them recreate it.",
                    },
                    {
                        "id": "codespaces",
                        "label": "Codespaces is open",
                        "fix": "Close Codespaces. It is not class anymore, and it is what was crashing computers. Use {url} while class is on.",
                        "suggest": "They were still in Codespaces. Point them at the class link.",
                    },
                    {
                        "id": "still",
                        "label": "One tab still crashes",
                        "open": True,
                        "suggest": "One class tab still crashes the laptop. Ask the browser and whether a school extension is injected.",
                    },
                ],
            }
        ],
    },
    {
        "id": "work",
        "label": "Lost work",
        "blurb": "A project or a save is missing.",
        "hints": ("lost", "gone", "deleted", "disappeared", "where is my", "save"),
        "intro": "Do not make a new project yet. {projects}\n{github}\n{class_line}",
        "steps": [
            {
                "id": "which",
                "ask": "Which project?",
                "dynamic": "projects",
                "goto": "when",
                "extra": [{"id": "missing", "label": "It is not in that list", "goto": "name"}],
            },
            {
                "id": "name",
                "kind": "text",
                "ask": "What is the project called?",
                "hint": "The name you remember is enough.",
                "goto": "when",
            },
            {
                "id": "when",
                "ask": "When did you last see it?",
                "choices": [
                    {
                        "id": "before-off",
                        "label": "Before class turned off",
                        "fix": "{class_line}\nThe save from before shutdown is the one that counts. {github}. If GitHub is connected, the copy is in that repo. If not, a teacher can open the class copy. Do not start a second project.",
                        "suggest": "Look up that project on the class computer and GitHub before telling them it is gone.",
                    },
                    {
                        "id": "mid",
                        "label": "It was there this class",
                        "fix": "Go to Home and open the same project. A new project with the same idea does not bring the old files back. {projects}",
                        "suggest": "They may have opened a second copy. Open the older project from the account.",
                    },
                    {
                        "id": "pushed",
                        "label": "After I connected GitHub",
                        "fix": "{github}. If it is connected, look at that GitHub account for the repo. If the push failed, the class copy can still be there.",
                        "suggest": "Check GitHub and the class copy. Do not ask them for a token.",
                    },
                ],
            },
        ],
    },
    {
        "id": "github",
        "label": "GitHub",
        "blurb": "Connect, push, or find the code after class.",
        "hints": ("github", "repo", "push", "sync", "token"),
        "intro": "{github}. A teacher never needs your password or a token.\n{class_line}",
        "steps": [
            {
                "id": "what",
                "ask": "What went wrong?",
                "choices": [
                    {
                        "id": "connect",
                        "label": "It is not connected",
                        "fix": "In the IDE, open your account and press Connect GitHub. Approve only the TeachForth app. If it asks you to paste a token in Discord, stop. That is not the way.",
                        "suggest": "Walk them through Connect GitHub. Never take a token in chat.",
                    },
                    {
                        "id": "push",
                        "label": "Push failed",
                        "fix": "{class_line}\nIf it says authentication, use Connect GitHub again. If it says nothing to commit, there was no new save. If class is off, the push waits until class is back.",
                        "more": "push-text",
                        "suggest": "Read the push error. Reconnect GitHub if it is auth. Do not take a personal token.",
                    },
                    {
                        "id": "find",
                        "label": "I cannot find the repo",
                        "fix": "{github}. {projects}. The repo name matches the project. If GitHub is not connected, it was never pushed. The class copy can still exist.",
                        "suggest": "Confirm GitHub is connected, then find the repo. The class copy may be the only copy.",
                    },
                    {
                        "id": "password",
                        "label": "It asked for a password",
                        "fix": "Do not send a password or token here. GitHub login happens in the GitHub window from the Connect button. A teacher cannot use your password.",
                        "suggest": "They were about to paste a secret. Stop that and use the Connect button.",
                    },
                ],
            },
            {
                "id": "push-text",
                "kind": "text",
                "ask": "Paste the push message",
                "hint": "The red or grey line from GitHub is enough. Do not include a token.",
                "then": "decode",
            },
        ],
    },
    {
        "id": "lesson",
        "label": "Stuck on a lesson",
        "blurb": "The idea, the instructions, or a result that looks wrong.",
        "hints": ("lesson", "chapter", "stuck", "homework", "don't understand", "dont understand", "exercise"),
        "intro": "Being stuck is a normal ticket. {chapters}",
        "steps": [
            {
                "id": "kind",
                "ask": "What kind of stuck?",
                "choices": [
                    {
                        "id": "idea",
                        "label": "I don't understand it",
                        "goto": "which",
                        "suggest": "Explain the step. Do not just debug.",
                    },
                    {"id": "error", "label": "My code errors", "switch": "error"},
                    {
                        "id": "output",
                        "label": "Wrong output",
                        "goto": "expected",
                        "suggest": "Compare expected output with what the program printed.",
                    },
                    {
                        "id": "panel",
                        "label": "I can't find the instructions",
                        "fix": "Open the lesson panel in the IDE, next to the editor. The instructions are not in an old doc or a Codespaces tab.",
                        "suggest": "They could not find the lesson panel.",
                    },
                ],
            },
            {
                "id": "which",
                "kind": "text",
                "ask": "Which lesson, and what part is confusing?",
                "hint": "The lesson name and the step are enough.",
                "then": "open",
                "priority": "normal",
                "suggest": "Explain that step in plain language. They said they do not understand it.",
            },
            {
                "id": "expected",
                "kind": "text",
                "ask": "What did you expect, and what did it do?",
                "hint": "One sentence each is enough.",
                "then": "open",
                "suggest": "Compare the expected result with the actual output. The code may be running the wrong file.",
            },
        ],
    },
    {
        "id": "error",
        "label": "I have an error",
        "blurb": "Paste the red text. I'll read the common classroom ones.",
        "hints": ("error", "syntax", "traceback", "exception", "red text", "undefined"),
        "intro": "Paste the error. I can clear the common ones. A teacher gets the exact text if I cannot.",
        "steps": [
            {
                "id": "paste",
                "kind": "text",
                "ask": "Paste the error",
                "hint": "The line that names the error is the useful part. Leave out any token or password.",
                "then": "decode",
            }
        ],
    },
    {
        "id": "pair",
        "label": "Who is my teacher",
        "blurb": "Pairing, a missing teacher, or a handoff.",
        "hints": ("teacher", "pair", "who's my", "whos my", "nobody is here", "partner"),
        "intro": "Teachers are assigned by who is free. Past work still stays on your account.\n{pair}",
        "steps": [
            {
                "id": "need",
                "ask": "What do you need?",
                "choices": [
                    {
                        "id": "who",
                        "label": "Who am I with?",
                        "fix": "{pair}. If that says no pair yet, you are not forgotten. The next free teacher can open your work from a ticket. {projects}",
                        "suggest": "Tell them the current pair, or assign one. Their projects are already on the account.",
                    },
                    {
                        "id": "gone",
                        "label": "My teacher is not here",
                        "fix": "{class_line}\n{pair}. You can keep working if class is on. This ticket reaches whoever is on duty, not only that one teacher.",
                        "suggest": "Their assigned teacher is away. Another teacher can take the ticket. Do not make them wait on one person.",
                    },
                    {
                        "id": "wrong",
                        "label": "This is the wrong person",
                        "goto": "expected",
                        "suggest": "They expected a different teacher. Check the pair before changing it.",
                    },
                    {
                        "id": "handoff",
                        "label": "I need a different teacher",
                        "open": True,
                        "priority": "normal",
                        "suggest": "They asked for a handoff. Keep the old notes. Any on-duty teacher can reply.",
                    },
                ],
            },
            {
                "id": "expected",
                "kind": "text",
                "ask": "Who did you expect?",
                "hint": "A first name is enough.",
                "then": "open",
                "suggest": "Check the pair against the name they expected. Do not drop the ticket.",
            },
        ],
    },
    {
        "id": "start",
        "label": "How do I start",
        "blurb": "New project, language, or where your work lives.",
        "hints": ("how do i", "how to", "new project", "where do i", "start"),
        "intro": "Your work lives on the class computer. {projects}",
        "steps": [
            {
                "id": "want",
                "ask": "What are you trying to do?",
                "choices": [
                    {
                        "id": "new",
                        "label": "Start a project",
                        "fix": "From Home, press New project and use the language the lesson names. If you already have one, open that. A second copy splits your work. {projects}",
                        "suggest": "They wanted a new project. Check they do not already have one for this lesson.",
                    },
                    {
                        "id": "language",
                        "label": "Which language?",
                        "fix": "Use the language written on the lesson. A Python lesson in a JavaScript project will not run the examples. {chapters}",
                        "suggest": "Point them at the lesson language. Wrong-language projects are a common dead end.",
                    },
                    {
                        "id": "where",
                        "label": "Where is my stuff?",
                        "fix": "After login, Home lists your projects. {projects}. {github}. The org website is not the editor. The editor is {url} while class is on.",
                        "suggest": "They could not find Home. Send the class link if class is on.",
                    },
                    {
                        "id": "share",
                        "label": "Show a teacher",
                        "fix": "You do not send a zip. Open a ticket, name the project, and a teacher can open your account. Connect GitHub if you want a copy after class. {github}",
                        "suggest": "They want a teacher to see the work. Open the named project. Do not ask for a file upload.",
                    },
                ],
            }
        ],
    },
    {
        "id": "link",
        "label": "Where is the link",
        "blurb": "Class link, an old tab, or a Codespaces bookmark.",
        "hints": ("link", "url", "bookmark", "where is class", "address"),
        "intro": "{class_line}\nThe editor, while class is on, is {url}",
        "steps": [
            {
                "id": "tried",
                "ask": "What did you open?",
                "choices": [
                    {
                        "id": "bookmark",
                        "label": "A bookmark",
                        "fix": "Bookmarks often point at old Codespaces. Close that. Open {url}. {class_line}",
                        "suggest": "Stale bookmark. Send the class link.",
                    },
                    {
                        "id": "sent",
                        "label": "An old message",
                        "fix": "Use the latest class link, not a link from another week. Right now that is {url}. {class_line}",
                        "suggest": "They used an old message. Send the current link.",
                    },
                    {
                        "id": "site",
                        "label": "The TeachForth site",
                        "fix": "The org site is not the editor. While class is on, the editor is {url}. {class_line}",
                        "suggest": "They opened the marketing site. Send the class link.",
                    },
                    {
                        "id": "none",
                        "label": "I have no link",
                        "fix": "Open {url}. If class is off, that page will say so. You did not miss a secret link.",
                        "suggest": "They had no link. Class status matters more than a new URL.",
                    },
                ],
            }
        ],
    },
    {
        "id": "feedback",
        "label": "Lesson was confusing",
        "blurb": "Tell teachers what to fix in the lesson. This is not an emergency.",
        "hints": ("confusing", "feedback", "the lesson is wrong", "typo", "instructions are"),
        "intro": "This goes to teachers as lesson feedback, not as a blocked-student emergency.",
        "steps": [
            {
                "id": "note",
                "kind": "text",
                "ask": "Which lesson, and what was confusing?",
                "hint": "A lesson name and one sentence is enough.",
                "then": "open",
                "priority": "low",
                "suggest": "Lesson feedback. Fix the instructions later. They are not blocked unless they also say so.",
            }
        ],
    },
]

BY_ID = {item["id"]: item for item in PLUGINS}
STATUS = {
    "need": "Your teacher needs one more detail. Reply here with it.",
    "onit": "A teacher is looking at this now.",
    "solved": "This is marked solved. Reply here if it is not.",
}


class _Safe(dict):
    def __missing__(self, key):
        return ""


def plugin(plugin_id):
    return BY_ID.get(plugin_id)


def label(plugin_id):
    item = plugin(plugin_id)
    return item["label"] if item else "Help"


def match(text):
    low = (text or "").lower()
    scored = []
    for item in PLUGINS:
        score = sum(1 for hint in item["hints"] if hint in low)
        if score:
            scored.append((score, item["id"]))
    scored.sort(reverse=True)
    if not scored:
        return ""
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]
    return ""


def fill(text, state):
    data = _Safe(state or {})
    data["url"] = CLASS_URL
    try:
        return str(text or "").format_map(data)
    except (ValueError, IndexError):
        return str(text or "")


def checked(state):
    bits = [state.get("class_line") or "Class status did not answer"]
    if state.get("linked") is False:
        bits.append("This Discord is not linked to an IDE account")
    elif state.get("role"):
        bits.append(str(state["role"]))
    if state.get("github"):
        bits.append(state["github"])
    if state.get("pair"):
        bits.append(state["pair"])
    return " · ".join(bit for bit in bits if bit)


def priority_for(state):
    phase = state.get("class_phase") or ""
    plugin_id = state.get("plugin") or ""
    if plugin_id == "feedback":
        return "low"
    if plugin_id == "page" and phase == "off":
        return "low"
    if phase in {"on", "starting"} and plugin_id in {"page", "login", "editor", "crash", "lesson", "error"}:
        return "high"
    return "normal"


def step_def(state):
    item = plugin(state.get("plugin"))
    if not item:
        return None
    for step in item["steps"]:
        if step["id"] == state.get("step"):
            return step
    return item["steps"][0]


def begin(plugin_id, first, ctx):
    item = plugin(plugin_id) or PLUGINS[-1]
    state = {
        "plugin": item["id"],
        "step": item["steps"][0]["id"],
        "awaiting": "choice",
        "trail": [],
        "first": (first or "")[:500],
        "status": "guiding",
        "url": CLASS_URL,
    }
    state.update(ctx or {})
    state["priority"] = priority_for(state)
    return state


def home_prompt(first=""):
    heard = f"You said: {first[:180]}\n\n" if first else ""
    return {
        "title": "What broke?",
        "body": heard + "Pick the closest one. I check class and your account, try the usual fix, then open a ticket only if you still need a teacher.",
        "footer": "TeachForth Help",
        "select": {
            "custom_id": "tfp:home",
            "placeholder": "Pick a helper",
            "options": [
                {"id": item["id"], "label": item["label"], "desc": item["blurb"][:100]}
                for item in PLUGINS
            ],
        },
    }


def prompt(state):
    item = plugin(state.get("plugin"))
    if not item:
        return home_prompt(state.get("first"))
    if state.get("awaiting") == "fix":
        return {
            "title": state.get("error_title") or "Try this",
            "body": state.get("last_fix") or "Try that once.",
            "footer": f"TeachForth Help · {item['label']}",
            "buttons": [
                {"id": "tfp:fixed", "label": "That fixed it", "style": "success"},
                {"id": "tfp:still", "label": "Still broken", "style": "secondary"},
                {"id": "tfp:restart", "label": "Wrong problem", "style": "secondary"},
            ],
        }
    step = step_def(state)
    body = fill(step.get("hint") or step.get("ask") or "", state)
    if state.get("step") == item["steps"][0]["id"] and not state.get("trail"):
        body = fill(item.get("intro") or "", state) + "\n\n" + checked(state) + "\n\n" + body
    shown = _choices(step, state)
    if step.get("kind") == "text" or (step.get("dynamic") == "projects" and not shown):
        state["awaiting"] = "text"
        return {
            "title": step["ask"],
            "body": body if step.get("kind") == "text" else "I cannot see a project list yet. Type the name you remember.",
            "footer": f"TeachForth Help · {item['label']}",
            "buttons": [{"id": "tfp:restart", "label": "Wrong problem", "style": "secondary"}],
        }
    state["awaiting"] = "choice"
    return {
        "title": step["ask"],
        "body": body,
        "footer": f"TeachForth Help · {item['label']}",
        "select": {
            "custom_id": "tfp:step",
            "placeholder": "Choose one",
            "options": [{"id": choice["id"], "label": choice["label"], "desc": ""} for choice in shown],
        },
        "buttons": [{"id": "tfp:restart", "label": "Wrong problem", "style": "secondary"}],
    }


def _choices(step, state):
    if step.get("dynamic") == "projects":
        names = list(state.get("project_names") or [])[:20]
        if not names:
            return []
        state["project_ids"] = {f"p{index}": name for index, name in enumerate(names)}
        choices = [{"id": f"p{index}", "label": names[index][:80], "goto": step.get("goto") or "when"} for index in range(len(names))]
        choices.extend(step.get("extra") or [])
        return choices
    return list(step.get("choices") or [])


def _choice(step, state, choice_id):
    for choice in _choices(step, state):
        if choice["id"] == choice_id:
            return choice
    return None


def apply_choice(state, choice_id):
    step = step_def(state)
    choice = _choice(step, state, choice_id) if step else None
    if choice is None:
        return "again", None
    state.setdefault("trail", []).append({"q": step.get("ask") or "Choice", "a": choice["label"]})
    if choice.get("switch"):
        return "switch", choice["switch"]
    if choice.get("open"):
        state["suggest"] = choice.get("suggest") or state.get("suggest") or ""
        state["priority"] = choice.get("priority") or priority_for(state)
        return "open", None
    if choice.get("goto"):
        state["step"] = choice["goto"]
        state["awaiting"] = "choice"
        state["suggest"] = choice.get("suggest") or state.get("suggest") or ""
        return "step", None
    state["last_fix"] = fill(choice.get("fix") or "Try that once.", state)
    state["suggest"] = choice.get("suggest") or ""
    state["awaiting"] = "fix"
    state["pending"] = choice.get("more")
    state.pop("error_title", None)
    return "fix", state["last_fix"]


def apply_text(state, text):
    step = step_def(state)
    if step is None:
        return "again", None
    clean = (text or "").strip()[:800]
    if len(clean) < 2:
        return "again", None
    state.setdefault("trail", []).append({"q": step.get("ask") or "Answer", "a": clean})
    if step.get("dynamic") == "projects":
        state["step"] = step.get("goto") or "when"
        state["awaiting"] = "choice"
        return "step", None
    if step.get("then") == "decode":
        title, body, suggest = decode(clean)
        state["error_title"] = title
        state["last_fix"] = body
        state["suggest"] = suggest
        state["awaiting"] = "fix"
        state["pending"] = None
        return "fix", body
    if step.get("then") == "open" or step.get("open"):
        state["suggest"] = step.get("suggest") or ""
        state["priority"] = step.get("priority") or priority_for(state)
        return "open", None
    if step.get("goto"):
        state["step"] = step["goto"]
        state["awaiting"] = "choice"
        return "step", None
    state["priority"] = priority_for(state)
    return "open", None


def apply_still(state):
    pending = state.get("pending")
    if pending and plugin(state.get("plugin")):
        state["step"] = pending
        state["awaiting"] = "choice"
        state["pending"] = None
        return "step", None
    state["priority"] = state.get("priority") or priority_for(state)
    return "open", None


def decode(text):
    low = text.lower()
    rules = [
        ("syntax", "Syntax error", "A character is missing or extra. Read the line number. Check quotes, parentheses, and colons. Fix that line only, then run again."),
        ("indentation", "Indent error", "Python cares about spaces. Line the block up with the line above it. Do not mix tabs and spaces. The lesson uses spaces."),
        ("not defined", "Unknown name", "That name is spelled differently from the one you created, or you are running the wrong file. Check the lesson spelling."),
        ("nameerror", "Unknown name", "That name is spelled differently from the one you created, or you are running the wrong file."),
        ("typeerror", "Wrong type of value", "A number and text got mixed, or a function got the wrong kind of input. Look at the line number and the values just above it."),
        ("no module named", "Missing module", "That library is not in this project. Tell a teacher the module name. Do not install random packages."),
        ("cannot find module", "Missing module", "That library is not in this project. Tell a teacher the module name. Do not install random packages."),
        ("modulenotfounderror", "Missing module", "That library is not in this project. Tell a teacher the module name."),
        ("is not a function", "Not a function", "You called something that is not a function. Check the spelling against the lesson."),
        ("address already in use", "Port in use", "An old run is still going. Stop it, then press Run once."),
        ("eaddrinuse", "Port in use", "An old run is still going. Stop it, then press Run once."),
        ("authentication failed", "GitHub login failed", "Do not paste a token. Use Connect GitHub in the IDE and approve TeachForth again."),
        ("support for password", "GitHub login failed", "GitHub will not take a password here. Use Connect GitHub in the IDE."),
        ("repository not found", "Repo not found", "The repo is missing, or GitHub is connected to a different account. Check Connect GitHub before making a new repo."),
        ("nothing to commit", "Nothing new to save", "GitHub has the last save. Edit the project, then push again."),
        ("permission denied", "Blocked by the class computer", "That action is blocked on purpose. Do not look for a way around it. A teacher can see the project."),
        ("failed to fetch", "The page could not reach class", "Class may be off, or the tab is stale. Close it and open the class link once."),
        ("404", "Page not found", "That address is old. Use the class link, not a Codespaces bookmark."),
    ]
    for needle, title, body in rules:
        if needle in low:
            return title, body + "\n\nIf that was not it, a teacher gets the exact text you pasted.", f"Known error: {title}. Confirm the line number with them."
    return "I don't recognize that one", "I don't know this error well enough to guess. A teacher should see the exact text. Leave out any password or token.", "Unknown error. Read the pasted text with them. Do not ask them to install packages."


def case_lines(state):
    trail = state.get("trail") or []
    walked = "\n".join(f"{item.get('q')}: {item.get('a')}" for item in trail[-8:]) or "No answers yet."
    return [
        ("Helper", label(state.get("plugin"))),
        ("Priority", state.get("priority") or priority_for(state)),
        ("Status", state.get("status") or "open"),
        ("Checked", checked(state)),
        ("What they tried", walked),
        ("First message", state.get("first") or "No text."),
        ("Do this next", state.get("suggest") or "Reply in this thread. Their answers are above."),
        ("Last fix shown", state.get("last_fix") or "None."),
    ]


def summary_text(state):
    lines = [f"{name}: {text}" for name, text in case_lines(state)]
    return "\n".join(lines)[:1800]


def fixes_for(state):
    item = plugin(state.get("plugin"))
    found = []
    if state.get("last_fix"):
        found.append(("last", "Resend the last step", state["last_fix"]))
    if not item:
        return found
    for step in item["steps"]:
        for choice in step.get("choices") or []:
            if choice.get("fix"):
                found.append((choice["id"], choice["label"], fill(choice["fix"], state)))
    return found[:12]


def card_html(state, escape):
    if not state:
        return ""
    rows = "".join(
        f"<p><b>{escape(name)}</b><br>{escape(text)}</p>" for name, text in case_lines(state)
    )
    return f'<div class="card"><h2>Case</h2>{rows}</div>'


def library_html(stats, escape):
    by = (stats or {}).get("by") or {}
    cards = []
    for item in PLUGINS:
        row = by.get(item["id"]) or {}
        asks = "".join(f"<li>{escape(step.get('ask') or step['id'])}</li>" for step in item["steps"])
        cards.append(
            f"<div class='card'><h2>{escape(item['label'])}</h2><p>{escape(item['blurb'])}</p>"
            f"<p>Solved without a teacher: {int(row.get('fixed') or 0)}. Opened: {int(row.get('opened') or 0)}.</p>"
            f"<ul>{asks}</ul></div>"
        )
    return "".join(cards)


def check():
    errors = []
    for item in PLUGINS:
        ids = {step["id"] for step in item["steps"]}
        for step in item["steps"]:
            for choice in step.get("choices") or []:
                more = choice.get("more") or choice.get("goto")
                if more and more not in ids:
                    errors.append(f"{item['id']} {choice['id']} -> {more}")
                if choice.get("switch") and choice["switch"] not in BY_ID:
                    errors.append(f"switch {choice['switch']}")
            goto = step.get("goto")
            if goto and goto not in ids:
                errors.append(f"{item['id']} step {step['id']} -> {goto}")
        home_prompt()
        sample = begin(item["id"], "test", {"class_line": "Class is on.", "github": "GitHub is not connected", "projects": "no projects yet", "pair": "No pair yet", "chapters": "none", "project_names": ["Snake"]})
        prompt(sample)
    return errors
