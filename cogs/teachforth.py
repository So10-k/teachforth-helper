"""TeachForth commands on top of the Modmail desk."""

from discord.ext import commands

import teachforth_portal


class TeachForth(commands.Cog):
    """Registration for the helpdesk."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await teachforth_portal.start(self.bot)

    @commands.command(name="login")
    async def login(self, ctx, code: str = ""):
        """Register this Discord account. `.login CODE` also finishes a browser login."""
        if ctx.guild is None:
            return await ctx.send("Run that in the TeachForth server.")
        app = getattr(self.bot, "_teachforth_app", None)
        if app is None:
            return await ctx.send("The helpdesk is still starting. Try again in a few seconds.")
        status, data = teachforth_portal.accept_registration(
            app,
            ctx.author.id,
            ctx.author.display_name,
            code,
            getattr(ctx.author.guild_permissions, "value", 0),
        )
        if status != 200:
            return await ctx.send(data.get("error") or "That didn't register.")
        if data.get("code"):
            return await ctx.send(
                f"You're registered. Helpdesk code: `{data['code']}`\nPaste it at {teachforth_portal.PUBLIC}"
            )
        await ctx.send(data.get("message") or "You're registered.")


async def setup(bot):
    await bot.add_cog(TeachForth(bot))
