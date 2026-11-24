"""SWOOZ PitWall — Public Lobby Racing, Broadcast & Open GP League Suite.

100% compliant with Backseat Champions' official `public_lobby` Game API rules:
- Never injects blocked car/menu commands (`pick_card`, `set_pit`, `pick_tire`, `boost`, `drive`) in public lobbies.
- Uses sanctioned 50Hz read-only telemetry (`Motion`, `Car Telemetry`, `Car Status`, `Car Abilities`, `Player`, `Event`),
  sanctioned `set_camera` view switching, and sanctioned `POST /race-results` host uploads.
"""
from __future__ import annotations

import glob
import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

FIA_POINTS = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)


# ==============================================================================
# 1. 50HZ 3D HELICOPTER BLIND-SPOT RADAR & SPATIAL SPOTTER
# ==============================================================================

def compute_proximity_radar(cars: List[Any], my_idx: int, num_cars: int) -> Dict[str, Any]:
    """Projects nearby cars into player-car local coordinates (meters):
    - `rel_x`: +right / -left (meters from player centerline)
    - `rel_z`: +ahead / -behind (meters from player center)
    """
    if num_cars <= 0 or my_idx < 0 or my_idx >= num_cars:
        return {
            "status": "CLEAR",
            "left_state": "CLEAR",
            "right_state": "CLEAR",
            "nearest_m": 99.0,
            "contacts": [],
        }

    me = cars[my_idx]
    mx, _, mz = me.position_xyz
    yaw_rad = math.radians(float(me.yaw))
    # Unity left-handed world frame: yaw=0 -> +Z forward, +X right; yaw=90 -> +X forward, -Z right
    fx = math.sin(yaw_rad)
    fz = math.cos(yaw_rad)
    rx = math.cos(yaw_rad)
    rz = -math.sin(yaw_rad)
    my_spd_mps = float(me.speed_kmh) / 3.6

    contacts: List[Dict[str, Any]] = []
    left_overlap = False
    right_overlap = False
    left_dive = False
    right_dive = False
    nearest_m = 99.0

    for i in range(num_cars):
        if i == my_idx:
            continue
        c = cars[i]
        if getattr(c, "in_pits", False) != getattr(me, "in_pits", False):
            continue
        cx, _, cz = c.position_xyz
        dx = cx - mx
        dz = cz - mz
        dist = math.hypot(dx, dz)
        if dist > 28.0 or dist < 0.05:
            continue

        rel_z = dx * fx + dz * fz
        rel_x = dx * rx + dz * rz
        if abs(rel_z) > 24.0 or abs(rel_x) > 11.0:
            continue

        if dist < nearest_m:
            nearest_m = dist

        # Closing rate along track heading (m/s)
        c_spd_mps = float(c.speed_kmh) / 3.6
        c_yaw = math.radians(float(c.yaw))
        c_fwd_along_me = math.cos(c_yaw - yaw_rad) * c_spd_mps
        closing_mps = (c_fwd_along_me - my_spd_mps) if rel_z < 0 else (my_spd_mps - c_fwd_along_me)

        # Car body length ~4.8m -> overlap zone is |rel_z| <= 4.7m and lateral 0.65m..6.5m
        in_overlap = (-4.7 <= rel_z <= 4.5) and (0.60 <= abs(rel_x) <= 6.5)
        in_dive = (-13.5 <= rel_z < -4.7) and (abs(rel_x) <= 6.8) and (closing_mps >= 4.0)

        threat = "NEAR"
        if in_overlap:
            threat = "OVERLAP"
            if rel_x < 0:
                left_overlap = True
            else:
                right_overlap = True
        elif in_dive:
            threat = "DIVEBOMB"
            if rel_x < 0:
                left_dive = True
            else:
                right_dive = True

        contacts.append({
            "index": i,
            "name": c.name,
            "pos": c.position,
            "kind": getattr(c, "kind", "ai"),
            "compound": getattr(c, "tire_compound", "Standard"),
            "rel_x": round(rel_x, 2),
            "rel_z": round(rel_z, 2),
            "dist_m": round(dist, 2),
            "closing_mps": round(closing_mps, 1),
            "threat": threat,
        })

    contacts.sort(key=lambda item: item["dist_m"])

    left_state = "OVERLAP" if left_overlap else ("DIVE" if left_dive else "CLEAR")
    right_state = "OVERLAP" if right_overlap else ("DIVE" if right_dive else "CLEAR")

    if left_overlap and right_overlap:
        status = "3-WIDE"
    elif left_overlap:
        status = "CAR LEFT"
    elif right_overlap:
        status = "CAR RIGHT"
    elif left_dive:
        status = "DIVE LEFT"
    elif right_dive:
        status = "DIVE RIGHT"
    else:
        status = "CLEAR"

    return {
        "status": status,
        "left_state": left_state,
        "right_state": right_state,
        "nearest_m": round(nearest_m, 1),
        "contacts": contacts[:8],
    }


# ==============================================================================
# 2. LIVE RIVAL BUILD SPY & WEAPON UNLOCK ESPIONAGE
# ==============================================================================

def _build_car_dossier(me: Any, rv: Optional[Any], role: str) -> Optional[Dict[str, Any]]:
    if rv is None or rv.index == me.index:
        return None
    mp = me.performance
    rp = rv.performance

    my_straight = (mp.get("EngineTorque", 0.85) + mp.get("Drag", 0.85) + mp.get("Acceleration", 0.85)) / 3.0
    rv_straight = (rp.get("EngineTorque", 0.85) + rp.get("Drag", 0.85) + rp.get("Acceleration", 0.85)) / 3.0
    straight_edge_pct = round((rv_straight - my_straight) * 100.0, 2)

    my_corner = (mp.get("Downforce", 0.85) + mp.get("Suspension", 0.85) + mp.get("TractionControl", 0.85)) / 3.0
    rv_corner = (rp.get("Downforce", 0.85) + rp.get("Suspension", 0.85) + rp.get("TractionControl", 0.85)) / 3.0
    corner_edge_pct = round((rv_corner - my_corner) * 100.0, 2)

    ab = rv.abilities or {}
    weapons: List[str] = []
    if ab.get("super_boost_unlocked"):
        weapons.append("SUPER BOOST")
    if ab.get("drs_unlocked"):
        weapons.append("DRS")
    if ab.get("party_mode_unlocked"):
        weapons.append("PARTY")

    gap_s = round(me.interval_ahead if role == "AHEAD" else me.interval_behind, 3)
    th_pct = round(rv.tire_health * 100.0, 0)
    erg_pct = round(rv.energy * 100.0, 0)

    if role == "AHEAD":
        if rv.tire_health < 0.26:
            tip = f"TIRES DYING ({th_pct:.0f}%) — PRESS FOR UNDERCUT / FORCED ERROR"
        elif straight_edge_pct < -1.2:
            tip = f"WE HAVE +{abs(straight_edge_pct):.1f}% STRAIGHT SPEED — PASS ON EXIT"
        elif corner_edge_pct < -1.2:
            tip = f"WE HAVE +{abs(corner_edge_pct):.1f}% APEX GRIP — DIVE BRAKING ZONE"
        elif "SUPER BOOST" in weapons and erg_pct > 55:
            tip = f"SUPER BOOST ARMED ({erg_pct:.0f}% ERS) — BAIT BATTERY FIRST"
        else:
            tip = f"EVEN HARDWARE — HOLD SLIPSTREAM (<1.0s) & WAIT FOR CLIFF"
    else:
        if "SUPER BOOST" in weapons and erg_pct > 50 and gap_s < 1.5:
            tip = f"DANGER: SUPER BOOST LOADED ({erg_pct:.0f}%) — DEFEND INSIDE LINE!"
        elif straight_edge_pct > 1.5:
            tip = f"RIVAL +{straight_edge_pct:.1f}% FASTER ON STRAIGHTS — SAVE ERS FOR EXIT"
        elif rv.recharging if hasattr(rv, "recharging") else ab.get("recharging"):
            tip = "RIVAL BATTERY DEPLETED (RECHARGING) — BREAK TOW NOW!"
        else:
            tip = f"GAP {gap_s:.2f}s — SMOOTH EXITS KEEP THEM OUT OF DRAFT"

    return {
        "role": role,
        "index": rv.index,
        "pos": rv.position,
        "name": rv.name,
        "kind": rv.kind,
        "gap_s": gap_s,
        "compound": rv.tire_compound,
        "tire_pct": int(th_pct),
        "energy_pct": int(erg_pct),
        "recharging": bool(ab.get("recharging", False)),
        "weapons": weapons,
        "straight_delta_pct": straight_edge_pct,  # + means rival is stronger on straights
        "corner_delta_pct": corner_edge_pct,      # + means rival is stronger in corners
        "tip": tip,
    }


def compute_rival_spy(
    cars: List[Any],
    my_idx: int,
    num_cars: int,
    known_unlocks: Dict[int, Set[str]],
    session_time: float,
) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    """Tracks live rival hardware advantages and newly unlocked abilities across all 16 cars."""
    radio_alerts: List[Tuple[str, str]] = []
    if num_cars <= 0 or my_idx < 0 or my_idx >= num_cars:
        return {"ahead": None, "behind": None, "field_unlocks": []}, radio_alerts

    me = cars[my_idx]
    car_ahead = None
    car_behind = None
    field_unlocks: List[Dict[str, Any]] = []

    for i in range(num_cars):
        c = cars[i]
        if i != my_idx:
            if me.position > 1 and c.position == me.position - 1:
                car_ahead = c
            elif c.position == me.position + 1:
                car_behind = c

        ab = c.abilities or {}
        prev_set = known_unlocks.setdefault(i, set())
        cur_weapons: List[str] = []
        for flag_key, label in (
            ("super_boost_unlocked", "Super Boost"),
            ("drs_unlocked", "D R S"),
            ("party_mode_unlocked", "Party Mode"),
        ):
            if ab.get(flag_key):
                cur_weapons.append(label.replace(" ", ""))
                if flag_key not in prev_set:
                    prev_set.add(flag_key)
                    # Only call out over radio after grid settle (t > 6s) for adjacent threats / P1 / humans!
                    is_close_threat = abs(c.position - me.position) <= 2 or c.position == 1 or c.kind == "remote"
                    if i != my_idx and session_time > 6.0 and is_close_threat:
                        radio_alerts.append((
                            f"spy_{i}_{flag_key}",
                            f"Intel alert: P{c.position} {c.name} just unlocked {label}!",
                        ))
        if cur_weapons and i != my_idx:
            field_unlocks.append({
                "index": i,
                "pos": c.position,
                "name": c.name,
                "weapons": cur_weapons,
            })

    field_unlocks.sort(key=lambda x: x["pos"])
    spy_payload = {
        "ahead": _build_car_dossier(me, car_ahead, "AHEAD"),
        "behind": _build_car_dossier(me, car_behind, "BEHIND"),
        "field_unlocks": field_unlocks[:6],
    }
    return spy_payload, radio_alerts


# ==============================================================================
# 3. AI TV BROADCAST DIRECTOR (`set_camera` IS ALLOWED IN PUBLIC LOBBIES!)
# ==============================================================================

def select_tv_director_camera(
    me: Any,
    session_time: float,
    last_cam: str,
    last_switch_mono: float,
    now_mono: float,
) -> Optional[str]:
    """Chooses the most cinematic F1 camera angle without rapid-cut strobing."""
    dwell = now_mono - last_switch_mono
    if dwell < 4.2:
        return None

    # 1. Race Start Grid Launch (0..9s) -> Helicopter overhead!
    if 0.2 <= session_time <= 9.0:
        target = "Helicopter"
    # 2. Pit Lane Stop -> TrackSide!
    elif getattr(me, "in_pits", False):
        target = "TrackSide"
    # 3. Wheel-to-Wheel Overtake / Defense (< 0.52s ahead or < 0.42s behind) -> BattleCam!
    elif (0.01 < me.interval_ahead <= 0.52) or (0.01 < me.interval_behind <= 0.42):
        target = "Onboard_BattleCam"
    # 4. High-Speed DRS / Super-Boost Blast -> T-Cam!
    elif me.speed_kmh >= 248.0 and (
        me.abilities.get("drs") or me.abilities.get("super_boost") or me.abilities.get("speed_boost")
    ):
        target = "Onboard_TCam"
    # 5. Scenic Clear-Air Rotation every ~8.5s
    else:
        if dwell < 8.5 and last_cam in ("Chase", "Onboard_TVAngle", "Drone", "Onboard_TCam"):
            return None
        cycle = ("Onboard_TVAngle", "Chase", "Onboard_TCam", "Drone")
        idx = int(session_time // 9.0) % len(cycle)
        target = cycle[idx]

    if target != last_cam:
        return target
    return None


# ==============================================================================
# 4. SWOOZ OPEN GP PUBLIC LEADERBOARD, ELO STANDINGS & DISCORD AUTO-WEBHOOK
# ==============================================================================

class LeagueManager:
    """Computes live Championship Points, Multiplayer Elo, Track Records, and Discord Webhooks
    from hosted Backseat Champions `POST /race-results` uploads.
    """

    def __init__(self, results_dir: str) -> None:
        self.results_dir = results_dir
        os.makedirs(self.results_dir, exist_ok=True)
        self.config_path = os.path.join(self.results_dir, "league_config.json")
        self.config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        default = {
            "league_name": "SWOOZ OPEN GP CHAMPIONSHIP",
            "season_tag": "SEASON 1 · PUBLIC & OPEN LOBBIES",
            "discord_webhook_url": "",
            "auto_post_discord": True,
            "humans_only": False,
        }
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    default.update({k: saved[k] for k in default if k in saved})
            except Exception:
                pass
        return default

    def update_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        for k in ("league_name", "season_tag", "discord_webhook_url"):
            if k in patch and patch[k] is not None:
                self.config[k] = str(patch[k]).strip()[:260]
        for k in ("auto_post_discord", "humans_only"):
            if k in patch:
                self.config[k] = bool(patch[k])
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except OSError:
            pass
        return dict(self.config)

    @staticmethod
    def _is_human_entry(entry: Dict[str, Any]) -> bool:
        drv = str(entry.get("driver", "")).lower()
        if drv in ("human", "local", "remote", "player"):
            return True
        if entry.get("steam_id") is not None or entry.get("local_seat") is not None:
            return True
        if "ai" in drv:
            return False
        return False

    def build_leaderboard(self, humans_only: Optional[bool] = None) -> Dict[str, Any]:
        only_humans = self.config.get("humans_only", False) if humans_only is None else bool(humans_only)
        files = sorted(glob.glob(os.path.join(self.results_dir, "*.results.json")))

        drivers: Dict[str, Dict[str, Any]] = {}
        track_records: Dict[str, Dict[str, Any]] = {}
        recent_races: List[Dict[str, Any]] = []
        total_races = 0
        public_races = 0

        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception:
                continue

            is_pub = bool(doc.get("public_lobby", False))
            fname = os.path.basename(path).replace(".results.json", "")

            for sess in doc.get("sessions") or []:
                kind = str(sess.get("kind", "Race"))
                track = str(sess.get("track") or "Unknown_Circuit")
                raw_cls = sess.get("classification") or []
                if not raw_cls:
                    continue

                # Record track x car_class fastest laps across both Qualifying and Race
                for row in raw_cls:
                    is_hum = self._is_human_entry(row)
                    if only_humans and not is_hum:
                        continue
                    blap = row.get("best_lap_s") or row.get("best_lap")
                    if isinstance(blap, (int, float)) and 5.0 < float(blap) < 600.0:
                        car_cls = str(row.get("car_class") or row.get("car_type") or "Formula")
                        rec_key = f"{track}::{car_cls}"
                        cur_rec = track_records.get(rec_key)
                        if cur_rec is None or float(blap) < cur_rec["best_lap_s"]:
                            track_records[rec_key] = {
                                "track": track,
                                "car_class": car_cls,
                                "best_lap_s": round(float(blap), 3),
                                "driver": str(row.get("name") or "Driver"),
                                "is_human": is_hum,
                                "session": kind,
                                "public_lobby": is_pub,
                            }

                if kind.lower() != "race":
                    continue

                filtered = [r for r in raw_cls if (not only_humans or self._is_human_entry(r))]
                if not filtered:
                    continue

                total_races += 1
                if is_pub:
                    public_races += 1

                # Find fastest lap of the race
                best_race_lap = None
                fastest_name = None
                for r in filtered:
                    bl = r.get("best_lap_s") or r.get("best_lap")
                    if isinstance(bl, (int, float)) and 5.0 < float(bl) < 600.0:
                        if best_race_lap is None or float(bl) < best_race_lap:
                            best_race_lap = float(bl)
                            fastest_name = str(r.get("name") or "")

                # Ensure all participants exist before pairwise Elo update
                ordered = sorted(filtered, key=lambda r: int(r.get("position") or 99))
                for r in ordered:
                    dname = str(r.get("name") or "Driver").strip()
                    if not dname:
                        continue
                    if dname not in drivers:
                        drivers[dname] = {
                            "name": dname,
                            "is_human": self._is_human_entry(r),
                            "elo": 1500.0,
                            "points": 0,
                            "races": 0,
                            "public_races": 0,
                            "wins": 0,
                            "podiums": 0,
                            "fastest_laps": 0,
                            "positions_gained": 0,
                            "finish_sum": 0,
                            "best_lap_s": None,
                        }
                    elif self._is_human_entry(r):
                        drivers[dname]["is_human"] = True

                # Pairwise Multiplayer Elo update (K=28 scaled by (N-1))
                n_field = len(ordered)
                elo_deltas: Dict[str, float] = {str(r.get("name") or "Driver").strip(): 0.0 for r in ordered}
                if n_field >= 2:
                    k_pair = 28.0 / max(1, n_field - 1)
                    for idx_a in range(n_field):
                        na = str(ordered[idx_a].get("name") or "Driver").strip()
                        ra = drivers[na]["elo"]
                        for idx_b in range(idx_a + 1, n_field):
                            nb = str(ordered[idx_b].get("name") or "Driver").strip()
                            if na == nb:
                                continue
                            rb = drivers[nb]["elo"]
                            exp_a = 1.0 / (1.0 + (10.0 ** ((rb - ra) / 400.0)))
                            # idx_a finished ahead of idx_b -> score = 1.0
                            delta = k_pair * (1.0 - exp_a)
                            elo_deltas[na] += delta
                            elo_deltas[nb] -= delta

                for rank_idx, r in enumerate(ordered):
                    dname = str(r.get("name") or "Driver").strip()
                    d = drivers[dname]
                    pos = rank_idx + 1 if only_humans else int(r.get("position") or (rank_idx + 1))
                    grid = int(r.get("grid") or r.get("grid_position") or pos)
                    pts = FIA_POINTS[pos - 1] if 1 <= pos <= len(FIA_POINTS) else 0
                    if dname == fastest_name and pos <= 10:
                        pts += 1
                    if dname == fastest_name:
                        d["fastest_laps"] += 1

                    d["points"] += pts
                    d["races"] += 1
                    if is_pub:
                        d["public_races"] += 1
                    if pos == 1:
                        d["wins"] += 1
                    if pos <= 3:
                        d["podiums"] += 1
                    d["positions_gained"] += (grid - pos)
                    d["finish_sum"] += pos
                    d["elo"] = max(1000.0, d["elo"] + elo_deltas.get(dname, 0.0))

                    bl = r.get("best_lap_s") or r.get("best_lap")
                    if isinstance(bl, (int, float)) and 5.0 < float(bl) < 600.0:
                        if d["best_lap_s"] is None or float(bl) < d["best_lap_s"]:
                            d["best_lap_s"] = round(float(bl), 3)

                podium_names = [str(x.get("name") or "?") for x in ordered[:3]]
                recent_races.append({
                    "id": fname,
                    "track": track,
                    "public_lobby": is_pub,
                    "cars": len(ordered),
                    "podium": podium_names,
                    "fastest_driver": fastest_name,
                    "fastest_lap_s": round(best_race_lap, 3) if best_race_lap else None,
                })

        standings = []
        for d in drivers.values():
            rc = max(1, d["races"])
            standings.append({
                "name": d["name"],
                "is_human": d["is_human"],
                "elo": int(round(d["elo"])),
                "points": d["points"],
                "races": d["races"],
                "public_races": d["public_races"],
                "wins": d["wins"],
                "podiums": d["podiums"],
                "win_pct": round((d["wins"] / rc) * 100.0, 1),
                "fastest_laps": d["fastest_laps"],
                "avg_finish": round(d["finish_sum"] / rc, 2),
                "positions_gained": d["positions_gained"],
                "best_lap_s": d["best_lap_s"],
            })

        standings.sort(key=lambda x: (-x["points"], -x["elo"], -x["wins"], x["avg_finish"]))
        for idx, row in enumerate(standings):
            row["rank"] = idx + 1

        records_list = sorted(track_records.values(), key=lambda x: (x["track"], x["best_lap_s"]))
        recent_races.reverse()

        return {
            "config": {
                "league_name": self.config.get("league_name", "SWOOZ OPEN GP CHAMPIONSHIP"),
                "season_tag": self.config.get("season_tag", "SEASON 1"),
                "humans_only": only_humans,
                "auto_post_discord": bool(self.config.get("auto_post_discord", True)),
                "has_discord_webhook": bool(self.config.get("discord_webhook_url", "").strip()),
            },
            "totals": {
                "races": total_races,
                "public_races": public_races,
                "drivers": len(standings),
                "records": len(records_list),
            },
            "standings": standings[:32],
            "track_records": records_list[:24],
            "recent_races": recent_races[:12],
        }

    def post_to_discord(self, summary: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Posts the latest race result + Top-5 Season Standings embed to the configured Discord Webhook."""
        url = str(self.config.get("discord_webhook_url") or "").strip()
        if not url.startswith("https://discord.com/api/webhooks/") and not url.startswith("https://discordapp.com/api/webhooks/"):
            return False, "Set a valid https://discord.com/api/webhooks/... URL first."

        lb = self.build_leaderboard()
        race_info = None
        if summary and summary.get("sessions"):
            race_sessions = [s for s in summary["sessions"] if str(s.get("kind", "")).lower() == "race"]
            sess = race_sessions[-1] if race_sessions else summary["sessions"][-1]
            cls = sess.get("classification") or []
            podium = [f"**P{i+1}** {r.get('name', '?')}" for i, r in enumerate(cls[:3])]
            race_info = {
                "track": sess.get("track") or "Grand Prix",
                "public_lobby": bool(summary.get("public_lobby", False)),
                "podium_str": " · ".join(podium) if podium else "Finished",
            }
        elif lb["recent_races"]:
            rr = lb["recent_races"][0]
            podium = [f"**P{i+1}** {n}" for i, n in enumerate(rr.get("podium") or [])]
            race_info = {
                "track": rr["track"],
                "public_lobby": rr["public_lobby"],
                "podium_str": " · ".join(podium),
            }

        top5 = lb["standings"][:5]
        standings_lines = [
            f"`#{r['rank']}` **{r['name']}** — **{r['points']} pts** · `{r['elo']} Elo` ({r['wins']}W / {r['podiums']}P)"
            for r in top5
        ] or ["No races archived yet — host a race to populate standings!"]

        lobby_tag = "🌐 PUBLIC LOBBY" if (race_info and race_info["public_lobby"]) else "🏁 HOSTED GP"
        title_str = f"🏆 {self.config.get('league_name', 'SWOOZ OPEN GP')} — {race_info['track'] if race_info else 'STANDINGS'}"
        desc_str = f"**{lobby_tag}**\n{race_info['podium_str']}" if race_info else "Live Championship Standings Update"

        payload = {
            "username": "SWOOZ PitWall · Race Control",
            "embeds": [
                {
                    "title": title_str,
                    "description": desc_str,
                    "color": 0xFF7B00,
                    "fields": [
                        {
                            "name": "📊 Top 5 Season Standings (Points & Elo)",
                            "value": "\n".join(standings_lines),
                            "inline": False,
                        }
                    ],
                    "footer": {
                        "text": f"Powered by SWOOZ PitWall · {lb['totals']['races']} Races Tracked · Backseat Champions"
                    },
                }
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SWOOZ-PitWall/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                if 200 <= resp.status < 300:
                    return True, "Posted Podium & Standings to Discord!"
                return False, f"Discord returned HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            return False, f"Discord HTTP {exc.code}"
        except Exception as exc:
            return False, str(exc)
