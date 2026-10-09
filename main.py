import os
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify
from google.cloud import bigquery

app = Flask(__name__)
bq = bigquery.Client()

TABLE = os.environ["BQ_TABLE"]  # e.g. my-project.pain_signals.reddit_posts
UA = f"pain-signals/0.1 by u/{os.environ.get('REDDIT_USERNAME', 'unknown')}"

SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("subreddit", "STRING"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("body", "STRING"),
    bigquery.SchemaField("score", "INTEGER"),
    bigquery.SchemaField("num_comments", "INTEGER"),
    bigquery.SchemaField("permalink", "STRING"),
    bigquery.SchemaField("created_utc", "TIMESTAMP"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]


def ensure_table():
    bq.create_table(bigquery.Table(TABLE, schema=SCHEMA), exists_ok=True)


def get_token():
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_posts(sub, token, limit=100):
    r = requests.get(
        f"https://oauth.reddit.com/r/{sub}/new",
        params={"limit": limit},
        headers={"Authorization": f"bearer {token}", "User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for child in r.json()["data"]["children"]:
        d = child["data"]
        rows.append({
            "id": d["id"],
            "subreddit": d["subreddit"],
            "title": d.get("title"),
            "body": d.get("selftext"),
            "score": d.get("score"),
            "num_comments": d.get("num_comments"),
            "permalink": "https://reddit.com" + d["permalink"],
            "created_utc": d["created_utc"],
            "ingested_at": now,
        })
    return rows


@app.route("/ingest", methods=["POST", "GET"])
def ingest():
    subs = request.args.get("subs", "smallbusiness,Entrepreneur,sysadmin").split(",")
    ensure_table()
    token = get_token()
    total = 0
    for sub in subs:
        rows = fetch_posts(sub.strip(), token)
        if not rows:
            continue
        # row_ids = post ids -> BigQuery best-effort dedupe on retries
        errors = bq.insert_rows_json(TABLE, rows, row_ids=[r["id"] for r in rows])
        if errors:
            return jsonify({"sub": sub, "errors": errors}), 500
        total += len(rows)
    return jsonify({"inserted": total, "subs": subs})


@app.route("/")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
