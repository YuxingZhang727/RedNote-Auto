import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"


def chat_json(system_prompt, user_prompt, retries=2):
    """Call DeepSeek in JSON mode and parse the result, retrying on malformed JSON
    (the json_object response format isn't strictly schema-validated, so the model
    occasionally emits an unescaped quote/newline inside a string value)."""
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)
    last_error = None

    for attempt in range(retries):
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = exc

    raise RuntimeError(f"DeepSeek 连续 {retries} 次返回了非法 JSON: {last_error}")


def chat_text(system_prompt, user_prompt):
    """Call DeepSeek without JSON mode and return the raw text.

    Prefer this over chat_json() when the output contains long free-form prose
    (quotes, newlines, emoji) — DeepSeek's json_object mode isn't schema-validated
    and frequently mis-escapes exactly that kind of content. Delimiter-based text
    extraction (see synthesizer.py) sidesteps JSON escaping entirely. Retrying on
    a bad extraction is the caller's job, since only the caller knows how to
    validate its own delimiter format."""
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content
