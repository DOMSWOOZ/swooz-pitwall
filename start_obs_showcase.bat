@echo off
cd /d "%~dp0"
echo Starting SWOOZ PitWall Server (http://127.0.0.1:8765) + OBS Showcase...
start "" "%~dp0start_pitwall.bat"
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq obs64.exe" 2>NUL | find /I /N "obs64.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo.
    echo OBS Studio is already open!
    echo In OBS top menu bar, click: Scene Collection -^> Import -^> add:
    echo   "%~dp0share\SWOOZ_PitWall_OBS_Scene_Collection.json"
    echo then select "SWOOZ PitWall Showcase" under Scene Collection!
    pause
) else (
    start "" /d "C:\Program Files\obs-studio\bin\64bit" "C:\Program Files\obs-studio\bin\64bit\obs64.exe" --collection "SWOOZ PitWall Showcase" --scene "1 // SPLIT SHOWCASE: GAME + PITWALL"
)
