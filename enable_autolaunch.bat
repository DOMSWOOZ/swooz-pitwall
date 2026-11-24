@echo off
title SWOOZ PitWall - Enable Auto-Popup With Steam
cd /d "%~dp0"
for /f "delims=" %%P in ('python -c "import os,sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYTHONW=%%P"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "BackseatPitWallWatcher" /t REG_SZ /d "\"%PYTHONW%\" \"%~dp0pitwall_companion.pyw\" --watch" /f >nul
start "" "%PYTHONW%" "%~dp0pitwall_companion.pyw" --watch
echo [OK] Auto-Popup enabled! SWOOZ PitWall will pop up automatically whenever Backseat Champions starts from Steam or Desktop.
pause
