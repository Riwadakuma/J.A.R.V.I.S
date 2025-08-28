import re

WAKE_WORDS = ["джарвис", "jarvis", "жарвис"]
FILLERS = ["надо бы", "пожалуйста", "плиз", "будь добр", "давай", "можешь", "пожалста"]

QUOTES_MAP = {
    "“": '"', "”": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'",
}

def _replace_quotes(t: str) -> str:
    for k, v in QUOTES_MAP.items():
        t = t.replace(k, v)
    return t

def normalize(text: str) -> str:
    t = text.strip().lower()
    t = _replace_quotes(t)
    # убрать обращение и вежливости
    for w in WAKE_WORDS + FILLERS:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
    # нормализовать пробелы
    t = re.sub(r"\s+", " ", t).strip()
    return t
