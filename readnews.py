import feedparser as fp
import html
import json
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
import pandas as pd

_UNICODE_MAP = str.maketrans({
    '‘': "'", '’': "'",
    '“': '"', '”': '"',
    '–': '-',  '—': '--',
    '…': '...', ' ': ' ',
})
_HTML_TAG_RE = re.compile(r'<[^>]+>')

_PUBLISHED_FMT = '%a, %d %b %Y %H:%M:%S GMT'

def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub('', text)
    text = text.translate(_UNICODE_MAP)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

def _clean_news_data(obj):
    if isinstance(obj, str):
        return _clean_text(obj)
    if isinstance(obj, list):
        return [_clean_news_data(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _clean_news_data(v) for k, v in obj.items()}
    return obj

def _normalize_published(entry):
    parsed = entry.get('published_parsed')
    if parsed is not None:
        return time.strftime(_PUBLISHED_FMT, parsed)
    return entry.get('published', '')

def get_RSS_feed(feed_url, category=None):
    key_list = ['category', 'published', 'title', 'summary']
    rawfeed = fp.parse(feed_url).entries
    cleaned_feed = []
    for entry in rawfeed:
        filtered_entry = {}
        filtered_entry['category'] = category
        filtered_entry['published'] = _normalize_published(entry)
        if 'title' in entry:
            filtered_entry['title'] = entry['title']
        if 'summary' in entry:
            filtered_entry['summary'] = entry['summary']
        elif 'description' in entry:
            filtered_entry['summary'] = entry['description']
        cleaned_feed.append(filtered_entry)
    if not cleaned_feed:
        return pd.DataFrame(columns=key_list)
    feed = pd.DataFrame(cleaned_feed)
    feed = feed.reindex(columns=key_list)
    return feed

def combine_RSS_df(url_dict):
    frames = [get_RSS_feed(url, category=category)
              for category, urls in url_dict.items()
              for url in urls]
    concat_feed = pd.concat(frames, ignore_index=True)
    concat_feed = concat_feed.astype(str).apply(lambda x: x.str.strip())
    final_feed = concat_feed.drop_duplicates(subset=['title'])
    final_feed = final_feed[final_feed.apply(filterRecentRSSEntries, axis=1, hour_amt=48)]
    return final_feed

def filterRecentRSSEntries(entry, hour_amt=1):
    current_datetime = datetime.now(timezone.utc)
    entry_datetime = _parse_published(entry)
    td = current_datetime - entry_datetime
    max_entry_age = timedelta(hours=hour_amt)
    if (td > max_entry_age):
        return False
    return True

def _parse_published(entry):
    parsed = getattr(entry, 'published_parsed', None)
    if parsed is not None:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    published = entry.published if hasattr(entry, 'published') else entry['published']
    try:
        return datetime.strptime(published, _PUBLISHED_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %z')

def printRSS(entry):
    print(f"{entry.published}: {entry.title}")
    print(f"Entry Link: {entry.link}")
    print(f"Entry Summary: {entry.summary}\n")

def RSSCompare(feed_url, entry):
    feed = fp.parse(feed_url)
    newentry = feed.entries[0]
    if (newentry.title != entry.title):
        return (True, newentry)
    return (False, entry)

def get_RSS_entry(feed_url, index=0):
    entry = get_RSS_feed(feed_url)[index]
    printRSS(entry)
    return entry

def export_news_json(df_news: pd.DataFrame):
    news_dict = _clean_news_data(df_news.to_dict(orient='records'))
    return json.dumps(news_dict)

RSS_feed_urls = {
    'tech': [
        'https://feeds.bloomberg.com/technology/news.rss',
        'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml',
    ],
    'geopolitics': [
        'https://feeds.bloomberg.com/politics/news.rss',
        'https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    ],
    'trade': [
        'https://feeds.bloomberg.com/markets/news.rss',
        'https://feeds.bloomberg.com/crypto/news.rss',
        'https://feeds.bloomberg.com/industries/news.rss',
    ],
    'economy': [
        'https://feeds.bloomberg.com/economics/news.rss',
        'https://feeds.bloomberg.com/wealth/news.rss',
        'https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml',
    ],
}

def run(urls=RSS_feed_urls):
    df_news = combine_RSS_df(urls)
    news_json = export_news_json(df_news)
    return news_json

if __name__ == '__main__':
    news = run()
    print(news)
