import datetime
import zoneinfo
from typing import Any

import discord
from discord.ext import commands, menus

from ... import CONFIG, BotBase, Cog, Context
from ...db import TimeZones
from ...types import User
from ...types.transformers import ZoneInfoTransformer
from ...utils.interactions import error
from ...utils.paginator import EmbedPaginator
from ...utils.slash import with_cog
from ...utils.strings import utc_offset
from ...utils.time import ALL_TIMEZONES, human_friendly_timestamp


class Timezone(Cog):
    """User Timezone Management Commands."""

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{WORLD MAP}")

    @commands.group(aliases=["time"], invoke_without_command=True)
    async def timezone(self, ctx: Context, *, argument: zoneinfo.ZoneInfo | User | None = None) -> None:
        """Get the current time for a user or time zone."""
        if argument is None:
            argument = zoneinfo.ZoneInfo("UTC")

        if isinstance(argument, User):
            return await ctx.invoke(self.timezone_get, user=argument)

        embed = discord.Embed(title=human_friendly_timestamp(datetime.datetime.now(tz=argument)))
        embed.set_author(name=f"Time in {argument}")

        await ctx.reply(embed=embed)

    @timezone.command(name="get")
    async def timezone_get(self, ctx: Context, *, user: User | None = None) -> None:
        """Get a user's time zone."""
        if user is None:
            user = ctx.author

        async with ctx.db as connection:
            timezone = await TimeZones.get_timezone(connection, user)

        if timezone is None:
            raise commands.BadArgument(f"{user.mention} does not have a time zone set.")

        embed = discord.Embed(title=human_friendly_timestamp(datetime.datetime.now(tz=timezone)))
        embed.set_author(name=f"Time for {user.display_name}", icon_url=user.display_avatar.url)
        embed.set_footer(text=f"{timezone} ({utc_offset(timezone)})")

        await ctx.reply(embed=embed)

    @timezone.command(name="set")
    async def timezone_set(self, ctx: Context, *, timezone: zoneinfo.ZoneInfo) -> None:
        """Set your time zone."""
        async with ctx.db as connection:
            await TimeZones.insert(
                connection,
                update_on_conflict=(TimeZones.time_zone,),
                returning=None,
                user_id=ctx.author.id,
                time_zone=str(timezone),
            )

        local_time = human_friendly_timestamp(datetime.datetime.now(tz=timezone))
        embed = discord.Embed(title=f"Local Time: {local_time}")
        embed.set_author(name=f"Timezone set to {timezone}")

        await ctx.reply(embed=embed)

    @timezone.command(name="list")
    async def timezone_list(self, ctx: Context) -> None:
        """List all avilable time zones."""
        embed = EmbedPaginator[discord.Embed](max_description=512)

        def get_offset(t: tuple[Any, zoneinfo.ZoneInfo]) -> float:
            _, tzinfo = t

            now = datetime.datetime.now(datetime.timezone.utc)

            offset = tzinfo.utcoffset(now)
            if offset is not None:
                return offset.total_seconds()
            return 0

        for name, tzinfo in sorted(ALL_TIMEZONES.items(), key=get_offset):
            embed.add_line(f"`{name}` ({utc_offset(tzinfo)})")

        await menus.MenuPages(embed).start(ctx)

    @commands.command()
    async def timezones(self, ctx: Context) -> None:
        """List all avilable time zones."""
        return await self.timezone_list(ctx)


@with_cog(Timezone)
class _Timezone(discord.app_commands.Group, name="timezone"):
    """User Timezone Management Commands."""

    def __init__(self, client: BotBase, *args: Any, **kwargs: Any) -> None:
        self.client: BotBase = client
        super().__init__(*args, **kwargs)

    @discord.app_commands.command()
    @discord.app_commands.describe(
        timezone="The timezone to get the current time for.",
        user="The user to get the current time for.",
        private="Whether to invoke this command privately.",
    )
    async def get(
        self,
        interaction: discord.Interaction,
        timezone: discord.app_commands.Transform[zoneinfo.ZoneInfo, ZoneInfoTransformer] | None,
        user: User | None,
        private: bool = True,
    ) -> None:
        """Get the current time for a user or time zone."""
        if timezone is not None:
            if user is not None:
                return await error(interaction, "You can't specify both a timezone and a user.")

            embed = discord.Embed(title=human_friendly_timestamp(datetime.datetime.now(tz=timezone)))
            embed.set_author(name=f"Time in {timezone}")

        else:
            if user is None:
                user = interaction.user

            async with self.client.pool.acquire() as connection:
                timezone = await TimeZones.get_timezone(connection, user)

            if timezone is None:
                return await error(interaction, f"{user.mention} does not have a time zone set.")

            embed = discord.Embed(title=human_friendly_timestamp(datetime.datetime.now(tz=timezone)))
            embed.set_author(name=f"Time for {user.display_name}", icon_url=user.display_avatar.url)
            embed.set_footer(text=f"{timezone} ({utc_offset(timezone)})")

        await interaction.response.send_message(embed=embed, ephemeral=private)

    @discord.app_commands.command()
    @discord.app_commands.describe(
        timezone="The timezone to set.",
    )
    async def set(
        self,
        interaction: discord.Interaction,
        timezone: discord.app_commands.Transform[zoneinfo.ZoneInfo, ZoneInfoTransformer],
    ) -> None:
        """Set your timezone."""
        async with self.client.pool.acquire() as connection:
            await TimeZones.insert(
                connection,
                update_on_conflict=(TimeZones.time_zone,),
                returning=None,
                user_id=interaction.user.id,
                time_zone=str(timezone),
            )

        local_time = human_friendly_timestamp(datetime.datetime.now(tz=timezone))
        embed = discord.Embed(title=f"Local Time: {local_time}")
        embed.set_author(name=f"Timezone set to {timezone}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: BotBase):
    if CONFIG.DATABASE.DISABLED:
        return
    await bot.add_cog(Timezone(bot))
    bot.tree.add_command(_Timezone(bot))


async def teardown(bot: BotBase):
    bot.tree.remove_command("timezone")
