@echo off
title SWOOZ PitWall - Deploy Live Web Demo to Vercel
cd /d "%~dp0static"
echo =====================================================================
echo  SWOOZ PITWALL — 1-CLICK VERCEL WEB DEMO UPDATER
echo  Deploys static/ straight to your live https://backseat-pitwall.vercel.app/
echo =====================================================================
echo.
call npx vercel --prod --yes
echo.
echo [DONE] Your live Vercel Web Demo is now synced with SWOOZ PitWall Pro!
pause
