import re

from core.llm_json import chat_text
from core.xhs_client import DESC_CHAR_LIMIT

# Leave headroom below the platform's hard 1000-char limit: publisher.py appends
# " #name[话题]# " per resolved topic on top of this, after generation.
TARGET_DESC_CHARS = 800

SYSTEM_PROMPT = (
    "你是跨境支付/跨境电商领域的小红书内容编辑。"
    "下面会给你同一个话题下、从多篇小红书笔记里采集到的原始信息(标题+正文)。"
    "你的任务:综合这些信息里的共性观点、经验和线索,并结合你自己已有的知识,"
    "写一篇关于该话题的原创小红书笔记——不要照抄任何一篇原文的具体表述,"
    "可以补充笔记里没有提到但相关的背景知识。\n\n"
    "要求:\n"
    "- 标题符合小红书风格,可用少量emoji\n"
    "- 正文分段清晰、口语化,适合小红书阅读习惯\n"
    f"- 正文字数严格控制在{TARGET_DESC_CHARS}字以内——小红书正文有1000字硬上限,"
    "发布时系统还会在结尾自动追加话题标签文字,所以生成阶段必须留出余量,宁可少写也不要超\n"
    "- 涉及具体费率、政策、平台规则等信息时措辞要留有余地(如“目前了解到”“据我所知”),"
    "不要把不确定的信息说成绝对事实;这类内容不构成专业财税/法律建议\n\n"
    "输出格式必须严格如下,不要输出markdown代码块标记,不要输出多余文字,"
    "标题只能占一行,正文写在 [DESC] 标记之后直到输出结束:\n"
    "[TITLE]\n"
    "标题内容(单行)\n"
    "[DESC]\n"
    "正文内容(可以有多个段落和换行)"
)

# No closing tags — the model occasionally drops trailing markers on long output,
# so [DESC] is treated as "everything from here to the end of the response."
_PATTERN = re.compile(r"\[TITLE\]\s*(.*?)\s*\[DESC\]\s*(.*)", re.DOTALL)


def _truncate_desc(desc, limit):
    if len(desc) <= limit:
        return desc
    cut = desc[:limit]
    # Prefer cutting at the last sentence/paragraph boundary within the limit
    # so we don't chop off mid-sentence.
    boundary = max(cut.rfind("\n"), cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
    if boundary > limit * 0.6:  # only use the boundary if it doesn't waste too much
        cut = cut[: boundary + 1]
    return cut.rstrip()


def synthesize_notes(topic, notes, retries=3):
    """notes: list of {"title": ..., "content": ...} collected under the same topic/keyword."""
    sources_text = "\n\n".join(
        f"【来源{i + 1}】标题:{n['title']}\n正文:{n['content']}"
        for i, n in enumerate(notes)
    )
    user_prompt = f"话题:{topic}\n\n{sources_text}"

    last_raw = None
    shortest_over_limit = None
    for attempt in range(retries):
        raw = chat_text(SYSTEM_PROMPT, user_prompt)
        match = _PATTERN.search(raw)
        if match:
            new_title, new_desc = match.group(1).strip(), match.group(2).strip()
            if new_title and new_desc:
                if len(new_desc) <= DESC_CHAR_LIMIT:
                    return new_title, new_desc
                if shortest_over_limit is None or len(new_desc) < len(shortest_over_limit[1]):
                    shortest_over_limit = (new_title, new_desc)
        last_raw = raw

    if shortest_over_limit:
        new_title, new_desc = shortest_over_limit
        return new_title, _truncate_desc(new_desc, DESC_CHAR_LIMIT)

    raise RuntimeError(
        f"DeepSeek 连续 {retries} 次没有返回符合格式的内容,最后一次原始输出:\n{last_raw}"
    )
