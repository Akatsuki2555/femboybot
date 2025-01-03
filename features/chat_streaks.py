#      Akabot is a general purpose bot with a ton of features.
#      Copyright (C) 2023-2025 mldchan
#
#      This program is free software: you can redistribute it and/or modify
#      it under the terms of the GNU Affero General Public License as
#      published by the Free Software Foundation, either version 3 of the
#      License, or (at your option) any later version.
#
#      This program is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU Affero General Public License for more details.
#
#      You should have received a copy of the GNU Affero General Public License
#      along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import datetime

import discord
import sentry_sdk
from discord.ext import commands as commands_ext, pages

from database import client
from utils.analytics import analytics
from utils.languages import get_translation_for_key_localized as trl, get_language
from utils.logging_util import log_into_logs
from utils.per_user_settings import get_per_user_setting
from utils.tips import append_tip_to_message
from utils.tzutil import get_server_midnight_time


class ChatStreakStorage:
    """Chat Streaks Storage.
    Every member has 24 hours before their streak gets reset.
    If their streak day changes to the next day without expiring, they get congratulated.
    """

    def __init__(self) -> None:
        super().__init__()

    def set_streak(self, guild_id: int, member_id: int) -> tuple[str, int, int]:
        """Set streak

        Args:
            guild_id (int): Guild ID
            member_id (int): Member ID

        Returns:
            str: The state of the streak
        """

        res = client['ChatStreaks'].find_one({'GuildID': str(guild_id), 'MemberID': str(member_id)})

        if not res:
            start_time = get_server_midnight_time(guild_id)
            client['ChatStreaks'].insert_one(
                {'GuildID': str(guild_id), 'MemberID': str(member_id), 'LastMessage': start_time,
                 'StartTime': start_time})

            return "started", 0, 0

        last_message = res['LastMessage']
        start_time = res['StartTime']

        # Check for streak expiry
        if get_server_midnight_time(guild_id) - last_message > datetime.timedelta(days=1, hours=1):
            streak = max((last_message - start_time).days, 0)
            client['ChatStreaks'].update_one({'GuildID': str(guild_id), 'MemberID': str(member_id)}, {
                '$set': {'LastMessage': get_server_midnight_time(guild_id),
                         'StartTime': get_server_midnight_time(guild_id)}})
            return "expired", streak, 0

        before_update = (last_message - start_time).days

        client['ChatStreaks'].update_one({'GuildID': str(guild_id), 'MemberID': str(member_id)},
                                         {'$set': {'LastMessage': get_server_midnight_time(guild_id)}})

        after_update = (get_server_midnight_time(guild_id) - start_time).days

        if before_update != after_update:
            return "updated", before_update, after_update

        return "stayed", after_update, 0

    def reset_streak(self, guild_id: int, member_id: int) -> None:
        """Reset streak

        Args:
            guild_id (int): Guild ID
            member_id (int): Member ID
        """

        if client['ChatStreaks'].find_one({'GuildID': str(guild_id), 'MemberID': str(member_id)}) is None:
            client['ChatStreaks'].insert_one({'GuildID': str(guild_id), 'MemberID': str(member_id),
                                              'LastMessage': get_server_midnight_time(guild_id),
                                              'StartTime': get_server_midnight_time(guild_id)})
        else:
            client['ChatStreaks'].update_one({'GuildID': str(guild_id), 'MemberID': str(member_id)}, {
                '$set': {'LastMessage': get_server_midnight_time(guild_id),
                         'StartTime': get_server_midnight_time(guild_id)}})


class ChatStreaks(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.streak_storage = ChatStreakStorage()

    @discord.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if message.author.bot:
                return

            (state, old_streak, new_streak) = self.streak_storage.set_streak(message.guild.id, message.author.id)

            print('[Chat Streaks] Info', state, old_streak, new_streak)

            if state == "expired":
                if old_streak == 0:
                    return
                if get_per_user_setting(message.author.id, 'chat_streaks_alerts', 'on') == 'off':
                    return
                msg = await message.reply(
                    trl(message.author.id, message.guild.id, "chat_streaks_expired").format(streak=old_streak))
                await msg.delete(delay=3)

            if state == "updated":
                if get_per_user_setting(message.author.id, 'chat_streaks_alerts', 'on') != 'on':
                    return  # Only trigger if the user has the setting on
                msg = await message.reply(
                    trl(message.author.id, message.guild.id, "chat_streaks_updated").format(streak=new_streak))
                await msg.delete(delay=3)
        except Exception as e:
            sentry_sdk.capture_exception(e)

    streaks_subcommand = discord.SlashCommandGroup(name='streaks', description='Manage the chat streaks')

    @streaks_subcommand.command(name="reset", description="Reset streak for a specific user")
    @commands_ext.guild_only()
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @discord.option(name='user', description='The user to reset the streak for', type=discord.Member)
    @analytics("streaks reset")
    async def reset_streak_command(self, ctx: discord.ApplicationContext, user: discord.Member):
        try:
            # Reset streak
            self.streak_storage.reset_streak(ctx.guild.id, user.id)

            # Create a embed for logs
            logging_embed = discord.Embed(title=trl(ctx.user.id, ctx.guild.id, "chat_streaks_reset_log_title"))
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "chat_streaks_reset_log_admin"),
                                    value=f'{ctx.user.mention}')
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_user"), value=f'{user.mention}')

            # Send to log
            await log_into_logs(ctx.guild, logging_embed)

            # Respond
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "chat_streaks_reset_success", append_tip=True).format(user=user.mention),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @streaks_subcommand.command(name="streak", description="Get someone's streak, to get yours, /streak.")
    @commands_ext.guild_only()
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @discord.option(name='user', description='The user to get the streak for', type=discord.Member)
    @analytics("streaks streak")
    async def get_user_streak(self, ctx: discord.ApplicationContext, user: discord.Member):
        try:
            (_, streak, _) = self.streak_storage.set_streak(ctx.guild.id, user.id)
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "chat_streaks_streak_admin", append_tip=True).format(user=user.mention,
                                                                                                    streak=str(streak)),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @discord.slash_command(name='streak', description='Get your current streak')
    @analytics("streak")
    async def get_streak_command(self, ctx: discord.ApplicationContext):
        try:
            (_, streak, _) = self.streak_storage.set_streak(ctx.guild.id, ctx.user.id)
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "chat_streaks_streak", append_tip=True).format(streak=streak),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    # Leaderboard

    @streaks_subcommand.command(name="leaderboard", description="Get the chat streak leaderboard")
    @commands_ext.guild_only()
    @analytics("streaks leaderboard")
    async def streaks_lb(self, ctx: discord.ApplicationContext):
        try:
            rows = client['ChatStreaks'].aggregate([
                {
                    "$match": {"GuildID": str(ctx.guild.id)}
                },
                {
                    "$addFields": {
                        "MaxStreak": {"$max": {'$divide': [{"$subtract": ["$LastMessage", "$StartTime"]}, 86400000]}}
                    }
                },
                {
                    "$sort": {"MaxStreak": -1}
                }
            ]).to_list()

            lb_pages = []
            lb_last = False
            message = trl(ctx.user.id, ctx.guild.id, "chat_streak_leaderboard_title")

            i = 1
            for _, row in enumerate(rows):
                member = ctx.guild.get_member(int(row['MemberID']))
                if member is None:
                    continue

                days = int(row['MaxStreak'])

                message += trl(ctx.user.id, ctx.guild.id, "chat_streak_leaderboard_line").format(position=i,
                                                                                                 user=member.mention,
                                                                                                 days=str(days))

                i += 1
                lb_last = True

                if i % 10 == 0:
                    if get_per_user_setting(ctx.user.id, 'tips_enabled', 'true') == 'true':
                        language = get_language(ctx.guild.id, ctx.user.id)
                        message = append_tip_to_message(ctx.guild.id, ctx.user.id, message, language)

                    lb_pages.append(message)
                    message = trl(ctx.user.id, ctx.guild.id, "chat_streak_leaderboard_title")
                    lb_last = False

            if not lb_last:
                if get_per_user_setting(ctx.user.id, 'tips_enabled', 'true') == 'true':
                    language = get_language(ctx.guild.id, ctx.user.id)
                    message = append_tip_to_message(ctx.guild.id, ctx.user.id, message, language)

                lb_pages.append(message)

            resp = pages.Paginator(pages=lb_pages)
            await resp.respond(ctx.interaction, ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)
