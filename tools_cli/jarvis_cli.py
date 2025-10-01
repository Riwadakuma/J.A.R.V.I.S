#!/usr/bin/env python3
import argparse, sys, os, json, time, threading
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import requests, yaml

try:  # pragma: no cover - runtime import guard
    from .stylist import get_stylist, say, say_key
except ImportError:  # pragma: no cover - script execution fallback
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from interaction.stylist import get_stylist, say, say_key  # type: ignore

_stylist = get_stylist()
_stylist.update_defaults(signature="командир", signature_short="сэр")

DEFAULT_CFG = {
    "controller": {"base_url": "http://127.0.0.1:8010", "timeout_sec": 30},
    "toolrunner": {"base_url": "http://127.0.0.1:8011", "timeout_sec": 30, "shared_token": ""},
    "ui": {
        "mode": "pretty",                     # pretty | json | raw
        "history_file": "../data/cli_history.txt",
        "log_file": "../logs/cli.log",
        "spinner": True,
        "confirm_on_low_conf": False,
        "auto_exec": True,
    },
}

ENV_OVERRIDES = {
    "controller.base_url": "JARVIS_CONTROLLER_URL",
    "toolrunner.base_url": "JARVIS_TOOLRUNNER_URL",
    "toolrunner.shared_token": "JARVIS_TOOLRUNNER_TOKEN",
}

# ---------- config & io ----------

def load_cfg(custom_cfg_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration, applying defaults and environment overrides.

    Args:
        custom_cfg_path: optional path to YAML config file. If not provided,
            defaults to tools_cli/cli_config.yaml near this script.

    Returns:
        Combined configuration dictionary.
    """
    here = Path(__file__).parent
    cfg_path = Path(custom_cfg_path) if custom_cfg_path else (here / "cli_config.yaml")
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            logging.exception(f"Failed to load config from {cfg_path}")
            data = {}
    cfg = deep_merge(DEFAULT_CFG, data)
    # env overrides
    for key, env in ENV_OVERRIDES.items():
        val = os.getenv(env)
        if val:
            set_deep(cfg, key, val)
    return cfg


def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge mapping ``b`` into ``a`` and return the result."""
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def set_deep(d: Dict[str, Any], dotted: str, value: Any):
    """Set a nested ``value`` in ``d`` using dotted path notation."""
    node = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def ensure_parent(p: Path):
    """Create parent directories for ``p`` if they do not exist."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        logging.exception(f"Failed to create parent directory for {p}")


def append_line(p: Path, line: str):
    """Append a line to a file, creating parent directories if needed."""
    try:
        ensure_parent(p)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logging.exception(f"Failed to append line to {p}")


def now_ts() -> str:
    """Return current timestamp as a string."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def log_event(cfg: Dict[str, Any], event: str, payload: Dict[str, Any]):
    """Append an event record to the log file configured in ``cfg``."""
    lf = (cfg.get("ui") or {}).get("log_file")
    if not lf:
        return
    rec = {"ts": now_ts(), "event": event, **payload}
    append_line(Path(lf), json.dumps(rec, ensure_ascii=False))


def append_history(cfg: Dict[str, Any], text: str):
    """Save user input to the history file if configured."""
    hist = (cfg.get("ui") or {}).get("history_file")
    if not hist:
        return
    append_line(Path(hist), text.replace("\n", " "))

# ---------- http helpers ----------

def http_post_json(
    url: str,
    data: Dict[str, Any],
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any], Dict[str, str], float]:
    """Send a POST request with JSON body and return response details.

    Returns a tuple of status code, decoded body, headers and duration in ms.
    """
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=data, timeout=timeout, headers=headers or {})
        dur = (time.perf_counter() - t0) * 1000.0
        try:
            body = r.json()
        except Exception:
            body = {"detail": r.text}
        return r.status_code, body, dict(r.headers or {}), dur
    except Exception as e:
        dur = (time.perf_counter() - t0) * 1000.0
        return 599, {"detail": f"{type(e).__name__}: {e}"}, {}, dur


def http_get_json(
    url: str,
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any], Dict[str, str], float]:
    """Send a GET request and return response details."""
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {})
        dur = (time.perf_counter() - t0) * 1000.0
        try:
            body = r.json()
        except Exception:
            body = {"detail": r.text}
        return r.status_code, body, dict(r.headers or {}), dur
    except Exception as e:
        dur = (time.perf_counter() - t0) * 1000.0
        return 599, {"detail": f"{type(e).__name__}: {e}"}, {}, dur

def do_chat(cfg: Dict[str, Any], text: str):
    """Call the controller's ``/chat`` endpoint with provided text."""
    base = cfg["controller"]["base_url"].rstrip("/")
    timeout = int(cfg["controller"]["timeout_sec"])
    return http_post_json(f"{base}/chat", {"text": text}, timeout)

def do_execute(cfg: Dict[str, Any], command: str, args: Dict[str, Any]):
    """Invoke the toolrunner to execute a command with arguments."""
    base = cfg["toolrunner"]["base_url"].rstrip("/")
    timeout = int(cfg["toolrunner"]["timeout_sec"])
    headers = {}
    token = (cfg["toolrunner"].get("shared_token") or "").strip()
    if token:
        headers["X-Jarvis-Token"] = token
    return http_post_json(
        f"{base}/execute", {"command": command, "args": args or {}}, timeout, headers=headers
    )


def do_diagnostics(cfg: Dict[str, Any], mode: str | None = None) -> int:
    """Call controller's ``/diagnostics`` endpoint and print the result."""
    base = cfg["controller"]["base_url"].rstrip("/")
    timeout = int(cfg["controller"]["timeout_sec"])
    if mode is None:
        mode = (cfg.get("ui") or {}).get("mode", "pretty")
    if mode == "pretty":
        print(say_key("cli.diagnostics.start"))
    spinner = Spinner(bool((cfg.get("ui") or {}).get("spinner", True)))
    spinner.start(say_key("spinner.diagnostics"))
    status, body, _hdr, dur = http_get_json(f"{base}/diagnostics", timeout)
    spinner.stop()
    log_event(cfg, "diagnostics_response", {"status": status, "ms": round(dur, 1), "body": body})
    if status >= 400:
        detail = body.get("detail", "E_CONTROLLER")
        if mode == "pretty":
            print(say_key("cli.diagnostics.failure", detail=detail))
        resp = {"type": "chat", "text": say_key("errors.controller", detail=detail)}
        printer(mode, resp)
        return 1
    if mode == "pretty":
        print(say_key("cli.diagnostics.success"))
    return printer(mode, body)

# ---------- spinner ----------

class Spinner:
    """Minimal console spinner used while waiting on network calls."""

    FRAMES = ["|", "/", "—", "\\"]

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._alive = False
        self._t = None
        self._last_len = 0
        self._label = ""

    def start(self, label: str = ""):
        """Start showing the spinner with an optional label."""
        if not self.enabled or self._alive:
            return
        self._alive = True
        self._label = (label + " ") if label else ""

        def _run():
            i = 0
            while self._alive:
                line = self._label + self.FRAMES[i % len(self.FRAMES)]
                self._last_len = len(line)
                sys.stdout.write("\r" + line)
                sys.stdout.flush()
                i += 1
                time.sleep(0.08)

        self._t = threading.Thread(target=_run, daemon=True)
        self._t.start()

    def stop(self):
        """Stop the spinner and clean up the line."""
        if not self.enabled:
            return
        self._alive = False
        if self._t:
            self._t.join(timeout=0.2)
        # Полностью затереть хвост «execute |/» и вернуть курсор в начало строки
        sys.stdout.write("\r" + (" " * max(self._last_len, len(self._label) + 2)) + "\r")
        sys.stdout.flush()


# ---------- printers ----------

def print_json(resp: Dict[str, Any]) -> int:
    """Print response dictionary as formatted JSON."""
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0

def print_raw(resp: Dict[str, Any]) -> int:
    """Print response without additional formatting."""
    t = resp.get("type")
    if t == "chat":
        print(say(resp.get("text", "")))
    elif t == "command":
        ok = resp.get("ok", None)
        if ok is None:
            preview = f"{resp.get('command','')} {json.dumps(resp.get('args') or {}, ensure_ascii=False)}"
            print(say(preview))
            if str(resp.get("error", "")).upper() == "CANCELLED":
                print(say_key("status.cancelled"))
        else:
            if ok and resp.get("result") is None:
                print(say_key("status.ok"))
            elif ok and isinstance(resp.get("result"), str):
                print(say(resp.get("result")))
            elif not ok:
                err = resp.get("error") or "E_COMMAND_FAILED"
                print(say_key("status.error", error=err))
            else:
                print(
                    json.dumps(
                        {"ok": ok, "result": resp.get("result"), "error": resp.get("error")},
                        ensure_ascii=False,
                    )
                )
    else:
        print(json.dumps(resp, ensure_ascii=False))
    return 0

def print_pretty(resp: Dict[str, Any]) -> int:
    """Human-friendly printer that highlights chat and command responses."""
    t = resp.get("type")
    if t == "chat":
        print(say(resp.get("text", "")))
        return 0
    if t == "command":
        ok = resp.get("ok", None)
        if ok is None:
            meta = resp.get("meta") or {}
            info = []
            conf = meta.get("resolver", {}).get("confidence")
            if conf is not None:
                info.append(f"conf={conf}")
            fb = meta.get("resolver", {}).get("fallback_used")
            if fb:
                info.append("fallback")
            planner_rule = (meta.get("planner") or {}).get("planner_rule_id")
            if planner_rule:
                info.append(f"rule={planner_rule}")
            planner_error = (meta.get("planner") or {}).get("error")
            if planner_error:
                info.append(str(planner_error))
            executor_errors = (meta.get("executor") or {}).get("errors") or []
            if executor_errors:
                info.append("exec_error")
            suffix = ("  [" + ", ".join(info) + "]") if info else ""
            preview = (
                f"[command] {resp.get('command')} {json.dumps(resp.get('args') or {}, ensure_ascii=False)}{suffix}"
            )
            print(say(preview))
            if str(resp.get("error", "")).upper() == "CANCELLED":
                print(say_key("status.cancelled"))
            return 0
        if ok:
            res = resp.get("result")
            if isinstance(res, (dict, list)):
                print(json.dumps(res, ensure_ascii=False, indent=2))
            elif res is None:
                print(say_key("status.ok"))
            else:
                print(say(str(res)))
            return 0
        else:
            err = resp.get("error") or "E_COMMAND_FAILED"
            if str(err).upper() == "CANCELLED":
                print(say_key("status.cancelled"), file=sys.stderr)
            else:
                print(say_key("status.error", error=err), file=sys.stderr)
            return 1
    print(json.dumps(resp, ensure_ascii=False))
    return 0

def printer(mode: str, resp: Dict[str, Any]) -> int:
    """Dispatch response printer based on output ``mode``."""
    if mode == "json":
        return print_json(resp)
    if mode == "raw":
        return print_raw(resp)
    return print_pretty(resp)

# ---------- core flows ----------

def run_once(
    cfg: Dict[str, Any],
    text: str,
    mode: str,
    no_exec: bool = False,
    verbose: int = 0,
) -> int:
    """Handle a single user request and print the result.

    Args:
        cfg: Configuration dictionary.
        text: User input text.
        mode: Output mode (``pretty``, ``json`` or ``raw``).
        no_exec: If ``True``, do not execute returned commands.
        verbose: Verbosity level for debugging.

    Returns:
        Shell-style exit code.
    """
    spinner = Spinner(bool((cfg.get("ui") or {}).get("spinner", True)))
    spinner.start(say_key("spinner.thinking"))
    status, chat, headers, dur_ms = do_chat(cfg, text)
    spinner.stop()

    log_event(cfg, "chat_response", {"status": status, "ms": round(dur_ms, 1), "body": chat})

    if status >= 400:
        detail = chat.get("detail", "E_CONTROLLER")
        resp = {"type": "chat", "text": say_key("errors.controller", detail=detail)}
        return printer(mode, resp)

    # поддержка метаданных от контроллера (если они включены)
    meta = chat.get("meta") or {}

    if chat.get("type") == "command" and chat.get("command"):
        cmd, args = chat["command"], chat.get("args") or {}
        planner_meta = (meta.get("planner") or {})
        preview_key = (planner_meta.get("stylist") or {}).get("preview")
        if preview_key and mode == "pretty":
            print(say_key(preview_key, **args))
        if no_exec:
            out = {
                "type": "command",
                "command": cmd,
                "args": args,
                "ok": None,
                "result": None,
                "error": None,
                "meta": meta,
            }
            return printer(mode, out)

        # опциональное подтверждение при низкой уверенности
        if (cfg.get("ui") or {}).get("confirm_on_low_conf"):
            conf = (meta.get("resolver") or {}).get("confidence")
            if isinstance(conf, (int, float)) and conf < 0.75:
                prompt = say_key("prompts.confirm_low_conf", confidence=conf, command=cmd)
                yn = input(prompt).strip().lower()
                if yn not in ("y", "yes", "д", "да"):
                    out = {
                        "type": "command",
                        "command": cmd,
                        "args": args,
                        "ok": None,
                        "result": None,
                        "error": "CANCELLED",
                        "meta": meta,
                    }
                    return printer(mode, out)

        if not (cfg.get("ui") or {}).get("auto_exec", True):
            out = {
                "type": "command",
                "command": cmd,
                "args": args,
                "ok": None,
                "result": None,
                "error": None,
                "meta": meta,
            }
            return printer(mode, out)

        spinner.start(say_key("spinner.execute"))
        st2, out, _hdr2, dur2 = do_execute(cfg, cmd, args)
        spinner.stop()
        log_event(cfg, "execute_response", {"status": st2, "ms": round(dur2, 1), "body": out})

        if st2 >= 400:
            resp = {
                "type": "command",
                "command": cmd,
                "args": args,
                "ok": False,
                "result": None,
                "error": out.get("detail") or "E_COMMAND_FAILED",
            }
            return printer(mode, resp)

        resp = {
            "type": "command",
            "command": cmd,
            "args": args,
            "ok": bool(out.get("ok")),
            "result": out.get("result"),
            "error": out.get("error"),
        }
        return printer(mode, resp)

    # иначе это чат
    append_history(cfg, text)
    return printer(mode, chat)

def repl(cfg: Dict[str, Any], mode: str, no_exec: bool, verbose: int):
    """Interactive shell for communicating with JARVIS."""
    print(say_key("cli.greeting"))
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            if line in ("/q", "/quit", "/exit"):
                print(say_key("cli.goodbye"))
                break
            if line == "/json":
                mode = "json"; print(say_key("cli.mode_switch", mode="json")); continue
            if line == "/pretty":
                mode = "pretty"; print(say_key("cli.mode_switch", mode="pretty")); continue
            if line == "/raw":
                mode = "raw"; print(say_key("cli.mode_switch", mode="raw")); continue
            code = run_once(cfg, line, mode, no_exec=no_exec, verbose=verbose)
            if code != 0:
                # не валим REPL из-за ошибки команды
                pass
        except KeyboardInterrupt:
            print()
            print(say_key("cli.goodbye"))
            break

# ---------- main ----------

def main():
    """Parse CLI arguments and run the requested mode."""
    p = argparse.ArgumentParser(prog="jarvis", description="CLI клиент для локального JARVIS")
    g = p.add_mutually_exclusive_group()
    g.add_argument("-e", "--execute", dest="text", help="Одноразовый запуск: отправить строку в /chat (и /execute при команде)")
    g.add_argument("-f", "--file", dest="file", help="Прочитать файл и отправить содержимое")
    g.add_argument("--diagnostics", action="store_true", help="Запросить диагностику контроллера и выйти")
    p.add_argument("--config", dest="config", help="Путь к YAML-конфигу (по умолчанию tools_cli/cli_config.yaml)")
    p.add_argument("--json", action="store_true", help="Вывод JSON")
    p.add_argument("--raw", action="store_true", help="Сырой вывод без форматирования")
    p.add_argument("--no-exec", action="store_true", help="Не выполнять команды (dry-run, только показать)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Подробности (повтор для ещё больше)")
    args = p.parse_args()

    cfg = load_cfg(args.config)
    mode = (cfg.get("ui") or {}).get("mode", "pretty")
    if args.json:
        mode = "json"
    if args.raw:
        mode = "raw"

    if args.diagnostics:
        (cfg.setdefault("ui", {}))["mode"] = mode
        result = do_diagnostics(cfg, mode)
        if isinstance(result, tuple):
            status = result[0]
            sys.exit(0 if status < 400 else 1)
        sys.exit(result)

    # чтение из файла
    if args.file:
        pth = Path(args.file)
        if not pth.exists():
            print(say_key("errors.file_not_found", path=str(pth)), file=sys.stderr)
            sys.exit(1)
        text = pth.read_text(encoding="utf-8", errors="ignore")
        sys.exit(run_once(cfg, text, mode, no_exec=args.no_exec, verbose=args.verbose))

    # одноразовый запуск
    if args.text is not None:
        sys.exit(run_once(cfg, args.text, mode, no_exec=args.no_exec, verbose=args.verbose))

    # если на вход подали stdin (pipeline)
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        sys.exit(run_once(cfg, text, mode, no_exec=args.no_exec, verbose=args.verbose))

    # REPL
    repl(cfg, mode, no_exec=args.no_exec, verbose=args.verbose)
    sys.exit(0)

if __name__ == "__main__":
    main()
