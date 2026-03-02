@pushd .
@cd /d %~dp0
@call .venv/Scripts/activate.bat

@if not defined MIKUBOT_DISCORD_KEY (
    @for /F "usebackq delims=" %%A in ("token.txt") do @set "MIKUBOT_DISCORD_KEY=%%A"
)

@if not defined MIKUBOT_SETTINGS_FILE (
    @set "MIKUBOT_SETTINGS_FILE=settings.json"
)

:loop
@python -m mikubot
@SET code=%ERRORLEVEL%

@IF %code%==39 (
    @echo Relaunching...
    @goto loop
) ELSE (
    @echo Stopping...
)

@popd
@exit /b %code%
