param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $Args
)

# Найти корень скрипта и venv
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root "..\venv\Scripts\Activate.ps1"
$Py   = "python"

# Активировать venv, если есть
if (Test-Path $Venv) {
  . $Venv
}

# Запуск jarvis_cli.py с пробросом аргументов
$Script = Join-Path $Root "jarvis_cli.py"
& $Py $Script @Args
exit $LASTEXITCODE
