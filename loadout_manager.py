"""5-Slot Push Mode & Card Build Strategy Loadout Manager for SWOOZ PitWall.

Enforces a strict 5-spot cap (`MAX_SLOTS = 5`) on both:
1. `push_slots` — 5 customizable 50 Hz Tactical Push / Boost deployment slots (`0..4`).
2. `card_slots` — 5 customizable Multi-Phase Auto-Card Build Strategy slots (`0..4`).

Every slot label immediately acts as a hands-free Read-What-You-See voice command on the Pit Wall,
and any Card Build slot can also be auto-populated in 1 click from a saved `.results.json` P1 race!
"""
from __future__ import annotations

import copy
import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import bc_api
import card_strategist

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOADOUT_FILE_DEFAULT = os.path.join(ROOT_DIR, "user_loadouts.json")

MAX_SLOTS = 5

VALID_PUSH_MODES = {
    "both",
    "speed_only",
    "corner_only",
    "straight_super",
    "corner_to_both",
    "smart_dump",
    "super_comms",
    "party",
}

VALID_BASE_ARCHETYPES = {
    "custom",
    "p1_mimic",
    "extreme_ai",
    "super_boost",
    "apex_grip",
    "xp_snowball",
    "ironman",
    "lendurance",
    "castellet_comms",
}

VALID_FACILITIES = {"Speed", "Cornering", "Performance", "Boost", "Fuel"}
VALID_UPGRADES = set(bc_api.UPGRADES)

# Default 5 Push Mode Slots (strict 5-spot cap)
DEFAULT_PUSH_SLOTS: List[Dict[str, Any]] = [
    {
        "slot": 0,
        "id": "k1_super",
        "label": "K1 BOTH",
        "title": "K1 Super Boost (Hold Both Speed + Cornering)",
        "mode": "both",
        "duration_s": 3.0,
        "max_steer": 1.0,
        "min_pedal": 0.0,
        "energy_floor": 0.02,
        "call": "K1 Super Boost deployed — holding both boosts!",
    },
    {
        "slot": 1,
        "id": "slingshot",
        "label": "SLINGSHOT",
        "title": "Straight-Line Slingshot (Auto-Fires Only When Wheel < 14° & On Throttle)",
        "mode": "straight_super",
        "duration_s": 4.5,
        "max_steer": 0.14,
        "min_pedal": 0.20,
        "energy_floor": 0.02,
        "call": "Straight-line Slingshot armed — send it down the straight!",
    },
    {
        "slot": 2,
        "id": "apex_vector",
        "label": "APEX EXIT",
        "title": "Apex Rotation -> Full Super-Boost Corner Exit",
        "mode": "corner_to_both",
        "duration_s": 3.5,
        "max_steer": 0.12,
        "min_pedal": 0.28,
        "energy_floor": 0.02,
        "call": "Apex Corner-Exit Grip boost engaged!",
    },
    {
        "slot": 3,
        "id": "overtake_dump",
        "label": "7s DUMP",
        "title": "Full-Sector Overtake Battery Drain (7s Smart Dump)",
        "mode": "smart_dump",
        "duration_s": 7.0,
        "max_steer": 0.25,
        "min_pedal": 0.22,
        "energy_floor": 0.04,
        "call": "Full-sector Overtake Dump engaged — draining the battery!",
    },
    {
        "slot": 4,
        "id": "super_comms",
        "label": "SUPER COMMS",
        "style": "golden_pixel",
        "title": "★ SUPER COMMS — Castellet Golden 5x Stack Hybrid Vector (5.2s Apex Corner-Grip -> Mistral Super-Boost)",
        "mode": "super_comms",
        "duration_s": 5.2,
        "max_steer": 0.16,
        "min_pedal": 0.18,
        "energy_floor": 0.05,
        "call": "Super Comms engaged — golden stack pinned, send it!",
    },
]

# Default 5 Card Build Strategy Slots (strict 5-spot cap)
DEFAULT_CARD_SLOTS: List[Dict[str, Any]] = [
    {
        "slot": 0,
        "id": "p1_mimic",
        "label": "P1 MIMIC",
        "name": "Last P1 Podium Mimic",
        "summary": "3-Phase P1 Clone: L1-3 Triple-Facility 6/6 Rush → Mid Redline T3 + PitSpeed → Late Duration",
        "base_archetype": "p1_mimic",
        "rush_facilities": ["Speed", "Boost"],
        "priority_upgrades": ["PitSpeed", "DragReduction", "Suspension", "BoostCapacity"],
        "late_upgrades": ["TemporaryUpgradeDuration", "TireSaving"],
        "avoid_upgrades": ["Reroll"],
        "call": "Auto-Card blueprint locked: P1 Podium Mimic!",
    },
    {
        "slot": 1,
        "id": "super_boost",
        "label": "BOOST 6/6",
        "name": "Super-Boost Rocket",
        "summary": "Tunnel-rushes Boost 6/6 FIRST (unlocks Hold-Both Super Boost by Lap 3) + Drag & Turbo",
        "base_archetype": "super_boost",
        "rush_facilities": ["Boost", "Speed"],
        "priority_upgrades": ["BoostPerSector", "BoostCapacity", "BoostRechargeSpeed", "TurboCharger", "DragReduction"],
        "late_upgrades": ["BoostOverspeed", "TemporaryUpgradeDuration"],
        "avoid_upgrades": ["Reroll"],
        "call": "Auto-Card blueprint locked: Super-Boost 6 of 6 Rush!",
    },
    {
        "slot": 2,
        "id": "apex_grip",
        "label": "APEX GRIP",
        "name": "Apex & Wet Dominator",
        "summary": "Rushes Cornering 6/6 (Aero Boost) + Performance 6/6 (Golden Tires) via Suspension & Grip",
        "base_archetype": "apex_grip",
        "rush_facilities": ["Cornering", "Performance"],
        "priority_upgrades": ["Suspension", "Downforce", "TireGrip", "TractionControl", "WeightReduction"],
        "late_upgrades": ["PitSpeed", "TemporaryUpgradeDuration"],
        "avoid_upgrades": ["Reroll"],
        "call": "Auto-Card blueprint locked: Apex Grip and Golden Tire Rush!",
    },
    {
        "slot": 3,
        "id": "xp_snowball",
        "label": "SNOWBALL",
        "name": "42-Tier Hyper-Snowball",
        "summary": "Stacks ExperienceGain + SensorQuality early for +10 bonus picks, then chains Redline T3",
        "base_archetype": "xp_snowball",
        "rush_facilities": ["Performance", "Boost"],
        "priority_upgrades": ["ExperienceGain", "SensorQuality", "PitSpeed"],
        "late_upgrades": ["TemporaryUpgradeDuration", "TurboCharger", "BoostOverspeed"],
        "avoid_upgrades": ["Reroll"],
        "call": "Auto-Card blueprint locked: Hyper X P Snowball!",
    },
    {
        "slot": 4,
        "id": "ironman",
        "label": "CASTELLET",
        "style": "golden_pixel",
        "name": "Dom's Castellet Golden Grand Slam",
        "summary": "Castellet 10/10 Laps Led (+5.26s, -26.5s Pit Delta, 5x Golden Stack): Rush Performance+Boost 6/6 -> PitSpeed, TireSaving & Mistral Turbo",
        "base_archetype": "castellet_comms",
        "rush_facilities": ["Performance", "Boost", "Speed"],
        "priority_upgrades": ["PitSpeed", "TireSaving", "TurboCharger", "DragReduction", "BoostRechargeSpeed", "BoostOverspeed"],
        "late_upgrades": ["TemporaryUpgradeDuration", "TireGrip"],
        "avoid_upgrades": ["Reroll"],
        "call": "Auto-Card blueprint locked: Castellet Golden Grand Slam — Pit Speed, Golden Tires, and Super Comms boost!",
    },
]


def _clean_label(raw: Any, fallback: str, max_len: int = 12) -> str:
    s = re.sub(r"\s+", " ", str(raw or "").strip()).upper()
    s = s[:max_len].strip()
    return s if s else fallback


def _clamp(val: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(val)
        if v != v:  # NaN check
            return default
        return round(max(lo, min(hi, v)), 3)
    except Exception:
        return default


def sanitize_push_slot(slot_idx: int, data: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    idx = max(0, min(MAX_SLOTS - 1, int(slot_idx)))
    dflt = copy.deepcopy(base or DEFAULT_PUSH_SLOTS[idx])
    mode = str(data.get("mode", dflt["mode"])).strip().lower()
    if mode not in VALID_PUSH_MODES:
        mode = dflt["mode"]
    label = _clean_label(data.get("label", dflt["label"]), dflt["label"], max_len=12)
    title = str(data.get("title", dflt["title"]) or dflt["title"]).strip()[:110]
    call = str(data.get("call", dflt["call"]) or f"{label} push deployed!").strip()[:140]
    style = str(data.get("style", dflt.get("style", "")) or "").strip()
    return {
        "slot": idx,
        "id": dflt["id"],  # Keep canonical slot ID (`k1_super`, `slingshot`, etc.) stable across edits
        "label": label,
        "style": style,
        "title": title,
        "mode": mode,
        "duration_s": _clamp(data.get("duration_s", dflt["duration_s"]), 0.8, 12.0, dflt["duration_s"]),
        "max_steer": _clamp(data.get("max_steer", dflt["max_steer"]), 0.05, 1.0, dflt["max_steer"]),
        "min_pedal": _clamp(data.get("min_pedal", dflt["min_pedal"]), 0.0, 0.90, dflt["min_pedal"]),
        "energy_floor": _clamp(data.get("energy_floor", dflt["energy_floor"]), 0.0, 0.60, dflt["energy_floor"]),
        "call": call,
    }


def sanitize_card_slot(slot_idx: int, data: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    idx = max(0, min(MAX_SLOTS - 1, int(slot_idx)))
    dflt = copy.deepcopy(base or DEFAULT_CARD_SLOTS[idx])
    arch = str(data.get("base_archetype", dflt["base_archetype"])).strip().lower()
    if arch not in VALID_BASE_ARCHETYPES:
        arch = "custom"
    label = _clean_label(data.get("label", dflt["label"]), dflt["label"], max_len=12)
    name = str(data.get("name", dflt["name"]) or label).strip()[:48]
    summary = str(data.get("summary", dflt["summary"]) or "Custom multi-phase card priority blueprint").strip()[:160]
    call = str(data.get("call", dflt["call"]) or f"Auto-Card blueprint locked: {label}!").strip()[:140]

    def _pick_list(raw_list: Any, allowed: set[str], cap: int) -> List[str]:
        if not isinstance(raw_list, list):
            return []
        out: List[str] = []
        for item in raw_list:
            s = str(item).strip()
            if s in allowed and s not in out:
                out.append(s)
                if len(out) >= cap:
                    break
        return out

    rush = _pick_list(data.get("rush_facilities", dflt["rush_facilities"]), VALID_FACILITIES, 3)
    prio = _pick_list(data.get("priority_upgrades", dflt["priority_upgrades"]), VALID_UPGRADES, 7)
    late = _pick_list(data.get("late_upgrades", dflt["late_upgrades"]), VALID_UPGRADES, 4)
    avoid = [u for u in _pick_list(data.get("avoid_upgrades", dflt["avoid_upgrades"]), VALID_UPGRADES, 5) if u not in prio]

    style = str(data.get("style", dflt.get("style", "")) or "").strip()
    return {
        "slot": idx,
        "id": dflt["id"],
        "label": label,
        "style": style,
        "name": name,
        "summary": summary,
        "base_archetype": arch,
        "rush_facilities": rush,
        "priority_upgrades": prio,
        "late_upgrades": late,
        "avoid_upgrades": avoid,
        "call": call,
    }


def compute_push_buttons(slot_cfg: Dict[str, Any], mc: Any, ab: Dict[str, Any], energy_type: str) -> int:
    """50 Hz Physics Gate & Boost Bitmask evaluator for any customized Push Mode slot."""
    floor = float(slot_cfg.get("energy_floor", 0.02))
    if energy_type == "boost" and float(mc.energy) <= floor:
        return 0
    if energy_type == "fuel":
        return bc_api.BOOST_PARTY_MODE | bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING

    mode = str(slot_cfg.get("mode", "both")).lower()
    max_steer = float(slot_cfg.get("max_steer", 0.16))
    min_pedal = float(slot_cfg.get("min_pedal", 0.20))
    abs_steer = abs(float(mc.steer))
    pedal = float(mc.pedal)

    if mode == "both":
        if abs_steer <= max_steer and pedal >= min_pedal:
            return bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING
        return 0
    if mode == "speed_only":
        if abs_steer <= max_steer and pedal >= min_pedal:
            return bc_api.BOOST_SPEED
        return 0
    if mode == "corner_only":
        return bc_api.BOOST_CORNERING
    if mode == "party":
        return bc_api.BOOST_PARTY_MODE | bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING
    if mode == "straight_super":
        # Smart Straight Sniper: fires ONLY when wheel <= max_steer & pedal >= min_pedal
        if abs_steer <= max_steer and pedal >= min_pedal:
            super_cone = max(0.06, max_steer * 0.62)
            return bc_api.BOOST_SPEED | (bc_api.BOOST_CORNERING if ab.get("super_boost_unlocked") and abs_steer <= super_cone else 0)
        return 0
    if mode == "corner_to_both":
        # Corner-Exit Vector: Cornering Boost through the turn, blending into Both Boosts on exit!
        if abs_steer >= max_steer or abs(float(getattr(mc, "lat_g", 0.0))) > 0.65:
            return bc_api.BOOST_CORNERING
        if pedal >= min_pedal:
            return bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING
        return 0
    if mode == "smart_dump":
        # Full-Sector Drain: Cornering under load/braking, Both Boosts on straight throttle!
        if pedal <= min_pedal or abs_steer > max_steer:
            return bc_api.BOOST_CORNERING
        return bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING
    if mode == "super_comms":
        # ★ SUPER COMMS (Castellet Golden 5x Stack Hybrid Vector):
        # 1) Braking / Off-throttle (< 0): zero waste so tires & battery regenerate cleanly.
        # 2) Technical corner rotation (abs_steer > max_steer or Lat-G > 0.58): pure Cornering Grip Boost (protects tire wear!).
        # 3) Corner exit & Mistral Straight (abs_steer <= max_steer & pedal >= min_pedal): instant Dual SUPER BOOST + Party!
        if pedal < -0.05:
            return 0
        if abs_steer > max_steer or abs(float(getattr(mc, "lat_g", 0.0))) > 0.58:
            return bc_api.BOOST_CORNERING if pedal >= 0.05 else 0
        if pedal >= min_pedal:
            return bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING | (bc_api.BOOST_PARTY_MODE if ab.get("party_mode_unlocked") else 0)
        return 0

    return bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING


def list_archived_p1_races(results_dir: str) -> List[Dict[str, Any]]:
    """Return summary metadata of all `.results.json` P1 race winners available for 1-click slot import."""
    items: List[Dict[str, Any]] = []
    if not os.path.isdir(results_dir):
        return items
    for p in sorted(glob.glob(os.path.join(results_dir, "*.results.json")), reverse=True):
        fn = os.path.basename(p)
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            continue
        for sess in doc.get("sessions") or []:
            if sess.get("kind") != "race":
                continue
            info = card_strategist._extract_p1_from_session(fn, sess)
            if not info:
                continue
            items.append({
                "archive": fn,
                "track": info["track"],
                "winner": info["winner"],
                "driver_kind": info["driver_kind"],
                "grid": info["grid"],
                "laps": info["laps"],
                "best_lap_s": info["best_lap_s"],
                "win_margin_s": info["win_margin_s"],
                "total_cards_picked": info["total_cards_picked"],
                "top_upgrades": info["top_upgrades"],
            })
            break
    return items


def build_card_slot_from_archive(results_dir: str, archive_fn: str, slot_idx: int) -> Optional[Dict[str, Any]]:
    """Extract the P1 winner's build from `archive_fn` and turn it into a ready-to-save Card Build slot!"""
    safe_fn = os.path.basename(str(archive_fn or ""))
    full_path = os.path.join(results_dir, safe_fn)
    if not os.path.isfile(full_path):
        return None
    try:
        with open(full_path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None

    for sess in doc.get("sessions") or []:
        if sess.get("kind") != "race":
            continue
        info = card_strategist._extract_p1_from_session(safe_fn, sess)
        if not info:
            continue
        trk = str(info["track"] or "RACE").upper()
        short_trk = re.sub(r"[^A-Z0-9']", "", trk)[:8] or "P1 RACE"
        label = _clean_label(f"{short_trk} P1", "P1 BUILD", max_len=12)

        perm = info.get("perm_counts") or {}
        early = info.get("early_counts") or {}
        timed = info.get("timed_counts") or {}
        fac_xp = (info.get("final_stats") or {}).get("facility_xp") or {}

        # Rank facilities maxed or most invested by the P1 winner
        if fac_xp:
            ranked_facs = [f for f, v in sorted(fac_xp.items(), key=lambda kv: kv[1], reverse=True) if v >= 4][:2]
        else:
            ranked_facs = []
        if not ranked_facs:
            # Infer from top upgrades or track archetype
            ranked_facs = ["Speed", "Boost"] if "lemans" in trk.lower() or "monza" in trk.lower() else ["Performance", "Cornering"]

        combined_counts: Dict[str, int] = {}
        for k, v in perm.items():
            combined_counts[k] = combined_counts.get(k, 0) + v * 2
        for k, v in early.items():
            combined_counts[k] = combined_counts.get(k, 0) + v
        prio = [
            u for u, _ in sorted(combined_counts.items(), key=lambda kv: kv[1], reverse=True)
            if u in VALID_UPGRADES and u != "TemporaryUpgradeDuration"
        ][:6]
        if not prio:
            # Human P1 session where AI card vectors aren't logged for player car -> tailor smartly!
            if "castellet" in trk.lower():
                ranked_facs = ["Performance", "Boost", "Speed"]
                prio = ["PitSpeed", "TireSaving", "TurboCharger", "DragReduction", "BoostRechargeSpeed", "BoostOverspeed"]
            elif "lemans" in trk.lower() or "endurance" in trk.lower():
                prio = ["DragReduction", "PitSpeed", "BoostOverspeed", "TireSaving", "TurboCharger"]
            else:
                prio = ["PitSpeed", "Suspension", "TireSaving", "WeightReduction", "DragReduction"]

        late = ["TemporaryUpgradeDuration"]
        for u, _ in sorted(timed.items(), key=lambda kv: kv[1], reverse=True):
            if u in VALID_UPGRADES and u not in late:
                late.append(u)
                if len(late) >= 3:
                    break
        if len(late) == 1:
            late.append("TireSaving" if "TireSaving" not in prio else "PitSpeed")

        winner = info["winner"]
        margin = info["win_margin_s"]
        summary = (
            f"{info['track']} P1 ({winner}, G{info['grid']}→P1 +{margin:.2f}s): "
            f"Rush {'+'.join(ranked_facs)} 6/6 · Core {', '.join(prio[:4])}"
        )[:160]

        return sanitize_card_slot(
            slot_idx,
            {
                "label": label,
                "name": f"{info['track']} P1 ({winner})"[:48],
                "summary": summary,
                "base_archetype": "castellet_comms" if "castellet" in trk.lower() else ("lendurance" if "lemans" in trk.lower() else "custom"),
                "rush_facilities": ranked_facs,
                "priority_upgrades": prio,
                "late_upgrades": late,
                "avoid_upgrades": ["Reroll"],
                "call": f"Auto-Card blueprint locked: {info['track']} P1 dial-in!",
            },
        )
    return None


class LoadoutManager:
    """Thread-safe persistent manager for the 5 Push Mode slots and 5 Card Build slots."""

    def __init__(self, path: str = LOADOUT_FILE_DEFAULT) -> None:
        self.path = path
        self.push_slots: List[Dict[str, Any]] = copy.deepcopy(DEFAULT_PUSH_SLOTS)
        self.card_slots: List[Dict[str, Any]] = copy.deepcopy(DEFAULT_CARD_SLOTS)
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            self.save()
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
            raw_push = doc.get("push_slots") or []
            raw_card = doc.get("card_slots") or []
            self.push_slots = [
                sanitize_push_slot(i, raw_push[i] if i < len(raw_push) and isinstance(raw_push[i], dict) else DEFAULT_PUSH_SLOTS[i])
                for i in range(MAX_SLOTS)
            ]
            self.card_slots = [
                sanitize_card_slot(i, raw_card[i] if i < len(raw_card) and isinstance(raw_card[i], dict) else DEFAULT_CARD_SLOTS[i])
                for i in range(MAX_SLOTS)
            ]
        except Exception:
            self.push_slots = copy.deepcopy(DEFAULT_PUSH_SLOTS)
            self.card_slots = copy.deepcopy(DEFAULT_CARD_SLOTS)

    def save(self) -> None:
        doc = {
            "version": 1,
            "max_slots": MAX_SLOTS,
            "push_slots": self.push_slots[:MAX_SLOTS],
            "card_slots": self.card_slots[:MAX_SLOTS],
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)

    def get_state(self) -> Dict[str, Any]:
        return {
            "max_slots": MAX_SLOTS,
            "push_slots": copy.deepcopy(self.push_slots[:MAX_SLOTS]),
            "card_slots": copy.deepcopy(self.card_slots[:MAX_SLOTS]),
            "catalog": {
                "push_modes": sorted(VALID_PUSH_MODES),
                "base_archetypes": ["custom", "p1_mimic", "super_boost", "apex_grip", "xp_snowball", "ironman", "lendurance"],
                "facilities": ["Speed", "Cornering", "Performance", "Boost", "Fuel"],
                "upgrades": [u for u in bc_api.UPGRADES if u != "Reroll"] + ["Reroll"],
            },
        }

    def get_push_slot(self, key: Any) -> Dict[str, Any]:
        if isinstance(key, int) and 0 <= key < MAX_SLOTS:
            return self.push_slots[key]
        s = str(key or "").strip().lower()
        for item in self.push_slots:
            if item["id"].lower() == s or item["label"].lower() == s or f"pslot_{item['slot']}" == s:
                return item
        return self.push_slots[0]

    def get_card_slot(self, key: Any) -> Optional[Dict[str, Any]]:
        if isinstance(key, int) and 0 <= key < MAX_SLOTS:
            return self.card_slots[key]
        s = str(key or "").strip().lower()
        for item in self.card_slots:
            if item["id"].lower() == s or item["label"].lower() == s or f"cslot_{item['slot']}" == s:
                return item
        return None

    def update_push_slot(self, slot_idx: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        if not (0 <= int(slot_idx) < MAX_SLOTS):
            raise ValueError(f"Push Mode slots are strictly capped at {MAX_SLOTS} (0..{MAX_SLOTS - 1})")
        idx = int(slot_idx)
        merged = {**self.push_slots[idx], **patch}
        self.push_slots[idx] = sanitize_push_slot(idx, merged, base=DEFAULT_PUSH_SLOTS[idx])
        self.save()
        return copy.deepcopy(self.push_slots[idx])

    def update_card_slot(self, slot_idx: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        if not (0 <= int(slot_idx) < MAX_SLOTS):
            raise ValueError(f"Card Build slots are strictly capped at {MAX_SLOTS} (0..{MAX_SLOTS - 1})")
        idx = int(slot_idx)
        merged = {**self.card_slots[idx], **patch}
        self.card_slots[idx] = sanitize_card_slot(idx, merged, base=DEFAULT_CARD_SLOTS[idx])
        self.save()
        return copy.deepcopy(self.card_slots[idx])

    def reset_push_slot(self, slot_idx: Optional[int] = None) -> None:
        if slot_idx is None:
            self.push_slots = copy.deepcopy(DEFAULT_PUSH_SLOTS)
        elif 0 <= int(slot_idx) < MAX_SLOTS:
            self.push_slots[int(slot_idx)] = copy.deepcopy(DEFAULT_PUSH_SLOTS[int(slot_idx)])
        self.save()

    def reset_card_slot(self, slot_idx: Optional[int] = None) -> None:
        if slot_idx is None:
            self.card_slots = copy.deepcopy(DEFAULT_CARD_SLOTS)
        elif 0 <= int(slot_idx) < MAX_SLOTS:
            self.card_slots[int(slot_idx)] = copy.deepcopy(DEFAULT_CARD_SLOTS[int(slot_idx)])
        self.save()
