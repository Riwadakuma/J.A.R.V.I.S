from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import yaml

from .utils.normalize import normalize
from .utils.slots import extract_slots
from .utils.fuzzy import try_fuzzy_path
from .utils.safety import sandbox_ok, classify_write
from .llm import ask_ollama

@dataclass
class Cfg:
    mode: str = "hybrid"           # rule-only | hybrid
    llm_threshold: float = 0.75
    confirm_low_from: float = 0.50
    confirm_low_to: float = 0.74
    fallback_command: str = "files.list"
    workspace_root: str = "workspace"
    llm_enable: bool = True
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "tinyllama"

class Resolver:
    def __init__(self, rules_path: Path, user_lexicon_path: Optional[Path] = None):
        self.rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
        self.whitelist = set(self.rules.get("whitelist") or [])
        self._intents = self.rules.get("intents", [])
        self.user_lexicon = {}
        if user_lexicon_path and user_lexicon_path.exists():
            try:
                self.user_lexicon = json.loads(user_lexicon_path.read_text(encoding="utf-8"))
            except Exception:
                self.user_lexicon = {}

    def _apply_lexicon(self, t: str) -> str:
        aliases = (self.user_lexicon.get("phrases") or {})
        for k, v in aliases.items():
            if k in t:
                t = t.replace(k, v)
        return t

    def _required_slots_for(self, command: str) -> List[str]:
        for it in self._intents:
            if it.get("command") == command:
                return [s.replace("?", "") for s in (it.get("slots") or []) if not s.endswith("?")]
        return []

    def _match_intent(self, text: str) -> Dict[str, Any]:
        best = {"command": None, "score": 0.0, "why": []}
        for item in self._intents:
            kw = item.get("keywords", [])
            hits = sum(1 for k in kw if k in text)
            score = 0.4 if hits > 0 else 0.0
            if hits > 1:
                score += 0.1
            if score > best["score"]:
                best = {"command": item["command"], "score": score, "why": [f"keywords:{hits}"]}
        return best

    def _missing_required_slot(self, command: Optional[str], slots: Dict[str, Any]) -> bool:
        if not command:
            return True
        req = self._required_slots_for(command)
        return any(r not in slots or slots.get(r) in ("", None) for r in req)

    def _pack(
        self,
        trace_id: str,
        command: str,
        slots: Dict[str, Any],
        confidence: float,
        why: List[str],
        workspace: Path,
    ) -> Dict[str, Any]:
        args = dict(slots or {})
        explain = list(why or [])

        if "path" in args and not sandbox_ok(workspace, args["path"]):
            command = "files.list"
            args = {"mask": args.get("mask", "*")}
            confidence = 0.49
            explain.append("sandbox:violation")

        out = {
            "trace_id": trace_id,
            "command": command,
            "args": args,
            "confidence": confidence,
            "fallback_used": command == "files.list",
            "explain": explain,
            "write": classify_write(command),
        }
        return out

    def resolve(self, trace_id: str, text: str, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = Cfg(
            mode=config.get("mode", "hybrid"),
            llm_threshold=float(config.get("llm_threshold", 0.75)),
            workspace_root=context.get("cwd") or "workspace",
            llm_enable=bool(config.get("llm", {}).get("enable", True)),
            llm_base_url=config.get("llm", {}).get("base_url", "http://127.0.0.1:11434"),
            llm_model=config.get("llm", {}).get("model", "tinyllama"),
        )

        workspace = Path(cfg.workspace_root)

        # 1) нормализация и лексикон
        t = normalize(text)
        t = self._apply_lexicon(t)

        # 2) извлекаем слоты
        slots = extract_slots(t)

        # 3) правило-интент
        intent = self._match_intent(t)

        # 4) бонус за наличие ключевого слота path у команд, где он обязателен
        if intent.get("command") in ("files.create", "files.open", "files.read") and "path" in slots:
            intent["score"] += 0.15
            intent["why"].append("slot:path")

        # 5) общий бонус за любые найденные слоты
        if slots:
            intent["score"] += 0.2
            intent["why"].append("slots:yes")

        # 6) fuzzy: для create/append разрешаем новый путь (файл может не существовать)
        allow_new = intent.get("command") in ("files.create", "files.append")
        if "path" in slots:
            slots = try_fuzzy_path(workspace, slots, allow_new=allow_new)
            intent["score"] += 0.15
            intent["why"].append("fuzzy:path")

        # 7) LLM при неоднозначности или если не хватает обязательных слотов
        ambiguous = (
            0.50 <= intent["score"] < cfg.llm_threshold
        ) or self._missing_required_slot(intent.get("command"), slots)
        if cfg.mode == "hybrid" and cfg.llm_enable and ambiguous:
            try:
                llm_ans = ask_ollama(t, model=cfg.llm_model, base_url=cfg.llm_base_url)
                if isinstance(llm_ans, dict):
                    cmd = llm_ans.get("command")
                    args = llm_ans.get("args") or {}
                    if cmd in self.whitelist:
                        intent["command"] = cmd or intent["command"]
                        for k, v in args.items():
                            slots.setdefault(k, v)
                        intent["score"] = max(intent["score"], cfg.llm_threshold)
                        intent["why"].append("llm:disambiguation")
            except Exception:
                intent["why"].append("llm:fail")

        # 8) fallback, если так и не распознали
        if not intent.get("command"):
            return self._pack(
                trace_id,
                cfg.fallback_command,
                {"mask": slots.get("mask", "*")},
                0.49,
                intent["why"],
                workspace,
            )

        conf = min(0.99, intent["score"])
        return self._pack(trace_id, intent["command"], slots, conf, intent["why"], workspace)

