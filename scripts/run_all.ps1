param(
  [int]$ControllerPort = 8010,
  [int]$ToolPort = 8011,
  [int]$ResolverPort = 8020
)
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PRJ  = Split-Path -Parent $ROOT
$VENV = Join-Path $PRJ ".venv\Scripts\Activate.ps1"
if (Test-Path $VENV) { . $VENV }

Start-Process pwsh -ArgumentList "-NoExit","-Command","Set-Location '$PRJ'; uvicorn controller.app:app --host 127.0.0.1 --port $ControllerPort --reload"
Start-Process pwsh -ArgumentList "-NoExit","-Command","Set-Location '$PRJ'; uvicorn toolrunner.app:app --host 127.0.0.1 --port $ToolPort --reload"
Start-Process pwsh -ArgumentList "-NoExit","-Command","Set-Location '$PRJ'; uvicorn interaction.resolver.main:app --host 127.0.0.1 --port $ResolverPort --reload"
