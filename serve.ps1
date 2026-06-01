# Same as START_APP.bat — starts Flask; Python opens the browser when the port is ready.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and (Get-Command py -ErrorAction SilentlyContinue)) {
    py -3 -m pip install -r requirements.txt -q
    py -3 app_server.py
} else {
    python -m pip install -r requirements.txt -q
    python app_server.py
}
