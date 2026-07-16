import argparse
from collections import defaultdict

from core.collector import collect_by_keyword
from core.db import (
    get_conn,
    insert_draft,
    insert_exploration,
    list_notes_by_status,
    set_note_status,
    update_draft_images,
)
from core.publisher import publish_approved
from core.review import run_review
from core.synthesizer import synthesize_notes
from core.text_card import generate_text_card
from core.topic_planner import brainstorm_subtopics


def cmd_collect(args):
    conn = get_conn()
    inserted, skipped = collect_by_keyword(args.keyword, args.limit, conn)
    print(f"采集完成: 新增 {inserted} 篇, 跳过重复 {skipped} 篇")


def cmd_explore(args):
    conn = get_conn()
    print(f"正在为「{args.theme}」拆解 {args.topics} 个小切口...")
    subtopics = brainstorm_subtopics(args.theme, args.topics)
    insert_exploration(conn, args.theme, subtopics)

    for subtopic in subtopics:
        print(f"\n子话题: {subtopic}")
        inserted, skipped = collect_by_keyword(subtopic, args.limit, conn)
        print(f"  采集完成: 新增 {inserted} 篇, 跳过重复 {skipped} 篇")

    print("\n采集结束。接下来跑 `python cli.py draft` 会对每个子话题分别综合生成一篇草稿。")


def cmd_draft(args):
    conn = get_conn()
    notes = list_notes_by_status(conn, "new")
    if not notes:
        print("没有待处理的笔记。")
        return

    groups = defaultdict(list)
    for note in notes:
        groups[note["keyword"]].append(note)

    for keyword, group_notes in groups.items():
        print(f"综合话题「{keyword}」下 {len(group_notes)} 篇笔记...")
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
        print(f"  -> 草稿已生成: {new_title}")


def cmd_review(args):
    conn = get_conn()
    run_review(conn)


def cmd_publish(args):
    conn = get_conn()
    publish_approved(conn, dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(description="小红书内容运营 pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="按关键词采集笔记")
    collect_parser.add_argument("--keyword", required=True)
    collect_parser.add_argument("--limit", type=int, default=20)
    collect_parser.set_defaults(func=cmd_collect)

    explore_parser = subparsers.add_parser(
        "explore", help="把一个大方向拆成几个小切口,分别去搜索采集"
    )
    explore_parser.add_argument("--theme", required=True, help="大方向话题")
    explore_parser.add_argument("--topics", type=int, default=3, help="拆成几个小切口")
    explore_parser.add_argument("--limit", type=int, default=5, help="每个小切口采集多少篇")
    explore_parser.set_defaults(func=cmd_explore)

    draft_parser = subparsers.add_parser(
        "draft", help="按话题综合同一关键词下的所有新笔记,生成原创草稿"
    )
    draft_parser.set_defaults(func=cmd_draft)

    review_parser = subparsers.add_parser("review", help="交互式审核草稿")
    review_parser.set_defaults(func=cmd_review)

    publish_parser = subparsers.add_parser("publish", help="发布已审核通过的草稿")
    publish_parser.add_argument("--dry-run", action="store_true")
    publish_parser.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
