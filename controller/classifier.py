import json
from .ollama_client import ollama_chat

_PROMPT = """Ты распознаёшь намерение пользователя.
Верни ТОЛЬКО JSON по схеме:
- intent: "chat" | "command"
- если "command":
  - command: одно из ["files.list","files.read","files.create","files.append","files.open","files.reveal","files.shortcut_to_desktop","system.help","system.config_get","system.config_set"]
  - args: объект с аргументами
Правила:
- Не выдумывай команды. Если не уверен — intent="chat".
- Пути указывать как относительные.
Вход: {text}
Ответ:
"""

def classify_to_command(user_text: str) -> dict | None:
    try:
        msg = [
            {"role": "system", "content": "Возвращай только валидный JSON без пояснений."},
            {"role": "user", "content": _PROMPT.format(text=user_text)},
        ]
        raw = ollama_chat(model="qwen2.5:1.5b", messages=msg, sampling={"temperature": 0.0, "max_tokens": 200})
        return json.loads(raw)
    except Exception:
        return None
