import json
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException

from core import xhs_client
from core.collector import collect_by_keyword
from core.db import (
    delete_draft,
    get_conn,
    insert_draft,
    insert_exploration,
    latest_exploration_keywords,
    list_drafts_by_status,
    list_explorations_tree,
    list_notes_by_status,
    set_draft_status,
    set_note_status,
    update_draft_images,
    update_draft_text,
)
from core.publisher import publish_approved
from core.synthesizer import synthesize_notes
from core.text_card import generate_text_card
from core.topic_planner import brainstorm_subtopics
from core.xhs_client import ACCOUNTS_PATH, XhsApiError

PROJECT_ROOT = Path(__file__).resolve().parent
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"

app = Flask(__name__)


@app.errorhandler(XhsApiError)
def handle_xhs_api_error(exc):
    return jsonify({"error": str(exc)}), 502


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    return jsonify({"error": str(exc)}), 500


def _draft_to_dict(row):
    d = dict(row)
    d["image_paths"] = json.loads(d.pop("image_paths_json") or "[]")
    titles = d.get("source_titles")
    d["source_titles"] = titles.split(" | ") if titles else []
    return d


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/images/<path:subpath>")
def serve_image(subpath):
    target = (DRAFTS_DIR / subpath).resolve()
    if not str(target).startswith(str(DRAFTS_DIR.resolve()) + "/"):
        return "forbidden", 403
    return send_from_directory(DRAFTS_DIR, subpath)


@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    if not ACCOUNTS_PATH.exists():
        return jsonify({"pc": {"configured": False}, "creator": {"configured": False}})

    accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    mtime = ACCOUNTS_PATH.stat().st_mtime
    result = {}
    for which in ("pc", "creator"):
        cookies_str = accounts.get(which, {}).get("cookies_str", "")
        result[which] = {
            "configured": bool(cookies_str),
            "updated_at": mtime,
        }
    return jsonify(result)


@app.route("/api/accounts", methods=["POST"])
def update_accounts():
    body = request.get_json(force=True)
    accounts = {"pc": {"cookies_str": ""}, "creator": {"cookies_str": ""}}
    if ACCOUNTS_PATH.exists():
        accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))

    for which in ("pc", "creator"):
        if body.get(which):
            accounts.setdefault(which, {})["cookies_str"] = body[which]

    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_PATH.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify({"ok": True})


@app.route("/api/accounts/test", methods=["POST"])
def test_account():
    body = request.get_json(force=True)
    which = body.get("which")
    try:
        accounts = xhs_client.load_accounts()
        cookies_str = accounts[which]["cookies_str"]
        if which == "pc":
            xhs_client.call(
                "pc", "get_user_self_info", {"cookies_str": cookies_str}, retries=2
            )
        else:
            # get_publish_note_info's endpoint gets connection-reset by XHS's
            # anti-bot layer in this environment regardless of cookie validity;
            # get_topic is a reliable, lightweight probe for creator-session validity.
            cookies = xhs_client.cookies_dict_from_str(cookies_str)
            xhs_client.call(
                "creator", "get_topic", {"keyword": "test", "cookies": cookies}, retries=2
            )
        return jsonify({"ok": True, "message": "连接正常"})
    except (XhsApiError, KeyError) as exc:
        return jsonify({"ok": False, "message": str(exc)})


@app.route("/api/explore", methods=["POST"])
def api_explore():
    body = request.get_json(force=True)
    theme = body["theme"]
    topics = int(body.get("topics", 3))
    limit = int(body.get("limit", 5))

    conn = get_conn()
    subtopics = brainstorm_subtopics(theme, topics)
    insert_exploration(conn, theme, subtopics)

    results = []
    for subtopic in subtopics:
        inserted, skipped = collect_by_keyword(subtopic, limit, conn)
        results.append({"subtopic": subtopic, "inserted": inserted, "skipped": skipped})

    return jsonify({"theme": theme, "results": results})


@app.route("/api/draft", methods=["POST"])
def api_draft():
    conn = get_conn()
    notes = list_notes_by_status(conn, "new")

    groups = defaultdict(list)
    for note in notes:
        groups[note["keyword"]].append(note)

    created = []
    for keyword, group_notes in groups.items():
        source_notes = [
            {"title": n["title"], "content": n["content"]} for n in group_notes
        ]
        new_title, new_desc = synthesize_notes(keyword, source_notes)

        note_ids = [n["note_id"] for n in group_notes]
        draft_id = insert_draft(conn, keyword, new_title, new_desc, note_ids)
        image_paths = generate_text_card(new_title, draft_id)
        update_draft_images(conn, draft_id, image_paths)
        for note_id in note_ids:
            set_note_status(conn, note_id, "drafted")
        created.append({"id": draft_id, "topic": keyword, "new_title": new_title})

    return jsonify({"drafts": created})


@app.route("/api/drafts", methods=["GET"])
def api_list_drafts():
    status = request.args.get("status", "pending")
    conn = get_conn()
    drafts = [_draft_to_dict(row) for row in list_drafts_by_status(conn, status)]

    # Scope the page to the current (latest) explore run, matching the tree view —
    # older drafts stay in the DB and are still reachable via the CLI, just not
    # surfaced here. `keywords is None` means no exploration exists yet at all,
    # in which case there's nothing to scope against.
    keywords = latest_exploration_keywords(conn)
    if keywords is not None:
        drafts = [d for d in drafts if d["topic"] in keywords]

    return jsonify({"drafts": drafts})


@app.route("/api/drafts/<int:draft_id>/approve", methods=["POST"])
def api_approve(draft_id):
    conn = get_conn()
    set_draft_status(conn, draft_id, "approved")
    return jsonify({"ok": True})


@app.route("/api/drafts/<int:draft_id>/reject", methods=["POST"])
def api_reject(draft_id):
    conn = get_conn()
    set_draft_status(conn, draft_id, "rejected")
    return jsonify({"ok": True})


@app.route("/api/drafts/<int:draft_id>/update", methods=["POST"])
def api_update(draft_id):
    body = request.get_json(force=True)
    conn = get_conn()
    update_draft_text(conn, draft_id, body["new_title"], body["new_desc"])
    return jsonify({"ok": True})


@app.route("/api/drafts/<int:draft_id>", methods=["DELETE"])
def api_delete(draft_id):
    conn = get_conn()
    delete_draft(conn, draft_id)
    return jsonify({"ok": True})


@app.route("/api/publish", methods=["POST"])
def api_publish():
    body = request.get_json(force=True)
    dry_run = bool(body.get("dry_run", True))
    conn = get_conn()
    results = publish_approved(conn, dry_run=dry_run)
    return jsonify({"results": results})


@app.route("/api/tree", methods=["GET"])
def api_tree():
    conn = get_conn()
    return jsonify({"tree": list_explorations_tree(conn)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
