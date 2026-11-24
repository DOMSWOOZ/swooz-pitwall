"""Build SWOOZ PitWall Community Share Bundles:
1. `share/Backseat_PitWall_SingleFile.html` — Self-contained interactive web preview
2. `share/Backseat_PitWall_Web.zip` — Static web deployment archive (Vercel / Netlify / iPhone)
3. `share/SWOOZ_PitWall_Community_Edition.zip` — Full Ready-to-Share Itch.io PWYW Community Release zip!
"""
from __future__ import annotations

import base64
import os
import zipfile

ROOT = r"C:\Users\souls\.gemini\antigravity\scratch\backseat-pitwall"
STATIC = os.path.join(ROOT, "static")
SHARE = os.path.join(ROOT, "share")
os.makedirs(SHARE, exist_ok=True)


def build_single_file_html() -> None:
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    css = open(os.path.join(STATIC, "styles.css"), encoding="utf-8").read()
    sim_js = open(os.path.join(STATIC, "standalone_sim.js"), encoding="utf-8").read()
    app_js = open(os.path.join(STATIC, "app.js"), encoding="utf-8").read()
    logo_path = os.path.join(STATIC, "swooz_logo.png")
    if os.path.isfile(logo_path):
        b64_logo = base64.b64encode(open(logo_path, "rb").read()).decode("ascii")
        html = html.replace('./swooz_logo.png', f"data:image/png;base64,{b64_logo}")

    html = html.replace('<link rel="stylesheet" href="./styles.css" />', f"<style>{css}</style>")
    html = html.replace('<script src="./standalone_sim.js"></script>', f"<script>{sim_js}</script>")
    html = html.replace('<script src="./app.js"></script>', f"<script>{app_js}</script>")
    out_path = os.path.join(SHARE, "Backseat_PitWall_SingleFile.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Built {out_path} ({os.path.getsize(out_path) // 1024} KB)")


def build_web_zip() -> None:
    out_zip = os.path.join(SHARE, "Backseat_PitWall_Web.zip")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root_dir, _, files in os.walk(STATIC):
            for fn in files:
                full = os.path.join(root_dir, fn)
                rel = os.path.relpath(full, STATIC)
                zf.write(full, rel)
    print(f"Built {out_zip} ({os.path.getsize(out_zip) // 1024} KB)")


def build_community_itch_zip() -> None:
    readme_txt = """========================================================================
  SWOOZ PITWALL — LIVE RACE ENGINEER & TEAM COMMS (Community Edition)
  Created by Dom_Swooz for Backseat Champions (v0.88.2+ Telemetry API)
  Backseat Champions on Steam: https://store.steampowered.com/app/2174510/Backseat_Champions/
  Itch.io Page & Live Demo:    https://dom-swooz.itch.io/swooz-pitwall
  GitHub Source & Full Docs:   https://github.com/DOMSWOOZ/swooz-pitwall
========================================================================

QUICK START (ZERO SETUP):
1. Make sure Python 3.10+ is installed on Windows (https://python.org).
2. Double-click `start_pitwall.bat` (or run `enable_autolaunch.bat` once so
   SWOOZ PitWall pops up automatically whenever Backseat Champions starts!).
3. In Backseat Champions -> Settings -> Telemetry:
   - Enable Telemetry Out (`127.0.0.1`, Port `29770`)
   - Enable Player/Driver Commands (`127.0.0.1`, Port `29771`)
   - (Optional) Race Results URL: `http://127.0.0.1:8765/race-results`

WHAT'S INSIDE:
- Live Zero-Lag Pit-Radio Comms (~45ms local WinRT synthesis + 90s V10 FX + 60 FPS Dual-Channel Oscilloscope)
- Hands-Free "Read-What-You-See" Voice Commands (Press [V] and read ANY button on screen aloud!)
- Zero-Alt-Tab Mode: In-Game Hotkeys (F5/MB5=Push, F6/MB4=Box, F7=Auto Card, F8=Sitrep, Num1-3=Pick Card, Num9=Mini HUD) + Instant Game Refocus!
- Extreme AI 80.7K Sync + 5-Slot Push Mode Lab & 5-Slot Card Build Strategy Lab (Customize or import from any P1 `.results.json` race!)
- Custom Crew Voice Studio: Choose from 11 regional engineers, or record & share your own `.zip` voice packs!
"""
    readme_path = os.path.join(ROOT, "README_COMMUNITY.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_txt)

    out_zip = os.path.join(SHARE, "SWOOZ_PitWall_Community_Edition.zip")
    core_files = [
        "bc_api.py",
        "card_strategist.py",
        "loadout_manager.py",
        "swooz_persona.py",
        "engine.py",
        "simulator.py",
        "server.py",
        "pitwall_companion.pyw",
        "start_pitwall.bat",
        "enable_autolaunch.bat",
        "disable_autolaunch.bat",
        "swooz_pitwall.ico",
        "pitwall.ico",
        "README_COMMUNITY.txt",
    ]
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fn in core_files:
            p = os.path.join(ROOT, fn)
            if os.path.isfile(p):
                zf.write(p, f"SWOOZ-PitWall/{fn}")
        for root_dir, _, files in os.walk(STATIC):
            for fn in files:
                full = os.path.join(root_dir, fn)
                rel = os.path.relpath(full, ROOT)
                zf.write(full, f"SWOOZ-PitWall/{rel}")
    print(f"Built {out_zip} ({os.path.getsize(out_zip) // 1024} KB)")


if __name__ == "__main__":
    build_single_file_html()
    build_web_zip()
    build_community_itch_zip()
