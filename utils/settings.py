from database import client


def get_setting(server_id: int, key: str, default: str) -> str:
    res = client['ServerSettings'].find_one({'ServerID': str(server_id)})
    return res[key] if res and key in res else default


def set_setting(server_id: int, key: str, value) -> None:
    if client['ServerSettings'].count_documents({'ServerID': str(server_id)}) == 0:
        client['ServerSettings'].insert_one({'ServerID': str(server_id)})

    if value is not None:
        client['ServerSettings'].update_one({'ServerID': str(server_id)}, {'$set': {key: value}})
    else:
        client['ServerSettings'].update_one({'ServerID': str(server_id)}, {'$unset': {key: 1}})
