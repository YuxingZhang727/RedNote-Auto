import json

from core import xhs_client
from core.db import insert_published, list_drafts_by_status


def _build_note_info(draft):
    image_paths = json.loads(draft["image_paths_json"])
    return {
        "title": draft["new_title"],
        "desc": draft["new_desc"],
        "postTime": None,
        "location": None,
        "type": 0,
        "media_type": "image",
        "topics": [],
        "images": image_paths,
    }


def publish_approved(conn, dry_run=False):
    accounts = xhs_client.load_accounts()
    creator_cookies = accounts["creator"]["cookies_str"]

    drafts = list_drafts_by_status(conn, "approved")
    results = []
    if not drafts:
        print("没有待发布的草稿。")
        return results

    for draft in drafts:
        note_info = _build_note_info(draft)

        if not note_info["images"]:
            print(f"draft #{draft['id']} 没有配图,跳过发布(先补充图片再重新审核)")
            results.append({"draft_id": draft["id"], "status": "skipped_no_image"})
            continue

        if dry_run:
            print(f"[dry-run] draft #{draft['id']} 将发布的 payload:")
            print(json.dumps(note_info, ensure_ascii=False, indent=2))
            results.append(
                {"draft_id": draft["id"], "status": "dry_run", "note_info": note_info}
            )
            continue

        result = xhs_client.call(
            "creator",
            "post_note",
            {"noteInfo": note_info, "cookies_str": creator_cookies},
        )
        publish_note_id = result.get("data", {}).get("note_id") if isinstance(result, dict) else None
        insert_published(conn, draft["id"], publish_note_id, result)
        print(f"draft #{draft['id']} 发布成功, note_id={publish_note_id}")
        results.append(
            {"draft_id": draft["id"], "status": "published", "note_id": publish_note_id}
        )

    return results
