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
from database import client


def db_get_statistic_channels(guild_id: int):
    """Returns an array of {GuildID: str, ChannelID: str, StatisticText: str}"""
    data = client['StatisticChannels'].find({'GuildID': str(guild_id)}).to_list()

    return data


def db_set_statistic_channel(guild_id: int, channel_id: int, statistic_text: str):
    """Updates or creates a record in DB"""
    client['StatisticChannels'].update_one({'GuildID': str(guild_id), 'ChannelID': str(channel_id)}, {'$set': {
        'StatisticText': statistic_text}},
                                           upsert=True)


def db_remove_statistic_channel(guild_id: int, channel_id: int):
    """Removes a record from DB"""
    client['StatisticChannels'].delete_one({'GuildID': str(guild_id), 'ChannelID': str(channel_id)})
