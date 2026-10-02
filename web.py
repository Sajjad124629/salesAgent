import bootstrap
import os
import json
import time
import sqlite3
import httpx
import feedparser
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from config import EXA_API_KEY, EXA_SEARCH_URL, EXA_CONTENTS_URL, DB_PATH, LOOKBACK_DAYS

CACHE_TTL_SECONDS = 6 * 3600  # 6 hours cache


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_cache_db() -> None:
    conn = get_db_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS web_cache (
                cache_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
    conn.close()


init_cache_db()


def get_cached_response(key: str) -> Optional[Any]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT response_json, created_at FROM web_cache WHERE cache_key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        resp_json, created_at = row["response_json"], row["created_at"]
        if time.time() - created_at < CACHE_TTL_SECONDS:
            try:
                return json.loads(resp_json)
            except Exception:
                return None
    return None


def set_cached_response(key: str, data: Any) -> None:
    conn = get_db_connection()
    with conn:
        conn.execute("""
            INSERT INTO web_cache (cache_key, response_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                created_at = excluded.created_at
        """, (key, json.dumps(data), time.time()))
    conn.close()


def wrap_untrusted(text: str) -> str:
    """Wraps text in untrusted_data tags for Day 5 security defense against prompt injection."""
    if not text:
        return ""
    return f"<untrusted_data>\n{text.strip()}\n</untrusted_data>"


def _is_url_handled(url: str) -> bool:
    """Check if URL has already been handled in the leads table (Day 3 requirement)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Check if table exists
        cur.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='leads'")
        if cur.fetchone()[0] == 0:
            conn.close()
            return False
        cur.execute("SELECT 1 FROM leads WHERE url = ?", (url,))
        row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def get_reddit_posts(subreddit: str) -> List[Dict[str, Any]]:
    """
    Fetch recent posts from a subreddit RSS feed.
    Subreddits: Upwork, freelance, Daytrading, CryptoCurrency, sales.
    Caches for 6 hours. Filters out handled leads.
    """
    subreddit = subreddit.strip().lstrip("r/").strip()
    cache_key = f"reddit:{subreddit.lower()}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        posts = cached
    else:
        url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScoutBot/1.0 (educational agent)"}
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    return [{"error": f"Reddit RSS returned HTTP {res.status_code} for r/{subreddit}"}]
                feed = feedparser.parse(res.text)
        except Exception as e:
            return [{"error": f"Failed to fetch Reddit RSS for r/{subreddit}: {str(e)}"}]

        posts = []
        for entry in feed.entries[:25]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")
            posts.append({
                "source": f"reddit/r/{subreddit}",
                "title": title,
                "url": link,
                "published": published,
                "summary": summary[:1500],  # trim raw HTML/text
            })
        set_cached_response(cache_key, posts)

    # Filter out already handled leads and wrap untrusted text
    results = []
    for p in posts:
        url = p.get("url", "")
        if url and _is_url_handled(url):
            continue
        results.append({
            "source": p.get("source"),
            "title": wrap_untrusted(p.get("title", "")),
            "url": url,
            "published": p.get("published"),
            "summary": wrap_untrusted(p.get("summary", "")),
        })
    return results


def search_hn(query: str, days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Search Hacker News stories by keyword and date via the Algolia API.
    Caches for 6 hours. Filters out handled leads.
    """
    cache_key = f"hn:{query.lower()}:{days}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        hits = cached
    else:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        api_url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&numericFilters=created_at_i>{cutoff}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(api_url)
                if res.status_code != 200:
                    return [{"error": f"Hacker News Algolia API error {res.status_code}: {res.text}"}]
                data = res.json()
                raw_hits = data.get("hits", [])
        except Exception as e:
            return [{"error": f"Failed to search Hacker News: {str(e)}"}]

        hits = []
        for item in raw_hits[:20]:
            title = item.get("title", "")
            story_url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('objectID')}"
            author = item.get("author", "")
            created_at = item.get("created_at", "")
            story_text = item.get("story_text") or ""
            hits.append({
                "source": "hacker_news",
                "title": title,
                "url": story_url,
                "author": author,
                "created_at": created_at,
                "text": story_text[:1500],
            })
        set_cached_response(cache_key, hits)

    # Filter out already handled leads and wrap untrusted text
    results = []
    for h in hits:
        url = h.get("url", "")
        if url and _is_url_handled(url):
            continue
        results.append({
            "source": h.get("source"),
            "title": wrap_untrusted(h.get("title", "")),
            "url": url,
            "author": h.get("author"),
            "created_at": h.get("created_at"),
            "text": wrap_untrusted(h.get("text", "")),
        })
    return results


def search_web(query: str, domains: Optional[List[str]] = None, days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Search web using Exa search API. Filters by domain and date.
    Caches for 6 hours. Filters out handled leads.
    """
    if not EXA_API_KEY:
        return [{"error": "EXA_API_KEY is not configured in .env"}]

    domains_key = ",".join(sorted(domains)) if domains else "all"
    cache_key = f"exa_search:{query.lower()}:{domains_key}:{days}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        items = cached
    else:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        payload: Dict[str, Any] = {
            "query": query,
            "num_results": 6,
            "start_published_date": f"{start_date}T00:00:00.000Z",
        }
        if domains:
            payload["include_domains"] = domains

        headers = {
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.post(EXA_SEARCH_URL, headers=headers, json=payload)
                if res.status_code != 200:
                    return [{"error": f"Exa search API error {res.status_code}: {res.text}"}]
                data = res.json()
                raw_results = data.get("results", [])
        except Exception as e:
            return [{"error": f"Failed Exa search: {str(e)}"}]

        items = []
        for r in raw_results:
            items.append({
                "source": "exa_web_search",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "published_date": r.get("published_date", ""),
                "text": (r.get("text") or "")[:1500],
            })
        set_cached_response(cache_key, items)

    results = []
    for item in items:
        url = item.get("url", "")
        if url and _is_url_handled(url):
            continue
        results.append({
            "source": item.get("source"),
            "title": wrap_untrusted(item.get("title", "")),
            "url": url,
            "published_date": item.get("published_date"),
            "text": wrap_untrusted(item.get("text", "")),
        })
    return results


def read_page(url: str) -> Dict[str, Any]:
    """
    Read clean page text for research using Exa contents API, capped at 3,000 characters.
    Caches for 6 hours.
    """
    if not EXA_API_KEY:
        return {"error": "EXA_API_KEY is not configured in .env"}

    cache_key = f"exa_contents:{url}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        return cached

    headers = {
        "x-api-key": EXA_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "urls": [url],
        "text": {"max_characters": 3000},
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(EXA_CONTENTS_URL, headers=headers, json=payload)
            if res.status_code != 200:
                return {"error": f"Exa contents API error {res.status_code}: {res.text}"}
            data = res.json()
            results = data.get("results", [])
            if not results:
                return {"url": url, "text": wrap_untrusted("No content found.")}
            page = results[0]
            clean_text = page.get("text", "")[:3000]
            output = {
                "url": url,
                "title": page.get("title", ""),
                "text": wrap_untrusted(clean_text),
            }
            set_cached_response(cache_key, output)
            return output
    except Exception as e:
        return {"error": f"Failed to read page {url}: {str(e)}"}


if __name__ == "__main__":
    print("Testing get_reddit_posts...")
    r = get_reddit_posts("Upwork")
    print(f"Reddit Upwork posts found: {len(r)}")
    print("Testing search_hn...")
    h = search_hn("freelance")
    print(f"HN posts found: {len(h)}")
    print("Testing read_page...")
    p = read_page("https://news.ycombinator.com")
    print(f"Read page title: {p.get('title')}, text len: {len(p.get('text', ''))}")
