@echo off
setlocal
set "PRJ=%~dp0.."
set "VENV=%PRJ%\.venv\Scripts\Activate.ps1"
if exist "%VENV%" pwsh -NoLogo -Command ". '%VENV%'"

start "Controller (8010)" pwsh -NoExit -Command "Set-Location '%PRJ%'; uvicorn controller.app:app --host 127.0.0.1 --port 8010 --reload"
start "ToolRunner (8011)" pwsh -NoExit -Command "Set-Location '%PRJ%'; uvicorn toolrunner.app:app --host 127.0.0.1 --port 8011 --reload"
start "Resolver (8020)"  pwsh -NoExit -Command "Set-Location '%PRJ%'; uvicorn interaction.resolver.main:app --host 127.0.0.1 --port 8020 --reload"
