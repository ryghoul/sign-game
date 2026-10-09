$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$sourcePython = 'C:\Users\jeide\OneDrive\Documents\hand-track\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $localPython) { $gamePython = $localPython }
elseif (Test-Path -LiteralPath $sourcePython) { $gamePython = $sourcePython }
else { throw 'Install dependencies first: python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt' }
Start-Process 'http://127.0.0.1:8765'
& $gamePython server.py
