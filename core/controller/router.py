from typing import Any, Dict

from interaction.resolver.legacy_router import ALLOWED, legacy_route


def route(user_text: str) -> Dict[str, Any]:
    intent = legacy_route(user_text)
    if intent.is_command():
        return {"type": "command", "command": intent.name or "", "args": dict(intent.args)}
    return {"type": "chat"}
