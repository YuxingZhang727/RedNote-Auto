import json
import os
import subprocess
import tempfile

from core.db import list_drafts_by_status, set_draft_status, update_draft_text
from core.xhs_client import DESC_CHAR_LIMIT


def _edit_text(initial_title, initial_desc):
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(f"{initial_title}\n---\n{initial_desc}\n")
        path = f.name
    subprocess.run([editor, path])
    content = open(path, encoding="utf-8").read()
    os.unlink(path)
    title, _, desc = content.partition("\n---\n")
    return title.strip(), desc.strip()


def run_review(conn):
    drafts = list_drafts_by_status(conn, "pending")
    if not drafts:
        print("没有待审核的草稿。")
        return

    for draft in drafts:
        print("=" * 60)
        print(f"draft #{draft['id']}  话题: {draft['topic']}")
        print(f"参考来源笔记: {draft['source_titles']}")
        print("-" * 60)
        desc_len = len(draft["new_desc"])
        over_limit = " ⚠️超过小红书1000字上限" if desc_len > DESC_CHAR_LIMIT else ""
        print(f"新标题: {draft['new_title']}")
        print(f"新正文({desc_len}字{over_limit}): {draft['new_desc']}")
        image_paths = json.loads(draft["image_paths_json"])
        print(f"配图: {image_paths if image_paths else '(无, 需要你自己补充)'}")
        choice = input("批准发布(y) / 拒绝(n) / 编辑文字(e) / 跳过(s): ").strip().lower()

        if choice == "y":
            set_draft_status(conn, draft["id"], "approved")
        elif choice == "n":
            set_draft_status(conn, draft["id"], "rejected")
        elif choice == "e":
            new_title, new_desc = _edit_text(draft["new_title"], draft["new_desc"])
            if len(new_desc) > DESC_CHAR_LIMIT:
                print(f"⚠️ 编辑后正文 {len(new_desc)} 字,超过小红书1000字上限,发布时会被跳过")
            update_draft_text(conn, draft["id"], new_title, new_desc)
            set_draft_status(conn, draft["id"], "approved")
        else:
            continue
