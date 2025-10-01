@echo off
setlocal

REM путь к PowerShell 7
set "PWSH=C:\Program Files\PowerShell\7-previewpwsh.exe"

REM корень проекта
set "ROOT=%~dp0"
set "VENV=%ROOT%venv\Scripts\Activate.ps1"

REM Controller (8010)
start "JARVIS Controller (8010)" "%PWSH%" -NoExit -Command ^
 "Set-Location '%ROOT%'; . '%VENV%'; python -m uvicorn core.controller.app:app --app-dir . --host 127.0.0.1 --port 8010 --reload --log-level debug"

REM ToolRunner (8011)
start "JARVIS ToolRunner (8011)" "%PWSH%" -NoExit -Command ^
 "Set-Location '%ROOT%'; . '%VENV%'; python -m uvicorn toolrunner.app:app --app-dir toolrunner --host 127.0.0.1 --port 8011 --reload --log-level debug"

echo Запущены два окна: Controller (8010) и ToolRunner (8011).
pause
