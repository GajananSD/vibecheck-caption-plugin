"""SQLite store: team posts (training data), received checks, generated captions."""
import json
import sqlite3
import time
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    team_id     INTEGER NOT NULL,
    post_id     INTEGER NOT NULL,
    caption     TEXT    NOT NULL,
    clean_text  TEXT    NOT NULL,
    hashtags    TEXT    NOT NULL,   -- JSON list
    emojis      TEXT    NOT NULL,   -- JSON list
    n_words     INTEGER NOT NULL,
    likes       INTEGER,
    comments    INTEGER,
    posted_at   TEXT,
    PRIMARY KEY (team_id, post_id)
);
CREATE TABLE IF NOT EXISTS team_sync (
    team_id      INTEGER PRIMARY KEY,
    last_fetched REAL NOT NULL,
    n_posts      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id     INTEGER,
    team_id      INTEGER,
    received_at  REAL NOT NULL,
    description  TEXT,
    vibe_score   REAL,
    keywords     TEXT,   -- JSON list
    mood         TEXT,   -- JSON list
    source       TEXT,   -- gemini | template
    elapsed_ms   INTEGER
);
CREATE TABLE IF NOT EXISTS suggestions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    check_row_id  INTEGER NOT NULL REFERENCES checks(id),
    rank          INTEGER NOT NULL,
    caption       TEXT NOT NULL,
    tone_match    REAL,
    keyword_hits  INTEGER,
    pred_likes    REAL,
    fit           REAL
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with connect() as c:
        c.executescript(SCHEMA)


def upsert_posts(team_id: int, rows: list[dict]):
    """rows: output of etl.clean_post()."""
    with connect() as c:
        c.executemany(
            """INSERT INTO posts (team_id, post_id, caption, clean_text, hashtags, emojis,
                                  n_words, likes, comments, posted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(team_id, post_id) DO UPDATE SET
                 caption=excluded.caption, clean_text=excluded.clean_text,
                 hashtags=excluded.hashtags, emojis=excluded.emojis, n_words=excluded.n_words,
                 likes=COALESCE(excluded.likes, posts.likes),
                 comments=COALESCE(excluded.comments, posts.comments),
                 posted_at=COALESCE(excluded.posted_at, posts.posted_at)""",
            [(team_id, r["post_id"], r["caption"], r["clean_text"], json.dumps(r["hashtags"]),
              json.dumps(r["emojis"]), r["n_words"], r["likes"], r["comments"], r["posted_at"])
             for r in rows],
        )


def team_posts(team_id: int) -> list[dict]:
    with connect() as c:
        cur = c.execute("SELECT * FROM posts WHERE team_id=? ORDER BY posted_at", (team_id,))
        out = []
        for r in cur:
            d = dict(r)
            d["hashtags"] = json.loads(d["hashtags"])
            d["emojis"] = json.loads(d["emojis"])
            out.append(d)
        return out


def last_fetched(team_id: int) -> float:
    with connect() as c:
        r = c.execute("SELECT last_fetched FROM team_sync WHERE team_id=?", (team_id,)).fetchone()
        return r["last_fetched"] if r else 0.0


def mark_fetched(team_id: int, n_posts: int):
    with connect() as c:
        c.execute(
            """INSERT INTO team_sync (team_id, last_fetched, n_posts) VALUES (?,?,?)
               ON CONFLICT(team_id) DO UPDATE SET last_fetched=excluded.last_fetched,
                                                  n_posts=excluded.n_posts""",
            (team_id, time.time(), n_posts),
        )


def log_check(check_id, team_id, description, vibe_score, keywords, mood, source,
              elapsed_ms, scored: list[dict]) -> int:
    with connect() as c:
        cur = c.execute(
            """INSERT INTO checks (check_id, team_id, received_at, description, vibe_score,
                                   keywords, mood, source, elapsed_ms)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (check_id, team_id, time.time(), description, vibe_score,
             json.dumps(keywords), json.dumps(mood), source, elapsed_ms),
        )
        row_id = cur.lastrowid
        c.executemany(
            """INSERT INTO suggestions (check_row_id, rank, caption, tone_match, keyword_hits,
                                        pred_likes, fit) VALUES (?,?,?,?,?,?,?)""",
            [(row_id, i + 1, s["caption"], s["tone_match"], s["keyword_hits"],
              s["pred_likes"], s["fit"]) for i, s in enumerate(scored)],
        )
        return row_id
