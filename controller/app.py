from fastapi import FastAPI
from pathlib import Path
from typing import Dict, Tuple
import yaml
import httpx

from .contracts import ChatIn, ChatOut
from .router import route                     
from .ollama_client import ollama_chat
from .resolver_adapter import ResolverAdapter  

CFG_PATH = Path(__file__).parent / "config.yaml"
_config = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) if CFG_PATH.exists() else {}

app = FastAPI(title="JARVIS Controller")

SYSTEM_PROMPT = (
    "Ты локальный офлайн-ассистент. Отвечай кратко, по-русски. "
    "Не придумывай факты. Если не уверен — 'Не знаю'."
)

# ---- Interaction / Resolver wiring -------------------------------------------------

_interaction = _config.get("interaction") or {}
_resolver_enabled = bool(_interaction.get("enabled", True))

# Маппинг из команд резолвера в твои «белые» русские команды
_RESOLVER_TO_TOOL: Dict[str, str] = {
    "files.list": "файлы",
    "files.read": "прочитай",
    "files.create": "создай файл",
    "files.append": "допиши",
    "files.open": "открой",
    "files.reveal": "покажи",
    "files.shortcut_to_desktop": "ярлык",
    "system.help": "помощь",
    "system.config_get": "конфиг показать",
    "system.config_set": "конфиг установить",
}

# Обратный список для передачи в резолвер (whitelist)
_WHITELIST_RESOLVER = list(_RESOLVER_TO_TOOL.keys())

# Путь workspace: если нет в конфиге — рядом с проектом
_workspace_root = str((Path(__file__).parent.parent / "workspace").resolve())

_resolver = None
if _resolver_enabled:
    _resolver = ResolverAdapter(
        base_url=_interaction.get("resolver_url", "http://127.0.0.1:8020"),
        whitelist=_WHITELIST_RESOLVER,
        workspace_root=_workspace_root,
        mode=_interaction.get("resolver_mode", "hybrid"),            # rule-only | hybrid
        llm_threshold=float(_interaction.get("llm_threshold", 0.75)),
        timeout=float(_interaction.get("timeout_sec", 2.5)),
        llm_enable=bool((_interaction.get("llm") or {}).get("enable", True)),
        llm_base_url=(_interaction.get("llm") or {}).get("base_url", "http://127.0.0.1:11434"),
        llm_model=(_interaction.get("llm") or {}).get("model", "tinyllama"),
    )

# Нужна ли автоматическая деградация на legacy при низкой уверенности
_use_legacy_when_low_conf = bool(_interaction.get("use_legacy_when_low_conf", True))
_low_conf_threshold = float(_interaction.get("low_conf_threshold", 0.50))

def _map_resolver_to_tool(cmd: str, args: Dict) -> Tuple[str, Dict]:
    """Преобразуем команду резолвера в твою русскую команду."""
    mapped = _RESOLVER_TO_TOOL.get(cmd)
    return mapped or "", args or {}

# ---- Toolrunner proxy config -------------------------------------------------------

_controller_cfg = _config.get("controller") or {}
_proxy_commands = bool(_controller_cfg.get("proxy_commands", False))

_toolrunner_cfg = _config.get("toolrunner") or {}
_tr_base = (_toolrunner_cfg.get("base_url", "http://127.0.0.1:8011") or "").rstrip("/")
_tr_timeout = int(_toolrunner_cfg.get("timeout_sec", 30))
_tr_token = (_toolrunner_cfg.get("shared_token") or "").strip()

# ---- Health -----------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "model": (_config.get("model") or {}).get("name", ""),
        "proxy_commands": _proxy_commands,
        "resolver_enabled": _resolver_enabled,
    }

# ---- Chat -------------------------------------------------------------------------

@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    """
    Порядок:
    1) Если резолвер включен — пробуем его.
       - При ошибке/низкой уверенности (если включено) — деградация на legacy route().
    2) Если это команда и включен proxy_commands — проксируем в toolrunner.
    3) Иначе это чат — зовём модель через Ollama.
    """
    # 1) Попытка резолвера
    decision = None
    if _resolver is not None:
        res = _resolver.resolve(inp.text)
        if res.get("error"):
            # Резолвер лёг — уходим на legacy
            decision = route(inp.text)
        else:
            mapped_cmd, mapped_args = _map_resolver_to_tool(res.get("command", ""), res.get("args") or {})
            conf = float(res.get("confidence", 0.0))
            # если низкая уверенность и включена деградация — пускаем по старому
            if _use_legacy_when_low_conf and conf < _low_conf_threshold:
                decision = route(inp.text)
            else:
                # если команда распознана, формируем командное решение
                if mapped_cmd:
                    decision = {
                        "type": "command",
                        "command": mapped_cmd,
                        "args": mapped_args
                    }
                else:
                    # нет команды — на legacy, пусть он решит, что это чат или команда
                    decision = route(inp.text)
    else:
        # Резолвер выключен — старое поведение
        decision = route(inp.text)

    # 2) Командный режим: возможно проксируем в toolrunner
    if decision["type"] == "command":
        if _proxy_commands:
            url = f"{_tr_base}/execute"
            headers = {"X-Jarvis-Token": _tr_token} if _tr_token else {}
            payload = {"command": decision["command"], "args": decision.get("args", {})}
            try:
                with httpx.Client(timeout=_tr_timeout) as client:
                    r = client.post(url, json=payload, headers=headers)
                    if r.status_code >= 400:
                        # возвращаем ChatOut с ошибкой выполнения
                        detail = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text}).get("detail", "E_COMMAND_FAILED")
                        return ChatOut(
                            type="command",
                            command=decision["command"],
                            args=decision.get("args"),
                            ok=False,
                            error=detail,
                        )
                    data = r.json()
                return ChatOut(
                    type="command",
                    command=decision["command"],
                    args=decision.get("args"),
                    ok=bool(data.get("ok")),
                    result=data.get("result"),
                    error=data.get("error"),
                )
            except Exception as e:
                return ChatOut(
                    type="command",
                    command=decision["command"],
                    args=decision.get("args"),
                    ok=False,
                    error=f"E_TOOLRUNNER:{e}",
                )
        # proxy_commands выключен — отдаём команду как сигнал клиенту
        return ChatOut(**decision)

    # 3) Чат: зовём модель
    model = (_config.get("model") or {}).get("name", "qwen2.5:1.5b")
    mhost = (_config.get("model") or {}).get("host", "127.0.0.1")
    mport = int((_config.get("model") or {}).get("port", 11434))
    mto = int((_config.get("model") or {}).get("timeout_sec", 60))
    sampling = _config.get("sampling") or {}

    text = ollama_chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": inp.text},
        ],
        sampling=sampling,
        host=mhost,
        port=mport,
        timeout_sec=mto,
    ).strip()

    return ChatOut(type="chat", text=text or "Не знаю")
