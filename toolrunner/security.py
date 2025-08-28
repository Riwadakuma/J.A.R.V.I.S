from pathlib import Path

def _cfg_workspace(config: dict) -> Path:
    """
    Возвращает абсолютный путь к корню workspace согласно конфигу.
    paths.workspace может быть относительным (относительно toolrunner/), либо абсолютным.
    """
    ws = (config.get("paths") or {}).get("workspace", "../workspace")
    p = Path(__file__).parent / ws if not Path(ws).is_absolute() else Path(ws)
    return p.resolve()

def workspace_path(rel: str, config: dict) -> Path:
    """
    Преобразует относительный путь из команды в безопасный абсолютный путь внутри workspace.
    Бросает E_PATH_OUTSIDE_WORKSPACE при попытке выхода за пределы.
    """
    base = _cfg_workspace(config)
    base.mkdir(parents=True, exist_ok=True)
    if not rel:
        raise ValueError("E_ARG_MISSING:path")
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        raise ValueError("E_PATH_OUTSIDE_WORKSPACE")
    return p

def normalize_args(args: dict) -> dict:
    """
    Нормализует строковые аргументы: обрезает пробелы и внешние кавычки.
    """
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str):
            s = v.strip()
            if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
                s = s[1:-1]
            out[k] = s
        else:
            out[k] = v
    return out

def ensure_allowed(command: str):
    from .registry import ALLOWED_COMMANDS
    if command not in ALLOWED_COMMANDS:
        raise ValueError("E_UNKNOWN_COMMAND")

def max_read_bytes(config: dict) -> int:
    return int((config.get("limits") or {}).get("max_read_bytes", 5_000_000))

def shared_token_ok(header_value: str | None, secret: str) -> bool:
    return bool(header_value) and header_value == secret

def feature_enabled(config: dict, key: str, default: bool = True) -> bool:
    """
    Читает флаг безопасности из security.* (например allow_open / allow_reveal / allow_shortcut).
    """
    sec = (config.get("security") or {})
    val = sec.get(key)
    if val is None:
        return default
    return bool(val)
