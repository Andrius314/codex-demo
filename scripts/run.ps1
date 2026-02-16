$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "1) Paleidziu testus..."
python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n`pytest` nerastas arba testai nepraejo."
    Write-Host "Paleisk: python -m pip install pytest"
    exit $LASTEXITCODE
}

Write-Host "`n2) Paleidziu programa..."
@"
Nerijus
"@ | python .\app.py
