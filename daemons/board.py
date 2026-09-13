"""
Board daemon - projects/columns/cards CRUD against SQLite.

A "project" is one independent board (e.g. one army) - each has its own
set of columns and cards, fully isolated from every other project.
"""

import json
import sqlite3
import uuid
from datetime import datetime

import config

DB_PATH = config.DATA_DIR / "pgmnt.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                position    INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS columns (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                position    INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id          TEXT PRIMARY KEY,
                column_id   TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
                title       TEXT NOT NULL DEFAULT '',
                notes       TEXT NOT NULL DEFAULT '',
                color       TEXT,
                checklist   TEXT NOT NULL DEFAULT '[]',
                position    INTEGER NOT NULL,
                starred     INTEGER NOT NULL DEFAULT 0,
                tags        TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                name TEXT PRIMARY KEY
            )
        """)

        # Pre-existing installs: columns table predates project_id.
        try:
            conn.execute("ALTER TABLE columns ADD COLUMN project_id TEXT REFERENCES projects(id)")
        except sqlite3.OperationalError:
            pass

        # Pre-existing installs: cards table predates starred.
        try:
            conn.execute("ALTER TABLE cards ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # Pre-existing installs: cards table predates tags.
        try:
            conn.execute("ALTER TABLE cards ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass

        if not conn.execute(
            "SELECT 1 FROM migrations WHERE name = ?", ("backfill_project_id",)
        ).fetchone():
            orphans = conn.execute("SELECT id FROM columns WHERE project_id IS NULL").fetchall()
            if orphans:
                default_id = str(uuid.uuid4())
                now = _now()
                conn.execute(
                    "INSERT INTO projects (id, name, position, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
                    (default_id, "My Army", now, now),
                )
                conn.execute("UPDATE columns SET project_id = ? WHERE project_id IS NULL", (default_id,))
            conn.execute("INSERT INTO migrations (name) VALUES (?)", ("backfill_project_id",))

        conn.execute("CREATE INDEX IF NOT EXISTS idx_columns_project_id ON columns (project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_column_id ON cards (column_id)")
        conn.commit()


def _now():
    return datetime.now().isoformat()


def _row_to_project(row):
    return {"id": row["id"], "name": row["name"], "position": row["position"]}


def _row_to_column(row, cards=None):
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "position": row["position"],
        "cards": cards if cards is not None else [],
    }


def _row_to_card(row):
    try:
        checklist = json.loads(row["checklist"]) if row["checklist"] else []
    except (json.JSONDecodeError, TypeError):
        checklist = []
    try:
        tags = json.loads(row["tags"]) if row["tags"] else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    return {
        "id": row["id"],
        "column_id": row["column_id"],
        "title": row["title"],
        "notes": row["notes"],
        "color": row["color"],
        "checklist": checklist,
        "position": row["position"],
        "starred": bool(row["starred"]),
        "tags": tags,
    }


def _normalize_project_positions(conn):
    rows = conn.execute("SELECT id FROM projects ORDER BY position").fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE projects SET position = ? WHERE id = ?", (idx, row["id"]))


def _normalize_column_positions(conn, project_id):
    rows = conn.execute(
        "SELECT id FROM columns WHERE project_id = ? ORDER BY position", (project_id,)
    ).fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE columns SET position = ? WHERE id = ?", (idx, row["id"]))


def _normalize_card_positions(conn, column_id):
    rows = conn.execute(
        "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (column_id,)
    ).fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE cards SET position = ? WHERE id = ?", (idx, row["id"]))


# ── Projects ─────────────────────────────────────────────────────────────────

def get_projects():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY position").fetchall()
    return [_row_to_project(row) for row in rows]


def create_project(name):
    name = (name or "").strip()
    if not name:
        return {"error": "Project name is required"}

    project_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        conn.execute(
            "INSERT INTO projects (id, name, position, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, name, count, now, now),
        )
        conn.commit()
    return {"id": project_id, "name": name, "position": count}


def rename_project(project_id, name):
    name = (name or "").strip()
    if not name:
        return {"error": "Project name is required"}

    with get_db() as conn:
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return {"error": "Project not found"}
        conn.execute(
            "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
            (name, _now(), project_id),
        )
        conn.commit()
    return {"id": project_id, "name": name}


def delete_project(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return {"error": "Project not found"}
        # Deleted explicitly (children first) rather than relying on ON DELETE
        # CASCADE: columns.project_id was added via ALTER TABLE on pre-existing
        # installs, and SQLite does not reliably cascade a FK added that way.
        conn.execute("""
            DELETE FROM cards WHERE column_id IN (
                SELECT id FROM columns WHERE project_id = ?
            )
        """, (project_id,))
        conn.execute("DELETE FROM columns WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        _normalize_project_positions(conn)
        conn.commit()
    return {"status": "deleted"}


def reorder_projects(ordered_ids):
    if not ordered_ids:
        return {"error": "ordered_ids is required"}

    with get_db() as conn:
        existing = {r["id"] for r in conn.execute("SELECT id FROM projects").fetchall()}
        if set(ordered_ids) != existing:
            return {"error": "ordered_ids does not match existing projects"}
        for idx, project_id in enumerate(ordered_ids):
            conn.execute("UPDATE projects SET position = ? WHERE id = ?", (idx, project_id))
        conn.commit()
    return {"status": "reordered"}


# ── Board (columns + cards for one project) ───────────────────────────────────

def get_board(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return {"error": "Project not found"}
        col_rows = conn.execute(
            "SELECT * FROM columns WHERE project_id = ? ORDER BY position", (project_id,)
        ).fetchall()
        col_ids = [row["id"] for row in col_rows]
        card_rows = []
        if col_ids:
            placeholders = ",".join("?" * len(col_ids))
            card_rows = conn.execute(
                f"SELECT * FROM cards WHERE column_id IN ({placeholders}) ORDER BY column_id, starred DESC, position",
                col_ids,
            ).fetchall()

    cards_by_column = {}
    for row in card_rows:
        cards_by_column.setdefault(row["column_id"], []).append(_row_to_card(row))

    columns = [_row_to_column(row, cards_by_column.get(row["id"], [])) for row in col_rows]
    return {"columns": columns}


def create_column(project_id, name):
    name = (name or "").strip()
    if not name:
        return {"error": "Column name is required"}

    col_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return {"error": "Project not found"}
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM columns WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO columns (id, project_id, name, position, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (col_id, project_id, name, count, now, now),
        )
        conn.commit()
    return {"id": col_id, "project_id": project_id, "name": name, "position": count, "cards": []}


def rename_column(column_id, name):
    name = (name or "").strip()
    if not name:
        return {"error": "Column name is required"}

    with get_db() as conn:
        row = conn.execute("SELECT id FROM columns WHERE id = ?", (column_id,)).fetchone()
        if not row:
            return {"error": "Column not found"}
        conn.execute(
            "UPDATE columns SET name = ?, updated_at = ? WHERE id = ?",
            (name, _now(), column_id),
        )
        conn.commit()
    return {"id": column_id, "name": name}


def delete_column(column_id):
    with get_db() as conn:
        row = conn.execute("SELECT project_id FROM columns WHERE id = ?", (column_id,)).fetchone()
        if not row:
            return {"error": "Column not found"}
        project_id = row["project_id"]
        conn.execute("DELETE FROM cards WHERE column_id = ?", (column_id,))
        conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))
        _normalize_column_positions(conn, project_id)
        conn.commit()
    return {"status": "deleted"}


def reorder_columns(project_id, ordered_ids):
    if not ordered_ids:
        return {"error": "ordered_ids is required"}

    with get_db() as conn:
        existing = {
            r["id"] for r in conn.execute(
                "SELECT id FROM columns WHERE project_id = ?", (project_id,)
            ).fetchall()
        }
        if set(ordered_ids) != existing:
            return {"error": "ordered_ids does not match existing columns"}
        for idx, col_id in enumerate(ordered_ids):
            conn.execute("UPDATE columns SET position = ? WHERE id = ?", (idx, col_id))
        conn.commit()
    return {"status": "reordered"}


def create_card(column_id, title):
    title = (title or "").strip()
    if not title:
        return {"error": "Card title is required"}

    with get_db() as conn:
        col = conn.execute("SELECT id FROM columns WHERE id = ?", (column_id,)).fetchone()
        if not col:
            return {"error": "Column not found"}

        count = conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE column_id = ?", (column_id,)
        ).fetchone()["n"]

        card_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """INSERT INTO cards (id, column_id, title, notes, color, checklist, position, created_at, updated_at)
               VALUES (?, ?, ?, '', NULL, '[]', ?, ?, ?)""",
            (card_id, column_id, title, count, now, now),
        )
        conn.commit()
    return {
        "id": card_id, "column_id": column_id, "title": title, "notes": "",
        "color": None, "checklist": [], "position": count, "starred": False, "tags": [],
    }


def update_card(card_id, title=None, notes=None, color=None, checklist=None, tags=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return {"error": "Card not found"}

        new_title = row["title"] if title is None else title.strip()
        new_notes = row["notes"] if notes is None else notes
        new_color = row["color"] if color is None else (color or None)
        new_checklist = row["checklist"] if checklist is None else json.dumps(checklist)
        new_tags = row["tags"] if tags is None else json.dumps(tags)

        conn.execute(
            "UPDATE cards SET title = ?, notes = ?, color = ?, checklist = ?, tags = ?, updated_at = ? WHERE id = ?",
            (new_title, new_notes, new_color, new_checklist, new_tags, _now(), card_id),
        )
        conn.commit()

        updated = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return _row_to_card(updated)


def toggle_card_star(card_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return {"error": "Card not found"}

        column_id = row["column_id"]
        now = _now()

        if row["starred"]:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) AS m FROM cards WHERE column_id = ? AND starred = 0",
                (column_id,),
            ).fetchone()["m"]
            conn.execute(
                "UPDATE cards SET starred = 0, position = ?, updated_at = ? WHERE id = ?",
                (max_pos + 1, now, card_id),
            )
        else:
            # Newly-starred cards join the starred group in alphabetical order
            # by default; existing starred siblings get renumbered alongside it
            # (drag-and-drop reorder can override this afterwards).
            siblings = conn.execute(
                "SELECT id, title FROM cards WHERE column_id = ? AND starred = 1 AND id != ?",
                (column_id, card_id),
            ).fetchall()
            ordered = sorted(
                [(row["title"], card_id)] + [(s["title"], s["id"]) for s in siblings],
                key=lambda t: t[0].lower(),
            )
            for idx, (_, cid) in enumerate(ordered):
                conn.execute("UPDATE cards SET position = ? WHERE id = ?", (idx, cid))
            conn.execute("UPDATE cards SET starred = 1, updated_at = ? WHERE id = ?", (now, card_id))

        conn.commit()
        updated = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return _row_to_card(updated)


def delete_card(card_id):
    with get_db() as conn:
        row = conn.execute("SELECT column_id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return {"error": "Card not found"}
        column_id = row["column_id"]
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        _normalize_card_positions(conn, column_id)
        conn.commit()
    return {"status": "deleted"}


def reorder_cards_in_column(column_id, ordered_ids):
    if not ordered_ids:
        return {"error": "ordered_ids is required"}

    with get_db() as conn:
        existing = {
            r["id"] for r in conn.execute(
                "SELECT id FROM cards WHERE column_id = ?", (column_id,)
            ).fetchall()
        }
        if set(ordered_ids) != existing:
            return {"error": "ordered_ids does not match cards in this column"}
        for idx, card_id in enumerate(ordered_ids):
            conn.execute("UPDATE cards SET position = ? WHERE id = ?", (idx, card_id))
        conn.commit()
    return {"status": "reordered"}


def move_card(card_id, dest_column_id, ordered_ids):
    if not ordered_ids:
        return {"error": "ordered_ids is required"}

    with get_db() as conn:
        card = conn.execute("SELECT column_id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not card:
            return {"error": "Card not found"}
        source = conn.execute(
            "SELECT project_id FROM columns WHERE id = ?", (card["column_id"],)
        ).fetchone()
        dest = conn.execute(
            "SELECT project_id FROM columns WHERE id = ?", (dest_column_id,)
        ).fetchone()
        if not dest:
            return {"error": "Destination column not found"}
        if source["project_id"] != dest["project_id"]:
            return {"error": "Cannot move a card between projects"}

        source_column_id = card["column_id"]

        conn.execute(
            "UPDATE cards SET column_id = ?, updated_at = ? WHERE id = ?",
            (dest_column_id, _now(), card_id),
        )

        existing_in_dest = {
            r["id"] for r in conn.execute(
                "SELECT id FROM cards WHERE column_id = ?", (dest_column_id,)
            ).fetchall()
        }
        if set(ordered_ids) != existing_in_dest:
            conn.rollback()
            return {"error": "ordered_ids does not match cards in destination column"}

        for idx, cid in enumerate(ordered_ids):
            conn.execute("UPDATE cards SET position = ? WHERE id = ?", (idx, cid))

        if source_column_id != dest_column_id:
            _normalize_card_positions(conn, source_column_id)

        conn.commit()
    return {"status": "moved"}
