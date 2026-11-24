@echo off
cd /d "%~dp0"
for /f "delims=" %%P in ('python -c "import os,sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYTHONW=%%P"
start "" "%PYTHONW%" "%~dp0pitwall_companion.pyw" --launch
