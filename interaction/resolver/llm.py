import json
import re
import httpx
from typing import Any, Dict, Optional

PROMPT_TEMPLATE = """Ты парсер команд. Используй только из белого списка:
files.list, files.read, files.create, files.append, files.open, files.reveal, files.shortcut_to_desktop,
system.help, system.config_get, system.config_set.

Формат ответа — ЧИСТЫЙ JSON:
{{
  "command": "<одно значение из whitelist>",
  "args": {{ "path": "...", "mask": "...", "content": "...", "key": "...", "value": "..." }}
}}

Если слот не нужен — не пиши его. Содержимое для файлов всегда клади в ключ "content".
Текст пользователя: "{text}"
"""

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

def _extract_json(s: str) -> Dict[str, Any]:
    m = JSON_RE.search(s)
    raw = m.group(0) if m else "{}"
    return json.loads(raw)

def ask_ollama(text: str,
               model: str = "tinyllama",
               base_url: str = "http://127.0.0.1:11434",
               timeout: float = 3.5) -> Optional[Dict[str, Any]]:
    payload = {"model": model, "prompt": PROMPT_TEMPLATE.format(text=text), "stream": False}
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{base_url}/api/generate", json=payload)
        r.raise_for_status()
        resp = r.json().get("response", "{}")
    try:
        return _extract_json(resp)
    except Exception:
        return None
