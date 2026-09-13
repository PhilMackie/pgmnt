# Pgmnt

Kanban board for Warhammer/art hobby projects — user-defined columns and cards per "army" (project), plus a global Supplies checklist. Flask service, spun off from Athena's UI/auth patterns. Runs on port 5004, deployed alongside duo-brain/chronos/athena/hermes on the Pi.

**Phil's Notes:** `/home/phil/Documents/philVault/dev/Pgmnt/`
**Repo:** `https://github.com/PhilMackie/pgmnt.git`

## Dev

- DEV: `source .venv/bin/activate && python3 app.py` → `http://localhost:5004`
- PROD: Pi at `duobrain.local:5004` — deploy only on explicit instruction, via `bash deploy/deploy-to-pi.sh`
- Dev PIN/secret live in `.env` (gitignored); `.env.example` documents the shape

## Architecture

- `app.py` — Flask routes + auth, calls `board.init_db()` and `supplies.init_db()` at startup
- `config.py` — env-backed config (PIN hash, secret key, port)
- `daemons/auth.py` — PIN auth (copied verbatim from Athena, generic/shared pattern)
- `daemons/board.py` — projects (armies) / columns / cards CRUD against SQLite
- `daemons/supplies.py` — global supplies checklist + buy-later list (ported from Quanta's grocery feature, minus its "remembered items" history)
- `templates/index.html` — single-page app: project selector (`#project-selector`) + board view (`#board-view`), toggled via `display`, all JS inlined at the bottom
- `templates/supplies.html` — standalone Supplies page, own inlined JS (duplicates `fetchApi`/`esc`/`apiJson` from index.html — no shared JS file exists yet)
- `templates/base.html` / `login.html` — shared shell + PIN keypad
- `static/css/style.css` — terminal aesthetic (JetBrains Mono, sharp corners), steel-grey `#7c8a99` accent (not Athena's purple)

## Storage

**Database:** `data/pgmnt.db` (SQLite, WAL mode). Every daemon module has its own `get_db()`/`init_db()` pointed at the same file.

```sql
projects ( id, name, position, created_at, updated_at )
columns  ( id, project_id → projects(id), name, position, created_at, updated_at )
cards    ( id, column_id → columns(id), title, notes, color, checklist (JSON), position, created_at, updated_at )
supply_items ( id, list_type ('active'|'buylater'), text, checked, position, created_at, updated_at )
```

**Important SQLite gotcha:** a foreign key added to an *existing* table via `ALTER TABLE ... ADD COLUMN ... REFERENCES ...` does **not** reliably cascade on delete (this bit `columns.project_id` when the `projects` table was retrofitted in). Don't rely on `ON DELETE CASCADE` for anything added this way — delete children explicitly in application code instead (see `delete_project`/`delete_column` in `board.py`).

## API Routes

| Area | Routes |
|---|---|
| Auth | `GET/POST /login`, `POST /logout` |
| Projects | `GET/POST /api/projects`, `PATCH/DELETE /api/projects/<id>`, `POST /api/projects/reorder` |
| Board | `GET /api/board?project_id=<id>` |
| Columns | `POST /api/columns`, `PATCH/DELETE /api/columns/<id>`, `POST /api/columns/reorder` |
| Cards | `POST /api/cards`, `PATCH/DELETE /api/cards/<id>`, `POST /api/cards/reorder`, `POST /api/cards/move` |
| Supplies | `GET/POST /api/supplies/active`, `PATCH/DELETE /api/supplies/active/<id>`, `POST /api/supplies/active/reorder`, `POST /api/supplies/active/clear-checked`, `GET/POST /api/supplies/buylater`, `DELETE /api/supplies/buylater/<id>`, `POST /api/supplies/buylater/<id>/add-to-active` |

Convention throughout: `data = request.get_json() or {}` → daemon function returns dict (or `{"error": "..."}`) → `jsonify(result), 400 if "error" else 200`. All reorder/move endpoints are **ID-based** (not text-matched — a deliberate fix vs. Athena's fragile text-matching reorder).

## UI — Key Patterns

- **Project selector → board**: `?project=<id>` in the URL drives which board is open; omit it to land on the selector. `currentProjectId` JS var scopes every board API call.
- **"Button reveals inline form"**: `+ Add column` / `+ Add card` / `+ Add army` are buttons that swap their wrapper's innerHTML for a small form (input + Add/Cancel) on click — not bare always-visible inputs (an earlier bare-input version looked broken because clicking it did nothing visible).
- **List View**: a header toggle (`localStorage['pgmnt-view-mode']`) renders all cards as a flat top-down text list grouped by column, for quick scanning. The global "click outside closes card panel" handler must exempt `.list-row` as well as `.card-title-text`, or the panel opens and immediately re-closes.
- **Drag-and-drop**: SortableJS, one instance per card-list + one for column reordering; `onEnd` posts the full ID-ordered array to a reorder/move endpoint, then reloads.
- **Board columns** are flexible-width (`flex:1 1 180px; min-width:160px; max-width:280px`), not fixed — they shrink to fit the viewport before falling back to horizontal scroll.
- **Supplies "buy later" semantics**: clicking a buy-later chip adds a *new* item to the active list but does **not** remove the chip — it's a recurring-reminder holding pen, not a one-shot queue (matches Quanta's original behavior).

## Deploy

```bash
bash deploy/deploy-to-pi.sh
```

Pi service: `/etc/systemd/system/pgmnt.service`
Pi app path: `/opt/pgmnt/app/`
Pi venv: `/opt/pgmnt/venv/`
Logs: `/opt/pgmnt/logs/`

First-time Pi setup: `bash /opt/pgmnt/app/deploy/pi-setup.sh` (creates venv, prompts for a PIN, opens firewall port 5004, installs+starts the systemd service). **Pgmnt shares its PIN hash with Athena/Quanta/Hermes on the Pi** — same PIN logs into all four.

## Key Gotchas

- Local dev `.env` and the Pi's `.env` are independent — a PIN change on one doesn't propagate to the other automatically.
- The Flask dev server's reloader watches `.py`/template changes but **not** `.env` — editing `.env` requires a manual restart to take effect.
- Local dev DB and the Pi's DB are two separate SQLite files with no sync — "copy my local data to the Pi" means literally `scp`-ing `data/pgmnt.db` over (stop the systemd service first, back up the Pi's existing file, copy, restart).
- The Pi has no `sqlite3` CLI installed; inspect its DB via `python3 -c "import sqlite3; ..."` over SSH instead.
- Sibling Pi app ports: duo-brain 5000, chronos 5001, athena 5002, hermes 5003, **pgmnt 5004**, Hecate 5050, rudy 5100, aria 5200.
