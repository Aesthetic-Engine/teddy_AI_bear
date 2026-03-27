"""SQLite-backed structured memory for Teddy.

Tables:
  user_facts     -- durable semantic facts about the user (preferences, relationships, etc.)
  episodes       -- immutable autobiographical session summaries (written once, never re-compressed)
  working_memory -- short-lived per-session context bullets (cleared at session end)
  meta           -- schema version and misc key/value

All writes use Pass / Update / Append deduplication logic.
All reads are deterministic SQL -- no vectors, no external processes.
"""

from __future__ import annotations

import datetime
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_facts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT    NOT NULL,
    fact         TEXT    NOT NULL,
    confidence   REAL    NOT NULL DEFAULT 1.0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    last_updated TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_uf_category ON user_facts (category, is_active);

CREATE TABLE IF NOT EXISTS episodes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date     TEXT    NOT NULL,
    topic            TEXT    NOT NULL,
    summary          TEXT    NOT NULL,
    importance_score INTEGER NOT NULL DEFAULT 5,
    emotional_valence TEXT   NOT NULL DEFAULT 'neutral',
    last_accessed    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ep_date ON episodes (session_date DESC);

CREATE TABLE IF NOT EXISTS working_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    bullet     TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wm_session ON working_memory (session_id);
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    db_path = config.MEMORY_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they do not already exist. Safe to call multiple times."""
    with _connect() as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')"
        )


# ---------------------------------------------------------------------------
# user_facts
# ---------------------------------------------------------------------------

def upsert_fact(category: str, fact: str, confidence: float = 1.0) -> str:
    """Apply Pass / Update / Append logic for a single incoming fact.

    Pass:   incoming fact is semantically identical to an existing active row.
    Update: same category, different content -- old row is soft-deleted, new inserted.
    Append: genuinely new category/fact -- inserted as a fresh row.

    Returns the operation string: 'pass', 'update', or 'append'.
    """
    category = category.strip()[:80]
    fact = fact.strip()[:300]
    normalized = fact.lower()
    now = datetime.datetime.now().isoformat()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, fact FROM user_facts WHERE category = ? AND is_active = 1",
            (category,),
        ).fetchall()

        for row in rows:
            if row["fact"].strip().lower() == normalized:
                conn.execute(
                    "UPDATE user_facts SET last_updated = ? WHERE id = ?",
                    (now, row["id"]),
                )
                return "pass"

        # Soft-delete any existing active rows for this category (contradiction/update)
        if rows:
            ids = [r["id"] for r in rows]
            conn.executemany(
                "UPDATE user_facts SET is_active = 0, last_updated = ? WHERE id = ?",
                [(now, row_id) for row_id in ids],
            )

        conn.execute(
            "INSERT INTO user_facts (category, fact, confidence, is_active, last_updated) "
            "VALUES (?, ?, ?, 1, ?)",
            (category, fact, max(0.0, min(1.0, confidence)), now),
        )
        return "update" if rows else "append"


def get_active_facts() -> list[dict]:
    """Return all active user_facts ordered by most recently updated first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, fact, confidence, last_updated "
            "FROM user_facts WHERE is_active = 1 ORDER BY last_updated DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def compile_user_profile(max_chars: int) -> str:
    """Return a compact User Profile string for prompt injection.

    Format: one bullet per fact, grouped loosely, hard-capped at max_chars.
    """
    facts = get_active_facts()
    if not facts:
        return ""
    lines: list[str] = []
    total = 0
    for f in facts:
        line = f"- {f['category']}: {f['fact']}"
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# episodes
# ---------------------------------------------------------------------------

def append_episode(
    topic: str,
    summary: str,
    importance_score: int = 5,
    emotional_valence: str = "neutral",
) -> int:
    """Write one immutable episode row. Returns the new row id."""
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO episodes "
            "(session_date, topic, summary, importance_score, emotional_valence, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                today,
                topic.strip()[:100],
                summary.strip()[:600],
                max(1, min(10, importance_score)),
                emotional_valence.strip()[:30],
                now,
            ),
        )
        return cur.lastrowid or 0


def query_episodes(
    keywords: list[str],
    max_count: int = 3,
    max_chars: int = 1600,
) -> list[dict]:
    """Return episodes matching any keyword, ranked by recency + importance.

    Caps on max_count and combined total chars are strictly enforced.
    If keywords is empty, returns the N most recent high-importance episodes.
    """
    with _connect() as conn:
        if keywords:
            clauses = " OR ".join(
                ["(topic LIKE ? OR summary LIKE ?)"] * len(keywords)
            )
            params: list = []
            for kw in keywords:
                like = f"%{kw}%"
                params.extend([like, like])
            rows = conn.execute(
                f"SELECT topic, summary, session_date, importance_score, emotional_valence "
                f"FROM episodes WHERE {clauses} "
                f"ORDER BY session_date DESC, importance_score DESC LIMIT ?",
                params + [max_count * 3],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT topic, summary, session_date, importance_score, emotional_valence "
                "FROM episodes ORDER BY session_date DESC, importance_score DESC LIMIT ?",
                (max_count * 3,),
            ).fetchall()

    results: list[dict] = []
    total_chars = 0
    for row in rows:
        if len(results) >= max_count:
            break
        entry = dict(row)
        chunk = f"[{entry['session_date']}] {entry['topic']}: {entry['summary']}"
        if total_chars + len(chunk) + 1 > max_chars:
            break
        results.append(entry)
        total_chars += len(chunk) + 1

    if results:
        _touch_episodes([r["topic"] for r in results])

    return results


def _touch_episodes(topics: list[str]) -> None:
    """Update last_accessed for retrieved episodes (for LRU scoring)."""
    now = datetime.datetime.now().isoformat()
    with _connect() as conn:
        for topic in topics:
            conn.execute(
                "UPDATE episodes SET last_accessed = ? WHERE topic = ?",
                (now, topic),
            )


def format_episodes(episodes: list[dict]) -> str:
    if not episodes:
        return ""
    lines = [
        f"- [{e['session_date']}] {e['topic']}: {e['summary']}"
        for e in episodes
    ]
    return "\n".join(lines)


def prune_episodes(older_than_days: int | None = None, min_importance: int | None = None) -> int:
    """Delete low-importance old episodes. Returns count deleted."""
    days = older_than_days if older_than_days is not None else config.MEMORY_EPISODE_PRUNE_DAYS
    min_imp = min_importance if min_importance is not None else config.MEMORY_EPISODE_PRUNE_MIN_IMPORTANCE
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM episodes WHERE session_date < ? AND importance_score < ?",
            (cutoff, min_imp),
        )
        return cur.rowcount


# ---------------------------------------------------------------------------
# working_memory
# ---------------------------------------------------------------------------

def set_working_memory(session_id: str, bullets: list[str]) -> None:
    """Replace all working memory bullets for a session atomically."""
    now = datetime.datetime.now().isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM working_memory WHERE session_id = ?", (session_id,))
        for bullet in bullets:
            b = bullet.strip()
            if b:
                conn.execute(
                    "INSERT INTO working_memory (session_id, bullet, created_at) VALUES (?, ?, ?)",
                    (session_id, b[:300], now),
                )


def get_working_memory(session_id: str, max_chars: int = 600) -> str:
    """Return formatted working memory bullets for a session."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT bullet FROM working_memory WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    lines: list[str] = []
    total = 0
    for row in rows:
        line = f"- {row['bullet']}"
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def get_combined_working_memory(session_id: str, max_chars: int = 600) -> str:
    """Return persistent + session-specific working memory in one bounded block."""
    blocks: list[str] = []
    remaining = max_chars
    persistent = get_working_memory(config.MEMORY_PERSISTENT_WORKING_KEY, max_chars=remaining)
    if persistent:
        blocks.append(persistent)
        remaining -= len(persistent)
    if session_id and remaining > 0:
        current = get_working_memory(session_id, max_chars=remaining)
        if current:
            blocks.append(current)
    return "\n".join(blocks).strip()


def clear_working_memory(session_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM working_memory WHERE session_id = ?", (session_id,))
