@FOR /F "delims=" %%A IN (token.txt) DO @SET MIKUBOT_DISCORD_KEY=%%A

@SET MIKUBOT_SETTINGS_FILE=settings.json
@py -m mikubot
