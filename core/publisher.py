import json
import re

from core import xhs_client
from core.db import insert_published, list_drafts_by_status

_HASHTAG_PATTERN = re.compile(r"#([^\s#]+)")
MAX_TOPICS = 8


def _extract_hashtags(desc):
    seen = []
    for match in _HASHTAG_PATTERN.finditer(desc):
        name = match.group(1).replace("[话题]", "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen[:MAX_TOPICS]


def _resolve_topics(candidates, creator_cookies_dict):
    """creator.post_note aborts the whole publish if any topic keyword has zero
    matches on XHS's topic-suggestion search, so pre-filter to keywords that
    actually resolve rather than passing raw LLM-generated hashtags straight
    through."""
    resolved = []
    for keyword in candidates:
        try:
            result = xhs_client.call(
                "creator",
                "get_topic",
                {"keyword": keyword, "cookies": creator_cookies_dict},
                retries=2,
            )
        except xhs_client.XhsApiError:
            continue
        if result.get("data", {}).get("topic_info_dtos"):
            resolved.append(keyword)
    return resolved


def _build_note_info(draft, creator_cookies_dict):
    image_paths = json.loads(draft["image_paths_json"])
    candidates = _extract_hashtags(draft["new_desc"])
    topics = _resolve_topics(candidates, creator_cookies_dict) if candidates else []
    # post_note appends its own correctly-marked-up "#name[话题]#" text (plus a
    # matching hash_tag entry) for every resolved topic, so the plain "#word"
    # text is stripped here to avoid ending up with the tag twice.
    desc = _HASHTAG_PATTERN.sub("", draft["new_desc"]).rstrip()
    return {
        "title": draft["new_title"],
        "desc": desc,
        "postTime": None,
        "location": None,
        "type": 0,
        "media_type": "image",
        "topics": topics,
        "images": image_paths,
    }


def publish_approved(conn, dry_run=False):
    accounts = xhs_client.load_accounts()
    creator_cookies = accounts["creator"]["cookies_str"]
    creator_cookies_dict = xhs_client.cookies_dict_from_str(creator_cookies)

    drafts = list_drafts_by_status(conn, "approved")
    results = []
    if not drafts:
        print("没有待发布的草稿。")
        return results

    for draft in drafts:
        note_info = _build_note_info(draft, creator_cookies_dict)

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
