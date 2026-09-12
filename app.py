from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import timedelta
import logging
import config
from daemons.auth import (
    login_required, verify_pin, is_locked_out,
    record_failed_attempt, clear_failed_attempts
)
from daemons.board import (
    init_db, get_board,
    get_projects, create_project, rename_project, delete_project, reorder_projects,
    create_column, rename_column, delete_column, reorder_columns,
    create_card, update_card, delete_card, reorder_cards_in_column, move_card,
)
from daemons.supplies import (
    init_db as init_supplies_db,
    get_active_items, add_active_item, toggle_active_item, delete_active_item,
    reorder_active_items, clear_checked_items,
    get_buylater_items, add_buylater_item, remove_buylater_item, add_active_from_buylater,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(config.DATA_DIR / "app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.permanent_session_lifetime = timedelta(days=30)

init_db()
init_supplies_db()


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if not config.AUTH_ENABLED:
        session["authenticated"] = True
        return redirect(url_for("index"))

    if session.get("authenticated"):
        return redirect(url_for("index"))

    error = None
    locked_seconds = 0

    locked, remaining = is_locked_out()
    if locked:
        return render_template("login.html", error=None, locked_seconds=remaining)

    if request.method == "POST":
        pin = request.form.get("pin", "")
        if verify_pin(pin, config.PIN_HASH):
            clear_failed_attempts()
            session.permanent = True
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            attempts_left, now_locked = record_failed_attempt()
            if now_locked:
                error = "Too many attempts. Locked for 5 minutes."
                locked_seconds = 300
            else:
                error = f"Wrong PIN. {attempts_left} attempts remaining."

    return render_template("login.html", error=error, locked_seconds=locked_seconds)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/supplies")
@login_required
def supplies_page():
    return render_template("supplies.html")


# ── API: Projects ─────────────────────────────────────────────────────────────

@app.route("/api/projects", methods=["GET"])
@login_required
def api_projects_get():
    return jsonify(get_projects())


@app.route("/api/projects", methods=["POST"])
@login_required
def api_project_create():
    data = request.get_json() or {}
    result = create_project(data.get("name", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/projects/<project_id>", methods=["PATCH"])
@login_required
def api_project_rename(project_id):
    data = request.get_json() or {}
    result = rename_project(project_id, data.get("name", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/projects/<project_id>", methods=["DELETE"])
@login_required
def api_project_delete(project_id):
    result = delete_project(project_id)
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/projects/reorder", methods=["POST"])
@login_required
def api_projects_reorder():
    data = request.get_json() or {}
    result = reorder_projects(data.get("ordered_ids", []))
    return jsonify(result), (400 if "error" in result else 200)


# ── API: Board ────────────────────────────────────────────────────────────────

@app.route("/api/board", methods=["GET"])
@login_required
def api_board_get():
    project_id = request.args.get("project_id", "")
    result = get_board(project_id)
    return jsonify(result), (400 if "error" in result else 200)


# ── API: Columns ──────────────────────────────────────────────────────────────

@app.route("/api/columns", methods=["POST"])
@login_required
def api_column_create():
    data = request.get_json() or {}
    result = create_column(data.get("project_id", ""), data.get("name", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/columns/<column_id>", methods=["PATCH"])
@login_required
def api_column_rename(column_id):
    data = request.get_json() or {}
    result = rename_column(column_id, data.get("name", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/columns/<column_id>", methods=["DELETE"])
@login_required
def api_column_delete(column_id):
    result = delete_column(column_id)
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/columns/reorder", methods=["POST"])
@login_required
def api_columns_reorder():
    data = request.get_json() or {}
    result = reorder_columns(data.get("project_id", ""), data.get("ordered_ids", []))
    return jsonify(result), (400 if "error" in result else 200)


# ── API: Cards ────────────────────────────────────────────────────────────────

@app.route("/api/cards", methods=["POST"])
@login_required
def api_card_create():
    data = request.get_json() or {}
    result = create_card(data.get("column_id", ""), data.get("title", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/cards/<card_id>", methods=["PATCH"])
@login_required
def api_card_update(card_id):
    data = request.get_json() or {}
    result = update_card(
        card_id,
        title=data.get("title"),
        notes=data.get("notes"),
        color=data.get("color"),
        checklist=data.get("checklist"),
    )
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/cards/<card_id>", methods=["DELETE"])
@login_required
def api_card_delete(card_id):
    result = delete_card(card_id)
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/cards/reorder", methods=["POST"])
@login_required
def api_cards_reorder():
    data = request.get_json() or {}
    result = reorder_cards_in_column(data.get("column_id", ""), data.get("ordered_ids", []))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/cards/move", methods=["POST"])
@login_required
def api_cards_move():
    data = request.get_json() or {}
    result = move_card(
        data.get("card_id", ""),
        data.get("dest_column_id", ""),
        data.get("ordered_ids", []),
    )
    return jsonify(result), (400 if "error" in result else 200)


# ── API: Supplies ─────────────────────────────────────────────────────────────

@app.route("/api/supplies/active", methods=["GET"])
@login_required
def api_supplies_active_get():
    return jsonify(get_active_items())


@app.route("/api/supplies/active", methods=["POST"])
@login_required
def api_supplies_active_create():
    data = request.get_json() or {}
    result = add_active_item(data.get("text", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/active/<item_id>", methods=["PATCH"])
@login_required
def api_supplies_active_toggle(item_id):
    data = request.get_json() or {}
    result = toggle_active_item(item_id, bool(data.get("checked")))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/active/<item_id>", methods=["DELETE"])
@login_required
def api_supplies_active_delete(item_id):
    result = delete_active_item(item_id)
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/active/reorder", methods=["POST"])
@login_required
def api_supplies_active_reorder():
    data = request.get_json() or {}
    result = reorder_active_items(data.get("ordered_ids", []))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/active/clear-checked", methods=["POST"])
@login_required
def api_supplies_clear_checked():
    result = clear_checked_items()
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/buylater", methods=["GET"])
@login_required
def api_supplies_buylater_get():
    return jsonify(get_buylater_items())


@app.route("/api/supplies/buylater", methods=["POST"])
@login_required
def api_supplies_buylater_create():
    data = request.get_json() or {}
    result = add_buylater_item(data.get("text", ""))
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/buylater/<item_id>", methods=["DELETE"])
@login_required
def api_supplies_buylater_delete(item_id):
    result = remove_buylater_item(item_id)
    return jsonify(result), (400 if "error" in result else 200)


@app.route("/api/supplies/buylater/<item_id>/add-to-active", methods=["POST"])
@login_required
def api_supplies_buylater_add_to_active(item_id):
    result = add_active_from_buylater(item_id)
    return jsonify(result), (400 if "error" in result else 200)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=config.PORT)
