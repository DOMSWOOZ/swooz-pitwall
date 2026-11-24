"""High-fidelity 50 Hz 16-car race simulator emitting exact bc_api-shaped packets.

Used when no live Backseat Champions session is broadcasting yet (or when Demo Sim is toggled on),
and yields immediately the instant real UDP packets arrive from 127.0.0.1:29770.
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple

import bc_api

DRIVER_NAMES = [
    "Dom_Swooz", "Thruster", "Pole", "Circler", "Arizona", "DeFranco",
    "Valkyrie", "Mystic", "Strider", "Jaguar", "Drift", "Nacho",
    "The Serpent", "Apexia", "Vortex", "Kowalski",
]

COMPOUND_SPEED_MULT = {
    "Golden": 1.032,
    "Fast": 1.022,
    "Boost": 1.012,
    "Experimental": 1.015,
    "Standard": 1.000,
    "Durable": 0.988,
    "Wet": 0.965,
}

COMPOUND_WEAR_MULT = {
    "Golden": 1.25,
    "Fast": 1.42,
    "Boost": 1.15,
    "Experimental": 1.35,
    "Standard": 1.00,
    "Durable": 0.62,
    "Wet": 1.18,
}


class DemoRaceSimulator:
    """Simulates a dynamic 16-car Grand Prix on a technical circuit with elevation, DRS, weather, cards & pit stops."""

    def __init__(self) -> None:
        self.rng = random.Random(42)
        self.session_uid = 99004201
        self.frame = 0
        self.session_time = 0.0
        self.total_laps = 18
        self.player_car = 0
        self.weather = -0.32  # Starts dry/partly cloudy, slowly drifts toward light rain mid-race
        self.weather_vel = 0.0028

        # Build a smooth closed-loop F1-style Grand Prix circuit (figure-8 / technical GP curve in [x, y, z])
        self.num_waypoints = 240
        self.track_pts: List[Tuple[float, float, float]] = []
        self.left_pts: List[Tuple[float, float, float]] = []
        self.right_pts: List[Tuple[float, float, float]] = []
        self.curvatures: List[float] = []
        self.seg_lengths: List[float] = []
        self.total_length_m = 0.0
        self._build_circuit()

        # Player & card state
        self.points = 3
        self.upgrades_applied = 4
        self.ban_tokens = 2
        self.compound_picks_left = {
            "Standard": None, "Boost": 2, "Experimental": 1,
            "Fast": 2, "Durable": 2, "Wet": None, "Golden": 1,
        }
        self.hand = self._deal_hand()
        self.tire_modal_open = False
        self.api_driving = False
        self.api_pedal = 1.0
        self.api_steer = 0.0
        self.api_drive_until = 0.0
        self.api_boost_flags = 0
        self.api_boost_until = 0.0

        # Initialize 16 cars starting mid-stint (Lap 9 of 18) so tire cliff & strategy data is immediately rich!
        self.cars: List[Dict] = []
        for idx in range(16):
            is_player = idx == self.player_car
            # Put player in P1 battling closely with P2 & P3, with realistic F1 mid-race field spread (~1.15s/car)
            start_lap = 8
            progress_offset = 0.0 if idx == 0 else (-0.018 if idx == 1 else -(idx * 0.044))
            s_norm = (0.62 + progress_offset) % 1.0
            lap = start_lap + math.floor(0.62 + progress_offset)

            base_perf = {
                "Suspension": 0.8800 + self.rng.uniform(-0.035, 0.045),
                "EngineTorque": 0.8100 + self.rng.uniform(-0.045, 0.055),
                "Downforce": 0.8950 + self.rng.uniform(-0.040, 0.045),
                "Acceleration": 0.9200 + self.rng.uniform(-0.030, 0.035),
                "Drag": 0.7650 + self.rng.uniform(-0.035, 0.045),
                "AngularDrag": 1.1500 + self.rng.uniform(-0.025, 0.025),
                "TractionControl": 0.9400 + self.rng.uniform(-0.040, 0.040),
                "Weight": 0.8420 + self.rng.uniform(-0.028, 0.032),
            }
            if is_player:
                # Give player competitive stats with realistic ~0.01 diffs vs P2/P3
                base_perf.update({
                    "Weight": 0.8612,
                    "EngineTorque": 0.8540,
                    "Downforce": 0.9215,
                    "Acceleration": 0.9480,
                    "Drag": 0.7910,
                    "Suspension": 0.9105,
                    "TractionControl": 0.9620,
                    "AngularDrag": 1.1640,
                })
            elif idx == 1:
                # P2 Thruster: +0.0114 lighter Weight, slightly less Downforce!
                base_perf.update({
                    "Weight": 0.8726,
                    "EngineTorque": 0.8615,
                    "Downforce": 0.9040,
                    "Acceleration": 0.9510,
                    "Drag": 0.8025,
                })

            compound = "Fast" if is_player else self.rng.choice(["Standard", "Fast", "Durable", "Boost"])
            health = 0.284 if is_player else self.rng.uniform(0.36, 0.84)

            self.cars.append({
                "index": idx,
                "name": DRIVER_NAMES[idx],
                "kind": "local" if is_player else "ai",
                "car_type": "ModernFormula",
                "grid": idx + 1 if idx != 0 else 4,
                "s": s_norm,  # 0..1 track progress
                "lateral_offset": 0.0,
                "speed_mps": 52.0,
                "prev_speed_mps": 52.0,
                "pedal": 1.0,
                "steer": 0.0,
                "yaw": 0.0,
                "yaw_rate": 0.0,
                "lap": lap,
                "total_dist": (lap + s_norm) * self.total_length_m,
                "tire_compound": compound,
                "tire_health": health,
                "tire_age_laps": 5 if is_player else self.rng.randint(2, 6),
                "puncture": False,
                "pit_stops": 1 if health > 0.65 else 0,
                "pit_planned": False,
                "in_pits": False,
                "pit_timer": 0.0,
                "energy": 0.74 if is_player else self.rng.uniform(0.35, 0.95),
                "recharging": False,
                "recharge_left": 0.0,
                "performance": base_perf,
                "skill": 1.005 if is_player else 1.002 - idx * 0.0022,
            })

        self.session_time = 8 * 28.4

    def _build_circuit(self) -> None:
        pts = []
        for i in range(self.num_waypoints):
            t = (i / self.num_waypoints) * 2.0 * math.pi
            # Technical circuit: main straight + fast esses + hairpin + elevation climb
            x = 260.0 * math.cos(t) + 75.0 * math.sin(2.0 * t) - 35.0 * math.cos(3.0 * t)
            z = 175.0 * math.sin(t) + 55.0 * math.cos(2.0 * t) + 30.0 * math.sin(4.0 * t)
            y = 14.0 * math.sin(t - 0.5) + 6.5 * math.cos(2.0 * t)
            pts.append((x, y, z))
        self.track_pts = pts

        n = self.num_waypoints
        half_w = 6.8
        for i in range(n):
            p_prev = pts[(i - 1) % n]
            p_curr = pts[i]
            p_next = pts[(i + 1) % n]
            dx = p_next[0] - p_prev[0]
            dz = p_next[2] - p_prev[2]
            norm = math.hypot(dx, dz) or 1.0
            # Unity left-handed (+Z=0 deg, +X=90 deg): left normal of (dx, dz) is (-dz, dx)
            lx, lz = -dz / norm, dx / norm
            self.left_pts.append((p_curr[0] + lx * half_w, p_curr[1], p_curr[2] + lz * half_w))
            self.right_pts.append((p_curr[0] - lx * half_w, p_curr[1], p_curr[2] - lz * half_w))

            seg_dx = p_next[0] - p_curr[0]
            seg_dz = p_next[2] - p_curr[2]
            seg_len = math.hypot(seg_dx, seg_dz)
            self.seg_lengths.append(seg_len)
            self.total_length_m += seg_len

            a1 = math.atan2(p_curr[0] - p_prev[0], p_curr[2] - p_prev[2])
            a2 = math.atan2(p_next[0] - p_curr[0], p_next[2] - p_curr[2])
            da = (a2 - a1 + math.pi) % (2.0 * math.pi) - math.pi
            self.curvatures.append(abs(da) / max(seg_len, 0.5))

    def _deal_hand(self) -> List[Dict]:
        pool = [
            ("TireSaving", "Cornering", 2),
            ("WeightReduction", "Performance", 2),
            ("EnginePower", "Speed", 1),
            ("Downforce", "Cornering", 2),
            ("DragReduction", "Speed", 1),
            ("BoostRechargeSpeed", "Boost", 1),
            ("TireGrip", "Cornering", 2),
            ("PitSpeed", "All", 1),
            ("TurboCharger", "Redline", 2),
            ("Suspension", "Cornering", 1),
        ]
        chosen = self.rng.sample(pool, 4)
        return [
            {"index": i, "upgrade": u, "facility": f, "tier": t, "banned": False}
            for i, (u, f, t) in enumerate(chosen)
        ]

    def _sample_track(self, s_norm: float) -> Tuple[Tuple[float, float, float], float, float, int]:
        s = (s_norm % 1.0) * self.num_waypoints
        idx = int(s) % self.num_waypoints
        frac = s - int(s)
        n = self.num_waypoints
        p0 = self.track_pts[idx]
        p1 = self.track_pts[(idx + 1) % n]
        x = p0[0] + (p1[0] - p0[0]) * frac
        y = p0[1] + (p1[1] - p0[1]) * frac
        z = p0[2] + (p1[2] - p0[2]) * frac
        yaw = math.degrees(math.atan2(p1[0] - p0[0], p1[2] - p0[2]))
        curv = self.curvatures[idx] * (1.0 - frac) + self.curvatures[(idx + 1) % n] * frac
        return (x, y, z), yaw, curv, idx

    def handle_command(self, cmd_name: str, args: Dict) -> Tuple[str, Dict]:
        """Processes commands in simulator mode just like the real game."""
        req_id = int(args.get("request_id", 1))
        pcar = self.cars[self.player_car]
        now = time.monotonic()

        if cmd_name == "hello":
            return "hello", {
                "request_id": req_id,
                "game_version": "0.88.2-SIM",
                "player_input": True,
                "driver_input": True,
                "public_lobby": False,
                "driver_data": True,
                "player_data": True,
                "decision_events": True,
                "ai_observations": True,
                "rate_hz": 50,
                "feature_schema_version": 12,
                "feature_schema_hash": "0x40A5F76F",
            }
        if cmd_name == "ping":
            return "ack", {"command": "ping", "request_id": req_id}
        if cmd_name == "set_pit":
            pcar["pit_planned"] = bool(args.get("pit", True))
            return "ack", {"command": "set_pit", "request_id": req_id}
        if cmd_name == "pick_card":
            idx = int(args.get("index", 0))
            if self.points <= 0:
                return "error", {"command": "pick_card", "request_id": req_id, "reason": "no_points"}
            if not (0 <= idx < len(self.hand)):
                return "error", {"command": "pick_card", "request_id": req_id, "reason": "invalid_index"}
            card = self.hand[idx]
            if card["banned"]:
                return "error", {"command": "pick_card", "request_id": req_id, "reason": "card_banned"}
            # Apply realistic stat upgrade!
            upg = card["upgrade"]
            perf = pcar["performance"]
            boost_amt = 0.0145 * (1 + card["tier"] * 0.4)
            stat_map = {
                "WeightReduction": "Weight",
                "EnginePower": "EngineTorque",
                "TurboCharger": "Acceleration",
                "Downforce": "Downforce",
                "DragReduction": "Drag",
                "Suspension": "Suspension",
                "TireGrip": "TractionControl",
                "TireSaving": "Suspension",
            }
            target_stat = stat_map.get(upg, "Acceleration")
            perf[target_stat] = perf.get(target_stat, 0.85) + boost_amt
            self.points = max(0, self.points - 1)
            self.upgrades_applied += 1
            self.hand = self._deal_hand() if self.points > 0 else []
            return "ack", {"command": "pick_card", "request_id": req_id}
        if cmd_name == "ban_card":
            idx = int(args.get("index", 0))
            if self.ban_tokens <= 0 or not (0 <= idx < len(self.hand)):
                return "error", {"command": "ban_card", "request_id": req_id, "reason": "ban_refused"}
            unbanned = [c for c in self.hand if not c["banned"]]
            if len(unbanned) <= 1 or self.hand[idx]["banned"]:
                return "error", {"command": "ban_card", "request_id": req_id, "reason": "ban_refused"}
            self.hand[idx]["banned"] = True
            self.ban_tokens -= 1
            return "ack", {"command": "ban_card", "request_id": req_id}
        if cmd_name == "pick_tire":
            comp = str(args.get("compound", "Standard"))
            if comp not in bc_api.COMPOUNDS:
                return "error", {"command": "pick_tire", "request_id": req_id, "reason": "invalid_compound"}
            left = self.compound_picks_left.get(comp)
            if left is not None and left <= 0:
                return "error", {"command": "pick_tire", "request_id": req_id, "reason": "compound_refused"}
            pcar["next_compound"] = comp
            if pcar["in_pits"]:
                pcar["tire_compound"] = comp
                if left is not None:
                    self.compound_picks_left[comp] = max(0, left - 1)
            return "ack", {"command": "pick_tire", "request_id": req_id}
        if cmd_name == "drive":
            self.api_driving = True
            self.api_pedal = max(-1.0, min(1.0, float(args.get("pedal", 1.0))))
            self.api_steer = max(-1.0, min(1.0, float(args.get("steer", 0.0))))
            self.api_drive_until = now + 0.30
            return "none", {}
        if cmd_name == "release_drive":
            self.api_driving = False
            return "ack", {"command": "release_drive", "request_id": req_id}
        if cmd_name == "boost":
            flags = int(args.get("buttons", 0))
            self.api_boost_flags = flags
            self.api_boost_until = now + 0.30 if flags else 0.0
            return "none", {}
        if cmd_name == "set_camera":
            return "ack", {"command": "set_camera", "request_id": req_id}
        return "ack", {"command": cmd_name, "request_id": req_id}

    def step(self, dt: float = 0.02) -> List[Tuple[Dict, Dict]]:
        """Advances physics by dt (50 Hz) and returns decoded (header, body) packets."""
        self.frame += 1
        self.session_time += dt
        now = time.monotonic()

        if self.api_driving and now > self.api_drive_until:
            self.api_driving = False
        if self.api_boost_flags and now > self.api_boost_until:
            self.api_boost_flags = 0

        # Slowly evolve weather between clear (-0.45) and wet (+0.35)
        self.weather += self.weather_vel * dt
        if self.weather > 0.38:
            self.weather_vel = -0.0032
        elif self.weather < -0.45:
            self.weather_vel = 0.0028

        events_out: List[Dict] = []

        # Advance every car
        for c in self.cars:
            is_player = c["index"] == self.player_car
            _, track_yaw, curv, wp_idx = self._sample_track(c["s"])
            # Look ahead curvature for braking
            _, _, ahead_curv, _ = self._sample_track(c["s"] + 0.032)

            if c["in_pits"]:
                c["pit_timer"] -= dt
                c["speed_mps"] = 22.0
                c["pedal"] = 0.25
                c["steer"] = 0.0
                if c["pit_timer"] <= 0.0:
                    c["in_pits"] = False
                    new_comp = c.pop("next_compound", None)
                    if not new_comp:
                        new_comp = "Wet" if self.weather > 0.05 else ("Standard" if (self.total_laps - c["lap"]) > 6 else "Fast")
                    if is_player and self.compound_picks_left.get(new_comp) is not None:
                        if self.compound_picks_left[new_comp] > 0:
                            self.compound_picks_left[new_comp] -= 1
                        else:
                            new_comp = "Standard"
                    c["tire_compound"] = new_comp
                    c["tire_health"] = 1.0
                    c["tire_age_laps"] = 0
                    c["puncture"] = False
                    c["pit_stops"] += 1
                    if is_player:
                        events_out.append({"code": "PITO", "seat": 0})
            else:
                # Physics speed target from curvature, compound, weather, tire health, upgrades
                perf = c["performance"]
                grip_factor = (0.55 + 0.45 * perf["Downforce"]) * COMPOUND_SPEED_MULT.get(c["tire_compound"], 1.0)
                if self.weather > 0.02:
                    if c["tire_compound"] == "Wet":
                        grip_factor *= 1.03
                    else:
                        grip_factor *= max(0.76, 1.0 - self.weather * 0.32)
                elif c["tire_compound"] == "Wet":
                    grip_factor *= 0.94

                # Tire cliff & puncture penalty!
                if c["puncture"]:
                    grip_factor *= 0.56
                elif c["tire_health"] < 0.20:
                    grip_factor *= 0.86 + 0.70 * c["tire_health"]

                max_straight_mps = (69.5 + 14.0 * perf["EngineTorque"] + 8.0 * perf["Drag"] + 6.0 * perf["Weight"]) * c["skill"]
                corner_limit_mps = min(max_straight_mps, (25.5 / math.sqrt(max(ahead_curv, 0.0035))) * grip_factor)
                if c["puncture"]:
                    max_straight_mps *= 0.62

                # DRS on main straight (waypoints 220..240 and 0..28)
                drs_open = (wp_idx >= 218 or wp_idx <= 28) and curv < 0.012
                c["drs"] = drs_open

                # Boost logic
                speed_boost = False
                corner_boost = False
                if is_player and self.api_boost_flags:
                    if not c["recharging"] and c["energy"] > 0.01:
                        speed_boost = bool(self.api_boost_flags & bc_api.BOOST_SPEED)
                        corner_boost = bool(self.api_boost_flags & bc_api.BOOST_CORNERING)
                elif not is_player and not c["recharging"] and c["energy"] > 0.35 and drs_open:
                    speed_boost = True

                if speed_boost or corner_boost:
                    c["energy"] = max(0.0, c["energy"] - 0.14 * dt)
                    if c["energy"] <= 0.005:
                        c["recharging"] = True
                        c["recharge_left"] = 1.0
                else:
                    c["energy"] = min(1.0, c["energy"] + 0.045 * dt)
                    if c["recharging"]:
                        c["recharge_left"] = max(0.0, c["recharge_left"] - 0.18 * dt)
                        if c["recharge_left"] <= 0.0:
                            c["recharging"] = False

                c["speed_boost"] = speed_boost
                c["cornering_boost"] = corner_boost
                c["super_boost"] = speed_boost and corner_boost

                target_mps = corner_limit_mps * (1.055 if drs_open else 1.0) * (1.07 if speed_boost else 1.0)

                if is_player and self.api_driving:
                    c["pedal"] = self.api_pedal
                    c["steer"] = self.api_steer
                    accel = (self.api_pedal * 24.0 * perf["Acceleration"]) if self.api_pedal >= 0 else (self.api_pedal * 38.0)
                    drag_decel = 0.0042 * (c["speed_mps"] ** 2)
                    c["prev_speed_mps"] = c["speed_mps"]
                    c["speed_mps"] = max(8.0, min(96.0, c["speed_mps"] + (accel - drag_decel) * dt))
                    prev_yaw = c["yaw"]
                    c["yaw"] = (c["yaw"] + self.api_steer * 85.0 * dt + 180.0) % 360.0 - 180.0
                    c["yaw_rate"] = math.radians((c["yaw"] - prev_yaw + 180.0) % 360.0 - 180.0) / dt
                else:
                    err_v = target_mps - c["speed_mps"]
                    c["pedal"] = max(-1.0, min(1.0, err_v * 0.16))
                    accel = err_v * 3.8
                    c["prev_speed_mps"] = c["speed_mps"]
                    c["speed_mps"] = max(14.0, c["speed_mps"] + accel * dt)
                    # Steer follows track curvature
                    _, next_yaw, _, _ = self._sample_track(c["s"] + 0.012)
                    dyaw = (next_yaw - track_yaw + 180.0) % 360.0 - 180.0
                    c["steer"] = max(-1.0, min(1.0, dyaw / 22.0))
                    c["yaw_rate"] = math.radians(dyaw) * (c["speed_mps"] / max(self.total_length_m * 0.012, 1.0))
                    c["yaw"] = track_yaw

                # Tire wear per physics tick (~6.8% per lap on Standard, ~9.6% on Fast!)
                ds = (c["speed_mps"] * dt) / self.total_length_m
                wear_mult = COMPOUND_WEAR_MULT.get(c["tire_compound"], 1.0) * (1.12 - 0.15 * perf["Suspension"])
                c["tire_health"] = max(0.0, c["tire_health"] - ds * 0.068 * wear_mult)

                # Puncture hazard under 8% health!
                if not c["puncture"] and c["tire_health"] < 0.065:
                    if self.rng.random() < 0.008:
                        c["puncture"] = True

                # AI auto-pit under 22% health if >= 2 laps left
                if not is_player and c["tire_health"] < 0.22 and (self.total_laps - c["lap"]) >= 2:
                    c["pit_planned"] = True

            # Advance track coordinate
            ds = (c["speed_mps"] * dt) / self.total_length_m
            prev_s = c["s"]
            new_s = prev_s + ds
            if new_s >= 1.0:
                c["s"] = new_s - 1.0
                c["lap"] += 1
                c["tire_age_laps"] += 1
                if c["pit_planned"] and c["lap"] < self.total_laps:
                    c["in_pits"] = True
                    c["pit_planned"] = False
                    c["pit_timer"] = 6.31  # matches pit_lane_time_loss_s!
                    if is_player:
                        events_out.append({"code": "PITI", "seat": 0})
                        events_out.append({
                            "code": "TIRE",
                            "seat": 0,
                            "pre_race": False,
                            "current": c["tire_compound"],
                            "allowed": list(bc_api.COMPOUNDS),
                            "picks_left": dict(self.compound_picks_left),
                        })
                if is_player:
                    if c["lap"] >= self.total_laps:
                        c["lap"] = 8  # Loop endless demo stint cleanly if race finishes
                        for rc in self.cars:
                            rc["lap"] = 8
                            rc["tire_health"] = 0.88 if rc["index"] == 0 else self.rng.uniform(0.55, 0.95)
                            rc["puncture"] = False
                    if c["lap"] % 2 == 0:
                        self.points = min(5, self.points + 1)
                        self.hand = self._deal_hand()
                        events_out.append({"code": "CARD", "seat": 0, "points": self.points, "hand": list(self.hand)})
                    events_out.append({"code": "LAPC", "seat": 0, "lap": c["lap"], "position": c.get("position", 1)})
                    events_out.append({
                        "code": "PITW",
                        "seat": 0,
                        "lap": c["lap"],
                        "pit_planned": c["pit_planned"],
                        "can_pit": c["lap"] < self.total_laps - 1,
                    })
            else:
                c["s"] = new_s

            c["total_dist"] = (c["lap"] + c["s"]) * self.total_length_m

        # Sort standings by total_dist
        ranked = sorted(self.cars, key=lambda x: x["total_dist"], reverse=True)
        leader_dist = ranked[0]["total_dist"]
        avg_mps = max(ranked[0]["speed_mps"], 38.0)
        for pos_idx, car in enumerate(ranked):
            car["position"] = pos_idx + 1
            car["gap_to_leader"] = 0.0 if pos_idx == 0 else (leader_dist - car["total_dist"]) / avg_mps
            car["interval_ahead"] = 0.0 if pos_idx == 0 else (ranked[pos_idx - 1]["total_dist"] - car["total_dist"]) / avg_mps
            car["interval_behind"] = (
                -0.25 if pos_idx == len(ranked) - 1
                else -(car["total_dist"] - ranked[pos_idx + 1]["total_dist"]) / avg_mps
            )
            # Slipstream if within 0.85s of car ahead on low curvature
            car["slipstream"] = max(0.0, min(1.0, 1.0 - car["interval_ahead"] / 0.85)) if pos_idx > 0 and car["interval_ahead"] < 0.85 else 0.0

        def mk_hdr(pid: int, pver: int = 1) -> Dict:
            return {
                "packet_format": 1,
                "packet_id": pid,
                "packet_version": pver,
                "game_version": "0.88.2-SIM",
                "num_cars": 16,
                "session_uid": self.session_uid,
                "frame": self.frame,
                "session_time": self.session_time,
                "seat_car": [self.player_car, 255, 255, 255],
                "packet": bc_api.PACKET_NAMES[pid],
                "simulated": True,
            }

        packets: List[Tuple[Dict, Dict]] = []

        # 0: Motion & 1: Car Telemetry & 2: Lap Data & 12: Car Abilities & 13: Racing Line & 4: Player
        motion_cars = []
        telem_cars = []
        lap_cars = []
        abil_cars = []
        for c in self.cars:
            pos, track_yaw, curv, _ = self._sample_track(c["s"])
            if not (c["index"] == self.player_car and self.api_driving):
                c["yaw"] = track_yaw
            lat_v = c["steer"] * c["speed_mps"] * 0.045
            motion_cars.append({
                "position": pos,
                "velocity": (lat_v, 0.0, c["speed_mps"]),
                "angular_velocity": (0.0, c["yaw_rate"], 0.0),
                "pitch": 0.0,
                "roll": c["steer"] * 2.1,
                "yaw": c["yaw"],
            })
            lat_slip_f = c["steer"] * (c["speed_mps"] / 55.0) * 0.16
            lat_slip_r = lat_slip_f * (0.86 if c["tire_health"] > 0.35 else 1.24)  # worn tires oversteer!
            long_slip_r = max(0.0, c["pedal"]) * 0.24 * (1.35 - 0.35 * c["tire_health"])
            long_slip_f = min(0.0, c["pedal"]) * 0.18
            wheels = [
                {"on_track": True, "grounded": True, "slip_forward": long_slip_f, "slip_sideways": lat_slip_f},
                {"on_track": True, "grounded": True, "slip_forward": long_slip_f, "slip_sideways": lat_slip_f * 1.03},
                {"on_track": True, "grounded": True, "slip_forward": long_slip_r, "slip_sideways": lat_slip_r},
                {"on_track": True, "grounded": True, "slip_forward": long_slip_r * 0.98, "slip_sideways": lat_slip_r * 1.02},
            ]
            telem_cars.append({
                "speed_kmh": c["speed_mps"] * 3.6,
                "pedal": c["pedal"],
                "steer": c["steer"],
                "wheels": wheels,
                "tire_compound": c["tire_compound"],
                "puncture": c["puncture"],
                "tire_health": c["tire_health"],
                "energy": c["energy"],
            })
            lap_cars.append({
                "position": c["position"],
                "class_position": c["position"],
                "lap": c["lap"],
                "in_pits": c["in_pits"],
                "finished": False,
                "pit_planned": c["pit_planned"],
                "api_driving": c["index"] == self.player_car and self.api_driving,
                "pit_stops": c["pit_stops"],
                "gap_to_leader": c["gap_to_leader"],
                "interval_ahead": c["interval_ahead"],
                "interval_behind": c["interval_behind"],
            })
            abil_cars.append({
                "speed_boost": c.get("speed_boost", False),
                "cornering_boost": c.get("cornering_boost", False),
                "super_boost": c.get("super_boost", False),
                "party_mode": False,
                "drs": c.get("drs", False),
                "boost_overspeed": c.get("drs", False) and c.get("speed_boost", False),
                "recharging": c["recharging"],
                "super_boost_unlocked": True,
                "party_mode_unlocked": False,
                "drs_unlocked": True,
                "api_boosting": c["index"] == self.player_car and bool(self.api_boost_flags),
                "ban_tokens": self.ban_tokens if c["index"] == self.player_car else 0,
                "slipstream": c.get("slipstream", 0.0),
                "recharge_left": c["recharge_left"],
            })

        packets.append((mk_hdr(bc_api.MOTION), {"cars": motion_cars}))
        packets.append((mk_hdr(bc_api.CAR_TELEMETRY), {"cars": telem_cars}))
        packets.append((mk_hdr(bc_api.LAP_DATA), {"cars": lap_cars}))
        packets.append((mk_hdr(bc_api.CAR_ABILITIES), {"cars": abil_cars}))

        # Player packet
        pc = self.cars[self.player_car]
        cars_ahead_5s = sum(1 for x in self.cars if x["position"] < pc["position"] and (pc["gap_to_leader"] - x["gap_to_leader"]) <= 5.0)
        cars_behind_5s = sum(1 for x in self.cars if x["position"] > pc["position"] and (x["gap_to_leader"] - pc["gap_to_leader"]) <= 5.0)
        packets.append((mk_hdr(bc_api.PLAYER), {
            "seat": 0,
            "car": self.player_car,
            "points": self.points,
            "hand": list(self.hand),
            "upgrades_applied": self.upgrades_applied,
            "total_laps": self.total_laps,
            "laps_remaining": max(0, self.total_laps - pc["lap"]),
            "pit_planned": pc["pit_planned"],
            "can_pit": not pc["in_pits"] and pc["lap"] < self.total_laps - 1,
            "in_pits": pc["in_pits"],
            "pit_stops": pc["pit_stops"],
            "tire_compound": pc["tire_compound"],
            "puncture": pc["puncture"],
            "tire_health": pc["tire_health"],
            "compound_picks_left": dict(self.compound_picks_left),
            "energy": pc["energy"],
            "strategy": {
                "start_grid_position": pc["grid"],
                "laps_since_pit": pc["tire_age_laps"],
                "tire_age_laps": pc["tire_age_laps"],
                "cars_within_5s_ahead": cars_ahead_5s,
                "cars_within_5s_behind": cars_behind_5s,
                "class_position": pc["position"],
                "class_size": 16,
                "class_gap_to_leader": pc["gap_to_leader"],
                "class_gap_to_ahead": pc["interval_ahead"],
                "class_gap_to_behind": abs(pc["interval_behind"]),
                "reference_lap_s": 28.140,
                "opponents": [],
                "near": [],
            },
        }))

        # Racing line ahead of player car (20 checkpoints)
        _, _, _, p_wp = self._sample_track(pc["s"])
        rline = []
        for k in range(1, 21):
            idx = (p_wp + k * 2) % self.num_waypoints
            rline.append({
                "racing_line": self.track_pts[idx],
                "left": self.left_pts[idx],
                "right": self.right_pts[idx],
            })
        packets.append((mk_hdr(bc_api.RACING_LINE), {"seat": 0, "car": self.player_car, "points": rline}))

        # Periodic packets (Session & Car Status twice/s, Participants every 2s)
        if self.frame % 25 == 1:
            packets.append((mk_hdr(bc_api.SESSION), {
                "session_type": "Race",
                "energy": "boost",
                "total_laps": self.total_laps,
                "player_input": True,
                "driver_input": True,
                "public_lobby": False,
                "weather": self.weather,
                "feature_schema_version": 12,
                "feature_schema_hash": "0x40A5F76F",
                "scene": "SuzukaWest_SimGP",
                "track": {
                    "length_km": self.total_length_m / 1000.0,
                    "corner_count": 9,
                    "avg_corner_speed": 41.2,
                    "straight_ratio": 0.58,
                    "elevation_change": 28.4,
                    "base_tire_wear_rate": 0.068,
                    "overtake_difficulty": 0.44,
                    "pit_lane_time_loss_s": 6.309,
                    "width_mean": 13.6,
                    "width_min": 11.8,
                    "barrier_ratio": 0.12,
                    "drs_zone_count": 1,
                    "drs_coverage": 0.24,
                    "lap_time_est_s": 28.140,
                },
            }))
            packets.append((mk_hdr(bc_api.CAR_STATUS), {
                "cars": [{"performance": dict(c["performance"])} for c in self.cars]
            }))

        if self.frame % 100 == 1:
            packets.append((mk_hdr(bc_api.PARTICIPANTS), {
                "cars": [
                    {"player_id": c["index"], "car_type": c["car_type"], "kind": c["kind"], "name": c["name"]}
                    for c in self.cars
                ]
            }))

        for ev in events_out:
            packets.append((mk_hdr(bc_api.EVENT), ev))

        return packets
