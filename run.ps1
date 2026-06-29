Push-Location $PSScriptRoot
. .\.venv\Scripts\Activate.ps1

if (-not $env:MIKUBOT_DISCORD_KEY) {
    $env:MIKUBOT_DISCORD_KEY = Get-Content -Raw token.txt
}

if (-not $env:MIKUBOT_SETTINGS_FILE) {
    $env:MIKUBOT_SETTINGS_FILE = "settings.json"
}

do {
    uv run mikubot run
    $code = $LASTEXITCODE

    if ($code -eq 39) {
        Write-Host "Relaunching..."
    } else {
        Write-Host "Stopping..."
    }
} while ($code -eq 39)

Pop-Location
exit $code
