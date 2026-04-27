$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir 'venv\Scripts\python.exe'

if (-not (Test-Path $PythonExe)) {
    $PythonExe = Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
}

if (-not $PythonExe) {
    $PythonExe = Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
}

if (-not $PythonExe) {
    throw 'Python was not found. Install Python or create the project virtual environment first.'
}

& $PythonExe (Join-Path $ScriptDir 'cli_reporter.py') @args
exit $LASTEXITCODE