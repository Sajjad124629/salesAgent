import bootstrap
import sqlite3
import time
from typing import Optional, List, Dict, Any
from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory() -> None:
    conn = get_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                url TEXT PRIMARY KEY,
                score REAL DEFAULT 0.0,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'saved',
                draft TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        # FTS5 table for notes & style feedback
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                content,
                category
            )
        """)
    conn.close()


init_memory()


def save_lead(url: str, score: float, reason: str, status: str = "saved", draft: str = "") -> str:
    """Save or update a lead in the leads table."""
    now = time.time()
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO leads (url, score, reason, status, draft, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                score = excluded.score,
                reason = excluded.reason,
                status = excluded.status,
                draft = CASE WHEN excluded.draft != '' THEN excluded.draft ELSE leads.draft END,
                updated_at = excluded.updated_at
        """, (url, float(score), reason, status, draft, now, now))
    conn.close()
    return f"Lead successfully recorded for {url} with status='{status}'"


def update_lead_status(url: str, status: str, draft: Optional[str] = None) -> str:
    now = time.time()
    conn = get_connection()
    with conn:
        if draft is not None:
            conn.execute("""
                UPDATE leads
                SET status = ?, draft = ?, updated_at = ?
                WHERE url = ?
            """, (status, draft, now, url))
        else:
            conn.execute("""
                UPDATE leads
                SET status = ?, updated_at = ?
                WHERE url = ?
            """, (status, now, url))
    conn.close()
    return f"Lead {url} updated to status '{status}'"


def is_lead_handled(url: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM leads WHERE url = ?", (url,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_lead(url: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE url = ?", (url,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_leads(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM leads WHERE status = ? ORDER BY updated_at DESC", (status,))
    else:
        cur.execute("SELECT * FROM leads ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remember(content: str, category: str = "general") -> str:
    """Store a fact, feedback, or note into FTS5 long-term memory."""
    if not content:
        return "Nothing to remember."
    conn = get_connection()
    with conn:
        conn.execute("INSERT INTO notes_fts (content, category) VALUES (?, ?)", (content.strip(), category.strip()))
    conn.close()
    return f"Remembered in category '{category}': {content[:80]}..."


def recall(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search long-term memory notes using SQLite FTS5."""
    if not query:
        return []
    conn = get_connection()
    cur = conn.cursor()
    clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
    if not clean_query:
        return []
    
    # Try FTS5 MATCH first
    try:
        cur.execute("""
            SELECT content, category, rank
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (clean_query, limit))
        rows = cur.fetchall()
    except Exception:
        # Fallback to LIKE if query has specific syntax issues
        cur.execute("""
            SELECT content, category, 0 as rank
            FROM notes_fts
            WHERE content LIKE ?
            LIMIT ?
        """, (f"%{clean_query}%", limit))
        rows = cur.fetchall()

    conn.close()
    return [{"content": r["content"], "category": r["category"]} for r in rows]


if __name__ == "__main__":
    print("Testing memory.py...")
    print(save_lead("https://reddit.com/r/Upwork/test1", 0.9, "Missing client messages", "saved"))
    print("Handled?", is_lead_handled("https://reddit.com/r/Upwork/test1"))
    print(remember("User prefers short, empathetic 2-sentence messages with no buzzwords.", "style_feedback"))
    print("Recall result:", recall("style feedback"))
