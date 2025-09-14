import uuid
import httpx
from pathlib import Path
from typing import List

class ResolverAdapter:
    def __init__(self, base_url: str, whitelist: List[str], workspace_root: str,
                 mode: str = "hybrid", llm_threshold: float = 0.75, timeout: float = 2.5,
                 llm_enable: bool = True, llm_base_url: str = "http://127.0.0.1:11434", llm_model: str = "tinyllama"):
        self.base_url = base_url.rstrip("/")
        self.whitelist = whitelist
        self.workspace_root = str(Path(workspace_root))
        self.mode = mode
        self.llm_threshold = llm_threshold
        self.timeout = timeout
        self.llm_enable = llm_enable
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

    def resolve(self, text: str, locale: str = "ru-RU"):
        trace_id = str(uuid.uuid4())
        payload = {
            "trace_id": trace_id,
            "text": text,
            "context": {"cwd": self.workspace_root, "locale": locale},
            "constraints": {"whitelist": self.whitelist},
            "config": {
                "mode": self.mode,
                "llm_threshold": self.llm_threshold,
                "llm": {
                    "enable": self.llm_enable,
                    "base_url": self.llm_base_url,
                    "model": self.llm_model
                }
            }
        }
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base_url}/resolve", json=payload)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError:
            return None
