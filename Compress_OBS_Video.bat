@echo off
title SWOOZ PitWall - Compress OBS Video (YouTube Review + Discord 10MB)
cd /d "%~dp0"
set "INPUT=%~1"
if "%INPUT%"=="" (
    echo Auto-selecting newest MP4 in "%USERPROFILE%\Videos"...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\compress_obs_video.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\compress_obs_video.ps1" -InputPath "%INPUT%"
)
echo.
echo Done! Files saved next to your recording:
echo   *_review_under90mb.mp4  (Full-length share/review copy under 95 MB)
echo   *_discord_under10mb.mp4 (42s highlight clip ready for Discord 10 MB free upload)
if "%~2"=="" pause
