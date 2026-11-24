@echo off
title Backseat Champions - Share Live Pit Wall to iPhone (5G / Anywhere)
cd /d "%~dp0"
echo =====================================================================
echo  BACKSEAT CHAMPIONS - INSTANT IPHONE PUBLIC HTTPS LINK
echo  1. Make sure server.py (or start_pitwall.bat) is running on 8765.
echo  2. Copy the https://*.lhr.life link printed below and text it
echo     to your friend's iPhone (or have him scan the QR code)!
echo =====================================================================
echo.
ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8765 nokey@localhost.run
pause
