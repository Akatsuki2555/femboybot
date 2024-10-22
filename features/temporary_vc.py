import discord
from discord.ext import commands

from database import client
from utils.languages import get_translation_for_key_localized as trl
from utils.settings import get_setting, set_setting


class TemporaryVC(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    temporary_vc_commands = discord.SlashCommandGroup(name='temporary_voice_channels', description='Temporary VC channels commands')

    async def new_temporary_channel(self, from_ch: discord.VoiceChannel, for_user: discord.Member) -> discord.VoiceChannel:
        category = from_ch.category

        new_ch_name = get_setting(for_user.guild.id, 'temporary_vc_name', '{name}\'s channel')

        new_ch_name = new_ch_name.replace('{name}', for_user.display_name)
        new_ch_name = new_ch_name.replace('{username}', for_user.name)
        new_ch_name = new_ch_name.replace('{guild}', for_user.guild.name)

        if not category:
            new_ch = await from_ch.guild.create_voice_channel(name=new_ch_name, reason=trl(0, for_user.guild.id, 'temporary_vc_mod_reason'), bitrate=from_ch.bitrate, user_limit=from_ch.user_limit)
        else:
            new_ch = await category.create_voice_channel(name=new_ch_name, reason=trl(0, for_user.guild.id, 'temporary_vc_mod_reason'), bitrate=from_ch.bitrate, user_limit=from_ch.user_limit)

        res = client['TemporaryVC'].insert_one({'ChannelID': str(new_ch.id), 'GuildID': str(new_ch.guild.id), 'CreatorID': str(for_user.id)})

        if '{id}' in new_ch_name:
            id = str(res.inserted_id)
            new_ch_name = new_ch_name.replace('{id}', str(id))
            await new_ch.edit(name=new_ch_name)

        return new_ch

    @discord.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # First let's check joining for temporary voice channel creation
        if after.channel and not before.channel:
            # cur = conn.cursor()
            # cur.execute('select * from temporary_vc_creator_channels where channel_id = ? and guild_id = ?', (after.channel.id, after.channel.guild.id))
            if client['TemporaryVCCreators'].count_documents({'ChannelID': str(after.channel.id), 'GuildID': str(after.channel.guild.id)}) > 0:
                vc = await self.new_temporary_channel(after.channel, member)
                await member.move_to(vc, reason=trl(0, member.guild.id, 'temporary_vc_mod_reason'))

        # Now let's check leaving for temporary voice channel deletion

        if before.channel and not after.channel:
            if len(before.channel.voice_states) > 0:
                return

            if client['TemporaryVC'].count_documents({'ChannelID': str(before.channel.id), 'GuildID': str(before.channel.guild.id)}) > 0:
                await before.channel.delete(reason=trl(0, member.guild.id, 'temporary_vc_mod_reason'))

            client['TemporaryVC'].delete_one({'ChannelID': str(before.channel.id), 'GuildID': str(before.channel.guild.id)})

    @temporary_vc_commands.command(name='add_creator_channel', description='Add a channel to create temporary voice channels')
    @discord.default_permissions(manage_guild=True)
    @commands.has_permissions(manage_guild=True)
    async def add_creator_channel(self, ctx: discord.ApplicationContext, channel: discord.VoiceChannel):
        client['TemporaryVCCreators'].insert_one({'ChannelID': str(channel.id), 'GuildID': str(channel.guild.id)})
        await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_creator_channel_add').format(channel=channel.mention), ephemeral=True)

    @temporary_vc_commands.command(name='remove_creator_channel', description='Remove a channel to create temporary voice channels')
    @discord.default_permissions(manage_guild=True)
    @commands.has_permissions(manage_guild=True)
    async def remove_creator_channel(self, ctx: discord.ApplicationContext, channel: discord.VoiceChannel):
        if client['TemporaryVCCreators'].delete_one({'ChannelID': str(channel.id), 'GuildID': str(channel.guild.id)}).deleted_count > 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_creator_channel_remove').format(channel=channel.mention), ephemeral=True)
        else:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_channel_not_in_creator').format(channel=channel.mention), ephemeral=True)

    @temporary_vc_commands.command(name='change_name', description='Change the name of a temporary voice channel')
    async def change_name(self, ctx: discord.ApplicationContext, name: str):
        if len(name) > 16:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_name_too_long'), ephemeral=True)
            return

        if len(name) < 2:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_name_too_short'), ephemeral=True)
            return

        if client['TemporaryVC'].count_documents({'ChannelID': str(ctx.guild.id), 'GuildID': str(ctx.guild.id), 'CreatorID': str(ctx.user.id)}) == 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_not_a_temporary_channel').format(channel=ctx.channel.mention), ephemeral=True)
            return

        await ctx.channel.edit(name=name)
        await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_name_change').format(channel=ctx.channel.mention, name=name), ephemeral=True)

    @temporary_vc_commands.command(name='change_max', description='Change the max users of a temporary voice channel')
    async def change_max(self, ctx: discord.ApplicationContext, max_users: int):
        if max_users < 2:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_min_users'), ephemeral=True)
            return

        if max_users > 99:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_max_users'), ephemeral=True)
            return

        if client['TemporaryVC'].count_documents({'ChannelID': str(ctx.guild.id), 'GuildID': str(ctx.guild.id), 'CreatorID': str(ctx.user.id)}) == 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_not_a_temporary_channel').format(channel=ctx.channel.mention), ephemeral=True)
            return

        await ctx.channel.edit(user_limit=max_users)
        await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_max_users_change').format(channel=ctx.channel.mention, max_users=str(max_users)), ephemeral=True)

    @temporary_vc_commands.command(name='change_bitrate', description='Change the bitrate of a temporary voice channel')
    async def change_bitrate(self, ctx: discord.ApplicationContext, bitrate: int):
        if bitrate < 8:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_min_bitrate'), ephemeral=True)
            return

        if bitrate > 96:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_max_bitrate'), ephemeral=True)
            return

        bitrate = bitrate * 1000

        if client['TemporaryVC'].count_documents({'ChannelID': str(ctx.guild.id), 'GuildID': str(ctx.guild.id), 'CreatorID': str(ctx.user.id)}) == 0:
            await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_error_not_a_temporary_channel').format(channel=ctx.channel.mention), ephemeral=True)
            return

        await ctx.channel.edit(bitrate=bitrate)
        await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_bitrate_change').format(channel=ctx.channel.mention, bitrate=str(bitrate)), ephemeral=True)

    @temporary_vc_commands.command(name='change_default_name', description='Default name syntax. {name}, {username}, {guild}, {id} are available')
    async def change_default_name(self, ctx: discord.ApplicationContext, name: str):
        set_setting(ctx.guild.id, 'temporary_vc_name', name)
        await ctx.respond(trl(ctx.user.id, ctx.guild.id, 'temporary_vc_name_format_change').format(name=name), ephemeral=True)