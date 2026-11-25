@echo off
setlocal
set "PS1=%~dp0tools\compress_obs_video.ps1"
if "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -SkipReview
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -SkipReview -InputPath "%~1"
)
echo.
pause
