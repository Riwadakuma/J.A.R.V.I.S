# controller/ai/ollama_client.py
from typing import List, Dict, Any
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
    """
    Вызов Ollama /api/chat без стриминга.
    Возвращает текст ответа ассистента или пустую строку при ошибке.
    """
    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "num_ctx": sampling.get("ctx", 2048),
            "temperature": sampling.get("temperature", 0.7),
            "top_p": sampling.get("top_p", 0.9),
            "top_k": sampling.get("top_k", 60),
            "repeat_penalty": sampling.get("repeat_penalty", 1.15),
        },
        "stream": False,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json() or {}
    except Exception:
        # Не душим весь сервис: вернём пустую строку, контроллер подставит "Не знаю"
        return ""

    # Форматы ответов Ollama:
    # { "message": {"role":"assistant","content":"..."} , ... }
    # или { "messages": [ ... {"role":"assistant","content":"..."} ] , ... }
    msg = data.get("message") or {}
    content = msg.get("content")
    if content:
        return content

    msgs = data.get("messages") or []
    if isinstance(msgs, list) and msgs:
        last = msgs[-1] or {}
        return last.get("content", "") or ""

    return ""
