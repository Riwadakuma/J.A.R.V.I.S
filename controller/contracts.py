from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# Вход в /chat
class ChatIn(BaseModel):
    text: str = Field(..., min_length=1)

# Выход из /chat
class ChatOut(BaseModel):
    type: Literal["chat", "command"]
    text: Optional[str] = None
    command: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    # опционально, если proxy_commands=true
    ok: Optional[bool] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
