import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pipeline.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS collected_notes (
    note_id TEXT PRIMARY KEY,
    keyword TEXT,
    title TEXT,
    content TEXT,
    images_json TEXT,
    author TEXT,
    url TEXT,
    xsec_token TEXT,
    collected_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    new_title TEXT,
    new_desc TEXT,
    image_paths_json TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS draft_sources (
    draft_id INTEGER REFERENCES drafts(id),
    note_id TEXT REFERENCES collected_notes(note_id),
    PRIMARY KEY (draft_id, note_id)
);

CREATE TABLE IF NOT EXISTS published_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id),
    publish_note_id TEXT,
    published_at TEXT DEFAULT (datetime('now')),
    raw_response_json TEXT
);

CREATE TABLE IF NOT EXISTS explorations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exploration_subtopics (
    exploration_id INTEGER REFERENCES explorations(id),
    keyword TEXT,
    PRIMARY KEY (exploration_id, keyword)
);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_collected_note(conn, note):
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO collected_notes
            (note_id, keyword, title, content, images_json, author, url, xsec_token, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """,
        (
            note["note_id"],
            note["keyword"],
            note["title"],
            note["content"],
            json.dumps(note["images"], ensure_ascii=False),
            note["author"],
            note["url"],
            note["xsec_token"],
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def list_notes_by_status(conn, status):
    return conn.execute(
        "SELECT * FROM collected_notes WHERE status = ?", (status,)
    ).fetchall()


def set_note_status(conn, note_id, status):
    conn.execute(
        "UPDATE collected_notes SET status = ? WHERE note_id = ?", (status, note_id)
    )
    conn.commit()


def insert_draft(conn, topic, new_title, new_desc, source_note_ids, image_paths=None):
    cur = conn.execute(
        """
        INSERT INTO drafts (topic, new_title, new_desc, image_paths_json, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (topic, new_title, new_desc, json.dumps(image_paths or [], ensure_ascii=False)),
    )
    draft_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO draft_sources (draft_id, note_id) VALUES (?, ?)",
        [(draft_id, note_id) for note_id in source_note_ids],
    )
    conn.commit()
    return draft_id


def list_drafts_by_status(conn, status):
    return conn.execute(
        """
        SELECT drafts.*, GROUP_CONCAT(collected_notes.title, ' | ') AS source_titles
        FROM drafts
        LEFT JOIN draft_sources ON draft_sources.draft_id = drafts.id
        LEFT JOIN collected_notes ON collected_notes.note_id = draft_sources.note_id
        WHERE drafts.status = ?
        GROUP BY drafts.id
        ORDER BY drafts.id
        """,
        (status,),
    ).fetchall()


def set_draft_status(conn, draft_id, status):
    conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, draft_id))
    conn.commit()


def update_draft_images(conn, draft_id, image_paths):
    conn.execute(
        "UPDATE drafts SET image_paths_json = ? WHERE id = ?",
        (json.dumps(image_paths, ensure_ascii=False), draft_id),
    )
    conn.commit()


def delete_draft(conn, draft_id):
    conn.execute("DELETE FROM draft_sources WHERE draft_id = ?", (draft_id,))
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    conn.commit()


def update_draft_text(conn, draft_id, new_title, new_desc):
    conn.execute(
        "UPDATE drafts SET new_title = ?, new_desc = ? WHERE id = ?",
        (new_title, new_desc, draft_id),
    )
    conn.commit()


def insert_published(conn, draft_id, publish_note_id, raw_response):
    conn.execute(
        """
        INSERT INTO published_notes (draft_id, publish_note_id, raw_response_json)
        VALUES (?, ?, ?)
        """,
        (draft_id, publish_note_id, json.dumps(raw_response, ensure_ascii=False)),
    )
    conn.execute("UPDATE drafts SET status = 'published' WHERE id = ?", (draft_id,))
    conn.commit()


def insert_exploration(conn, theme, subtopics):
    cur = conn.execute("INSERT INTO explorations (theme) VALUES (?)", (theme,))
    exploration_id = cur.lastrowid
    conn.executemany(
        "INSERT OR IGNORE INTO exploration_subtopics (exploration_id, keyword) VALUES (?, ?)",
        [(exploration_id, keyword) for keyword in subtopics],
    )
    conn.commit()
    return exploration_id


def _subtopic_node(conn, keyword):
    notes = conn.execute(
        "SELECT note_id, title, url, author FROM collected_notes WHERE keyword = ?",
        (keyword,),
    ).fetchall()
    drafts = conn.execute(
        "SELECT id, new_title, status FROM drafts WHERE topic = ?",
        (keyword,),
    ).fetchall()
    return {
        "keyword": keyword,
        "notes": [dict(n) for n in notes],
        "drafts": [dict(d) for d in drafts],
    }


def latest_exploration_keywords(conn):
    """Keywords belonging to the most recent explore run, or None if there isn't one
    (callers should treat None as "no scoping" rather than "match nothing")."""
    exp = conn.execute(
        "SELECT id FROM explorations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if exp is None:
        return None
    rows = conn.execute(
        "SELECT keyword FROM exploration_subtopics WHERE exploration_id = ?",
        (exp["id"],),
    ).fetchall()
    return [row["keyword"] for row in rows]


def list_explorations_tree(conn):
    # Only the most recent explore run is shown — older ones are still in the
    # DB but the tree view is meant to reflect "what's currently in flight",
    # not a full history.
    explorations = conn.execute(
        "SELECT id, theme, created_at FROM explorations ORDER BY id DESC LIMIT 1"
    ).fetchall()

    tree = []
    for exp in explorations:
        subtopic_rows = conn.execute(
            "SELECT keyword FROM exploration_subtopics WHERE exploration_id = ?",
            (exp["id"],),
        ).fetchall()
        keywords = [row["keyword"] for row in subtopic_rows]
        tree.append(
            {
                "exploration_id": exp["id"],
                "theme": exp["theme"],
                "created_at": exp["created_at"],
                "subtopics": [_subtopic_node(conn, kw) for kw in keywords],
            }
        )

    return tree
