import http.client
import json
import urllib.error
import urllib.request
from pathlib import Path

from ata.settings import env

SUMMARY_PROMPT = Path(__file__).parent / "prompt.md"
CHAT_PROMPT = Path(__file__).parent / "chat.md"
API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
LANG_NAMES = {"pt": "Português", "en": "English"}
HISTORY = 20
# deepseek-chat has a 128k-token context; ~350k characters of transcript leaves room for prompt and reply.
MAX_TRANSCRIPT = 350_000


def api_key() -> str:
    key = env("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("Configure DEEPSEEK_API_KEY no arquivo .env para usar o resumo.")
    return key


def meeting_context(meeting: dict) -> str:
    if len(meeting["transcript"]) > MAX_TRANSCRIPT:
        raise RuntimeError("A transcrição é longa demais para a DeepSeek (mais de ~5 h de reunião).")
    return (
        f"Título: {meeting['title'] or 'sem título'}\n"
        f"Data: {meeting['started_at']}\n"
        f"Idioma: {LANG_NAMES[meeting['lang']]}\n\n"
        f"<anotacoes>\n{meeting['notes'].strip() or '(nenhuma)'}\n</anotacoes>\n\n"
        f"<transcricao>\n{meeting['transcript'].strip() or '(vazia)'}\n</transcricao>"
    )


def summary_messages(meeting: dict) -> list[dict]:
    return [
        {"role": "system", "content": SUMMARY_PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": meeting_context(meeting)},
    ]


def chat_messages(meeting: dict, message: str) -> list[dict]:
    # ponytail: only the last HISTORY turns go to the model; summarize old turns if long chats lose context
    # Past replies go back in the same JSON shape the model must answer with, or it drifts to plain text.
    history = [
        {"role": "assistant", "content": json.dumps({"reply": m["content"], "summary": None}, ensure_ascii=False)}
        if m["role"] == "assistant" else {"role": "user", "content": m["content"]}
        for m in meeting["chat"][-HISTORY:]
    ]
    context = f"{meeting_context(meeting)}\n\n<resumo_atual>\n{meeting['ata'].strip() or '(ainda não gerado)'}\n</resumo_atual>"
    return [
        {"role": "system", "content": CHAT_PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": context},
        {"role": "assistant", "content": '{"reply": "Pode perguntar ou pedir um ajuste no resumo.", "summary": null}'},
        *history,
        {"role": "user", "content": message},
    ]


def _complete(messages: list[dict], json_mode: bool = False) -> str:
    payload = {"model": MODEL, "messages": messages, "temperature": 0.3}
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
        hint = {401: "chave inválida", 402: "sem saldo na DeepSeek", 429: "limite de uso atingido"}.get(e.code, "erro do servidor")
        raise RuntimeError(f"A DeepSeek recusou o pedido ({e.code}, {hint}).") from None
    except json.JSONDecodeError:
        raise RuntimeError("A DeepSeek respondeu em um formato inesperado.") from None
    except (OSError, http.client.HTTPException):
        raise RuntimeError("Sem conexão com a DeepSeek. Verifique a internet e tente de novo.") from None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError("A DeepSeek respondeu em um formato inesperado.") from None


def summarize(meeting: dict) -> str:
    return _complete(summary_messages(meeting))


def chat(meeting: dict, message: str) -> dict:
    raw = _complete(chat_messages(meeting, message), json_mode=True)
    try:
        data = json.loads(raw)
        reply, summary = data["reply"], data.get("summary")
    except (json.JSONDecodeError, KeyError, TypeError):
        raise RuntimeError("A DeepSeek respondeu em um formato inesperado.") from None
    if not isinstance(reply, str) or not (summary is None or isinstance(summary, str)):
        raise RuntimeError("A DeepSeek respondeu em um formato inesperado.")
    return {"reply": reply.strip(), "summary": summary.strip() if summary and summary.strip() else None}
