$ErrorActionPreference = 'Stop'
$seamPython = 'C:\PROJECTS\ARIA\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $seamPython)) {
    throw 'The existing ARIA Python environment is unavailable. No packages were installed.'
}
& $seamPython (Join-Path $PSScriptRoot 'phase8_seam_demo.py')
