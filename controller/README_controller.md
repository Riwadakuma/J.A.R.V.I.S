# JARVIS Controller

Мини‑сервис маршрутизации. Решает: «чат или команда».
- Если чат: вызывает Ollama и возвращает текст.
- Если команда: по умолчанию возвращает `{type:"command", command, args}`.
- Если `controller.proxy_commands=true` в `config.yaml`, то проксирует команду в ToolRunner и возвращает `ok/result/error`.

## Запуск

```bash
pip install -r controller/requirements.txt
uvicorn controller.app:app --host 127.0.0.1 --port 8010 --reload
