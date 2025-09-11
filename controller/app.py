from fastapi import FastAPI, HTTPException
from pathlib import Path
from typing import Dict, Tuple, List, Any, Optional
from collections import deque
import re
import yaml
import httpx

from .contracts import ChatIn, ChatOut
from .router import route, ALLOWED
from .ollama_client import ollama_chat, ollama_chat_auto
from .resolver_adapter import ResolverAdapter

CFG_PATH = Path(__file__).parent / "config.yaml"
_config = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) if CFG_PATH.exists() else {}
_diagnostic_mode = bool(_config.get("diagnostic_mode", False))

app = FastAPI(title="JARVIS Controller")

SYSTEM_PROMPT = (
    "Ты локальный офлайн-ассистент. Отвечай кратко, по-русски. "
    "Не придумывай факты. Если не уверен — 'Не знаю'."
)

# ---- Interaction / Resolver wiring -------------------------------------------------

_interaction = _config.get("interaction") or {}
_resolver_enabled = bool(_interaction.get("enabled", True))

# ВАЖНО: маппинг резолвера — КАНОНИЧЕСКИЕ имена команд
_RESOLVER_TO_TOOL: Dict[str, str] = {
    "files.list": "files.list",
    "files.read": "files.read",
    "files.create": "files.create",
    "files.append": "files.append",
    "files.open": "files.open",
    "files.reveal": "files.reveal",
    "files.shortcut_to_desktop": "files.shortcut_to_desktop",
    "system.help": "system.help",
    "system.config_get": "system.config_get",
    "system.config_set": "system.config_set",
}
_WHITELIST_RESOLVER = list(_RESOLVER_TO_TOOL.keys())
_workspace_root = str((Path(__file__).parent.parent / "workspace").resolve())

_resolver = None
if _resolver_enabled:
    _resolver = ResolverAdapter(
        base_url=_interaction.get("resolver_url", "http://127.0.0.1:8020"),
        whitelist=_WHITELIST_RESOLVER,
        workspace_root=_workspace_root,
        mode=_interaction.get("resolver_mode", "hybrid"),
        llm_threshold=float(_interaction.get("llm_threshold", 0.75)),
        timeout=float(_interaction.get("timeout_sec", 2.5)),
        llm_enable=bool((_interaction.get("llm") or {}).get("enable", True)),
        llm_base_url=(_interaction.get("llm") or {}).get("base_url", "http://127.0.0.1:11434"),
        llm_model=(_interaction.get("llm") or {}).get("model", "tinyllama"),
    )

_use_legacy_when_low_conf = bool(_interaction.get("use_legacy_when_low_conf", True))
_low_conf_threshold = float(_interaction.get("low_conf_threshold", 0.50))

def _map_resolver_to_tool(cmd: str, args: dict) -> tuple[str, dict]:
    mapped = _RESOLVER_TO_TOOL.get(cmd, "")
    return mapped, (args or {})

# ---- Toolrunner proxy config -------------------------------------------------------

_controller_cfg = _config.get("controller") or {}
_proxy_commands = bool(_controller_cfg.get("proxy_commands", False))

_toolrunner_cfg = _config.get("toolrunner") or {}
_tr_base = (_toolrunner_cfg.get("base_url", "http://127.0.0.1:8011") or "").rstrip("/")
_tr_timeout = int(_toolrunner_cfg.get("timeout_sec", 30))
_tr_token = (_toolrunner_cfg.get("shared_token") or "").strip()

# ---- Minimal in-process chat history ----------------------------------------------

_history = deque(maxlen=12)  # [ {"role": "...", "content": "..."} ]

# ---- Helpers: sanitize + RU quick intent fallback ---------------------------------

def _clean_arg(s: Any) -> Any:
    if not isinstance(s, str):
        return s
    s = s.strip()
    s = (s.replace("“", '"').replace("”", '"')
           .replace("«", '"').replace("»", '"')
           .replace("‘", "'").replace("’", "'"))
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    s = s.replace("\\\\", "\\")
    return s

# Очень быстрый fallback на случай, если резолвер не сработал/выключен.
# Закрывает базовые русские формулировки: создать/прочитать/показать/открыть/допиши.
_RU_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:создай|создать)\s+файл\s+(.+)$", re.I),       "files.create"),
    (re.compile(r"^(?:прочитай|прочитать)\s+файл\s+(.+)$", re.I),   "files.read"),
    (re.compile(r"^(?:покажи|список|файлы)\s+(.+)$", re.I),         "files.list"),
    (re.compile(r"^(?:открой|открыть)\s+файл\s+(.+)$", re.I),       "files.open"),
    (re.compile(r"^(?:допиши|добавь)\s+в\s+файл\s+(.+?)\s*[:\-–]\s*(.+)$", re.I), "files.append"),
]

def _ru_quick_intent(text: str) -> Optional[Dict[str, Any]]:
    t = text.strip()
    for rx, cmd in _RU_PATTERNS:
        m = rx.match(t)
        if not m:
            continue
        g1 = _clean_arg(m.group(1))
        if cmd == "files.create":
            return {"type": "command", "command": cmd, "args": {"path": g1, "text": ""}}
        if cmd == "files.read":
            return {"type": "command", "command": cmd, "args": {"path": g1}}
        if cmd == "files.list":
            return {"type": "command", "command": cmd, "args": {"pattern": g1}}
        if cmd == "files.open":
            return {"type": "command", "command": cmd, "args": {"path": g1}}
        if cmd == "files.append" and m.lastindex and m.lastindex >= 2:
            g2 = _clean_arg(m.group(2))
            return {"type": "command", "command": cmd, "args": {"path": g1, "text": g2}}
    return None

# ---- Health / Diagnostics ----------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "model": (_config.get("model") or {}).get("name", ""),
        "proxy_commands": _proxy_commands,
        "resolver_enabled": _resolver_enabled,
    }

@app.get("/diagnostics")
def diagnostics():
    if not _diagnostic_mode:
        raise HTTPException(status_code=404, detail="Diagnostics disabled")
    return {
        "diagnostic_mode": True,
        "config": _config,
        "commands": {"legacy": sorted(ALLOWED), "resolver_whitelist": _WHITELIST_RESOLVER},
        "resolver": {
            "enabled": _resolver_enabled,
            "active": _resolver is not None,
            "use_legacy_when_low_conf": _use_legacy_when_low_conf,
            "low_conf_threshold": _low_conf_threshold,
        },
        "model": _config.get("model") or {},
    }

# ---- Chat -------------------------------------------------------------------------

@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    """
    1) Резолвер (если включён)
    2) Если команда и proxy включён — шлём в toolrunner
    3) Иначе чат — авто-стиль (brief/smalltalk) через Ollama
    4) Fallback: быстрые RU-паттерны на случай, если (1) не сработал
    """

    # 0) Быстрый RU fallback ДО всего прочего (минимальная латентность на частые фразы)
    fb = _ru_quick_intent(inp.text)
    if fb and fb.get("command") in ALLOWED:
        decision = fb
    else:
        # 1) Решение: команда или чат через резолвер/роутер
        if _resolver is not None:
            res = _resolver.resolve(inp.text)
            if res.get("error"):
                decision = route(inp.text)
            else:
                mapped_cmd, mapped_args = _map_resolver_to_tool(res.get("command", ""), res.get("args") or {})
                conf = float(res.get("confidence", 0.0))
                if _use_legacy_when_low_conf and conf < _low_conf_threshold:
                    decision = route(inp.text)
                else:
                    if mapped_cmd:
                        decision = {"type": "command", "command": mapped_cmd, "args": mapped_args}
                    else:
                        decision = route(inp.text)
        else:
            decision = route(inp.text)

    # 2) Ветка команды: sanitize, allowlist, прокси в toolrunner
    if decision["type"] == "command":
        cmd = decision.get("command", "") or ""
        args = decision.get("args", {}) or {}

        # sanitize базовых ключей
        if isinstance(args, dict):
            for key in ("path", "pattern", "name", "text"):
                if key in args:
                    args[key] = _clean_arg(args[key])

        # не слать в toolrunner то, чего он не знает
        if cmd not in ALLOWED:
            return ChatOut(type="command", command=cmd, args=args, ok=False, error="E_UNKNOWN_COMMAND")

        if _proxy_commands:
            url = f"{_tr_base}/execute"
            headers = {"X-Jarvis-Token": _tr_token} if _tr_token else {}
            payload = {"command": cmd, "args": args}
            try:
                with httpx.Client(timeout=_tr_timeout) as client:
                    r = client.post(url, json=payload, headers=headers)

                if r.status_code >= 400:
                    is_json = r.headers.get("content-type", "").startswith("application/json")
                    detail = (r.json() if is_json else {"detail": r.text}).get("detail", "E_COMMAND_FAILED")
                    return ChatOut(type="command", command=cmd, args=args, ok=False, error=detail)

                data = r.json()
                return ChatOut(
                    type="command",
                    command=cmd,
                    args=args,
                    ok=bool(data.get("ok")),
                    result=data.get("result"),
                    error=data.get("error"),
                )

            except Exception as e:
                return ChatOut(type="command", command=cmd, args=args, ok=False, error=f"E_TOOLRUNNER:{e}")

        # если прокси выключен — отдать решение наверх как есть
        return ChatOut(type="command", command=cmd, args=args)

    # 3) Ветка чата: авто-стиль
    mcfg = _config.get("model") or {}
    model = mcfg.get("name", "qwen2.5:1.5b")
    mhost = mcfg.get("host", "127.0.0.1")
    mport = int(mcfg.get("port", 11434))
    mto = int(mcfg.get("timeout_sec", 60))
    profiles = (mcfg.get("profiles") or {})

    text = ollama_chat_auto(
        model=model,
        profiles=profiles,
        user_text=inp.text,
        history=list(_history),
        host=mhost,
        port=mport,
        timeout_sec=mto,
    ).strip()

    if not text:
        text = ollama_chat(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": inp.text}],
            sampling=_config.get("sampling") or {},
            host=mhost, port=mport, timeout_sec=mto,
        ).strip() or "Не знаю"

    _history.append({"role": "user", "content": inp.text})
    _history.append({"role": "assistant", "content": text})
    return ChatOut(type="chat", text=text)
