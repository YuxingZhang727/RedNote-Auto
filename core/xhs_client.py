import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
XHS_API_TOOL = (
    PROJECT_ROOT.parent / "XhsSkills" / "skills" / "xhs-apis" / "scripts" / "xhs_api_tool.py"
)
ACCOUNTS_PATH = PROJECT_ROOT / "config" / "accounts.json"

DESC_CHAR_LIMIT = 1000  # XHS note body hard limit


class XhsApiError(RuntimeError):
    pass


def load_accounts():
    if not ACCOUNTS_PATH.exists():
        raise XhsApiError(
            f"{ACCOUNTS_PATH} not found. Copy config/accounts.json.example to "
            "config/accounts.json and fill in your cookies_str."
        )
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def cookies_dict_from_str(cookies_str):
    """Mirrors the vendored runtime's trans_cookies() for callers that need a
    cookies dict directly (some creator methods take `cookies`, not `cookies_str`,
    and the CLI's auto-conversion leaves a stray `cookies_str` key that trips a
    TypeError on those methods)."""
    sep = "; " if "; " in cookies_str else ";"
    return {
        item.split("=")[0]: "=".join(item.split("=")[1:])
        for item in cookies_str.split(sep)
    }


def call(namespace, method, params, retries=1):
    """Call a vendored XHS API method via xhs_api_tool.py and return its `result` field.

    `retries` defaults to 1 (no retry) because a blind retry on a mutating call
    (e.g. creator.post_note) risks double-posting if the first attempt actually
    succeeded server-side but the response got corrupted in transit. Read-only
    callers (search, note detail, connectivity checks) should pass a higher
    value — this network occasionally drops chunked responses mid-stream
    (InvalidChunkLength) for reasons unrelated to cookie validity."""
    last_error = None
    for attempt in range(retries):
        try:
            return _call_once(namespace, method, params)
        except XhsApiError as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5)
    raise last_error


def _call_once(namespace, method, params):
    if not XHS_API_TOOL.exists():
        raise XhsApiError(f"xhs_api_tool.py not found at {XHS_API_TOOL}")

    # The proxy previously running on this machine corrupted large downloads
    # (see opencv-python install issue); bypass it for these API calls too so
    # behavior stays consistent with what was verified to work.
    env = dict(os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(key, None)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(params, f, ensure_ascii=False)
        params_path = f.name

    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(XHS_API_TOOL),
                "call",
                namespace,
                method,
                "--params-file",
                params_path,
            ],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(params_path)

    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise XhsApiError(
            f"{namespace}.{method} produced non-JSON output "
            f"(exit={proc.returncode}): {proc.stdout}\n{proc.stderr}"
        )

    if "error" in response:
        raise XhsApiError(f"{namespace}.{method} failed: {response['error']}")

    result = response["result"]
    # Vendored APIs return (success, msg, data) tuples serialized as a 3-item list.
    if isinstance(result, list) and len(result) == 3 and isinstance(result[0], bool):
        success, msg, data = result
        if not success:
            raise XhsApiError(f"{namespace}.{method} failed: {msg}")
        return data
    return result
