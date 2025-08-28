from pathlib import Path
from typing import Dict, Optional, Tuple
try:
    from Levenshtein import ratio as _lev_ratio
except Exception:
    # запасной вариант без внешних зависимостей
    import difflib
    def _lev_ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

# qwerty→йцукен для частого кейса
_KEYBOARD_MAP = str.maketrans(
    "qwertyuiop[]asdfghjkl;'zxcvbnm,.",
    "йцукенгшщзхъфывапролджэячсмитьбю"
)

def _best_candidate(workspace: Path, guess: str):
    guess_lower = guess.lower()
    best = (0.0, None)
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        sc = _lev_ratio(name, guess_lower)
        if sc > best[0]:
            best = (sc, p)
    return best[1]

def _rel_if_inside(workspace: Path, p: Path) -> Optional[str]:
    ws = workspace.resolve()
    try:
        rp = p.resolve().relative_to(ws)
        return str(rp)
    except Exception:
        return None

def try_fuzzy_path(workspace: Path, slots: Dict[str, str], *, allow_new: bool = False) -> Dict[str, str]:
    """
    Если allow_new=True (для create/append), не требуем существования,
    просто нормализуем относительный путь, проверяя что он внутри workspace.
    """
    out = dict(slots)
    g = slots.get("path")
    if not g:
        return out

    ws = workspace.resolve()

    # прямое попадание
    direct = (workspace / g).resolve()
    rel = _rel_if_inside(workspace, direct)
    if rel:
        if direct.exists():
            out["path"] = rel
            return out
        if allow_new:
            # файла нет, но путь валиден и внутри workspace — оставляем как есть
            out["path"] = rel
            return out

    # перевод раскладки
    alt = g.translate(_KEYBOARD_MAP)
    guess = alt if len(alt) >= 3 else g

    cand = _best_candidate(workspace, guess)
    if cand:
        rel2 = _rel_if_inside(workspace, cand)
        if rel2:
            out["path"] = rel2
            return out

    # если ничего не нашли, но allow_new разрешает — вернем нормализованный относительный
    if allow_new and rel:
        out["path"] = rel
    elif allow_new and not rel:
        # попробуем интерпретировать как относительный без resolve
        out["path"] = g.replace("\\", "/").lstrip("/")

    return out
