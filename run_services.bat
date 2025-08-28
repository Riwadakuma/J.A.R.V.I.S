@echo off
setlocal

REM путь к PowerShell 7 (если другой - поправь)
set "PWSH=C:\Program Files\PowerShell\7-preview\pwsh.exe"

REM корень проекта
set "ROOT=%~dp0"
set "VENV=%ROOT%venv\Scripts\Activate.ps1"

REM Controller (8010)
start "JARVIS Controller (8010)" "%PWSH%" -NoExit -Command ^
 "Set-Location '%ROOT%'; . '%VENV%'; python -m uvicorn controller.app:app --app-dir controller --host 127.0.0.1 --port 8010 --reload --log-level debug"

REM ToolRunner (8011)
start "JARVIS ToolRunner (8011)" "%PWSH%" -NoExit -Command ^
 "Set-Location '%ROOT%'; . '%VENV%'; python -m uvicorn toolrunner.app:app --app-dir toolrunner --host 127.0.0.1 --port 8011 --reload --log-level debug"

REM Resolver (8020)
start "JARVIS Resolver (8020)" "%PWSH%" -NoExit -Command ^
 "Set-Location '%ROOT%'; . '%VENV%'; python -m uvicorn interaction.resolver.main:app --app-dir interaction/resolver --host 127.0.0.1 --port 8020 --reload --log-level debug"

echo Запущены окна: Controller (8010), ToolRunner (8011), Resolver (8020).
pause
