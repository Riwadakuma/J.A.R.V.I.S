import re
from typing import Dict

# базовые паттерны
_RE_IN_QUOTES = re.compile(r'"([^"]+)"')
_RE_EXT_TOKEN = re.compile(r"\b([\w\-\./\\]+?\.[a-z0-9]{1,8})\b", re.IGNORECASE)

# команды, после которых часто сразу идет путь
_AFTER_VERB_PATH = [
    r"(?:создай(?:\s+файл)?)",
    r"(?:создать(?:\s+файл)?)",
    r"(?:допиши(?:\s+в)?)",
    r"(?:прочитай|покажи\s+содержимое|выведи)",
    r"(?:открой|open|запусти)",
    r"(?:покажи|показать\s+в\s+проводнике|show\s+in\s+explorer|открой\s+папку)",
]

def _extract_path_after_verb(text: str) -> str | None:
    """
    Ловим первый токен-путь после глагола: поддерживаем слова с точкой/слешами.
    Примеры: 'создай файл notes/todo.txt', 'открой plan.md'
    """
    pat = re.compile(rf"(?:{'|'.join(_AFTER_VERB_PATH)})\s+([^\s\"']+)", re.IGNORECASE)
    m = pat.search(text)
    if m:
        return m.group(1).strip()
    return None

def extract_slots(text: str) -> Dict[str, str]:
    slots: Dict[str, str] = {}

    # 1) path в кавычках — приоритетно
    m = _RE_IN_QUOTES.search(text)
    if m:
        slots["path"] = m.group(1).strip()

    # 2) если нет — попробуем после глагола
    if "path" not in slots:
        p2 = _extract_path_after_verb(text)
        if p2:
            slots["path"] = p2

    # 3) если всё ещё нет — возьмем любой токен с расширением (осторожно)
    if "path" not in slots:
        m3 = _RE_EXT_TOKEN.search(text)
        if m3:
            slots["path"] = m3.group(1).strip()

    # mask: *.py или "на питоне" → *.py
    if "на питоне" in text or "python" in text:
        slots["mask"] = "*.py"
    else:
        mm = re.search(r"\*\.[a-z0-9]+", text, re.IGNORECASE)
        if mm:
            slots["mask"] = mm.group(0)

    # конфиг: конфиг установить <ключ> <значение>
    mc = re.search(r"конфиг установить\s+(\S+)\s+(.+)", text)
    if mc:
        slots["key"], slots["value"] = mc.group(1), mc.group(2).strip().strip('"').strip("'")

    # текст для дописывания/создания: после "допиши" или "с содержимым"
    mt = re.search(r"(?:допиши|с содержимым)\s+(.+)$", text)
    if mt and "text" not in slots:
        slots["text"] = mt.group(1).strip().strip('"').strip("'")

    return slots
