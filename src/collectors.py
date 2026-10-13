"""Collectors. Each returns a list of post dicts; raw responses are saved to disk first."""
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

import config

HN_URL = "https://hn.algolia.com/api/v1/search_by_date"
GH_URL = "https://api.github.com/search/issues"
_raw_counter = 0


# ---------- helpers ----------

def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def from_epoch(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)


def from_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<\s*(p|br)\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html.unescape(text)).strip()


def save_raw(source, payload):
    """Keep every raw response so we can re-parse later without refetching."""
    global _raw_counter
    _raw_counter += 1
    folder = config.RAW_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{now_utc().strftime('%Y%m%dT%H%M%S')}-{_raw_counter:04d}.json"
    (folder / name).write_text(json.dumps(payload))


def get_json(source, url, params=None, headers=None, retries=3):
    h = {"User-Agent": config.USER_AGENT}
    h.update(headers or {})
    for attempt in range(retries):
        r = requests.get(url, params=params, headers=h, timeout=30)
        if r.status_code in (403, 429) and attempt < retries - 1:
            wait = int(r.headers.get("Retry-After", 30 * (attempt + 1)))
            print(f"  rate limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        save_raw(source, data)
        return data
    return {}


# ---------- Hacker News (Algolia search API, no auth) ----------

def collect_hn(days=7, queries=None, pages=2):
    queries = queries or config.PHRASE_QUERIES
    since = int(time.time()) - days * 86400
    rows = []
    for q in queries:
        for tag in ("story", "comment"):
            for page in range(pages):
                data = get_json("hn", HN_URL, params={
                    "query": f'"{q}"',
                    "tags": tag,
                    "numericFilters": f"created_at_i>{since}",
                    "hitsPerPage": 100,
                    "page": page,
                })
                rows += parse_hn_hits(data.get("hits", []))
                if page + 1 >= data.get("nbPages", 0):
                    break
                time.sleep(0.5)
        print(f"  hn: '{q}' done ({len(rows)} rows so far)")
    return rows


def parse_hn_hits(hits):
    rows = []
    for h in hits:
        body = clean_html(h.get("comment_text") or h.get("story_text") or "")
        title = h.get("title") or h.get("story_title") or ""
        if not (body or title):
            continue
        rows.append({
            "uid": f"hn:{h['objectID']}",
            "source": "hn",
            "container": h.get("story_title") or "front page",
            "title": title,
            "body": body,
            "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
            "score": h.get("points") or 0,
            "num_comments": h.get("num_comments") or 0,
            "created_at": from_epoch(h["created_at_i"]),
            "fetched_at": now_utc(),
        })
    return rows


# ---------- GitHub issues (search API; token optional but strongly advised) ----------

def collect_github(days=30, queries=None, per_page=50):
    queries = queries or config.GITHUB_QUERIES
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("  (no GITHUB_TOKEN set: search is limited to ~10 requests/minute)")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = []
    for q in queries:
        data = get_json("github", GH_URL, headers=headers, params={
            "q": f"{q} is:issue created:>{since}",
            "sort": "created",
            "order": "desc",
            "per_page": per_page,
        })
        rows += parse_github_items(data.get("items", []))
        print(f"  github: {q} done ({len(rows)} rows so far)")
        time.sleep(3 if token else 8)  # stay under search rate limits
    return rows


def parse_github_items(items):
    rows = []
    for it in items:
        repo = it["repository_url"].split("repos/")[-1]
        rows.append({
            "uid": f"gh:{it['id']}",
            "source": "github",
            "container": repo,
            "title": it.get("title") or "",
            "body": (it.get("body") or "")[:4000],
            "url": it["html_url"],
            "score": (it.get("reactions") or {}).get("total_count", 0),
            "num_comments": it.get("comments", 0),
            "created_at": from_iso(it["created_at"]),
            "fetched_at": now_utc(),
        })
    return rows


# ---------- Reddit (needs approved API credentials; skipped if not set) ----------

def collect_reddit(subs=None, queries=None, limit=100):
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        print("  reddit: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set, skipping")
        return []
    subs = subs or config.REDDIT_SUBREDDITS
    queries = queries or config.PHRASE_QUERIES
    tok = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(cid, secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": config.USER_AGENT},
        timeout=30,
    )
    tok.raise_for_status()
    headers = {"Authorization": f"bearer {tok.json()['access_token']}"}
    rows = []
    for sub in subs:
        for q in queries:
            data = get_json("reddit", f"https://oauth.reddit.com/r/{sub}/search", headers=headers, params={
                "q": f'"{q}"', "restrict_sr": 1, "sort": "new", "t": "month", "limit": limit,
            })
            rows += parse_reddit(data)
            time.sleep(1)
        print(f"  reddit: r/{sub} done ({len(rows)} rows so far)")
    return rows


def parse_reddit(data):
    rows = []
    for child in data.get("data", {}).get("children", []):
        d = child["data"]
        rows.append({
            "uid": f"reddit:{d['id']}",
            "source": "reddit",
            "container": d["subreddit"],
            "title": d.get("title") or "",
            "body": d.get("selftext") or "",
            "url": "https://reddit.com" + d["permalink"],
            "score": d.get("score") or 0,
            "num_comments": d.get("num_comments") or 0,
            "created_at": from_epoch(d["created_utc"]),
            "fetched_at": now_utc(),
        })
    return rows
