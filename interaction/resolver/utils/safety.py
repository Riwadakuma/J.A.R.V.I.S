from pathlib import Path

def sandbox_ok(workspace: Path, rel: str) -> bool:
    try:
        p = (workspace / (rel or "")).resolve()
        p.relative_to(workspace.resolve())
        return True
    except Exception:
        return False

def classify_write(command: str) -> bool:
    return command in {"files.create", "files.append", "system.config_set"}
