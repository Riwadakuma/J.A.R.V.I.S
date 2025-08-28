from pathlib import Path
from typing import Any, Dict

def _cfg_path(config: Dict[str, Any]) -> Path:
    # системный конфиг Runner'а хранится рядом с ним
    return (Path(__file__).parent.parent / "config.yaml").resolve()

def cmd_system_help(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    return (
        "команды: файлы/прочитай/создай файл/допиши/открой/покажи/ярлык; "
        "конфиг показать; конфиг установить <ключ> <значение>"
    )

def cmd_system_config_get(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    p = _cfg_path(config)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "{}"

def cmd_system_config_set(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    key = (args.get("key") or "").strip()
    value = (args.get("value") or "").strip()
    if not key:
        raise ValueError("E_ARG_MISSING:key")
    p = _cfg_path(config)
    txt = p.read_text(encoding="utf-8") if p.exists() else ""
    new_txt = f"# NOTE: simple append; consider manual YAML cleanup if needed\n{txt}\n{key}: {value}\n"
    p.write_text(new_txt, encoding="utf-8")
    return "OK"
