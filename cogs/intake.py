"""Runs the classroom troubleshooters in Discord, then opens a prepared case."""

import logging
import time
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

import teachforth_intake
import teachforth_plugins
import teachforth_portal

logger = logging.getLogger(__name__)
POWER_URL = "http://127.0.0.1:8791"
POWER_FILE = Path("/var/lib/teachforth-discord/power-secret")
COLOR = 0x7A1FA3


def _claim(interaction):
    cog = interaction.client.get_cog("Intake")
    if cog is None:
        return False
    if interaction.response.is_done() or interaction.id in cog._seen:
        return False
    cog._seen.add(interaction.id)
    return True


class GoButton(discord.ui.Button):
    def __init__(self, spec):
        style = {
            "success": discord.ButtonStyle.success,
            "primary": discord.ButtonStyle.primary,
        }.get(spec.get("style"), discord.ButtonStyle.secondary)
        super().__init__(label=spec["label"][:80], custom_id=spec["id"], style=style)

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Intake")
        if cog is not None and _claim(interaction):
            await cog.on_component(interaction)


class GoSelect(discord.ui.Select):
    def __init__(self, spec):
        options = [
            discord.SelectOption(
                label=item["label"][:100],
                value=item["id"][:100],
                description=(item.get("desc") or "")[:100] or None,
            )
            for item in spec["options"][:25]
        ]
        super().__init__(
            custom_id=spec["custom_id"],
            placeholder=spec.get("placeholder") or "Choose",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Intake")
        if cog is not None and _claim(interaction):
            await cog.on_component(interaction)


class StaffStatusView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Need a detail", custom_id="tfs:need", style=discord.ButtonStyle.secondary)
    async def need(self, interaction, _button):
        if _claim(interaction):
            await _staff_status(interaction, "need")

    @discord.ui.button(label="I'm on it", custom_id="tfs:onit", style=discord.ButtonStyle.primary)
    async def onit(self, interaction, _button):
        if _claim(interaction):
            await _staff_status(interaction, "onit")

    @discord.ui.button(label="Solved", custom_id="tfs:solved", style=discord.ButtonStyle.success)
    async def solved(self, interaction, _button):
        if _claim(interaction):
            await _staff_status(interaction, "solved")


async def _staff_status(interaction, kind):
    text = teachforth_plugins.STATUS.get(kind) or "Update from your teacher."
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("That is for the ticket channel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    bot = interaction.client
    try:
        thread = await bot.threads.find(channel=interaction.channel)
    except Exception:
        thread = None
    if thread is None or getattr(thread, "recipient", None) is None:
        await interaction.followup.send("This channel is not an open ticket.", ephemeral=True)
        return
    teachforth_intake.set_status(thread.recipient.id, kind)
    try:
        await thread.reply(
            teachforth_portal.fake_message(interaction.user, thread.channel, text),
            content=text,
        )
    except Exception:
        logger.warning("Status update did not reach the student")
        await interaction.followup.send("Saved here, but the student did not get the DM.", ephemeral=True)
        return
    await interaction.followup.send("Sent to the student.", ephemeral=True)


class Intake(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._class = {}
        self._class_at = 0.0
        self._seen = set()

    async def cog_load(self):
        self.bot.add_view(StaffStatusView())

    async def gate(self, message):
        if message.author.bot:
            return False
        text = (message.content or "").strip()
        low = text.lower()
        if low in {".status", "status"}:
            await self._status(message)
            return True
        try:
            thread = await self.bot.threads.find(recipient=message.author)
        except Exception:
            thread = None
        if thread is not None:
            return False
        state = teachforth_intake.get(message.author.id)
        if state.get("opening"):
            await self._send(message.channel, "Still opening", "Give it a second, then send status.")
            return True
        if state.get("open"):
            return False
        if low in {"menu", "restart", "start over"}:
            teachforth_intake.clear(message.author.id)
            await self._show(message.channel, teachforth_plugins.home_prompt())
            return True
        if not state or state.get("plugin") not in teachforth_plugins.BY_ID:
            guessed = teachforth_plugins.match(text)
            if guessed:
                await self._start(message.channel, message.author, guessed, text)
            else:
                teachforth_intake.put(message.author.id, {"first": text[:500], "status": "picking"})
                await self._show(message.channel, teachforth_plugins.home_prompt(text))
            return True
        if state.get("awaiting") == "fix":
            if any(part in low for part in ("fixed", "it worked", "that worked", "never mind", "all good")):
                await self._fixed(message.channel, message.author.id)
                return True
            if any(part in low for part in ("teacher", "still", "didn't", "did not", "not fixed", "need help")):
                await self._still(message.channel, message.author)
                return True
        if state.get("awaiting") == "text":
            kind, _payload = teachforth_plugins.apply_text(state, text)
            await self._after(message.channel, message.author, state, kind)
            return True
        state.setdefault("trail", []).append({"q": "Also said", "a": text[:500]})
        await self._render(message.channel, message.author.id, state)
        return True

    async def on_component(self, interaction):
        cid = (interaction.data or {}).get("custom_id") or ""
        if not cid.startswith("tfp:"):
            return
        await interaction.response.defer()
        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass
        user = interaction.user
        channel = interaction.channel
        if cid == "tfp:restart":
            first = teachforth_intake.get(user.id).get("first") or ""
            teachforth_intake.clear(user.id)
            await self._show(channel, teachforth_plugins.home_prompt(first))
            return
        if cid == "tfp:fixed":
            await self._fixed(channel, user.id)
            return
        if cid == "tfp:still":
            await self._still(channel, user)
            return
        if cid == "tfp:home":
            picked = ((interaction.data or {}).get("values") or [""])[0]
            first = teachforth_intake.get(user.id).get("first") or ""
            if picked not in teachforth_plugins.BY_ID:
                await self._show(channel, teachforth_plugins.home_prompt(first))
                return
            await self._start(channel, user, picked, first)
            return
        if cid == "tfp:step":
            choice = ((interaction.data or {}).get("values") or [""])[0]
            state = teachforth_intake.get(user.id)
            kind, _payload = teachforth_plugins.apply_choice(state, choice)
            if kind == "switch":
                await self._start(channel, user, _payload, state.get("first") or "")
                return
            await self._after(channel, user, state, kind)

    async def _start(self, channel, user, plugin_id, first):
        state = teachforth_plugins.begin(plugin_id, first, await self._context(user.id))
        await self._render(channel, user.id, state)

    async def _render(self, channel, user_id, state):
        spec = teachforth_plugins.prompt(state)
        teachforth_intake.put(user_id, state)
        await self._show(channel, spec)

    async def _after(self, channel, user, state, kind):
        if kind == "open":
            teachforth_intake.put(user.id, state)
            await self._open(channel, user)
            return
        if kind == "again":
            await self._send(channel, "Need a real answer", "Use the buttons, or type a sentence.")
        await self._render(channel, user.id, state)

    async def _still(self, channel, user):
        state = teachforth_intake.get(user.id)
        kind, _payload = teachforth_plugins.apply_still(state)
        await self._after(channel, user, state, kind)

    async def _fixed(self, channel, user_id):
        state = teachforth_intake.get(user_id)
        teachforth_intake.bump("fixed", state.get("plugin"))
        teachforth_intake.clear(user_id)
        await self._send(channel, "Good", "No ticket opened. Message here again if it comes back.")

    async def _open(self, channel, user):
        state = teachforth_intake.get(user.id)
        if state.get("opening") or state.get("open"):
            return
        state["opening"] = True
        state["status"] = "with teacher"
        state["priority"] = state.get("priority") or teachforth_plugins.priority_for(state)
        teachforth_intake.put(user.id, state)
        await self._send(
            channel,
            "Opening your ticket",
            "A teacher gets the steps you already tried. Keep replying here. Send status to check.",
        )
        try:
            thread = await self.bot.threads.create(user, creator=user)
            await thread.wait_until_ready()
        except Exception:
            logger.warning("Ticket create failed", exc_info=True)
            state["opening"] = False
            teachforth_intake.put(user.id, state)
            await self._send(channel, "That got stuck", "Send one more message and I'll try again.")
            return
        if getattr(thread, "cancelled", False) or getattr(thread, "channel", None) is None:
            state["opening"] = False
            teachforth_intake.put(user.id, state)
            await self._send(channel, "That got stuck", "Send one more message and I'll try again.")
            return
        state["opening"] = False
        state["open"] = True
        state["posted"] = True
        state["channel"] = str(thread.channel.id)
        teachforth_intake.put(user.id, state)
        teachforth_intake.bump("opened", state.get("plugin"))
        await self._post_case(thread, state)

    async def _post_case(self, thread, state):
        channel = thread.channel
        plugin_id = state.get("plugin") or "help"
        name = getattr(thread.recipient, "name", "student")
        slug = "".join(ch if ch.isalnum() else "-" for ch in f"{plugin_id}-{name}".lower())[:90].strip("-")
        try:
            await channel.edit(name=slug or plugin_id, topic=teachforth_plugins.label(plugin_id)[:100])
        except discord.HTTPException:
            logger.info("Could not rename ticket channel")
        priority = (state.get("priority") or "normal").title()
        embed = discord.Embed(
            title=f"{priority} · {teachforth_plugins.label(plugin_id)}",
            color=COLOR,
            description=(state.get("suggest") or "Their answers are below.")[:4000],
        )
        embed.set_footer(text="TeachForth Help")
        for field, text in teachforth_plugins.case_lines(state):
            if field == "Do this next":
                continue
            embed.add_field(name=field, value=(text or "None")[:1000], inline=False)
        try:
            await channel.send(teachforth_plugins.summary_text(state)[:1800])
            await channel.send(embed=embed, view=StaffStatusView())
        except discord.HTTPException:
            logger.warning("Could not post the case")

    async def _status(self, message):
        state = teachforth_intake.get(message.author.id)
        try:
            thread = await self.bot.threads.find(recipient=message.author)
        except Exception:
            thread = None
        if thread is not None and getattr(thread, "channel", None):
            status = teachforth_plugins.STATUS.get(state.get("status"))
            if not status or state.get("status") == "with teacher":
                status = "A teacher has your answers. Reply here to add anything."
            await self._send(
                message.channel,
                "Your ticket is open",
                f"{teachforth_plugins.label(state.get('plugin'))}. {status}",
            )
            return
        if state.get("plugin"):
            await self._send(message.channel, "Not open yet", "Finish this helper, or send restart to pick a different one.")
            return
        await self._send(message.channel, "No open ticket", "Tell me what is wrong and I'll walk you through it.")

    async def _context(self, user_id):
        phase, class_line = await self._class_info()
        account = await self._account(user_id)
        account.update({"class_phase": phase, "class_line": class_line, "url": teachforth_plugins.CLASS_URL})
        return account

    async def _class_info(self):
        if self._class and time.time() - self._class_at < 60:
            return self._class.get("phase") or "", self._class.get("line") or ""
        try:
            secret = POWER_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return "", "I could not check whether class is on."
        if len(secret) < 16:
            return "", "I could not check whether class is on."
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{POWER_URL}/api/internal/status",
                    headers={"authorization": f"Bearer {secret}"},
                ) as res:
                    data = await res.json(content_type=None) if res.status == 200 else {}
        except (aiohttp.ClientError, TimeoutError, OSError):
            return "", "I could not check whether class is on."
        phase = (data or {}).get("phase") or ("on" if (data or {}).get("running") else "off")
        if phase == "on":
            line = "Class is on. Use the class link, not an old tab."
        elif phase == "starting":
            line = "Class is starting. Give it a minute, then open the class link once."
        elif phase == "stopping":
            line = "Class is shutting down. Save if the page is still open."
        else:
            line = "Class is off. A blank page is expected until a teacher starts it."
        self._class = {"phase": phase, "line": line}
        self._class_at = time.time()
        return phase, line

    async def _account(self, user_id):
        empty = {
            "linked": None,
            "role": "",
            "github": "GitHub status unknown",
            "projects": "Projects unknown",
            "project_names": [],
            "pair": "Pair unknown",
            "chapters": "",
        }
        owners = list(getattr(self.bot, "bot_owner_ids", []) or [])
        actor = str(owners[0]) if owners else ""
        if not actor:
            return empty
        status, data = await teachforth_portal.ide_lookup(actor, target=str(user_id))
        if status != 200 or not isinstance(data, dict):
            if status == 0:
                empty["projects"] = "Class is off, so the project list is waiting"
            return empty
        if data.get("linked") is False:
            empty["linked"] = False
            empty["github"] = "No IDE account for this Discord yet"
            empty["projects"] = "No projects, because this Discord is not linked"
            empty["pair"] = "No pair yet"
            return empty
        person = data.get("person") or {}
        names = [str(item.get("title") or "") for item in (data.get("projects") or []) if item.get("title")]
        pairs = data.get("pairs") or []
        pair = "No pair on the account yet"
        if pairs:
            pair = f"{pairs[0].get('teacher') or 'Teacher'} with {pairs[0].get('student') or 'student'}"
        chapters = ", ".join(str(item.get("name") or "") for item in (data.get("chapters") or [])[:4])
        return {
            "linked": True,
            "role": person.get("role") or "",
            "github": "GitHub is connected" if person.get("githubLinked") else "GitHub is not connected",
            "projects": ", ".join(names[:6]) if names else "No projects yet",
            "project_names": names[:20],
            "pair": pair,
            "chapters": f"Chapters: {chapters}" if chapters else "",
        }

    async def _show(self, channel, spec):
        view = discord.ui.View(timeout=None)
        if spec.get("select"):
            view.add_item(GoSelect(spec["select"]))
        for button in spec.get("buttons") or []:
            view.add_item(GoButton(button))
        await self._send(channel, spec.get("title") or "TeachForth Help", spec.get("body") or "", view or None, spec.get("footer"))

    async def _send(self, channel, title, description, view=None, footer="TeachForth Help"):
        if channel is None:
            return
        embed = discord.Embed(title=title[:256], description=(description or "")[:4000], color=COLOR)
        embed.set_footer(text=footer or "TeachForth Help")
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            logger.warning("Help reply failed")

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        if not cid.startswith("tfp:"):
            return
        if not _claim(interaction):
            return
        await self.on_component(interaction)


async def setup(bot):
    await bot.add_cog(Intake(bot))
