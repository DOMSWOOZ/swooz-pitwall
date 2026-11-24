"""Multi-Persona Custom Crew Voice Studio & Ad-Lib Trigger Matcher for SWOOZ PitWall.

Ships with zero pre-bundled personal recordings out-of-the-box, while giving every player
in the Backseat Champions community a turnkey Crew Voice Studio to:
1. Create unlimited custom voice personas (`+ NEW PERSONA`) with custom WinRT fallback timbre (`Mark`/`Zira`/`David`),
   SSML pitch/rate contour, and Web Audio formant detune + presence EQ.
2. Record or freestyle their own custom spin on the 29 Pit-Wall race event triggers (`24kHz` RIFF WAV).
3. Type/save their own custom spoken line per trigger (`custom_lines` in `persona.json`) so `#radio-feed`
   transcripts and speaker-echo filtering match whatever slang or callout they actually recorded!
4. Export & Import `.zip` Persona Voice Packs in 1 click to share on Discord / Itch.io!
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONAS_DIR = os.path.join(ROOT_DIR, "personas")

DEFAULT_PERSONA_ID = "custom-crew"

# 29-Slot Core F1 Pit-Wall Trigger Bank (~2.5 minutes total to record; prompts are suggested vibe guides!)
SWOOZ_SCRIPT_BANK: List[Dict[str, str]] = [
    # --- A. Comms & Race Launch ---
    {
        "id": "radio_check",
        "cat": "COMMS & LAUNCH",
        "title": "Radio Check / Test Voice",
        "trigger_when": "Fires when clicking TEST VOICE or locking onto a live session",
        "script": "Pit wall copy — telemetry locked, loud and clear, send it!",
    },
    {
        "id": "lights_out",
        "cat": "COMMS & LAUNCH",
        "title": "Start Race / Lights Out",
        "trigger_when": "Fires when saying 'Start Race' / 'Lights Out' or launching off the grid",
        "script": "Copy that — holding grid launch! Lights out and away we go!",
    },
    {
        "id": "checkered",
        "cat": "COMMS & LAUNCH",
        "title": "Checkered Flag",
        "trigger_when": "Fires immediately when crossing the line on the final lap",
        "script": "Checkered flag! Get in there, mega drive, bring her home!",
    },
    {
        "id": "purple_lap",
        "cat": "COMMS & LAUNCH",
        "title": "Fastest Lap (Purple)",
        "trigger_when": "Fires whenever you set the fastest overall lap of the race",
        "script": "Purple lap! Fastest car on circuit, keep cooking!",
    },
    {
        "id": "final_lap",
        "cat": "COMMS & LAUNCH",
        "title": "Final Lap",
        "trigger_when": "Fires when starting the final lap of the race",
        "script": "Final lap! Empty the tank all the way to the line!",
    },
    # --- B. Pit Lane & Tire Milestones ---
    {
        "id": "box_confirm",
        "cat": "PIT & TIRES",
        "title": "Box Confirmed",
        "trigger_when": "Fires when calling 'Box Box' or Auto-Pit Guard arms your pit stop",
        "script": "Copy, box this lap confirmed — pit crew standing by!",
    },
    {
        "id": "stay_out",
        "cat": "PIT & TIRES",
        "title": "Stay Out / Cancel Pit",
        "trigger_when": "Fires when calling 'Stay Out' or cancelling a planned stop",
        "script": "Copy that, stay out, stay out — keep pushing!",
    },
    {
        "id": "pit_in",
        "cat": "PIT & TIRES",
        "title": "Entering Pit Lane",
        "trigger_when": "Fires as your car crosses the pit entry line",
        "script": "In the pit lane — limiter active, hit your marks.",
    },
    {
        "id": "pit_exit",
        "cat": "PIT & TIRES",
        "title": "Pit Exit Clear",
        "trigger_when": "Fires on pit exit with fresh 100% tires",
        "script": "Pit exit clear! Fresh rubber at one hundred percent — push now!",
    },
    {
        "id": "tires_75",
        "cat": "PIT & TIRES",
        "title": "Tires 75%",
        "trigger_when": "Fires at 75% tire life remaining",
        "script": "Tires at seventy-five percent — degradation looks clean.",
    },
    {
        "id": "tires_50",
        "cat": "PIT & TIRES",
        "title": "Tires 50% (Half Life)",
        "trigger_when": "Fires at 50% tire life remaining",
        "script": "Half tire life left — fifty percent, watch the fronts.",
    },
    {
        "id": "tires_35",
        "cat": "PIT & TIRES",
        "title": "Tires 35% (Window Open)",
        "trigger_when": "Fires at 35% tire life when your pit window opens",
        "script": "Tires down to thirty-five percent — pit window is open!",
    },
    {
        "id": "tires_25",
        "cat": "PIT & TIRES",
        "title": "Tires 25% (Box Soon)",
        "trigger_when": "Fires at 25% tire life warning",
        "script": "Warning, tires at twenty-five percent — recommend boxing soon!",
    },
    {
        "id": "tires_15",
        "cat": "PIT & TIRES",
        "title": "Critical Tires 15% / Puncture Cliff",
        "trigger_when": "Fires at <=15% critical wear, cliff threshold, or puncture",
        "script": "Critical tire wear! High puncture danger — box, box, box!",
    },
    # --- C. Weather, Rivals & Decisions ---
    {
        "id": "rain_start",
        "cat": "WEATHER & RIVALS",
        "title": "Rain Falling",
        "trigger_when": "Fires as soon as track wetness crosses 0% (Wet tires active)",
        "script": "Rain on track! Crossed zero — box for Wet tires!",
    },
    {
        "id": "rain_stop",
        "cat": "WEATHER & RIVALS",
        "title": "Track Drying",
        "trigger_when": "Fires when rain clears and slick compounds take over",
        "script": "Track is drying out — Slick compounds optimal now!",
    },
    {
        "id": "rival_pit",
        "cat": "WEATHER & RIVALS",
        "title": "Rival Pitting",
        "trigger_when": "Fires when your tracked rival dives into the pits (overcut chance)",
        "script": "Heads up — rival ahead just dived into the pit lane!",
    },
    {
        "id": "card_ready",
        "cat": "WEATHER & RIVALS",
        "title": "Upgrade Card Ready",
        "trigger_when": "Fires when a new upgrade card hand appears on screen",
        "script": "Upgrade ready on the wall — take the top E V call!",
    },
    {
        "id": "tire_menu",
        "cat": "WEATHER & RIVALS",
        "title": "Tire Menu Open",
        "trigger_when": "Fires when the pre-race or pit-stop tire selection modal opens",
        "script": "Tire menu open — lock in the recommended compound.",
    },
    # --- D. Push, Modes & Presets (5 Push Slots + 4 Pace Modes + L'Endurance) ---
    {
        "id": "super_boost",
        "cat": "PUSH & STRATEGY",
        "title": "Push Slot 1 (Default: K1 BOTH)",
        "trigger_when": "Fires when triggering Push Slot 1 (K1 Super Boost / Hold Both)",
        "script": "K1 Super Boost deployed — holding both boosts!",
    },
    {
        "id": "slingshot",
        "cat": "PUSH & STRATEGY",
        "title": "Push Slot 2 (Default: SLINGSHOT)",
        "trigger_when": "Fires when triggering Push Slot 2 (Straight-Line Slingshot)",
        "script": "Straight-line Slingshot armed — send it down the straight!",
    },
    {
        "id": "apex_exit",
        "cat": "PUSH & STRATEGY",
        "title": "Push Slot 3 (Default: APEX EXIT)",
        "trigger_when": "Fires when triggering Push Slot 3 (Apex Corner-Exit Grip)",
        "script": "Apex Exit vector engaged — grip through the turn!",
    },
    {
        "id": "overtake_dump",
        "cat": "PUSH & STRATEGY",
        "title": "Push Slot 4 (Default: 7s DUMP)",
        "trigger_when": "Fires when triggering Push Slot 4 (7-Second Overtake Dump)",
        "script": "Seven-second Overtake Dump — draining the battery!",
    },
    {
        "id": "defend_pulse",
        "cat": "PUSH & STRATEGY",
        "title": "Push Slot 5 (Default: ★ SUPER COMMS)",
        "trigger_when": "Fires when triggering Push Slot 5 (Golden Pixelated SUPER COMMS Push!)",
        "script": "Super Comms engaged — golden stack pinned, send it!",
    },
    {
        "id": "mode_conserve",
        "cat": "PUSH & STRATEGY",
        "title": "Conserve Mode",
        "trigger_when": "Fires when switching Pace Mode to CONSERVE",
        "script": "Copy, Conserve mode — lift and coast, protect the stint.",
    },
    {
        "id": "mode_balanced",
        "cat": "PUSH & STRATEGY",
        "title": "Balanced Mode",
        "trigger_when": "Fires when switching Pace Mode to BALANCED",
        "script": "Copy, Balanced pace — clean air crossover armed.",
    },
    {
        "id": "mode_attack",
        "cat": "PUSH & STRATEGY",
        "title": "Attack Mode",
        "trigger_when": "Fires when switching Pace Mode to ATTACK",
        "script": "Attack mode engaged — elbows out, hunt them down!",
    },
    {
        "id": "mode_hammer",
        "cat": "PUSH & STRATEGY",
        "title": "Hammer Time!",
        "trigger_when": "Fires when switching Pace Mode to HAMMER TIME",
        "script": "Copy that — Hammer Time! Pin both boosts, empty the tank!",
    },
    {
        "id": "lendurance_on",
        "cat": "PUSH & STRATEGY",
        "title": "L'Endurance P1 Package",
        "trigger_when": "Fires when toggling on the tailored L'ENDURANCE P1 preset",
        "script": "L'Endurance P1 package locked in — deep stint and Mulsanne trim active!",
    },
]

VALID_SLOT_IDS = {item["id"] for item in SWOOZ_SCRIPT_BANK}
SCRIPT_BY_SLOT = {item["id"]: item for item in SWOOZ_SCRIPT_BANK}

STARTER_TEMPLATE_META: Dict[str, Any] = {
    "id": DEFAULT_PERSONA_ID,
    "name": "My Custom Crew",
    "author": "Custom",
    "built_in": False,
    "base_voice": "Mark",       # Mark | Zira | David (local WinRT fallback timbre for unrecorded lines)
    "pitch_pct": 0,             # -18 .. +18 SSML pitch %
    "rate_offset": 3,           # -10 .. +18 SSML rate %
    "detune": 0,                # -120 .. +120 Web Audio cents
    "pres_hz": 1900,            # 1200 .. 3400 Hz presence EQ
    "pres_db": 3.0,             # 0.0 .. 6.0 dB presence gain
    "custom_lines": {},         # { slot_id: "User's custom spin / ad-lib transcript" }
}

# Ordered regex rules mapping live engine radio text -> canonical slot_id
_MATCH_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"on the pit wall|pit wall copy|loud and clear|telemetry locked on session|radio check", re.I), "radio_check"),
    (re.compile(r"lights out", re.I), "lights_out"),
    (re.compile(r"checkered flag", re.I), "checkered"),
    (re.compile(r"purple lap|fastest on track|fastest car on circuit", re.I), "purple_lap"),
    (re.compile(r"final lap", re.I), "final_lap"),
    (re.compile(r"box this lap confirmed|pit guard armed box", re.I), "box_confirm"),
    (re.compile(r"stay out confirmed|staying out|stay out, stay out", re.I), "stay_out"),
    (re.compile(r"in the pit lane", re.I), "pit_in"),
    (re.compile(r"pit exit clear", re.I), "pit_exit"),
    (re.compile(r"15 percent|at the .* cliff, box|puncture", re.I), "tires_15"),
    (re.compile(r"25 percent", re.I), "tires_25"),
    (re.compile(r"35 percent", re.I), "tires_35"),
    (re.compile(r"50 percent|half tire life", re.I), "tires_50"),
    (re.compile(r"75 percent", re.I), "tires_75"),
    (re.compile(r"rain on track|rain is falling|rain intensity", re.I), "rain_start"),
    (re.compile(r"track drying|track is drying|overheating wets", re.I), "rain_stop"),
    (re.compile(r"rival alert.*pit lane|rival ahead just dived", re.I), "rival_pit"),
    (re.compile(r"upgrade ready", re.I), "card_ready"),
    (re.compile(r"tire menu open", re.I), "tire_menu"),
    (re.compile(r"l'endurance p1 package", re.I), "lendurance_on"),
    (re.compile(r"hammer time", re.I), "mode_hammer"),
    (re.compile(r"attack mode", re.I), "mode_attack"),
    (re.compile(r"conserve mode", re.I), "mode_conserve"),
    (re.compile(r"balanced pace", re.I), "mode_balanced"),
    (re.compile(r"super comms|golden stack|defensive battery pulse|pslot_4", re.I), "defend_pulse"),
    (re.compile(r"overtake dump|pslot_3", re.I), "overtake_dump"),
    (re.compile(r"apex corner-exit|apex vector|apex exit|pslot_2", re.I), "apex_exit"),
    (re.compile(r"slingshot|pslot_1", re.I), "slingshot"),
    (re.compile(r"k1 super|super boost deployed|holding both boosts|pslot_0", re.I), "super_boost"),
]


def _slugify_persona_id(raw: str) -> str:
    s = re.sub(r"[^a-z0-9_-]", "-", str(raw or "").strip().lower())
    s = re.sub(r"-+", "-", s).strip("-_")
    if not s:
        s = DEFAULT_PERSONA_ID
    if not s.startswith("custom-"):
        s = f"custom-{s}"
    return s[:36]


def _clamp_int(v: Any, lo: int, hi: int, dflt: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except Exception:
        return dflt


def _clamp_float(v: Any, lo: float, hi: float, dflt: float) -> float:
    try:
        return round(max(lo, min(hi, float(v))), 2)
    except Exception:
        return dflt


def persona_dir(persona_id: str) -> str:
    pid = DEFAULT_PERSONA_ID if not persona_id else re.sub(r"[^a-z0-9_-]", "", persona_id.lower())
    if not pid:
        pid = DEFAULT_PERSONA_ID
    return os.path.join(PERSONAS_DIR, pid)


def persona_meta_path(persona_id: str) -> str:
    return os.path.join(persona_dir(persona_id), "persona.json")


def slot_path(slot_id: str, persona_id: str) -> str:
    safe = re.sub(r"[^a-z0-9_]", "", slot_id.lower())
    return os.path.join(persona_dir(persona_id), f"{safe}.wav")


def ensure_dirs() -> None:
    os.makedirs(PERSONAS_DIR, exist_ok=True)


def _sanitize_persona_meta(persona_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    base = STARTER_TEMPLATE_META
    bv = str(raw.get("base_voice", base["base_voice"])).strip()
    if bv not in ("Mark", "Zira", "David"):
        bv = "Mark"
    raw_lines = raw.get("custom_lines")
    clean_lines: Dict[str, str] = {}
    if isinstance(raw_lines, dict):
        for k, v in raw_lines.items():
            if k in VALID_SLOT_IDS and isinstance(v, str) and v.strip():
                clean_lines[k] = v.strip()[:200]
    return {
        "id": persona_id,
        "name": str(raw.get("name", base["name"]) or base["name"]).strip()[:42],
        "author": str(raw.get("author", base["author"]) or base["author"]).strip()[:32],
        "built_in": False,
        "base_voice": bv,
        "pitch_pct": _clamp_int(raw.get("pitch_pct", base["pitch_pct"]), -18, 18, base["pitch_pct"]),
        "rate_offset": _clamp_int(raw.get("rate_offset", base["rate_offset"]), -10, 18, base["rate_offset"]),
        "detune": _clamp_int(raw.get("detune", base["detune"]), -120, 120, base["detune"]),
        "pres_hz": _clamp_int(raw.get("pres_hz", base["pres_hz"]), 1200, 3400, base["pres_hz"]),
        "pres_db": _clamp_float(raw.get("pres_db", base["pres_db"]), 0.0, 6.0, base["pres_db"]),
        "custom_lines": clean_lines,
    }


def load_persona_meta(persona_id: str) -> Optional[Dict[str, Any]]:
    if not persona_id:
        return None
    ensure_dirs()
    pdir = persona_dir(persona_id)
    mpath = persona_meta_path(persona_id)
    if not os.path.isdir(pdir) or not os.path.isfile(mpath):
        return None
    try:
        with open(mpath, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    return _sanitize_persona_meta(os.path.basename(pdir), raw)


def is_custom_persona(persona_id: str) -> bool:
    if not persona_id:
        return False
    ensure_dirs()
    return os.path.isdir(persona_dir(persona_id)) and os.path.isfile(persona_meta_path(persona_id))


def list_personas() -> List[Dict[str, Any]]:
    ensure_dirs()
    items: List[Dict[str, Any]] = []
    for entry in sorted(os.listdir(PERSONAS_DIR)):
        full = os.path.join(PERSONAS_DIR, entry)
        if not os.path.isdir(full):
            continue
        meta = load_persona_meta(entry)
        if not meta:
            continue
        rec_count = 0
        for item in SWOOZ_SCRIPT_BANK:
            sp = slot_path(item["id"], entry)
            if os.path.isfile(sp) and os.path.getsize(sp) > 200:
                rec_count += 1
        items.append({
            **meta,
            "recorded_count": rec_count,
            "total_count": len(SWOOZ_SCRIPT_BANK),
        })
    items.sort(key=lambda x: x["name"].lower())
    return items


def _ensure_target_persona(persona_id: Optional[str]) -> str:
    """Resolve an existing custom persona or auto-create a clean starter persona when the user records/saves."""
    ensure_dirs()
    if persona_id and is_custom_persona(persona_id):
        return persona_id
    existing = list_personas()
    if existing:
        return existing[0]["id"]
    pid = _slugify_persona_id(persona_id or DEFAULT_PERSONA_ID)
    meta = _sanitize_persona_meta(pid, STARTER_TEMPLATE_META)
    os.makedirs(persona_dir(pid), exist_ok=True)
    with open(persona_meta_path(pid), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return pid


def create_or_update_persona(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dirs()
    req_id = str(payload.get("id") or "").strip()
    if req_id and is_custom_persona(req_id):
        pid = req_id
        existing = load_persona_meta(pid) or {}
    else:
        base_slug = _slugify_persona_id(req_id or str(payload.get("name") or DEFAULT_PERSONA_ID))
        pid = base_slug
        suffix = 2
        while os.path.isdir(persona_dir(pid)) and not req_id:
            pid = f"{base_slug[:32]}-{suffix}"
            suffix += 1
        existing = load_persona_meta(pid) or {}

    merged = {**existing, **payload}
    if "custom_lines" not in payload and "custom_lines" in existing:
        merged["custom_lines"] = existing["custom_lines"]
    meta = _sanitize_persona_meta(pid, merged)
    os.makedirs(persona_dir(pid), exist_ok=True)
    with open(persona_meta_path(pid), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return get_studio_manifest(pid)


def delete_persona(persona_id: str) -> Dict[str, Any]:
    ensure_dirs()
    if persona_id:
        pdir = persona_dir(persona_id)
        if os.path.isdir(pdir):
            shutil.rmtree(pdir, ignore_errors=True)
    remaining = list_personas()
    return get_studio_manifest(remaining[0]["id"] if remaining else "")


def get_studio_manifest(persona_id: str = "") -> Dict[str, Any]:
    ensure_dirs()
    personas = list_personas()
    if persona_id and is_custom_persona(persona_id):
        pid = persona_id
        meta = load_persona_meta(pid) or dict(STARTER_TEMPLATE_META)
    elif personas:
        pid = personas[0]["id"]
        meta = load_persona_meta(pid) or dict(STARTER_TEMPLATE_META)
    else:
        # Clean zero-persona state: show starter blueprint in Studio without polluting main dropdown until saved/recorded!
        pid = ""
        meta = dict(STARTER_TEMPLATE_META)

    custom_lines = meta.get("custom_lines") or {}
    slots: List[Dict[str, Any]] = []
    rec_count = 0
    for item in SWOOZ_SCRIPT_BANK:
        sid = item["id"]
        exists = False
        sz_kb = 0.0
        if pid:
            p = slot_path(sid, pid)
            exists = os.path.isfile(p) and os.path.getsize(p) > 200
            if exists:
                rec_count += 1
                sz_kb = round(os.path.getsize(p) / 1024.0, 1)
        custom_txt = str(custom_lines.get(sid) or "").strip()
        slots.append({
            **item,
            "custom_line": custom_txt,
            "effective_line": custom_txt if custom_txt else item["script"],
            "recorded": exists,
            "size_kb": sz_kb,
        })

    return {
        "persona_id": pid,
        "persona": meta,
        "personas": personas,
        "recorded_count": rec_count,
        "total_count": len(SWOOZ_SCRIPT_BANK),
        "slots": slots,
    }


def save_slot_line(slot_id: str, custom_line: str, persona_id: str = "") -> Dict[str, Any]:
    """Save or clear a user's custom spin / ad-lib transcript for a specific trigger slot."""
    if slot_id not in VALID_SLOT_IDS:
        raise ValueError(f"Unknown slot_id: {slot_id}")
    pid = _ensure_target_persona(persona_id)
    meta = load_persona_meta(pid) or _sanitize_persona_meta(pid, STARTER_TEMPLATE_META)
    clines = dict(meta.get("custom_lines") or {})
    cleaned = str(custom_line or "").strip()[:200]
    if cleaned:
        clines[slot_id] = cleaned
    else:
        clines.pop(slot_id, None)
    meta["custom_lines"] = clines
    os.makedirs(persona_dir(pid), exist_ok=True)
    with open(persona_meta_path(pid), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return get_studio_manifest(pid)


def save_slot_wav(
    slot_id: str,
    wav_bytes: bytes,
    persona_id: str = "",
    custom_line: Optional[str] = None,
) -> Dict[str, Any]:
    if slot_id not in VALID_SLOT_IDS:
        raise ValueError(f"Unknown slot_id: {slot_id}")
    if len(wav_bytes) < 200 or wav_bytes[:4] != b"RIFF":
        raise ValueError("Invalid RIFF WAV audio payload")
    pid = _ensure_target_persona(persona_id)
    os.makedirs(persona_dir(pid), exist_ok=True)
    p = slot_path(slot_id, pid)
    with open(p, "wb") as f:
        f.write(wav_bytes)
    if custom_line is not None:
        save_slot_line(slot_id, custom_line, pid)
    return get_studio_manifest(pid)


def delete_slot_wav(slot_id: str, persona_id: str = "") -> Dict[str, Any]:
    if slot_id not in VALID_SLOT_IDS:
        raise ValueError(f"Unknown slot_id: {slot_id}")
    if persona_id and is_custom_persona(persona_id):
        p = slot_path(slot_id, persona_id)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
        return get_studio_manifest(persona_id)
    return get_studio_manifest("")


def read_slot_wav(slot_id: str, persona_id: str) -> Optional[bytes]:
    if slot_id not in VALID_SLOT_IDS or not persona_id or not is_custom_persona(persona_id):
        return None
    p = slot_path(slot_id, persona_id)
    if os.path.isfile(p):
        try:
            with open(p, "rb") as f:
                data = f.read()
            return data if len(data) > 200 else None
        except OSError:
            return None
    return None


def match_slot_id(text_in: str) -> Optional[str]:
    for rx, sid in _MATCH_RULES:
        if rx.search(text_in):
            return sid
    return None


def get_custom_slot_line(text_in: str, persona_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Return `(slot_id, custom_line_or_None)` if `text_in` matches one of the 29 trigger slots."""
    sid = match_slot_id(text_in)
    if not sid or not is_custom_persona(persona_id):
        return None, None
    meta = load_persona_meta(persona_id)
    if not meta:
        return sid, None
    cline = (meta.get("custom_lines") or {}).get(sid)
    return sid, (cline if cline else None)


def match_recorded_wav(text_in: str, persona_id: str) -> Optional[Tuple[str, bytes, Optional[str]]]:
    """If a recorded WAV clip exists for `persona_id` matching `text_in`, returns `(slot_id, wav_bytes, custom_line)`."""
    if not is_custom_persona(persona_id):
        return None
    sid = match_slot_id(text_in)
    if not sid:
        return None
    wav = read_slot_wav(sid, persona_id)
    if wav is None:
        return None
    meta = load_persona_meta(persona_id) or {}
    cline = (meta.get("custom_lines") or {}).get(sid)
    return sid, wav, (str(cline).strip() if cline else None)


def export_persona_zip(persona_id: str) -> Tuple[str, bytes]:
    """Bundle `persona.json` + all recorded `<slot_id>.wav` clips into a shareable `.zip` voice pack."""
    ensure_dirs()
    if not persona_id or not is_custom_persona(persona_id):
        raise ValueError("Create and save a custom persona first before exporting a .zip pack.")
    meta = load_persona_meta(persona_id)
    if not meta:
        raise ValueError(f"Unknown persona: {persona_id}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("persona.json", json.dumps(meta, indent=2))
        for item in SWOOZ_SCRIPT_BANK:
            sid = item["id"]
            wav = read_slot_wav(sid, persona_id)
            if wav is not None:
                zf.writestr(f"{sid}.wav", wav)
    filename = f"{persona_id}_pitwall_voicepack.zip"
    return filename, buf.getvalue()


def import_persona_zip(zip_bytes: bytes) -> Dict[str, Any]:
    """Validate and install a community `.zip` voice pack safely (ignoring non-WAV / path-traversal entries)."""
    ensure_dirs()
    if len(zip_bytes) < 64 or len(zip_bytes) > 65 * 1024 * 1024:
        raise ValueError("Invalid voice pack size (max 65 MB)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except Exception as exc:
        raise ValueError("Uploaded file is not a valid .zip archive") from exc

    with zf:
        raw_meta: Dict[str, Any] = {}
        for name in zf.namelist():
            if os.path.basename(name).lower() == "persona.json":
                raw_meta = json.loads(zf.read(name).decode("utf-8"))
                break
        req_name = str(raw_meta.get("name") or "Imported Crew Pack").strip()
        raw_id = str(raw_meta.get("id") or req_name).strip()
        base_slug = _slugify_persona_id(raw_id)
        pid = base_slug
        suffix = 2
        while os.path.isdir(persona_dir(pid)):
            pid = f"{base_slug[:32]}-{suffix}"
            suffix += 1

        meta = _sanitize_persona_meta(pid, {**raw_meta, "name": req_name})
        os.makedirs(persona_dir(pid), exist_ok=True)
        with open(persona_meta_path(pid), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        for name in zf.namelist():
            bn = os.path.basename(name).lower()
            if not bn.endswith(".wav"):
                continue
            sid = bn[:-4]
            if sid not in VALID_SLOT_IDS:
                continue
            wav = zf.read(name)
            if len(wav) > 200 and wav[:4] == b"RIFF":
                with open(slot_path(sid, pid), "wb") as wf:
                    wf.write(wav)

    return get_studio_manifest(pid)
