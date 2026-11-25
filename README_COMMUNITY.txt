========================================================================
  SWOOZ PITWALL - LIVE RACE ENGINEER & TEAM COMMS (Community Edition)
  Built by DOMSWOOZ for Backseat Champions (v0.88.2+ Telemetry API)
  Backseat Champions on Steam: https://store.steampowered.com/app/2174510/Backseat_Champions/
  Itch.io Page & Web Demo:    https://dom-swooz.itch.io/swooz-pitwall
  GitHub Source & Full Docs:   https://github.com/DOMSWOOZ/swooz-pitwall
========================================================================

QUICK START (WINDOWS):
1. Make sure Python 3.10+ is installed (https://python.org).
2. Double-click `start_pitwall.bat` (or run `enable_autolaunch.bat` once so
   PitWall opens automatically whenever Backseat Champions starts).
3. In Backseat Champions -> Settings -> Telemetry:
   - Check Enable API ON
   - Keep Listen IP / Port at `127.0.0.1` : `29771` and Player Input ON
   - Under Broadcast: check Player Data, Decision Events, and Driver Data
   - Keep Targets at `127.0.0.1` : `29770` (50 Hz)
   - (Optional) Race Results Endpoint: `http://127.0.0.1:8765/race-results`

QUICK START (STEAM DECK / LINUX):
1. Open Terminal / Konsole inside this folder and run:
   ./start_pitwall_steamos.sh
2. Open the printed `http://<LAN-IP>:8765` link on any phone, foldable, or tablet.

WHAT IS INCLUDED:
- Clean default layout (`HUD: CLEAN`) with 1-click toggle to `HUD: PRO` telemetry plots
- Responsive `AUTO` layout adapting to Desktop, Foldable/Tablet, and Phone screens
- Local race engineer radio with optional pit-radio EQ and Web Speech fallback on Linux
- Push-to-talk `[V]` voice triggers and optional Windows in-game hotkeys (F5-F8, Numpad)
- Extreme AI strategy weights, 5-slot Boost/Card editor, Crew Voice Studio, and OBS overlays

AI-assisted coding workflow under DOMSWOOZ visual design and race testing direction.
