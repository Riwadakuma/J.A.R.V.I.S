import sys, json, requests

URL = "http://127.0.0.1:8010/chat"

def ask(t: str) -> str:
    r = requests.post(URL, json={"text": t}, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("text") or f"{data.get('command')} {data.get('args')}"

def main():
    print("JARVIS CLI. Введите текст. 'exit' для выхода.")
    while True:
        try:
            q = input("> ").strip()
        except EOFError:
            break
        if not q or q.lower() in ("exit","quit"): break
        try:
            print(ask(q))
        except Exception as e:
            print("Ошибка:", e)

if __name__ == "__main__":
    main()
