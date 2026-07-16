from core.llm_json import chat_json

SYSTEM_PROMPT = (
    "你是小红书选题策划。给你一个大方向的话题,"
    "请从中拆解出几个更具体、更小的切口/子话题——"
    "要具体到能直接拿去小红书站内搜索、且大概率能搜到相关笔记的程度"
    "(落到具体场景、人群、痛点或产品类型,不要泛泛而谈,也不要重复大话题本身)。"
    '只输出一个 JSON 对象,格式为 {"topics": ["子话题1", "子话题2", ...]},不要输出其他任何文字。'
)


def brainstorm_subtopics(theme, count=3):
    data = chat_json(SYSTEM_PROMPT, f"大方向:{theme}\n请给出 {count} 个子话题关键词。")
    return data["topics"][:count]
