from fastapi import FastAPI, HTTPException
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import deque
import re
import sys
import yaml
import httpx

try:  # pragma: no cover - runtime import guard
    from config.loader import load_config as load_core_config
    from core.pipeline import Pipeline, PipelineResult, build_http_pipeline
    from resolver.resolver import ResolverConfig
except ModuleNotFoundError:  # pragma: no cover - script execution fallback
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from config.loader import load_config as load_core_config  # type: ignore
    from core.pipeline import Pipeline, PipelineResult, build_http_pipeline  # type: ignore
    from resolver.resolver import ResolverConfig  # type: ignore

from controller.contracts import ChatIn, ChatOut
from controller.router import route, ALLOWED
from controller.ollama_client import ollama_chat, ollama_chat_auto
from controller.resolver_adapter import ResolverAdapter

CFG_PATH = Path(__file__).parent / "config.yaml"
_config = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) if CFG_PATH.exists() else {}
_diagnostic_mode = bool(_config.get("diagnostic_mode", False))

_core_config = load_core_config()
_core_features = _core_config.get("features") or {}
_planner_enabled = bool((_core_features.get("planner") or {}).get("enabled", True))
_strict_acl = bool(_core_features.get("strict_acl", True))
_provenance_verbose = bool(((_core_features.get("provenance") or {}).get("verbose")) or False)

_root_dir = Path(__file__).parent.parent

_planner_rules_path = Path((_core_config.get("planner") or {}).get("rules_path", "planner/rules.yaml"))
if not _planner_rules_path.is_absolute():
    _planner_rules_path = (_root_dir / _planner_rules_path).resolve()

app = FastAPI(title="JARVIS Controller")

SYSTEM_PROMPT = (
    "Ты локальный офлайн-ассистент. Отвечай кратко, по-русски. "
    "Не придумывай факты. Если не уверен — 'Не знаю'."
)

_interaction = _config.get("interaction") or {}
_resolver_enabled = bool(_interaction.get("enabled", True))

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
_workspace_root = _config.get(
    "workspace_root",
    str((Path(__file__).parent.parent / "workspace").resolve()),
)

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

_controller_cfg = _config.get("controller") or {}
_proxy_commands = bool(_controller_cfg.get("proxy_commands", False))

_toolrunner_cfg = _config.get("toolrunner") or {}
_core_toolrunner_cfg = (_core_config.get("executor") or {}).get("toolrunner") or {}
_tr_base = (
    _core_toolrunner_cfg.get("base_url")
    or _toolrunner_cfg.get("base_url", "http://127.0.0.1:8011")
    or ""
).rstrip("/")
_tr_timeout = int(_core_toolrunner_cfg.get("timeout_sec") or _toolrunner_cfg.get("timeout_sec", 30))
_tr_token = (
    _core_toolrunner_cfg.get("token")
    or _toolrunner_cfg.get("shared_token")
    or ""
).strip()


_history = deque(maxlen=12)  # [ {"role": "...", "content": "..."} ]


def _build_resolver_config() -> ResolverConfig:
    cfg = _core_config.get("resolver") or {}
    llm_cfg = cfg.get("llm") or (_interaction.get("llm") or {})
    return ResolverConfig(
        whitelist=_WHITELIST_RESOLVER,
        remote_url=cfg.get("remote_url") or _interaction.get("resolver_url", "http://127.0.0.1:8020"),
        timeout=float(cfg.get("timeout", _interaction.get("timeout_sec", 2.5))),
        mode=str(cfg.get("mode", _interaction.get("resolver_mode", "hybrid"))),
        low_conf_threshold=float(cfg.get("low_conf_threshold", _low_conf_threshold)),
        use_legacy_when_low_conf=bool(cfg.get("use_legacy_when_low_conf", _use_legacy_when_low_conf)),
        llm_threshold=float(cfg.get("llm_threshold", _interaction.get("llm_threshold", 0.75))),
        llm_enable=bool(llm_cfg.get("enable", True)),
        llm_base_url=str(llm_cfg.get("base_url", "http://127.0.0.1:11434")),
        llm_model=str(llm_cfg.get("model", "tinyllama")),
    )


def _pipeline_context() -> Dict[str, Any]:
    return {"cwd": _workspace_root, "locale": "ru-RU"}


def _pipeline_meta(result: PipelineResult) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"resolver": result.intent.asdict().get("meta")}
    if result.plan:
        planner_meta = dict(result.plan.provenance)
        planner_meta["error"] = result.plan.error
        planner_meta["stylist"] = dict(result.plan.stylist_keys)
        meta["planner"] = planner_meta
    if result.execution:
        executor_meta = dict(result.execution.provenance)
        executor_meta["errors"] = list(result.execution.errors)
        executor_meta["ok"] = result.execution.ok
        meta["executor"] = executor_meta
    return meta


_pipeline: Pipeline | None = None
_pipeline_error: Optional[str] = None
if _planner_enabled:
    try:
        resolver_config = _build_resolver_config()
        _pipeline = build_http_pipeline(
            resolver_config=resolver_config,
            planner_rules_path=_planner_rules_path,
            toolrunner_url=_tr_base or "http://127.0.0.1:8011",
            toolrunner_timeout=_tr_timeout,
            toolrunner_token=_tr_token or None,
            strict_acl=_strict_acl,
        )
    except Exception as exc:  # pragma: no cover - defensive
        _pipeline_error = f"pipeline_init:{exc}"
        _pipeline = None
        _planner_enabled = False


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

_RU_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:создай|создать)\s+файл\s+(.+)$", re.I),       "files.create"),
    (re.compile(r"^(?:прочитай|прочитать)\s+файл\s+(.+)$", re.I),   "files.read"),
    (re.compile(r"^(?:покажи|список|файлы)(?:\s+(.*))?$", re.I),    "files.list"),
    (re.compile(r"^(?:открой|открыть)\s+файл\s+(.+)$", re.I),       "files.open"),
    (re.compile(r"^(?:допиши|добавь)\s+в\s+файл\s+(.+?)\s*[:\-–]\s*(.+)$", re.I), "files.append"),
]

def _ru_quick_intent(text: str) -> Optional[Dict[str, Any]]:
    t = text.strip()
    for rx, cmd in _RU_PATTERNS:
        m = rx.match(t)
        if not m:
            continue
        g1 = _clean_arg(m.group(1)) if m.group(1) else None
        if cmd == "files.create":
            return {"type": "command", "command": cmd, "args": {"path": g1, "content": ""}}
        if cmd == "files.read":
            return {"type": "command", "command": cmd, "args": {"path": g1}}
        if cmd == "files.list":
            mask = g1 if g1 is not None else "*"
            return {"type": "command", "command": cmd, "args": {"mask": mask}}
        if cmd == "files.open":
            return {"type": "command", "command": cmd, "args": {"path": g1}}
        if cmd == "files.append" and m.lastindex and m.lastindex >= 2:
            g2 = _clean_arg(m.group(2))
            return {"type": "command", "command": cmd, "args": {"path": g1, "content": g2}}
    return None


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
        "planner": {
            "enabled": _planner_enabled,
            "pipeline_active": _pipeline is not None,
            "strict_acl": _strict_acl,
            "rules_path": str(_planner_rules_path),
            "error": _pipeline_error,
        },
        "model": _config.get("model") or {},
    }


def _from_resolver(text: str) -> Dict[str, Any]:
    """1) Резолвер (если включён)

    4) Fallback: быстрые RU-паттерны на случай, если (1) не сработал
    """

    fb = _ru_quick_intent(text)
    if fb and fb.get("command") in ALLOWED:
        return fb
    if _resolver is not None:
        res = _resolver.resolve(text)
        if not res or res.get("error"):
            return route(text)
        mapped_cmd, mapped_args = _map_resolver_to_tool(res.get("command", ""), res.get("args") or {})
        conf = float(res.get("confidence", 0.0))
        if _use_legacy_when_low_conf and conf < _low_conf_threshold:
            return route(text)
        if mapped_cmd:
            return {"type": "command", "command": mapped_cmd, "args": mapped_args}
        return route(text)
    return route(text)


def _proxy_toolrunner(cmd: str, args: Dict[str, Any], *, meta: Optional[Dict[str, Any]] = None) -> ChatOut:
    """2) Если команда и proxy включён — шлём в toolrunner"""

    if isinstance(args, dict):
        if "text" in args and "content" not in args:
            args["content"] = args.pop("text")
        for key in ("path", "pattern", "mask", "name", "content"):
            if key in args:
                args[key] = _clean_arg(args[key])

    if cmd not in ALLOWED:
        return ChatOut(type="command", command=cmd, args=args, ok=False, error="E_UNKNOWN_COMMAND", meta=meta)

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
                return ChatOut(type="command", command=cmd, args=args, ok=False, error=detail, meta=meta)

            data = r.json()
            return ChatOut(
                type="command",
                command=cmd,
                args=args,
                ok=bool(data.get("ok")),
                result=data.get("result"),
                error=data.get("error"),
                meta=meta,
            )

        except Exception as e:
            return ChatOut(type="command", command=cmd, args=args, ok=False, error=f"E_TOOLRUNNER:{e}", meta=meta)

    return ChatOut(type="command", command=cmd, args=args, meta=meta)


def _chat_with_model(user_text: str, *, meta: Optional[Dict[str, Any]] = None) -> ChatOut:
    """3) Иначе чат — авто-стиль (brief/smalltalk) через Ollama"""

    mcfg = _config.get("model") or {}
    model = mcfg.get("name", "qwen2.5:1.5b")
    mhost = mcfg.get("host", "127.0.0.1")
    mport = int(mcfg.get("port", 11434))
    mto = int(mcfg.get("timeout_sec", 60))
    profiles = (mcfg.get("profiles") or {})

    text = ollama_chat_auto(
        model=model,
        profiles=profiles,
        user_text=user_text,
        history=list(_history),
        host=mhost,
        port=mport,
        timeout_sec=mto,
    ).strip()

    if not text:
        text = ollama_chat(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}],
            sampling=_config.get("sampling") or {},
            host=mhost, port=mport, timeout_sec=mto,
        ).strip() or "Не знаю"

    _history.append({"role": "user", "content": user_text})
    _history.append({"role": "assistant", "content": text})
    return ChatOut(type="chat", text=text, meta=meta)


@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    meta: Optional[Dict[str, Any]] = None
    if _pipeline is not None:
        result = _pipeline.handle(inp.text, context=_pipeline_context())
        meta = _pipeline_meta(result)
        meta.setdefault("pipeline", {"enabled": True, "strict_acl": _strict_acl})
        if result.intent.is_command():
            if result.plan and result.execution:
                error = result.execution.errors[-1] if result.execution.errors else None
                return ChatOut(
                    type="command",
                    command=result.intent.name or "",
                    args=dict(result.intent.args),
                    ok=result.execution.ok,
                    result=result.execution.result,
                    error=error,
                    meta=meta,
                )
            meta["pipeline"]["fallback"] = result.plan.error if result.plan else "no_execution"
            meta["pipeline"]["used"] = False
        else:
            return _chat_with_model(inp.text, meta=meta)

    decision = _from_resolver(inp.text)
    if decision["type"] == "command":
        cmd = decision.get("command", "") or ""
        args = decision.get("args", {}) or {}
        fallback_meta: Optional[Dict[str, Any]] = None
        if _pipeline is not None:
            fallback_meta = meta
        return _proxy_toolrunner(cmd, args, meta=fallback_meta)
    return _chat_with_model(inp.text, meta=meta if _pipeline is not None else None)
