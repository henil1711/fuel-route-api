param([string]$PythonPath = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $PythonPath) {
    $projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $preparedPython = Join-Path $PSScriptRoot '..\..\work\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $projectPython) { $PythonPath = $projectPython }
    elseif (Test-Path -LiteralPath $preparedPython) { $PythonPath = $preparedPython }
    else { throw 'Complete the README setup first, or pass -PythonPath pointing to a configured Python environment.' }
}
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& $PythonPath manage.py runserver 127.0.0.1:8000
