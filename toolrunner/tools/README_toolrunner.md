# JARVIS ToolRunner

Исполнитель инструментов для локального ассистента. Контроллер решает «чат или команда»,
а ToolRunner получает `{command, args}` и выполняет с безопасностью.

## Запуск

```bash
pip install -r toolrunner/requirements.txt
uvicorn toolrunner.app:app --host 127.0.0.1 --port 8011 --reload
