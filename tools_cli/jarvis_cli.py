#!/usr/bin/env python3
import argparse, sys, os, json, time, threading
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import requests, yaml

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

def load_cfg() -> Dict[str, Any]:
    here = Path(__file__).parent
    cfg_path = here / "cli_config.yaml"
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    cfg = deep_merge(DEFAULT_CFG, data)
    # env overrides
    for key, env in ENV_OVERRIDES.items():
        val = os.getenv(env)
        if val:
            set_deep(cfg, key, val)
    return cfg

def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def set_deep(d: Dict[str, Any], dotted: str, value: Any):
    node = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value

def ensure_parent(p: Path):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def append_line(p: Path, line: str):
    try:
        ensure_parent(p)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

def log_event(cfg: Dict[str, Any], event: str, payload: Dict[str, Any]):
    lf = (cfg.get("ui") or {}).get("log_file")
    if not lf:
        return
    rec = {"ts": now_ts(), "event": event, **payload}
    append_line(Path(lf), json.dumps(rec, ensure_ascii=False))

def append_history(cfg: Dict[str, Any], text: str):
    hist = (cfg.get("ui") or {}).get("history_file")
    if not hist:
        return
    append_line(Path(hist), text.replace("\n", " "))

# ---------- http helpers ----------

def http_post_json(url: str, data: Dict[str, Any], timeout: int, headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, Any], Dict[str, str], float]:
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

def do_chat(cfg: Dict[str, Any], text: str):
    base = cfg["controller"]["base_url"].rstrip("/")
    timeout = int(cfg["controller"]["timeout_sec"])
    return http_post_json(f"{base}/chat", {"text": text}, timeout)

def do_execute(cfg: Dict[str, Any], command: str, args: Dict[str, Any]):
    base = cfg["toolrunner"]["base_url"].rstrip("/")
    timeout = int(cfg["toolrunner"]["timeout_sec"])
    headers = {}
    token = (cfg["toolrunner"].get("shared_token") or "").strip()
    if token:
        headers["X-Jarvis-Token"] = token
    return http_post_json(f"{base}/execute", {"command": command, "args": args or {}}, timeout, headers=headers)

# ---------- spinner ----------

class Spinner:
    FRAMES = ["|", "/", "—", "\\"]
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._alive = False
        self._t = None

    def start(self, label=""):
        if not self.enabled or self._alive:
            return
        self._alive = True
        def _run():
            i = 0
            while self._alive:
                sys.stdout.write("\r" + (label + " " if label else "") + self.FRAMES[i % len(self.FRAMES)])
                sys.stdout.flush()
                i += 1
                time.sleep(0.08)
        self._t = threading.Thread(target=_run, daemon=True)
        self._t.start()

    def stop(self):
        if not self.enabled:
            return
        self._alive = False
        if self._t:
            self._t.join(timeout=0.2)
        sys.stdout.write("\r")
        sys.stdout.flush()

# ---------- printers ----------

def print_json(resp: Dict[str, Any]) -> int:
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0

def print_raw(resp: Dict[str, Any]) -> int:
    t = resp.get("type")
    if t == "chat":
        print(resp.get("text", "").strip())
    elif t == "command":
        ok = resp.get("ok", None)
        if ok is None:
            print(f"{resp.get('command','')} {json.dumps(resp.get('args') or {}, ensure_ascii=False)}")
        else:
            print(json.dumps({"ok": ok, "result": resp.get("result"), "error": resp.get("error")}, ensure_ascii=False))
    else:
        print(json.dumps(resp, ensure_ascii=False))
    return 0

def print_pretty(resp: Dict[str, Any]) -> int:
    t = resp.get("type")
    if t == "chat":
        print(resp.get("text", "").strip())
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
            suffix = ("  [" + ", ".join(info) + "]") if info else ""
            print(f"[command] {resp.get('command')} {json.dumps(resp.get('args') or {}, ensure_ascii=False)}{suffix}")
            return 0
        if ok:
            res = resp.get("result")
            if isinstance(res, (dict, list)):
                print(json.dumps(res, ensure_ascii=False, indent=2))
            elif res is None:
                print("OK")
            else:
                print(str(res))
            return 0
        else:
            err = resp.get("error") or "E_COMMAND_FAILED"
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
    print(json.dumps(resp, ensure_ascii=False))
    return 0

def printer(mode: str, resp: Dict[str, Any]) -> int:
    if mode == "json":
        return print_json(resp)
    if mode == "raw":
        return print_raw(resp)
    return print_pretty(resp)

# ---------- core flows ----------

def run_once(cfg: Dict[str, Any], text: str, mode: str, no_exec: bool = False, verbose: int = 0) -> int:
    spinner = Spinner(bool((cfg.get("ui") or {}).get("spinner", True)))
    spinner.start("thinking")
    status, chat, headers, dur_ms = do_chat(cfg, text)
    spinner.stop()

    log_event(cfg, "chat_response", {"status": status, "ms": round(dur_ms, 1), "body": chat})

    if status >= 400:
        resp = {"type": "chat", "text": chat.get("detail", "E_CONTROLLER")}
        return printer(mode, resp)

    # поддержка метаданных от контроллера (если ты включишь их)
    meta = chat.get("meta") or {}

    if chat.get("type") == "command" and chat.get("command"):
        cmd, args = chat["command"], chat.get("args") or {}
        if no_exec:
            out = {"type": "command", "command": cmd, "args": args, "ok": None, "result": None, "error": None, "meta": meta}
            return printer(mode, out)

        # опциональное подтверждение при низкой уверенности
        if (cfg.get("ui") or {}).get("confirm_on_low_conf"):
            conf = (meta.get("resolver") or {}).get("confidence")
            if isinstance(conf, (int, float)) and conf < 0.75:
                yn = input(f"Уверенность {conf:.2f}. Выполнить команду {cmd}? [y/N] ").strip().lower()
                if yn not in ("y", "yes", "д", "да"):
                    out = {"type": "command", "command": cmd, "args": args, "ok": None, "result": None, "error": "CANCELLED", "meta": meta}
                    return printer(mode, out)

        if not (cfg.get("ui") or {}).get("auto_exec", True):
            out = {"type": "command", "command": cmd, "args": args, "ok": None, "result": None, "error": None, "meta": meta}
            return printer(mode, out)

        spinner.start("execute")
        st2, out, _hdr2, dur2 = do_execute(cfg, cmd, args)
        spinner.stop()
        log_event(cfg, "execute_response", {"status": st2, "ms": round(dur2, 1), "body": out})

        if st2 >= 400:
            resp = {"type": "command", "command": cmd, "args": args, "ok": False,
                    "result": None, "error": (out.get("detail") or "E_COMMAND_FAILED")}
            return printer(mode, resp)

        resp = {"type": "command", "command": cmd, "args": args,
                "ok": bool(out.get("ok")), "result": out.get("result"), "error": out.get("error")}
        return printer(mode, resp)

    # иначе это чат
    append_history(cfg, text)
    return printer(mode, chat)

def repl(cfg: Dict[str, Any], mode: str, no_exec: bool, verbose: int):
    print("JARVIS CLI. Введите запрос. Ctrl+C — выход.")
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            if line in ("/q", "/quit", "/exit"):
                break
            if line == "/json":
                mode = "json"; print("mode=json"); continue
            if line == "/pretty":
                mode = "pretty"; print("mode=pretty"); continue
            if line == "/raw":
                mode = "raw"; print("mode=raw"); continue
            code = run_once(cfg, line, mode, no_exec=no_exec, verbose=verbose)
            if code != 0:
                # не валим REPL из-за ошибки команды
                pass
        except KeyboardInterrupt:
            print()
            break

# ---------- main ----------

def main():
    p = argparse.ArgumentParser(prog="jarvis", description="CLI клиент для локального JARVIS")
    g = p.add_mutually_exclusive_group()
    g.add_argument("-e", "--execute", dest="text", help="Одноразовый запуск: отправить строку в /chat (и /execute при команде)")
    g.add_argument("-f", "--file", dest="file", help="Прочитать файл и отправить содержимое")
    p.add_argument("--json", action="store_true", help="Вывод JSON")
    p.add_argument("--raw", action="store_true", help="Сырой вывод без форматирования")
    p.add_argument("--no-exec", action="store_true", help="Не выполнять команды (dry-run, только показать)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Подробности (повтор для ещё больше)")
    args = p.parse_args()

    cfg = load_cfg()
    mode = (cfg.get("ui") or {}).get("mode", "pretty")
    if args.json: mode = "json"
    if args.raw: mode = "raw"

    # чтение из файла
    if args.file:
        pth = Path(args.file)
        if not pth.exists():
            print("E_FILE_NOT_FOUND", file=sys.stderr); sys.exit(1)
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
