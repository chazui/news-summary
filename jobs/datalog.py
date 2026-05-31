import json
import os
from datetime import datetime

def count_jsonl_lines(filepath):
    """Returns the number of lines in a file."""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, 'rb') as f:
        return sum(1 for _ in f)


def get_news_log_ID(news_log=None):
    """
    Retrieves the news log ID.

    If a news_log dictionary is provided, returns the ID within it.
    Otherwise, generates a new ID based on the current date and a
    hexadecimal counter, persisting it to current_newsID.json.
    """
    if news_log is not None:
        return news_log.get('newsID')

    filename = 'sys_variables/current_newsID.json'
    today = datetime.now()
    date_str = today.strftime('%m%d%Y')

    def save_new_id(id_string):
        with open(filename, 'w') as f:
            json.dump({'newsID': id_string}, f)
        return id_string

    if not os.path.exists(filename):
        return save_new_id(f"{date_str}_0000")

    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            current_id = data.get('newsID')
        if not current_id:
            return save_new_id(f"{date_str}_0000")
    except (json.JSONDecodeError, IOError):
        return save_new_id(f"{date_str}_0000")

    try:
        parts = current_id.split('_')
        if len(parts) != 2:
            return save_new_id(f"{date_str}_0000")
        stored_date, stored_hex = parts
    except ValueError:
        return save_new_id(f"{date_str}_0000")

    if stored_date != date_str:
        return save_new_id(f"{date_str}_0000")

    try:
        hex_val = int(stored_hex, 16)
        hex_val += 1
        new_hex = f"{hex_val:04X}"
        return save_new_id(f"{date_str}_{new_hex}")
    except ValueError:
        return save_new_id(f"{date_str}_0000")

def log_news(news_json, filename="sys_logs/news_logs.jsonl"):
    """
    Appends a news snapshot to a JSON Lines file.
    news_json is the raw JSON string produced by readnews.export_news_json().
    """
    news_id = get_news_log_ID()

    entry = {
        "newsID": news_id,
        "timestamp": datetime.now().isoformat(),
        "data": json.loads(news_json)
    }

    with open(filename, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, separators=(',', ':')) + '\n')