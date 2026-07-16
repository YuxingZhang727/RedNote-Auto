from core import xhs_client
from core.db import insert_collected_note


def _extract_images(note_card):
    images = []
    for image in note_card.get("image_list", []):
        info_list = image.get("info_list", [])
        url = None
        if len(info_list) > 1:
            url = info_list[1].get("url")
        elif info_list:
            url = info_list[0].get("url")
        if url:
            images.append(url)
    return images


def collect_by_keyword(keyword, limit, conn):
    accounts = xhs_client.load_accounts()
    pc_cookies = accounts["pc"]["cookies_str"]

    items = xhs_client.call(
        "pc",
        "search_some_note",
        {"query": keyword, "require_num": limit, "cookies_str": pc_cookies},
        retries=3,
    )

    inserted, skipped = 0, 0
    for item in items:
        if item.get("model_type") != "note":
            continue
        note_id = item.get("id")
        xsec_token = item.get("xsec_token")
        if not note_id or not xsec_token:
            skipped += 1
            continue
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"

        try:
            detail = xhs_client.call(
                "pc",
                "get_note_info",
                {"url": note_url, "cookies_str": pc_cookies},
                retries=3,
            )
        except xhs_client.XhsApiError:
            # One flaky note shouldn't abort the whole keyword's collection run.
            skipped += 1
            continue
        note_item = detail["data"]["items"][0]
        note_card = note_item["note_card"]

        note = {
            "note_id": note_id,
            "keyword": keyword,
            "title": note_card.get("title") or "无标题",
            "content": note_card.get("desc", ""),
            "images": _extract_images(note_card),
            "author": note_card.get("user", {}).get("nickname", ""),
            "url": note_url,
            "xsec_token": xsec_token,
        }
        if insert_collected_note(conn, note):
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped
