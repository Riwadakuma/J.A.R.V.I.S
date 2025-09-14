from pathlib import Path
import os
import subprocess
from typing import Any, Dict, List

from ..security import workspace_path, _cfg_workspace, max_read_bytes, feature_enabled

# Внутренний триммер для масок/путей (на случай, если нормализация args не сработала раньше)
def _clean_str(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1]
    return s

def cmd_files_list(args: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    """
    Рекурсивно ищет файлы по маске внутри workspace и возвращает относительные пути.
    Примеры масок: "*.txt", "notes/*.md", "**/*.py"
    """
    mask = _clean_str(args.get("mask", "*") or "*")
    if not mask:
        return []
    base = _cfg_workspace(config)
    # rglob поддерживает и **, и простые маски
    return sorted(
        str(p.relative_to(base))
        for p in base.rglob(mask)
        if p.is_file()
    )

def cmd_files_read(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    rel = _clean_str(args.get("path", ""))
    p = workspace_path(rel, config)
    limit = max_read_bytes(config)
    if p.exists() and p.is_file():
        if p.stat().st_size > limit:
            raise ValueError("E_FILE_TOO_LARGE")
        return p.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("E_NOT_FOUND")

def cmd_files_create(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    rel = _clean_str(args.get("path", ""))
    content = args.get("content") or ""
    p = workspace_path(rel, config)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content), encoding="utf-8")
    return "OK"

def cmd_files_append(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    rel = _clean_str(args.get("path", ""))
    content = args.get("content") or ""
    p = workspace_path(rel, config)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(str(content))
    return "OK"

def cmd_files_open(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    if not feature_enabled(config, "allow_open", True):
        raise ValueError("E_FORBIDDEN")
    rel = _clean_str(args.get("path", ""))
    p = workspace_path(rel, config)
    if not (p.exists() and p.is_file()):
        raise ValueError("E_NOT_FOUND")
    # Windows-only
    try:
        os.startfile(str(p))  # type: ignore[attr-defined]
    except AttributeError:
        raise ValueError("E_UNSUPPORTED_OS")
    return "OK"

def cmd_files_reveal(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    if not feature_enabled(config, "allow_reveal", True):
        raise ValueError("E_FORBIDDEN")
    rel = _clean_str(args.get("path", ""))
    p = workspace_path(rel, config)
    if not (p.exists() and p.is_file()):
        raise ValueError("E_NOT_FOUND")
    # Windows Explorer select
    try:
        subprocess.Popen(["explorer", "/select,", str(p)])
    except FileNotFoundError:
        raise ValueError("E_UNSUPPORTED_OS")
    return "OK"

def cmd_files_shortcut(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    if not feature_enabled(config, "allow_shortcut", True):
        raise ValueError("E_FORBIDDEN")
    rel = _clean_str(args.get("path", ""))
    p = workspace_path(rel, config)
    # PowerShell shortcut without external deps
    ps = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$Env:USERPROFILE\\Desktop\\{p.name}.lnk")
$Shortcut.TargetPath = "{str(p)}"
$Shortcut.Save()
'''
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    except FileNotFoundError:
        raise ValueError("E_UNSUPPORTED_OS")
    return "OK"
