import re
from typing import Dict, Any

# Жёсткий белый список
ALLOWED = {
    "files.list",
    "files.read",
    "files.create",
    "files.append",
    "files.open",
    "files.reveal",
    "files.shortcut_to_desktop",
    "system.help",
    "system.config_get",
    "system.config_set",
}

# Паттерны: строка → (command, args)
_PATTERNS = [
    (r'^\s*файлы\s+"([^"]+)"\s*$',                      lambda m: ("files.list", {"mask": m.group(1)})),
    (r'^\s*прочитай\s+"([^"]+)"\s*$',                   lambda m: ("files.read", {"path": m.group(1)})),
    (r'^\s*создай\s+файл\s+"([^"]+)"\s+с\s+содержимым\s+(.+)\s*$', lambda m: ("files.create", {"path": m.group(1), "content": m.group(2)})),
    (r'^\s*допиши\s+в\s+"([^"]+)"\s+текст\s+(.+)\s*$',  lambda m: ("files.append", {"path": m.group(1), "content": m.group(2)})),
    (r'^\s*открой\s+"([^"]+)"\s*$',                     lambda m: ("files.open", {"path": m.group(1)})),
    (r'^\s*покажи\s+"([^"]+)"\s*$',                     lambda m: ("files.reveal", {"path": m.group(1)})),
    (r'^\s*ярлык\s+"([^"]+)"\s*$',                      lambda m: ("files.shortcut_to_desktop", {"path": m.group(1)})),
    (r'^\s*помощь\s*$',                                 lambda m: ("system.help", {})),
    (r'^\s*конфиг\s+показать\s*$',                      lambda m: ("system.config_get", {})),
    (r'^\s*конфиг\s+установить\s+(\S+)\s+(.+)\s*$',     lambda m: ("system.config_set", {"key": m.group(1), "value": m.group(2)})),
]

def _normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, str):
            out[k] = v.strip().strip('"').strip("'")
        else:
            out[k] = v
    return out

def route(user_text: str) -> Dict[str, Any]:
    t = user_text.strip()
    for pattern, builder in _PATTERNS:
        m = re.match(pattern, t, flags=re.IGNORECASE)
        if m:
            cmd, args = builder(m)
            if cmd in ALLOWED:
                return {"type": "command", "command": cmd, "args": _normalize_args(args)}
    # если не попало под белый список — это чат
    return {"type": "chat"}
