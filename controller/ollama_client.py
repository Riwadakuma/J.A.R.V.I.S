import httpx
from typing import List, Dict, Any

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
    Простой вызов Ollama /api/chat без стриминга.
    """
    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {
            "temperature": sampling.get("temperature", 0.7),
            "top_p": sampling.get("top_p", 0.9),
            "top_k": sampling.get("top_k", 60),
            "repeat_penalty": sampling.get("repeat_penalty", 1.05),
            "num_ctx": sampling.get("ctx", 2048),
        },
        "stream": False,
    }
    with httpx.Client(timeout=timeout_sec) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    # формат Ollama: {"message":{"content":"..."}, ...}
    msg = (data or {}).get("message", {})
    return (msg or {}).get("content", "") or ""
