import http.client
import json
import urllib.error
import urllib.request
from pathlib import Path

from metranscript.privacy import Mask, glossary
from metranscript.settings import env

SUMMARY_PROMPT = Path(__file__).parent / "prompt.md"
CHAT_PROMPT = Path(__file__).parent / "chat.md"
API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
LANG_NAMES = {"pt": "Brazilian Portuguese", "en": "English"}
HISTORY = 20
# deepseek-chat has a 128k-token context; ~350k characters of transcript leaves room for prompt and reply.
MAX_TRANSCRIPT = 350_000


def api_key() -> str:
    key = env("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("Add your DeepSeek key in Settings to use summaries.")
    return key


def meeting_context(meeting: dict, mask: Mask) -> str:
    if len(meeting["transcript"]) > MAX_TRANSCRIPT:
        raise RuntimeError("The transcript is too long for DeepSeek (more than ~5 h of meeting).")
    return mask.apply(
        f"Title: {meeting['title'] or 'untitled'}\n"
        f"Date: {meeting['started_at']}\n"
        f"Language: {LANG_NAMES[meeting['lang']]}\n\n"
        f"<glossary>\n{chr(10).join(glossary()) or '(none)'}\n</glossary>\n\n"
        f"<notes>\n{meeting['notes'].strip() or '(none)'}\n</notes>\n\n"
        f"<transcript>\n{meeting['transcript'].strip() or '(empty)'}\n</transcript>"
    )


def summary_messages(meeting: dict, mask: Mask) -> list[dict]:
    return [
        {"role": "system", "content": SUMMARY_PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": meeting_context(meeting, mask)},
    ]


def chat_messages(meeting: dict, message: str, mask: Mask) -> list[dict]:
    # ponytail: only the last HISTORY turns go to the model; summarize old turns if long chats lose context
    # Past replies go back in the same JSON shape the model must answer with, or it drifts to plain text.
    history = [
        {"role": "assistant", "content": json.dumps({"reply": mask.apply(m["content"]), "summary": None}, ensure_ascii=False)}
        if m["role"] == "assistant" else {"role": "user", "content": mask.apply(m["content"])}
        for m in meeting["chat"][-HISTORY:]
    ]
    summary = mask.apply(meeting["summary"].strip()) or "(not generated yet)"
    context = f"{meeting_context(meeting, mask)}\n\n<current_summary>\n{summary}\n</current_summary>"
    return [
        {"role": "system", "content": CHAT_PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": context},
        {"role": "assistant", "content": '{"reply": "Ask a question or request a change to the summary.", "summary": null}'},
        *history,
        {"role": "user", "content": mask.apply(message)},
    ]


def _complete(messages: list[dict], json_mode: bool = False, temperature: float = 0.3, max_tokens: int | None = None) -> str:
    payload = {"model": MODEL, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key()}",
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            data = json.load(res)
    except urllib.error.HTTPError as e:
        hint = {401: "invalid key", 402: "no DeepSeek balance", 429: "rate limit reached"}.get(e.code, "server error")
        raise RuntimeError(f"DeepSeek rejected the request ({e.code}, {hint}).") from None
    except json.JSONDecodeError:
        raise RuntimeError("DeepSeek replied in an unexpected format.") from None
    except (OSError, http.client.HTTPException):
        raise RuntimeError("Cannot reach DeepSeek. Check your connection and try again.") from None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError("DeepSeek replied in an unexpected format.") from None


def summarize(meeting: dict, mask: Mask) -> str:
    # A low temperature keeps names and acronyms as written; 8000 tokens leave room for a complete summary of a long meeting.
    return mask.restore(_complete(summary_messages(meeting, mask), temperature=0.2, max_tokens=8000))


def chat(meeting: dict, message: str, mask: Mask) -> dict:
    raw = _complete(chat_messages(meeting, message, mask), json_mode=True)
    try:
        data = json.loads(raw)
        reply, summary = data["reply"], data.get("summary")
    except (json.JSONDecodeError, KeyError, TypeError):
        raise RuntimeError("DeepSeek replied in an unexpected format.") from None
    if not isinstance(reply, str) or not (summary is None or isinstance(summary, str)):
        raise RuntimeError("DeepSeek replied in an unexpected format.")
    return {"reply": mask.restore(reply.strip()),
            "summary": mask.restore(summary.strip()) if summary and summary.strip() else None}
