"""DuckDB storage: one file, two tables (posts, extractions)."""
import duckdb

import config

POST_COLS = [
    "uid", "source", "container", "title", "body", "url",
    "score", "num_comments", "created_at", "fetched_at",
]


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.DB_PATH))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            uid VARCHAR PRIMARY KEY,   -- e.g. hn:12345, gh:67890, reddit:abc
            source VARCHAR,
            container VARCHAR,         -- subreddit, repo, or parent story title
            title VARCHAR,
            body VARCHAR,
            url VARCHAR,
            score INTEGER,
            num_comments INTEGER,
            created_at TIMESTAMP,
            fetched_at TIMESTAMP,
            kw_score DOUBLE,           -- filled by `score` step
            kw_hits VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS extractions (
            uid VARCHAR PRIMARY KEY,
            is_pain BOOLEAN,
            who VARCHAR,
            problem VARCHAR,
            workaround VARCHAR,
            cost_signal VARCHAR,
            frequency VARCHAR,
            pays BOOLEAN,
            confidence DOUBLE,
            model VARCHAR,
            extracted_at TIMESTAMP
        )
        """
    )
    return con


def upsert_posts(con, rows):
    """Insert new posts, ignore ones we already have. Returns number of new rows."""
    if not rows:
        return 0
    before = con.execute("SELECT count(*) FROM posts").fetchone()[0]
    sql = (
        f"INSERT OR IGNORE INTO posts ({', '.join(POST_COLS)}) "
        f"VALUES ({', '.join('?' for _ in POST_COLS)})"
    )
    con.executemany(sql, [[r[c] for c in POST_COLS] for r in rows])
    after = con.execute("SELECT count(*) FROM posts").fetchone()[0]
    return after - before
