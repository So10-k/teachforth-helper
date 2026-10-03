"""Guided ticket opener. The student answers before a teacher is pinged."""

import logging
import time
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

import teachforth_intake
import teachforth_portal

logger = logging.getLogger(__name__)
POWER_URL = "http://127.0.0.1:8791"
POWER_FILE = Path("/var/lib/teachforth-discord/power-secret")


class TopicView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, label in teachforth_intake.TOPICS:
            self.add_item(TopicButton(key, label))


class TopicButton(discord.ui.Button):
    def __init__(self, key, label):
        super().__init__(label=label, custom_id=f"tfi:topic:{key}", style=discord.ButtonStyle.primary)
        self.key = key

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Intake")
        if cog is None:
            return
        await cog.choose(interaction, self.key)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="That fixed it", custom_id="tfi:fixed", style=discord.ButtonStyle.success)
    async def fixed(self, interaction, _button):
        cog = interaction.client.get_cog("Intake")
        if cog is not None:
            await cog.finish_fixed(interaction)

    @discord.ui.button(label="I still need a teacher", custom_id="tfi:teacher", style=discord.ButtonStyle.secondary)
    async def teacher(self, interaction, _button):
        cog = interaction.client.get_cog("Intake")
        if cog is not None:
            await cog.finish_teacher(interaction)


class Intake(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._class = ""
        self._class_at = 0.0

    async def cog_load(self):
        self.bot.add_view(TopicView())
        self.bot.add_view(HelpView())

    async def gate(self, message):
        if message.author.bot:
            return False
        text = (message.content or "").strip()
        if text.lower() in {".status", "status"}:
            await self._status(message)
            return True
        try:
            thread = await self.bot.threads.find(recipient=message.author)
        except Exception:
            thread = None
        if thread is not None:
            return False
        state = teachforth_intake.get(message.author.id)
        if state.get("open"):
            return False
        step = state.get("step")
        if not step:
            state = {
                "step": "topic",
                "first": (text or "[sent a file]")[:500],
                "updated": teachforth_intake.now(),
            }
            teachforth_intake.put(message.author.id, state)
            extra = " Send the file again after the ticket opens." if message.attachments else ""
            await self._ask_topic(message.channel, text, extra)
            return True
        if step == "topic":
            topic = teachforth_intake.guess_topic(text) or "other"
            await self._offer_help(message.channel, message.author.id, topic)
            return True
        if step == "article":
            if teachforth_intake.means_fixed(text):
                await self._solved(message.channel, message.author.id)
                return True
            if teachforth_intake.means_teacher(text) or text:
                await self._ask_trying(message.channel, message.author.id)
                return True
            return True
        if step == "trying":
            if len(text) < 3:
                await self._send(message.channel, "A bit more", "What were you trying to do? One sentence is enough.")
                return True
            state["trying"] = text[:500]
            state["step"] = "happened"
            state["updated"] = teachforth_intake.now()
            teachforth_intake.put(message.author.id, state)
            await self._send(
                message.channel,
                "What happened?",
                "What happened instead? Paste any error you saw. Then a teacher gets the whole thing.",
            )
            return True
        if step == "happened":
            if len(text) < 3:
                await self._send(message.channel, "What happened?", "Add a sentence, or paste the error.")
                return True
            state["happened"] = text[:800]
            state["open"] = True
            state["step"] = "open"
            state["updated"] = teachforth_intake.now()
            teachforth_intake.put(message.author.id, state)
            await self._send(
                message.channel,
                "Opening your ticket",
                "A teacher gets what you wrote. Keep replying in this chat. Send `status` anytime to check.",
            )
            return False
        return False

    async def choose(self, interaction, topic):
        if topic not in teachforth_intake.TOPIC_IDS:
            return
        await interaction.response.defer()
        await self._offer_help(interaction.channel, interaction.user.id, topic)

    async def finish_fixed(self, interaction):
        await interaction.response.defer()
        await self._solved(interaction.channel, interaction.user.id)

    async def finish_teacher(self, interaction):
        await interaction.response.defer()
        await self._ask_trying(interaction.channel, interaction.user.id)

    async def _offer_help(self, channel, user_id, topic):
        title, body = teachforth_intake.ARTICLES.get(topic, teachforth_intake.ARTICLES["other"])
        class_line = await self._class_line() if topic in {"ide", "login", "work"} else ""
        state = teachforth_intake.get(user_id)
        state.update({
            "step": "article",
            "topic": topic,
            "article": True,
            "class_line": class_line,
            "updated": teachforth_intake.now(),
        })
        teachforth_intake.put(user_id, state)
        extra = f"\n\n{class_line}" if class_line else ""
        await self._send(
            channel,
            title,
            body + extra + "\n\nIf that fixed it, you can stop here. If not, a teacher gets your answers next.",
            HelpView(),
        )

    async def _ask_trying(self, channel, user_id):
        state = teachforth_intake.get(user_id)
        if not state.get("topic"):
            state["topic"] = "other"
        state["step"] = "trying"
        state["updated"] = teachforth_intake.now()
        teachforth_intake.put(user_id, state)
        await self._send(channel, "What were you trying to do?", "One sentence. A teacher reads this before they reply.")

    async def _solved(self, channel, user_id):
        teachforth_intake.clear(user_id)
        await self._send(channel, "Good", "No ticket opened. Message here again if it comes back.")

    async def _ask_topic(self, channel, text, extra=""):
        heard = f"You said: {text[:180]}\n\n" if text else ""
        await self._send(
            channel,
            "What do you need?",
            heard + "Pick the closest one. I'll try the usual fix before a teacher is pulled in." + extra,
            TopicView(),
        )

    async def _status(self, message):
        state = teachforth_intake.get(message.author.id)
        try:
            thread = await self.bot.threads.find(recipient=message.author)
        except Exception:
            thread = None
        if thread is not None and getattr(thread, "channel", None):
            topic = teachforth_intake.topic_label(state.get("topic"))
            await self._send(
                message.channel,
                "Your ticket is open",
                f"{topic}. A teacher can already see it. Reply here to add anything.",
            )
            return
        if state.get("step") and not state.get("open"):
            await self._send(message.channel, "Not open yet", "Finish the questions and a teacher gets it.")
            return
        await self._send(message.channel, "No open ticket", "Tell me what is wrong and I'll walk you through it.")

    async def _class_line(self):
        if self._class and time.time() - self._class_at < 60:
            return self._class
        try:
            secret = POWER_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if len(secret) < 16:
            return ""
        try:
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{POWER_URL}/api/internal/status",
                    headers={"authorization": f"Bearer {secret}"},
                ) as res:
                    data = await res.json(content_type=None) if res.status == 200 else {}
        except (aiohttp.ClientError, TimeoutError, OSError):
            return ""
        phase = (data or {}).get("phase") or ("on" if (data or {}).get("running") else "off")
        if phase in {"on", "starting"}:
            line = "Class is on. Use the class link, not an old tab."
        elif phase == "stopping":
            line = "Class is shutting down. Save if you still have the page open."
        else:
            line = "Class is off right now. A blank page is expected until a teacher starts it."
        self._class = line
        self._class_at = time.time()
        return line

    async def _send(self, channel, title, description, view=None):
        if channel is None:
            return
        embed = discord.Embed(title=title, description=description[:4000], color=teachforth_intake.COLOR)
        embed.set_footer(text="TeachForth Help")
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            logger.warning("Intake reply failed")

    @commands.Cog.listener()
    async def on_thread_ready(self, thread, creator, category, initial_message):
        recipient = getattr(thread, "recipient", None)
        channel = getattr(thread, "channel", None)
        if recipient is None or channel is None:
            return
        state = teachforth_intake.get(recipient.id)
        if not state.get("open") or state.get("posted"):
            return
        state["posted"] = True
        state["channel"] = str(channel.id)
        teachforth_intake.put(recipient.id, state)
        topic = state.get("topic") or "other"
        slug = f"{topic}-{getattr(recipient, 'name', 'student')}".lower().replace(" ", "-")[:90]
        try:
            await channel.edit(name=slug, topic=teachforth_intake.topic_label(topic)[:100])
        except discord.HTTPException:
            logger.info("Could not rename ticket channel")
        embed = discord.Embed(
            title=f"Case · {teachforth_intake.topic_label(topic)}",
            color=teachforth_intake.COLOR,
        )
        embed.set_footer(text="TeachForth Help")
        for name, text in teachforth_intake.brief_lines(state):
            embed.add_field(name=name, value=text[:1000], inline=False)
        ide = await self._ide_line(recipient.id)
        if ide:
            embed.add_field(name="IDE", value=ide[:1000], inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Could not post the case card")

    async def _ide_line(self, user_id):
        owners = list(getattr(self.bot, "bot_owner_ids", []) or [])
        actor = str(owners[0]) if owners else ""
        if not actor:
            return ""
        status, data = await teachforth_portal.ide_lookup(actor, target=str(user_id))
        if status != 200 or not isinstance(data, dict) or data.get("linked") is False:
            if status == 0:
                return "Class is off, so the account panel is waiting."
            if data.get("linked") is False:
                return "This Discord account is not linked to an IDE account."
            return ""
        person = data.get("person") or {}
        github = "GitHub connected" if person.get("githubLinked") else "GitHub not connected"
        projects = ", ".join(
            str(item.get("title") or "") for item in (data.get("projects") or [])[:4]
        ) or "no projects"
        pair = ""
        pairs = data.get("pairs") or []
        if pairs:
            pair = f" Pair: {pairs[0].get('teacher') or ''} with {pairs[0].get('student') or ''}."
        return f"{person.get('role') or 'account'} · {github} · {projects}.{pair}"


async def setup(bot):
    await bot.add_cog(Intake(bot))
