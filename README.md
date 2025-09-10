# JARVIS (local assistant)

Модульный локальный ассистент: **controller** (FastAPI), **toolrunner** (исполнительно-командный сервис), **interaction/resolver** (интенты и стиль), **tools_cli** (CLI обёртка).

## Быстрый старт (Windows)

```powershell
# 1) создать и активировать окружение
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# 2) установить зависимости
pip install -r requirements.txt -r requirements-dev.txt

# 3) скопировать конфиги
Copy-Item .\controller\config.yaml .\controller\config.local.yaml -ErrorAction SilentlyContinue
Copy-Item .\toolrunner\config.yaml .\toolrunner\config.local.yaml -ErrorAction SilentlyContinue
```

### Запуск сервисов
```powershell
# Controller (8010)
uvicorn controller.app:app --host 127.0.0.1 --port 8010 --reload

# ToolRunner (8011)
uvicorn toolrunner.app:app --host 127.0.0.1 --port 8011 --reload

# Resolver (8020)
uvicorn interaction.resolver.main:app --host 127.0.0.1 --port 8020 --reload
```

### Структура
- `controller/` — REST API, интеграция с резолвером и LLM
- `toolrunner/` — файловые/системные инструменты
- `interaction/resolver/` — правила, нормализация, слоты, LLM-поддержка
- `tools_cli/` — PowerShell CLI (`tools_cli/jarvis.ps1`), HTTP-клиент
- `workspace/`, `logs/` — локальные артефакты (пустые)

### Конфигурация
`controller/config.yaml` и `toolrunner/config.yaml` используют относительные пути и localhost.
Если нужны абсолютные пути, правь секцию `paths.workspace` или добавь `*.local.yaml` и читай при старте.

CLI (`tools_cli/jarvis_cli.py`) по умолчанию использует `tools_cli/cli_config.yaml`.
Можно указать другой конфиг с помощью опции `--config <file>`.

### Tests
Тесты лежат в каталоге `tests/` и покрывают сервисы `controller`, `toolrunner`, `interaction/resolver` и `tools_cli`.

Требования: Python 3.10+ и dev-зависимости (`pytest`).

```bash
pip install -r requirements.txt  # базовые зависимости
pip install pytest               # dev-зависимости
pytest
```

Пример вывода:
```
8 passed in 1.14s
```

### Лицензия
MIT
