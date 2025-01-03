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
import logging
import re

import discord
import emoji
import sentry_sdk
from discord.ext import commands as commands_ext, pages

from database import client
from utils.analytics import analytics
from utils.generic import validate_day
from utils.languages import get_translation_for_key_localized as trl, get_language
from utils.leveling import calc_multiplier, get_xp, add_xp, get_level_for_xp, get_xp_for_level, \
    add_mult, mult_exists, mult_change_name, mult_change_multiplier, \
    mult_change_start, mult_change_end, mult_del, mult_list, \
    mult_get, update_roles_for_member
from utils.logging_util import log_into_logs
from utils.per_user_settings import get_per_user_setting, set_per_user_setting
from utils.settings import get_setting, set_setting
from utils.tips import append_tip_to_message
from utils.tzutil import get_now_for_server


class Leveling(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        super().__init__()

    @discord.Cog.listener()
    async def on_message(self, msg: discord.Message):
        try:
            if msg.author.bot:
                return

            xp = int(get_setting(msg.guild.id, 'leveling_initial_xp', 3))
            extra = int(get_setting(msg.guild.id, 'leveling_extra_xp', 0))
            extra_trigger = int(get_setting(msg.guild.id, 'leveling_extra_xp_trigger', 1))

            xp += extra * (len(msg.content) // extra_trigger)

            logging.debug(
                "Settings: Extra: %d, Extra Trigger: %d, Calculated Multiplications: %d, Calculated XP Addition: %d",
                extra, extra_trigger, len(msg.content) // extra_trigger, extra * (len(msg.content) // extra_trigger))
            logging.debug("Adding %d XP to %s (Message length: %d)", xp, msg.author.name, len(msg.content))

            before_level = get_level_for_xp(msg.guild.id, get_xp(msg.guild.id, msg.author.id))
            add_xp(msg.guild.id, msg.author.id, xp)
            after_level = get_level_for_xp(msg.guild.id, get_xp(msg.guild.id, msg.author.id))

            if not msg.channel.permissions_for(msg.guild.me).send_messages:
                return

            if msg.guild.me.guild_permissions.manage_roles:
                await update_roles_for_member(msg.guild, msg.author)

            if before_level != after_level and msg.channel.can_send():
                msg2 = await msg.channel.send(
                    trl(msg.author.id, msg.guild.id, "leveling_level_up").format(mention=msg.author.mention,
                                                                                 level=str(after_level)))
                await msg2.delete(delay=5)
        except Exception as e:
            sentry_sdk.capture_exception(e)

    @discord.slash_command(name='level', description='Get the level of a user')
    @commands_ext.guild_only()
    @analytics("level")
    async def get_level(self, ctx: discord.ApplicationContext, user: discord.User = None):
        try:
            user = user or ctx.user

            level_xp = get_xp(ctx.guild.id, user.id)
            level = get_level_for_xp(ctx.guild.id, level_xp)
            multiplier = calc_multiplier(ctx.guild.id)
            next_level_xp = get_xp_for_level(ctx.guild.id, level + 1)
            multiplier_list = mult_list(ctx.guild.id)

            msg = ""
            for i in multiplier_list:
                start_month, start_day = map(int, i['StartDate'].split('-'))
                end_month, end_day = map(int, i['EndDate'].split('-'))

                now = get_now_for_server(ctx.guild.id)
                start_date = datetime.datetime(now.year, start_month, start_day)
                end_date = datetime.datetime(now.year, end_month, end_day, hour=23, minute=59, second=59)

                if end_date < start_date:
                    end_date = end_date.replace(year=end_date.year + 1)

                # continue if the multiplier is not active
                if start_date > now or end_date < now:
                    continue

                msg += trl(ctx.user.id, ctx.guild.id, "leveling_level_multiplier_row").format(name=i['Name'],
                                                                                              multiplier=i[
                                                                                                  'Multiplier'],
                                                                                              start=i['StartDate'],
                                                                                              end=i['EndDate'])

            if user == ctx.user:
                icon = get_per_user_setting(ctx.user.id, 'leveling_icon', '')
                response = trl(ctx.user.id, ctx.guild.id, "leveling_level_info_self").format(icon=icon, level=level,
                                                                                             level_xp=level_xp,
                                                                                             next_level_xp=next_level_xp,
                                                                                             next_level=level + 1,
                                                                                             multiplier=multiplier)

                if len(msg) > 0:
                    response += trl(ctx.user.id, ctx.guild.id, "leveling_level_multiplier_title")
                    response += f'{msg}'

                await ctx.respond(response, ephemeral=True)
            else:
                icon = get_per_user_setting(user.id, 'leveling_icon', '')
                response = (
                    trl(ctx.user.id, ctx.guild.id, "leveling_level_info_another").format(icon=icon, user=user.mention,
                                                                                         level=level, level_xp=level_xp,
                                                                                         next_level_xp=next_level_xp,
                                                                                         next_level=level + 1,
                                                                                         multiplier=multiplier))

                if len(msg) > 0:
                    response += trl(ctx.user.id, ctx.guild.id, "leveling_level_multiplier_title")
                    response += f'{msg}'

                if get_per_user_setting(ctx.user.id, 'tips_enabled', 'true') == 'true':
                    language = get_language(ctx.guild.id, ctx.user.id)
                    response = append_tip_to_message(ctx.guild.id, ctx.user.id, response, language)
                await ctx.respond(response, ephemeral=True)

        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    leveling_subcommand = discord.SlashCommandGroup(name='leveling', description='Leveling settings')

    @leveling_subcommand.command(name="list", description="List the leveling settings")
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @analytics("leveling list")
    async def list_settings(self, ctx: discord.ApplicationContext):
        try:
            leveling_xp_multiplier = get_setting(ctx.guild.id, 'leveling_xp_multiplier', '1')

            multiplier_list = mult_list(ctx.guild.id)
            multiplier_list_msg = ""

            for i in multiplier_list:
                multiplier_list_msg += trl(ctx.user.id, ctx.guild.id, "leveling_level_multiplier_row").format(
                    name=i['Name'], multiplier=i['Multiplier'], start=i['StartDate'], end=i['EndDate'])

            if len(multiplier_list) != 0:
                multiplier_list_msg = trl(ctx.user.id, ctx.guild.id,
                                          "leveling_level_multiplier_title") + multiplier_list_msg
            else:
                multiplier_list_msg = trl(ctx.user.id, ctx.guild.id, "leveling_level_multipliers_none")

            embed = discord.Embed(title=trl(ctx.user.id, ctx.guild.id, "leveling_settings_title"),
                                  color=discord.Color.blurple(), description=multiplier_list_msg)
            embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "leveling_settings_multiplier"),
                            value=f'`{leveling_xp_multiplier}x`')

            await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='set_per_message',
                                 description='Set the XP per message, and an additional XP booster')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="initial", description="The XP given to any user for any message, of any length and any type.",
                    type=int)
    @discord.option(name="extra", description="The XP given any user with more effort in their message.", type=int)
    @discord.option(name="extra_requirement",
                    description="Requirement of letters in a message for it to be considered high effort.", type=int)
    @analytics("leveling multiplier")
    async def set_per_message(self, ctx: discord.ApplicationContext, initial: int, extra: int, extra_requirement: int):
        if 4000 < extra_requirement <= 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_extra_requirement"),
                              ephemeral=True)
            return

        if 100 < extra < 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_extra"), ephemeral=True)
            return

        if 100 < initial < 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_initial"), ephemeral=True)
            return

        set_setting(ctx.guild.id, 'leveling_initial_xp', str(initial))
        set_setting(ctx.guild.id, 'leveling_extra_xp', str(extra))
        set_setting(ctx.guild.id, 'leveling_extra_xp_trigger', str(extra_requirement))
        await ctx.respond(
            trl(ctx.user.id, ctx.guild.id, "leveling_set_per_message_success", append_tip=True).format(initial=initial,
                                                                                                       extra=extra,
                                                                                                       extra_requirement=extra_requirement),
            ephemeral=True)

    @leveling_subcommand.command(name='multiplier', description='Set the leveling multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="multiplier", description="The multiplier to set", type=int)
    @analytics("leveling multiplier")
    async def set_multiplier(self, ctx: discord.ApplicationContext, multiplier: int):
        try:
            # Get old setting
            old_multiplier = get_setting(ctx.guild.id, 'leveling_xp_multiplier', str(multiplier))

            # Set new setting
            set_setting(ctx.guild.id, 'leveling_xp_multiplier', str(multiplier))

            # Create message
            logging_embed = discord.Embed(title=trl(ctx.user.id, ctx.guild.id, "leveling_set_multiplier_log_title"))
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "leveling_log_multiplier"),
                                    value=f"{old_multiplier} -> {str(multiplier)}")

            # Send to logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_set_multiplier_success", append_tip=True).format(
                multiplier=multiplier), ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='add_multiplier', description='Add to the leveling multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="name", description="The name of the multiplier", type=str)
    @discord.option(name="multiplier", description="The multiplication", type=int)
    @discord.option(name='start_date', description='The start date of the multiplier, in format MM-DD', type=str)
    @discord.option(name='end_date', description='The end date of the multiplier, in format MM-DD', type=str)
    @analytics("leveling add multiplier")
    async def add_multiplier(self, ctx: discord.ApplicationContext, name: str, multiplier: int, start_date: str,
                             end_date: str):
        try:
            # Verify the format of start_date and end_date
            if not re.match(r'\d{2}-\d{2}', start_date) or not re.match(r'\d{2}-\d{2}', end_date):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_date_format"), ephemeral=True)
                return

            # Verify if the multiplier already exists
            if mult_exists(ctx.guild.id, name):
                await ctx.respond(
                    trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_already_exists").format(name=name),
                    ephemeral=True)
                return

            # Verify the month and day values
            start_month, start_day = map(int, start_date.split('-'))
            end_month, end_day = map(int, end_date.split('-'))

            now = get_now_for_server(ctx.guild.id)
            # Use the validate_day method to check if the start and end dates are valid
            if not validate_day(start_month, start_day, now.year):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_start_date"), ephemeral=True)
                return

            if not validate_day(end_month, end_day, now.year):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_end_date"), ephemeral=True)
                return

            # Multipliers apply to every year
            add_mult(ctx.guild.id, name, multiplier, start_month, start_day, end_month, end_day)

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_add_multiplier_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_name"), value=f"{name}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_log_multiplier"), value=f"{multiplier}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_log_start_date"), value=f"{start_date}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_log_end_date"), value=f"{end_date}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_add_multiplier_success", append_tip=True).format(name=name,
                                                                                                          multiplier=multiplier),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='change_multiplier_name', description='Change the name of a multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="old_name", description="The old name of the multiplier", type=str)
    @discord.option(name="new_name", description="The new name of the multiplier", type=str)
    @analytics("leveling change multiplier name")
    async def change_multiplier_name(self, ctx: discord.ApplicationContext, old_name: str, new_name: str):
        try:
            if not mult_exists(ctx.guild.id, old_name):
                await ctx.respond(
                    trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_doesnt_exist").format(name=old_name),
                    ephemeral=True)
                return

            if mult_exists(ctx.guild.id, new_name):
                await ctx.respond(
                    trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_already_exists").format(name=new_name),
                    ephemeral=True)
                return

            # Set new setting
            mult_change_name(ctx.guild.id, old_name, new_name)

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_rename_multiplier_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_rename_multiplier_log_old_name"),
                                    value=f"{old_name}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_rename_multiplier_log_new_name"),
                                    value=f"{new_name}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_rename_multiplier_success", append_tip=True).format(
                    old_name=old_name, new_name=new_name), ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='change_multiplier_multiplier',
                                 description='Change the multiplier of a multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="name", description="The name of the multiplier", type=str)
    @discord.option(name="multiplier", description="The new multiplier", type=int)
    @analytics("leveling change multiplier multiplier")
    async def change_multiplier_multiplier(self, ctx: discord.ApplicationContext, name: str, multiplier: int):
        try:
            if not mult_exists(ctx.guild.id, name):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_doesnt_exist"), ephemeral=True)
                return

            # Get old setting
            old_multiplier = mult_get(ctx.guild.id, name)['Multiplier']

            # Set new setting
            mult_change_multiplier(ctx.guild.id, name, multiplier)

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_multiplier_logs_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_name"), value=f"{name}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_multiplier_logs_old_multiplier"),
                                    value=f"{old_multiplier}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_multiplier_logs_new_multiplier"),
                                    value=f"{multiplier}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_success", append_tip=True).format(name=name,
                                                                                                      multiplier=multiplier),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='change_multiplier_start_date',
                                 description='Change the start date of a multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="name", description="The name of the multiplier", type=str)
    @discord.option(name="start_date", description="The new start date of the multiplier, in format MM-DD", type=str)
    @analytics("leveling change multiplier start date")
    async def change_multiplier_start_date(self, ctx: discord.ApplicationContext, name: str, start_date: str):
        try:
            if not mult_exists(ctx.guild.id, name):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_doesnt_exist").format(name=name),
                                  ephemeral=True)
                return

            # Verify the format of start_date
            if not re.match(r'\d{2}-\d{2}', start_date):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_date_format"), ephemeral=True)
                return

            # Verify the month and day values
            start_month, start_day = map(int, start_date.split('-'))

            now = get_now_for_server(ctx.guild.id)
            # Use the validate_day method to check if the start date is valid
            if not validate_day(start_month, start_day, now.year):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_start_date"), ephemeral=True)
                return

            start_year = now.year

            # Set new setting
            mult_change_start(ctx.guild.id, name, datetime.datetime(start_year, start_month, start_day))

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_start_date_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_name"), value=f"{name}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_start_date_new_start_date"),
                                    value=f"{start_date}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_start_date_success", append_tip=True).format(name=name,
                                                                                                      start_date=start_date),
                ephemeral=True)

        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='change_multiplier_end_date', description='Change the end date of a multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="name", description="The name of the multiplier", type=str)
    @discord.option(name="end_date", description="The new end date of the multiplier, in format MM-DD", type=str)
    @analytics("leveling change multiplier end date")
    async def change_multiplier_end_date(self, ctx: discord.ApplicationContext, name: str, end_date: str):
        try:
            if not mult_exists(ctx.guild.id, name):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_doesnt_exist").format(name=name),
                                  ephemeral=True)
                return

            # Verify the format of end_date
            if not re.match(r'\d{2}-\d{2}', end_date):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_date_format"), ephemeral=True)
                return

            # Verify the month and day values
            end_month, end_day = map(int, end_date.split('-'))

            now = get_now_for_server(ctx.guild.id)
            # Use the validate_day method to check if the end date is valid
            if not validate_day(end_month, end_day, now.year):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_error_invalid_end_date"), ephemeral=True)
                return

            year = now.year

            # Set new setting
            mult_change_end(ctx.guild.id, name, datetime.datetime(year, end_month, end_day))

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_end_date_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_name"), value=f"{name}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_error_invalid_end_date"), value=f"{end_date}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_end_date_success", append_tip=True).format(name=name,
                                                                                                    end_date=end_date),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='remove_multiplier', description='Remove a multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="name", description="The name of the multiplier", type=str)
    @analytics("leveling remove multiplier")
    async def remove_multiplier(self, ctx: discord.ApplicationContext, name: str):
        try:
            if not mult_exists(ctx.guild.id, name):
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_multiplier_doesnt_exist").format(name=name),
                                  ephemeral=True)
                return

            # Get old setting
            old_multiplier = mult_get(ctx.guild.id, name)['Multiplier']

            # Set new setting
            mult_del(ctx.guild.id, name)

            # Logging embed
            logging_embed = discord.Embed(title=trl(ctx.user.id, ctx.guild.id, "leveling_remove_multiplier_log_title"))
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_name"), value=f"{name}")
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "leveling_log_multiplier"),
                                    value=f"{old_multiplier}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_remove_multiplier_success", append_tip=True).format(name=name),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='get_multiplier', description='Get the leveling multiplier')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @analytics("leveling get multiplier")
    async def get_multiplier(self, ctx: discord.ApplicationContext):
        try:
            multiplier = calc_multiplier(ctx.guild.id)
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_get_multiplier_response", append_tip=True).format(
                    multiplier=multiplier), ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='set_xp_per_level', description='Set the XP per level')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="xp", description="The XP to set", type=int)
    @analytics("leveling set xp per level")
    async def set_xp_per_level(self, ctx: discord.ApplicationContext, xp: int):
        try:
            old_xp = get_setting(ctx.guild.id, 'leveling_xp_per_level', '500')
            set_setting(ctx.guild.id, 'leveling_xp_per_level', str(xp))
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_set_xp_per_level_success", append_tip=True).format(xp=xp),
                ephemeral=True)

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_set_xp_per_level_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_set_xp_per_level_log_old_xp"),
                                    value=f"{old_xp}")
            logging_embed.add_field(name=trl(0, ctx.guild.id, "leveling_set_xp_per_level_log_new_xp"), value=f"{xp}")

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='set_reward', description='Set a role for a level')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="level", description="The level to set the reward for", type=int)
    @discord.option(name='role', description='The role to set', type=discord.Role)
    @analytics("leveling set reward")
    async def set_reward(self, ctx: discord.ApplicationContext, level: int, role: discord.Role):
        try:
            # Get old setting
            old_role_id = get_setting(ctx.guild.id, f"leveling_reward_{level}", '0')
            old_role = ctx.guild.get_role(int(old_role_id))

            # Set new setting
            set_setting(ctx.guild.id, f'leveling_reward_{level}', str(role.id))

            # Logging embed
            logging_embed = discord.Embed(title=trl(0, ctx.guild.id, "leveling_set_reward_log_title"))
            logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            if old_role_id == '0':
                logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_role"),
                                        value=trl(0, ctx.guild.id, "leveling_set_reward_log_role_added").format(
                                            reward=role.mention))
            else:
                logging_embed.add_field(name=trl(0, ctx.guild.id, "logging_role"),
                                        value=trl(0, ctx.guild.id, "leveling_set_reward_log_role_changed").format(
                                            old_reward=old_role.mention if old_role is not None else old_role_id,
                                            new_reward=role.mention))

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_set_reward_success", append_tip=True).format(level=level,
                                                                                                      reward=role.mention),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='remove_reward', description='Remove a role for a level')
    @discord.default_permissions(manage_guild=True)
    @commands_ext.has_permissions(manage_guild=True)
    @commands_ext.guild_only()
    @discord.option(name="level", description="The level to remove the reward for", type=int)
    @analytics("leveling remove reward")
    async def remove_reward(self, ctx: discord.ApplicationContext, level: int):
        try:
            # Get old settingF
            old_role_id = get_setting(ctx.guild.id, f"leveling_reward_{level}", '0')
            old_role = ctx.guild.get_role(int(old_role_id))

            # Logging embed
            logging_embed = discord.Embed(title=trl(ctx.user.id, ctx.guild.id, "leveling_remove_reward_log_title"))
            logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_user"), value=f"{ctx.user.mention}")
            if old_role is not None:
                logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_role"),
                                        value=f"{old_role.mention}")
            else:
                logging_embed.add_field(name=trl(ctx.user.id, ctx.guild.id, "logging_role"),
                                        value=trl(ctx.user.id, ctx.guild.id, "leveling_remove_reward_log_role_unknown"))

            # Send into logs
            await log_into_logs(ctx.guild, logging_embed)

            # Set new setting
            set_setting(ctx.guild.id, f'leveling_reward_{level}', '0')

            # Send response
            await ctx.respond(
                trl(ctx.user.id, ctx.guild.id, "leveling_remove_reward_success", append_tip=True).format(level=level),
                ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name="set_icon", description="Set leveling icon")
    @analytics("leveling set icon")
    @commands_ext.guild_only()
    async def set_icon(self, ctx: discord.ApplicationContext, icon: str):
        try:
            success = False
            if emoji.is_emoji(icon):
                set_per_user_setting(ctx.user.id, 'leveling_icon', icon)
                success = True

            if re.match("<a?:[a-zA-Z0-9_]+:[0-9]+>", icon):
                set_per_user_setting(ctx.user.id, 'leveling_icon', icon)
                success = True

            if success:
                await ctx.respond(
                    trl(ctx.user.id, ctx.guild.id, "leveling_set_icon_success", append_tip=True).format(icon=icon),
                    ephemeral=True)
            else:
                await ctx.respond(trl(ctx.user.id, ctx.guild.id, "leveling_set_icon_error"), ephemeral=True)

        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)

    @leveling_subcommand.command(name='leaderboard', description='Get the leaderboard for the server')
    async def leveling_lb(self, ctx: discord.ApplicationContext):
        try:
            # Get the top 10 users
            top_users = client['Leveling'].aggregate([
                {
                    '$match': {
                        'GuildID': str(ctx.guild.id)
                    }
                },
                {
                    '$sort': {
                        'XP': -1
                    }
                }
            ])  # type: list[dict]
            # has GuildID, UserID, XP

            lb_pages = []
            insert_last = False

            # Create the embed
            leaderboard_message = trl(ctx.user.id, ctx.guild.id, "leveling_leaderboard_title")

            # Add the users to the embed
            i = 1
            for _, user in enumerate(top_users):
                user_obj = ctx.guild.get_member(int(user['UserID']))
                if user_obj is None:
                    continue
                leaderboard_message += trl(ctx.user.id, ctx.guild.id, "leveling_leaderboard_row").format(
                    position=i, user=user_obj.mention, level=get_level_for_xp(ctx.guild.id, user['XP']), xp=user['XP'])
                i += 1
                insert_last = True

                if i % 10 == 0:
                    if get_per_user_setting(ctx.user.id, 'tips_enabled', 'true') == 'true':
                        language = get_language(ctx.guild.id, ctx.user.id)
                        leaderboard_message = append_tip_to_message(ctx.guild.id, ctx.user.id, leaderboard_message,
                                                                    language)

                    lb_pages.append(leaderboard_message)
                    leaderboard_message = trl(ctx.user.id, ctx.guild.id, "leveling_leaderboard_title")
                    insert_last = False

            if not insert_last:
                if get_per_user_setting(ctx.user.id, 'tips_enabled', 'true') == 'true':
                    language = get_language(ctx.guild.id, ctx.user.id)
                    leaderboard_message = append_tip_to_message(ctx.guild.id, ctx.user.id, leaderboard_message,
                                                                language)

                lb_pages.append(leaderboard_message)

            pages_resp = pages.Paginator(pages=lb_pages)
            await pages_resp.respond(ctx.interaction, ephemeral=True)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, "command_error_generic"), ephemeral=True)
