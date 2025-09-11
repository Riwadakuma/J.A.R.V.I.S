"""HTTP client for interacting with an Ollama server + simple auto style selection."""

from typing import Any, Dict, List, Optional
import re
import httpx


def ollama_chat(
    *,
    model: str,
    messages: List[Dict[str, str]],
    sampling: Dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 11434,
    timeout_sec: int = 60,
) -> str:
    """Call the Ollama ``/api/chat`` endpoint without streaming.

    The function returns assistant text or an empty string if any error occurs.
    """
    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "num_ctx": sampling.get("ctx", 1024),
            "temperature": sampling.get("temperature", 0.5),
            "top_p": sampling.get("top_p", 0.9),
            "top_k": sampling.get("top_k", 40),
            "repeat_penalty": sampling.get("repeat_penalty", 1.1),
            "num_predict": sampling.get("num_predict", 160),
        },
        "keep_alive": sampling.get("keep_alive", None) or "15m",
        "stream": False,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json() or {}
    except Exception:
        # Не ломаем сервис — на любой ошибке отдаём пустую строку.
        return ""

    # {"message": {"role":"assistant","content":"..."}}
    msg = data.get("message") or {}
    content = msg.get("content")
    if content:
        return content

    # {"messages":[... , {"role":"assistant","content":"..."}]}
    msgs = data.get("messages") or []
    if isinstance(msgs, list) and msgs:
        last = msgs[-1] or {}
        return last.get("content", "") or ""

    return ""


# =========================
# Auto style + helpers
# =========================

SMALLTALK_SYSTEM = (
    "Ты — вежливый, краткий, ироничный ассистент в стиле JARVIS. "
    "Отвечай 2–4 предложениями. Поддерживай диалог: кратко отражай мысль пользователя "
    "и добавляй одно уместное уточнение. Без списков в бытовых вопросах."
)

BRIEF_SYSTEM = "Отвечай кратко и по делу. 1–3 строки, без воды."

FEW_SHOTS_SMALLTALK: List[Dict[str, str]] = [
    {"role": "user", "content": "Что такое пылесос?"},
    {"role": "assistant", "content": "Прибор, который всасывает пыль и мусор с пола и мебели. Быстрый способ убрать без швабры."},
    {"role": "user", "content": "Что ты такое?"},
    {"role": "assistant", "content": "Локальный офлайн-ассистент. Работаю без облака и лишней суеты, но разговор поддержу."},
]


def _looks_like_smalltalk(text: str) -> bool:
    """Грубые эвристики для 'поболтать'."""
    t = text.strip().lower()
    if not t:
        return False
    if re.search(r"\b(привет|здравствуй|как дела|как ты|что нового|чем занят|спасибо|салют)\b", t):
        return True
    if len(t.split()) <= 6 and not re.search(r"\b(запусти|создай|прочитай|покажи|скажи|объясни|как сделать|что такое)\b", t):
        return True
    if t.endswith("?") and not re.search(r"[\\/]|\.py\b|\.txt\b|\d{2,}", t):
        return True
    return False


def _build_messages_for_style(style: str, user_text: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    history = history or []
    msgs: List[Dict[str, str]] = []
    if style == "smalltalk":
        msgs.append({"role": "system", "content": SMALLTALK_SYSTEM})
        msgs.extend(FEW_SHOTS_SMALLTALK)
        msgs.extend(history[-6:])
        msgs.append({"role": "user", "content": user_text})
    else:
        msgs.append({"role": "system", "content": BRIEF_SYSTEM})
        msgs.extend(history[-4:])
        msgs.append({"role": "user", "content": user_text})
    return msgs


def ollama_chat_auto(
    *,
    model: str,
    profiles: Dict[str, Dict[str, Any]],
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    host: str = "127.0.0.1",
    port: int = 11434,
    timeout_sec: int = 60,
) -> str:
    """Определяет стиль ('smalltalk' или 'brief') и вызывает ollama_chat с нужным профилем."""
    style = "smalltalk" if _looks_like_smalltalk(user_text) else "brief"
    if style == "smalltalk":
        sampling = dict(profiles.get("smalltalk", {}))
        sampling.setdefault("ctx", 1024)
        sampling.setdefault("temperature", 0.7)
        sampling.setdefault("top_p", 0.9)
        sampling.setdefault("top_k", 40)
        sampling.setdefault("repeat_penalty", 1.08)
        sampling.setdefault("num_predict", 160)
    else:
        sampling = dict(profiles.get("balanced", {}))
        sampling.setdefault("ctx", 1024)
        sampling.setdefault("temperature", 0.5)
        sampling.setdefault("top_p", 0.9)
        sampling.setdefault("top_k", 40)
        sampling.setdefault("repeat_penalty", 1.1)
        sampling.setdefault("num_predict", 160)

    sampling.setdefault("keep_alive", "15m")
    messages = _build_messages_for_style(style, user_text, history)
    return ollama_chat(
        model=model, messages=messages, sampling=sampling,
        host=host, port=port, timeout_sec=timeout_sec
    )
