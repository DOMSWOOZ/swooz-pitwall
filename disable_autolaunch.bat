@echo off
title SWOOZ PitWall - Disable Auto-Popup
cd /d "%~dp0"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "BackseatPitWallWatcher" /f >nul 2>&1
python "%~dp0pitwall_companion.pyw" --stop
echo [OK] SWOOZ PitWall Auto-Popup disabled and background watcher stopped.
pause
