from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
import yaml
from pathlib import Path

from .registry import REGISTRY, ALLOWED_COMMANDS
from .security import normalize_args, ensure_allowed, shared_token_ok

# ---- config ----
CFG_PATH = Path(__file__).parent / "config.yaml"
_config = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) if CFG_PATH.exists() else {}

class ExecIn(BaseModel):
    command: str
    args: Dict[str, Any] = {}

class ExecOut(BaseModel):
    ok: bool
    result: Optional[Any] = None
    error: Optional[str] = None

app = FastAPI(title="JARVIS ToolRunner")

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "tools": sorted(list(ALLOWED_COMMANDS)),
        "workspace": str(Path(_config.get("paths", {}).get("workspace", "../workspace")).resolve()),
    }

@app.post("/execute", response_model=ExecOut)
def execute(req: Request, payload: ExecIn):
    # optional shared token
    token_from_cfg = (_config.get("security") or {}).get("shared_token") or ""
    if token_from_cfg and not shared_token_ok(req.headers.get("X-Jarvis-Token"), token_from_cfg):
        raise HTTPException(status_code=401, detail="E_UNAUTHORIZED")

    ensure_allowed(payload.command)
    handler = REGISTRY.get(payload.command)
    if not handler:
        raise HTTPException(status_code=400, detail="E_UNKNOWN_COMMAND")
    try:
        args = normalize_args(payload.args)
        result = handler(args, _config)  # all handlers accept (args, config)
        return ExecOut(ok=True, result=result)
    except HTTPException:
        raise
    except ValueError as e:
        # business errors should raise ValueError("E_CODE")
        msg = str(e)
        if msg.startswith("E_"):
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=f"E_RUNTIME:{msg}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"E_RUNTIME:{e}")
