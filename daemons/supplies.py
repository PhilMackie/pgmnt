"""
Supplies daemon - a single global checklist of hobby supplies (paint, glue,
tools, kits, etc.) plus a decoupled "buy later" holding list, against SQLite.

Not scoped per-project: one shared list for the whole app.
"""

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
            CREATE TABLE IF NOT EXISTS supply_items (
                id          TEXT PRIMARY KEY,
                list_type   TEXT NOT NULL,
                text        TEXT NOT NULL,
                checked     INTEGER NOT NULL DEFAULT 0,
                position    INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_supply_items_list_type ON supply_items (list_type)")
        conn.commit()


def _now():
    return datetime.now().isoformat()


def _row_to_item(row):
    return {
        "id": row["id"],
        "text": row["text"],
        "checked": bool(row["checked"]),
        "position": row["position"],
    }


def _normalize_supply_positions(conn, list_type):
    rows = conn.execute(
        "SELECT id FROM supply_items WHERE list_type = ? ORDER BY position", (list_type,)
    ).fetchall()
    for idx, row in enumerate(rows):
        conn.execute("UPDATE supply_items SET position = ? WHERE id = ?", (idx, row["id"]))


# ── Active list ────────────────────────────────────────────────────────────────

def get_active_items():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM supply_items WHERE list_type = 'active' ORDER BY position"
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def add_active_item(text):
    text = (text or "").strip()
    if not text:
        return {"error": "Item text is required"}

    item_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM supply_items WHERE list_type = 'active'"
        ).fetchone()["n"]
        conn.execute(
            """INSERT INTO supply_items (id, list_type, text, checked, position, created_at, updated_at)
               VALUES (?, 'active', ?, 0, ?, ?, ?)""",
            (item_id, text, count, now, now),
        )
        conn.commit()
    return {"id": item_id, "text": text, "checked": False, "position": count}


def toggle_active_item(item_id, checked):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM supply_items WHERE id = ? AND list_type = 'active'", (item_id,)
        ).fetchone()
        if not row:
            return {"error": "Item not found"}
        conn.execute(
            "UPDATE supply_items SET checked = ?, updated_at = ? WHERE id = ?",
            (1 if checked else 0, _now(), item_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM supply_items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(updated)


def delete_active_item(item_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM supply_items WHERE id = ? AND list_type = 'active'", (item_id,)
        ).fetchone()
        if not row:
            return {"error": "Item not found"}
        conn.execute("DELETE FROM supply_items WHERE id = ?", (item_id,))
        _normalize_supply_positions(conn, "active")
        conn.commit()
    return {"status": "deleted"}


def reorder_active_items(ordered_ids):
    if not ordered_ids:
        return {"error": "ordered_ids is required"}

    with get_db() as conn:
        existing = {
            r["id"] for r in conn.execute(
                "SELECT id FROM supply_items WHERE list_type = 'active'"
            ).fetchall()
        }
        if set(ordered_ids) != existing:
            return {"error": "ordered_ids does not match active items"}
        for idx, item_id in enumerate(ordered_ids):
            conn.execute("UPDATE supply_items SET position = ? WHERE id = ?", (idx, item_id))
        conn.commit()
    return {"status": "reordered"}


def clear_checked_items():
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM supply_items WHERE list_type = 'active' AND checked = 1"
        )
        removed = cursor.rowcount
        _normalize_supply_positions(conn, "active")
        conn.commit()
    return {"status": "cleared", "removed": removed}


# ── Buy Later list ───────────────────────────────────────────────────────────

def get_buylater_items():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM supply_items WHERE list_type = 'buylater' ORDER BY position"
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def add_buylater_item(text):
    text = (text or "").strip()
    if not text:
        return {"error": "Item text is required"}

    item_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM supply_items WHERE list_type = 'buylater'"
        ).fetchone()["n"]
        conn.execute(
            """INSERT INTO supply_items (id, list_type, text, checked, position, created_at, updated_at)
               VALUES (?, 'buylater', ?, 0, ?, ?, ?)""",
            (item_id, text, count, now, now),
        )
        conn.commit()
    return {"id": item_id, "text": text, "checked": False, "position": count}


def remove_buylater_item(item_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM supply_items WHERE id = ? AND list_type = 'buylater'", (item_id,)
        ).fetchone()
        if not row:
            return {"error": "Item not found"}
        conn.execute("DELETE FROM supply_items WHERE id = ?", (item_id,))
        _normalize_supply_positions(conn, "buylater")
        conn.commit()
    return {"status": "deleted"}


def add_active_from_buylater(item_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT text FROM supply_items WHERE id = ? AND list_type = 'buylater'", (item_id,)
        ).fetchone()
        if not row:
            return {"error": "Buy-later item not found"}
    # Insert as a brand new active item; the buy-later row is left untouched
    # so a recurring supply can be re-added again in the future.
    return add_active_item(row["text"])
