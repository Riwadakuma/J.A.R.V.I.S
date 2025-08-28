from fastapi import FastAPI
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any
from .pipeline import Resolver

app = FastAPI(title="Interaction Resolver", version="0.1.0")

_rules = Resolver(
    rules_path=Path(__file__).parent / "rules" / "rules.yaml",
    user_lexicon_path=Path.cwd() / "data" / "learning" / "user_lexicon.json"
)

class ResolveIn(BaseModel):
    trace_id: str
    text: str
    context: Dict[str, Any] = {}
    constraints: Dict[str, Any] = {}
    config: Dict[str, Any] = {}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/ready")
def ready():
    return {"ready": True}

@app.post("/resolve")
def resolve(inp: ResolveIn):
    out = _rules.resolve(inp.trace_id, inp.text, inp.context, inp.config)
    wl = set(inp.constraints.get("whitelist") or [])
    if wl and out["command"] not in wl:
        out["command"] = "files.list"
        out["args"] = {"mask": out["args"].get("mask", "*")}
        out["confidence"] = 0.49
        out["fallback_used"] = True
        out["explain"].append("whitelist:forced_fallback")
    return out
