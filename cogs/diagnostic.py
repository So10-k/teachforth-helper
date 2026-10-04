"""Staff diagnostics. A support code is consent for this ticket only."""

import logging
import re

import discord
from discord.ext import commands

import teachforth_plugins
import teachforth_portal
import teachforth_support
from core import checks
from core.models import PermissionLevel

logger = logging.getLogger(__name__)
COLOR = 0x7A1FA3
AUTO = "Automated"
TEMPLATES = {"web", "python", "javascript", "java", "c", "cpp", "markdown", "empty", "blank"}
FENCE = {"py": "python", "js": "javascript", "html": "html", "css": "css", "java": "java", "c": "c", "cpp": "cpp", "md": "markdown"}


def _claim(interaction):
    cog = interaction.client.get_cog("Diagnostic")
    if cog is None or interaction.response.is_done() or interaction.id in cog._seen:
        return False
    cog._seen.add(interaction.id)
    return True


class SupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support code", custom_id="tfd:code", style=discord.ButtonStyle.primary)
    async def code(self, interaction, _button):
        if _claim(interaction):
            await interaction.response.send_modal(CodeModal())


class CodeModal(discord.ui.Modal, title="Support code"):
    code = discord.ui.TextInput(label="Code from your profile", min_length=6, max_length=16, custom_id="tfd:codeinput")

    async def on_submit(self, interaction):
        cog = interaction.client.get_cog("Diagnostic")
        if cog is None or interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True)
        await cog.redeem(interaction, str(self.code))


class WalkButton(discord.ui.Button):
    def __init__(self, spec):
        style = discord.ButtonStyle.success if spec.get("style") == "success" else discord.ButtonStyle.secondary
        super().__init__(label=spec["label"][:80], custom_id=spec["id"], style=style)

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Diagnostic")
        if cog is not None and _claim(interaction):
            await cog.on_walk(interaction)


class WalkSelect(discord.ui.Select):
    def __init__(self, spec):
        options = [
            discord.SelectOption(label=item["label"][:100], value=item["id"][:100], description=(item.get("desc") or "")[:100] or None)
            for item in spec["options"][:25]
        ]
        super().__init__(custom_id=spec["custom_id"], placeholder=spec.get("placeholder") or "Choose", options=options)

    async def callback(self, interaction):
        cog = interaction.client.get_cog("Diagnostic")
        if cog is not None and _claim(interaction):
            await cog.on_walk(interaction)


class Diagnostic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._seen = set()

    async def cog_load(self):
        self.bot.add_view(SupportView())

    @commands.command(name="diagnostic")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def diagnostic(self, ctx):
        """Ask the student for a support code from their profile."""
        thread = await self._thread(ctx)
        if thread is None:
            return
        recipient = thread.recipient
        embed = discord.Embed(
            title="Support code",
            description=(
                "Open your TeachForth profile and press **Support code**.\n"
                "Then press the button here and paste it.\n\n"
                "That lets your teacher see your account for this ticket only. "
                "It is not your password, and it expires in 15 minutes."
            ),
            color=COLOR,
        )
        embed.set_footer(text="TeachForth Help")
        teachforth_support.note_teacher(thread.channel.id, ctx.author.id, recipient.id)
        try:
            await recipient.send(embed=embed, view=SupportView())
        except discord.HTTPException:
            return await ctx.send("I could not DM them. Ask them to open a DM with the bot.")
        await ctx.send(embed=self._embed("Asked for a support code", f"{recipient} can paste it from their profile."))

    async def redeem(self, interaction, code):
        thread = await self.bot.threads.find(recipient=interaction.user)
        channel = getattr(thread, "channel", None)
        if channel is None:
            await interaction.followup.send("Open a ticket first, then paste the code.", ephemeral=True)
            return
        status, data = await teachforth_portal.class_call("POST", "/api/discord/support/redeem", {
            "code": code,
            "channelId": str(channel.id),
            "teacherDiscordId": teachforth_support.teacher_for(channel.id),
        })
        if status != 200 or not data.get("grant"):
            await interaction.followup.send(data.get("error") or "That code did not work. Use Support code in the profile, not Link Discord.", ephemeral=True)
            return
        person = data.get("person") or {}
        teachforth_support.remember(channel.id, {
            "grant": data["grant"],
            "expires": data.get("expiresAt") or "",
            "name": person.get("name") or interaction.user.name,
            "role": person.get("role") or "",
            "recipient": str(interaction.user.id),
            "teacher": teachforth_support.teacher_for(channel.id),
        })
        await interaction.followup.send("Got it. Your teacher can see this account for this ticket. Not your password.", ephemeral=True)
        await channel.send(embeds=self._profile_embeds(data))

    async def redeem_text(self, thread, author, code):
        channel = thread.channel
        status, data = await teachforth_portal.class_call("POST", "/api/discord/support/redeem", {
            "code": code,
            "channelId": str(channel.id),
            "teacherDiscordId": teachforth_support.teacher_for(channel.id),
        })
        if status != 200 or not data.get("grant"):
            try:
                await author.send("That did not look like a support code. Press Support code, or copy the one from your profile.")
            except discord.HTTPException:
                pass
            return
        person = data.get("person") or {}
        teachforth_support.remember(channel.id, {
            "grant": data["grant"],
            "expires": data.get("expiresAt") or "",
            "name": person.get("name") or getattr(author, "name", ""),
            "role": person.get("role") or "",
            "recipient": str(author.id),
            "teacher": teachforth_support.teacher_for(channel.id),
        })
        await channel.send(embeds=self._profile_embeds(data))
        try:
            await author.send("Got it. Your teacher can see this account for this ticket. Not your password.")
        except discord.HTTPException:
            pass

    @commands.command(name="projects")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def projects(self, ctx):
        """List the consented account's projects."""
        row, channel = await self._grant(ctx)
        if not row:
            return
        status, data = await self._read(row, channel, "/api/discord/support/projects")
        if status != 200:
            return await ctx.send(data.get("error") or "Class did not answer.")
        lines = [
            f"`{item.get('id')}` · {item.get('title')} · {item.get('language')} · {'open' if item.get('open') else 'closed'}"
            for item in data.get("projects") or []
        ]
        await ctx.send(embed=self._embed("Projects", "\n".join(lines) or "No projects on this account."))

    @commands.group(name="project", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def project(self, ctx):
        """`.project view ID` or `.project create blank`."""
        await ctx.send("Use `.project view ID` or `.project create blank`.")

    @project.command(name="view")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def project_view(self, ctx, project_id: int):
        """Show that project's files in this staff channel."""
        row, channel = await self._grant(ctx)
        if not row:
            return
        status, data = await self._read(row, channel, "/api/discord/support/project", {"id": int(project_id)})
        if status != 200:
            return await ctx.send(data.get("error") or "That project did not open.")
        project = data.get("project") or {}
        source = project.get("source") or ""
        note = {
            "class": "Read from the class computer.",
            "github": "Read from GitHub. Hidden files stay hidden.",
            "closed": "Closed, and GitHub is not linked, so there are no files here.",
            "empty": "No files yet.",
        }.get(source, "")
        await ctx.send(embed=self._embed(
            project.get("title") or "Project",
            f"ID `{project.get('id')}` · {project.get('language') or ''}\n{note}\n{project.get('githubUrl') or ''}",
        ))
        files = data.get("files") or []
        if not files:
            return
        for item in files[:8]:
            await self._code(ctx.channel, item.get("path") or "file", item.get("content") or "", item.get("truncated"))

    @project.command(name="create")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def project_create(self, ctx, *, spec: str = ""):
        """Create a blank project, or `.project create python Title`."""
        row, channel = await self._grant(ctx)
        if not row:
            return
        template, title = self._parse_create(spec)
        status, data = await teachforth_portal.class_call("POST", "/api/discord/support/project", {
            "grant": row["grant"],
            "channelId": str(channel.id),
            "teacherDiscordId": str(ctx.author.id),
            "title": title,
            "template": template,
        })
        if status not in {200, 201}:
            return await ctx.send(data.get("error") or "That project was not created.")
        project = data.get("project") or {}
        reused = " The repo already existed." if data.get("reused") else ""
        await ctx.send(embed=self._embed(
            "Project created",
            f"`{project.get('id')}` · {project.get('title') or title} · {project.get('language') or template}.{reused}\n{project.get('githubUrl') or ''}",
        ))

    @commands.command(name="reports")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def reports(self, ctx):
        """Show session reports for the consented account. Students do not see this."""
        row, channel = await self._grant(ctx)
        if not row:
            return
        status, data = await self._read(row, channel, "/api/discord/support/reports")
        if status != 200:
            return await ctx.send(data.get("error") or "Reports did not answer.")
        rows = data.get("reports") or []
        if not rows:
            return await ctx.send(embed=self._embed("Reports", "None yet."))
        embeds = []
        for item in rows[:6]:
            body = item.get("body") or "No note."
            if item.get("diff"):
                body += f"\n\n{item['diff']}"
            embeds.append(self._embed(f"{item.get('author') or 'Report'} · {item.get('block') or ''}", body[:4000]))
        await ctx.send(embeds=embeds[:6])

    @commands.command(name="chapters")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def chapters(self, ctx):
        """Show chapters for the consented account."""
        row, channel = await self._grant(ctx)
        if not row:
            return
        status, data = await self._read(row, channel, "/api/discord/support/chapters")
        if status != 200:
            return await ctx.send(data.get("error") or "Chapters did not answer.")
        lines = [f"{item.get('name')} · {item.get('place') or 'no place'}" for item in data.get("chapters") or []]
        await ctx.send(embed=self._embed("Chapters", "\n".join(lines) or "No chapter on this account."))

    @commands.command(name="helpmenusend")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def helpmenusend(self, ctx, *, kind: str = ""):
        """Send an automated walkthrough and move the ticket."""
        thread = await self._thread(ctx)
        if thread is None:
            return
        picked = self._kind(kind)
        if not picked:
            lines = [f"`{item['id']}` · {item['label']} — {item['blurb']}" for item in teachforth_plugins.PLUGINS]
            return await ctx.send(embed=self._embed("Automated helpers", "\n".join(lines) + "\n\n`.helpmenusend page`"))
        moved, previous = await self._move(thread.channel, AUTO)
        state = teachforth_plugins.begin(picked, "", await self._fill(thread))
        state["automated"] = True
        state["channel"] = str(thread.channel.id)
        state["previous"] = previous
        teachforth_support.auto_put(thread.recipient.id, state)
        await self._show(thread, state)
        where = "Moved to Automated." if moved else "Could not move the channel. The walk still started."
        await ctx.send(embed=self._embed("Walk started", f"{teachforth_plugins.label(picked)}. {where}"))

    async def on_walk(self, interaction):
        cid = (interaction.data or {}).get("custom_id") or ""
        await interaction.response.defer()
        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass
        thread = await self.bot.threads.find(recipient=interaction.user)
        if thread is None or getattr(thread, "channel", None) is None:
            return
        state = teachforth_support.auto_get(interaction.user.id)
        if cid == "tfa:fixed":
            await self._finish(thread, state, "They said that fixed it.")
            return
        if cid == "tfa:restart":
            teachforth_support.auto_clear(interaction.user.id)
            await thread.channel.send(embed=self._embed("Walk stopped", "Run `.helpmenusend` to pick another."))
            return
        if cid == "tfa:still":
            kind, _payload = teachforth_plugins.apply_still(state)
        elif cid == "tfa:step":
            choice = ((interaction.data or {}).get("values") or [""])[0]
            kind, _payload = teachforth_plugins.apply_choice(state, choice)
        else:
            return
        await self._after(thread, state, kind)

    @commands.Cog.listener()
    async def on_thread_reply(self, thread, from_mod, message, _anonymous, _plain):
        if from_mod or message is None:
            return
        text = (getattr(message, "content", None) or "").strip()
        if re.fullmatch(r"[A-Za-z2-9]{8}", text):
            thread_channel = getattr(thread, "channel", None)
            pending = thread_channel is not None and teachforth_support.teacher_for(thread_channel.id)
            if pending and not (teachforth_support.consent(thread_channel.id) or {}).get("grant"):
                await self.redeem_text(thread, message.author, text)
                return
        state = teachforth_support.auto_get(getattr(message.author, "id", 0))
        if not state.get("automated"):
            return
        if not text or text.startswith("."):
            return
        if state.get("awaiting") == "text":
            kind, _payload = teachforth_plugins.apply_text(state, text)
            await self._after(thread, state, kind)
            return
        if state.get("awaiting") == "fix" and teachforth_plugins.apply_still:
            low = text.lower()
            if any(part in low for part in ("fixed", "it worked", "that worked")):
                await self._finish(thread, state, "They said that fixed it.")
                return
            if any(part in low for part in ("still", "didn't", "did not", "teacher")):
                kind, _payload = teachforth_plugins.apply_still(state)
                await self._after(thread, state, kind)

    async def _after(self, thread, state, kind):
        if kind == "open":
            await self._finish(thread, state, "The walk is done. They still need a teacher.")
            return
        if kind == "again":
            await thread.recipient.send(embed=self._embed("Need a real answer", "Use the buttons, or type a sentence."))
        spec = teachforth_plugins.prompt(state)
        teachforth_support.auto_put(thread.recipient.id, state)
        await self._show(thread, state, spec)

    async def _finish(self, thread, state, title):
        teachforth_support.auto_clear(thread.recipient.id)
        previous = state.get("previous")
        if previous:
            await self._move_back(thread.channel, previous)
        embed = self._embed(title, teachforth_plugins.summary_text(state)[:4000])
        await thread.channel.send(embed=embed)
        try:
            await thread.recipient.send(embed=self._embed("Back with a teacher", "A teacher has the steps you tried. Reply here if you need to add something."))
        except discord.HTTPException:
            pass

    async def _show(self, thread, state, spec=None):
        spec = spec or teachforth_plugins.prompt(state)
        spec = self._retag(spec)
        teachforth_support.auto_put(thread.recipient.id, state)
        view = discord.ui.View(timeout=None)
        if spec.get("select"):
            view.add_item(WalkSelect(spec["select"]))
        for button in spec.get("buttons") or []:
            view.add_item(WalkButton(button))
        embed = self._embed(spec.get("title") or "TeachForth Help", spec.get("body") or "")
        embed.set_footer(text=spec.get("footer") or "TeachForth Help")
        try:
            await thread.recipient.send(embed=embed, view=view if view.children else None)
        except discord.HTTPException:
            logger.warning("Automated step did not reach the student")
        await thread.channel.send(embed=embed)

    def _retag(self, spec):
        spec = dict(spec)
        if spec.get("select"):
            spec["select"] = dict(spec["select"], custom_id="tfa:step")
        buttons = []
        for button in spec.get("buttons") or []:
            item = dict(button)
            item["id"] = item["id"].replace("tfp:", "tfa:")
            buttons.append(item)
        spec["buttons"] = buttons
        return spec

    async def _fill(self, thread):
        row = teachforth_support.consent(thread.channel.id) or {}
        ctx = {
            "class_line": "Class status was not checked for this walk.",
            "github": "GitHub status is on the support card.",
            "projects": "See .projects",
            "project_names": [],
            "pair": "See the support card.",
            "chapters": "",
            "role": row.get("role") or "",
            "url": teachforth_plugins.CLASS_URL,
        }
        if not row.get("grant"):
            return ctx
        status, data = await self._read(row, thread.channel, "/api/discord/support/projects")
        if status != 200:
            return ctx
        person = data.get("person") or {}
        names = [item.get("title") for item in data.get("projects") or [] if item.get("title")]
        ctx.update({
            "github": "GitHub is connected" if person.get("githubLinked") else "GitHub is not connected",
            "projects": ", ".join(names[:6]) or "No projects yet",
            "project_names": names[:20],
            "role": person.get("role") or "",
        })
        return ctx

    async def _move(self, channel, name):
        previous = channel.category.id if channel.category else None
        guild = channel.guild
        me = guild.me if guild else None
        if me is None or not me.guild_permissions.manage_channels:
            return False, previous
        category = discord.utils.get(guild.categories, name=name)
        try:
            if category is None:
                category = await guild.create_category(name, reason="TeachForth automated help")
            await channel.edit(category=category, reason="Automated help")
        except discord.HTTPException:
            return False, previous
        return True, previous

    async def _move_back(self, channel, category_id):
        guild = channel.guild
        category = guild.get_channel(int(category_id)) if guild else None
        if category is None:
            category = getattr(self.bot, "main_category", None)
        if category is None:
            return
        try:
            await channel.edit(category=category, reason="Automated help finished")
        except discord.HTTPException:
            logger.info("Could not move the ticket back")

    async def _thread(self, ctx):
        try:
            thread = await self.bot.threads.find(channel=ctx.channel)
        except Exception:
            thread = None
        if thread is None or getattr(thread, "recipient", None) is None:
            await ctx.send("Run that in an open ticket.")
            return None
        if not await self._website_staff(ctx):
            return None
        return thread

    async def _grant(self, ctx):
        thread = await self._thread(ctx)
        if thread is None:
            return None, None
        row = teachforth_support.consent(thread.channel.id)
        if not row or str(row.get("recipient")) != str(thread.recipient.id):
            await ctx.send("No support consent on this ticket. Run `.diagnostic` and have them paste the code from their profile.")
            return None, None
        return row, thread.channel

    async def _website_staff(self, ctx):
        status, data = await teachforth_portal.class_call("GET", f"/api/discord/profile?discordId={ctx.author.id}")
        if status == 0:
            await ctx.send("Class is off, so I can't check your TeachForth role.")
            return False
        if status != 200 or data.get("role") not in {"teacher", "lead_teacher", "chapter_lead", "admin"}:
            await ctx.send("That command is for a linked teacher, chapter lead, or admin.")
            return False
        return True

    async def _read(self, row, channel, path, extra=None):
        body = {
            "grant": row["grant"],
            "channelId": str(channel.id),
            "teacherDiscordId": str(row.get("teacher") or ""),
        }
        if extra:
            body.update(extra)
        return await teachforth_portal.class_call("POST", path, body)

    def _profile_embeds(self, data):
        person = data.get("person") or {}
        github = f"GitHub @{person.get('githubLogin')}" if person.get("githubLinked") else "GitHub is not connected"
        projects = "\n".join(
            f"`{item.get('id')}` · {item.get('title')} · {item.get('language')}"
            for item in (data.get("projects") or [])[:8]
        ) or "None yet."
        chapters = ", ".join(item.get("name") or "" for item in data.get("chapters") or []) or "None"
        reports = data.get("reports") or []
        pairs = "\n".join(
            f"{item.get('block')} · {item.get('teacher')} with {item.get('student')}"
            for item in (data.get("pairs") or [])[:4]
        ) or "No pair"
        first = self._embed(
            person.get("name") or "Account",
            f"{person.get('role') or 'account'} · {person.get('email') or 'no email'}\n{github}\nConsent lasts until {data.get('expiresAt') or 'this ticket ends'}.",
        )
        rest = [
            self._embed("Projects", projects),
            self._embed("Chapters", chapters),
            self._embed("Reports", f"{len(reports)} on the account. `.reports` shows them here, not to the student."),
            self._embed("Pairs", pairs),
        ]
        first.set_footer(text="TeachForth Help · this ticket only")
        return [first, *rest]

    def _embed(self, title, description):
        embed = discord.Embed(title=str(title or "TeachForth")[:256], description=str(description or "")[:4000], color=COLOR)
        embed.set_footer(text="TeachForth Help")
        return embed

    async def _code(self, channel, path, content, truncated):
        lang = FENCE.get(path.rsplit(".", 1)[-1].lower(), "")
        body = content.replace("```", "'''")
        note = "\ntruncated" if truncated else ""
        chunk = body
        while chunk:
            piece = chunk[:1400]
            chunk = chunk[1400:]
            text = f"**{path}**{note}\n```{lang}\n{piece}\n```"
            try:
                await channel.send(text[:1900])
            except discord.HTTPException:
                return
            note = ""

    def _parse_create(self, spec):
        parts = (spec or "").split()
        if not parts or parts[0].lower() in {"blank", "empty"} and len(parts) == 1:
            return "empty", "Blank"
        if parts and parts[0].lower() in TEMPLATES:
            template = "empty" if parts[0].lower() == "blank" else parts[0].lower()
            title = " ".join(parts[1:]).strip() or "Blank"
            return template, title[:80]
        return "empty" if not spec else "web", (spec or "Blank")[:80]

    def _kind(self, text):
        key = re.sub(r"[^a-z]", "", (text or "").lower())
        if key in teachforth_plugins.BY_ID:
            return key
        for item in teachforth_plugins.PLUGINS:
            if key and key in re.sub(r"[^a-z]", "", item["label"].lower()):
                return item["id"]
        return ""


async def setup(bot):
    await bot.add_cog(Diagnostic(bot))
