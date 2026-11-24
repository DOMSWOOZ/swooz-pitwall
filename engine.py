"""Millisecond F1 Telemetry Analytics, Strategy Predictor, Radio Engineer & 50Hz Co-Pilot Engine."""
from __future__ import annotations

import collections
import math
import os
import re
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import bc_api
import card_strategist
import loadout_manager

RESULTS_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "race-results")

GRAVITY = 9.80665


def human_speech(text: str) -> str:
    """Strips underscores, CamelCase identifiers, and parenthetical codes for natural radio voice."""
    s = text.replace("_", " ")
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class CarAnalytics:
    """Per-car millisecond timing, tire degradation, physics & .0001 hardware stats."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.name = f"Car #{index + 1}"
        self.kind = "ai"
        self.car_type = "Formula"
        self.player_id = index

        # Timing & Standings
        self.position = index + 1
        self.class_position = index + 1
        self.start_grid: Optional[int] = None
        self.lap = 0
        self.last_lap_change_session_time: Optional[float] = None
        self.current_lap_elapsed_s = 0.0
        self.last_lap_s: Optional[float] = None
        self.best_lap_s: Optional[float] = None
        self.lap_history: List[Dict[str, Any]] = []

        self.gap_to_leader = 0.0
        self.interval_ahead = 0.0
        self.interval_behind = 0.0
        self.gap_samples: Deque[Tuple[float, float]] = collections.deque(maxlen=40)
        self.gap_rate_s_per_s = 0.0  # negative = catching leader

        # Pit & Flags
        self.in_pits = False
        self.prev_in_pits = False
        self.pit_planned = False
        self.finished = False
        self.api_driving = False
        self.pit_stops = 0

        # Tires & Energy
        self.tire_compound = "Standard"
        self.tire_health = 1.0
        self.puncture = False
        self.prev_puncture = False
        self.stint_laps = 0
        self.lap_start_tire_health: Optional[float] = None
        self.measured_wear_per_lap: Optional[float] = None
        self.health_samples: Deque[Tuple[float, float]] = collections.deque(maxlen=60)
        self.wear_per_sec = 0.0
        self.energy = 1.0

        # Telemetry & Physics
        self.speed_kmh = 0.0
        self.top_speed_kmh = 0.0
        self.pedal = 0.0
        self.steer = 0.0
        self.position_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.velocity_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.prev_vel_xyz: Optional[Tuple[float, float, float]] = None
        self.prev_motion_session_time: Optional[float] = None
        self.angular_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0

        self.long_g = 0.0
        self.lat_g = 0.0
        self.peak_total_g = 0.0
        self.wheels: List[Dict[str, Any]] = [
            {"on_track": True, "grounded": True, "slip_forward": 0.0, "slip_sideways": 0.0}
            for _ in range(4)
        ]
        self.understeer_index = 0.0
        self.off_track_count = 0
        self.was_off_track = False
        self.airborne_ms = 0.0

        # Abilities
        self.abilities: Dict[str, Any] = {
            "speed_boost": False,
            "cornering_boost": False,
            "super_boost": False,
            "party_mode": False,
            "drs": False,
            "boost_overspeed": False,
            "recharging": False,
            "super_boost_unlocked": False,
            "party_mode_unlocked": False,
            "drs_unlocked": False,
            "api_boosting": False,
            "ban_tokens": 0,
            "slipstream": 0.0,
            "recharge_left": 0.0,
        }

        # Car Status (8 Performance Areas)
        self.performance: Dict[str, float] = {area: 0.0 for area in bc_api.PERFORMANCE_AREAS}
        self.has_performance = False


class TelemetryEngine:
    """Processes 50 Hz packets into an F1 Pit Wall state and executes Co-Pilot / 50 Hz AI commands."""

    def __init__(self, command_sender: Callable[[str, Dict[str, Any]], None]) -> None:
        self.send_command = command_sender
        self.on_radio_emitted: Optional[Callable[[Dict[str, Any]], None]] = None
        self.selected_rival_car: Optional[int] = None

        # Co-pilot & Strategy Pace Mode settings
        self.copilot: Dict[str, Any] = {
            "lendurance_mode": False,      # Tailored Dom_Swooz LeMans G3->P1 (+1.901s) full-system dial-in
            "pace_mode": "balanced",       # conserve | balanced | attack | hammer
            "push_profile": "k1_super",    # k1_super | slingshot | apex_vector | overtake_dump
            "card_strategy": "p1_mimic",   # p1_mimic | super_boost | apex_grip | xp_snowball | ironman | lendurance
            "wear_mult": 1.0,              # 1.0 | 1.15 | 1.30 (pre-race Race Details card hint)
            "rain_forecast": "auto",       # auto | rain_soon | drying
            "auto_pit": False,
            "pit_cliff_threshold": 0.22,
            "auto_tire": False,
            "auto_card": False,
            "auto_boost": False,
            "auto_drive": False,
            "extreme_ai_sync": False,
        }
        self._was_auto_boosting = False
        self.loadout_mgr = loadout_manager.LoadoutManager()
        self.p1_blueprints: Dict[str, Any] = card_strategist.load_p1_blueprints(RESULTS_DIR_DEFAULT)
        self.extreme_ai_meta: Dict[str, Any] = card_strategist.load_extreme_ai_manifest()
        self.push_state: Dict[str, Any] = {
            "active": False,
            "hold": False,
            "profile": "k1_super",
            "until_mono": 0.0,
            "duration_s": 0.0,
            "custom_flags": None,  # Optional (speed, cornering, party) override
        }

        # Connection & bandwidth metrics
        self.last_live_packet_wall = 0.0
        self.packet_bytes_window: Deque[Tuple[float, int]] = collections.deque(maxlen=400)
        self.hello_state: Dict[str, Any] = {}
        self.command_log: Deque[Dict[str, Any]] = collections.deque(maxlen=40)
        self.radio_log: Deque[Dict[str, Any]] = collections.deque(maxlen=50)
        self.event_log: Deque[Dict[str, Any]] = collections.deque(maxlen=60)
        self._radio_cooldowns: Dict[str, float] = {}
        self._last_autopit_wall = 0.0
        self._last_autocard_wall = 0.0
        self._last_autotire_wall = 0.0
        self._radio_seq = 0
        self._request_seq = 100

        # Reset per-session state
        self.reset_session(0, simulated=True)

    def reset_session(self, session_uid: int, simulated: bool = False) -> None:
        self.session_uid = session_uid
        self.simulated = simulated
        self.game_version = "0.88.2"
        self.num_cars = 16
        self.frame = 0
        self.session_time = 0.0
        self.my_car_idx: int = bc_api.NO_CAR

        self.cars: List[CarAnalytics] = [CarAnalytics(i) for i in range(bc_api.MAX_CARS)]
        self.session_fastest_lap_s: Optional[float] = None
        self.session_fastest_car: Optional[int] = None

        self.session_info: Dict[str, Any] = {
            "session_type": "Race",
            "energy": "boost",
            "total_laps": 0,
            "player_input": False,
            "driver_input": False,
            "public_lobby": False,
            "weather": 0.0,
            "scene": "Waiting for Session...",
            "track": None,
        }
        self.weather_samples: Deque[Tuple[float, float]] = collections.deque(maxlen=80)
        self.weather_slope_per_min = 0.0

        self.player_state: Dict[str, Any] = {
            "points": 0,
            "hand": [],
            "upgrades_applied": 0,
            "total_laps": 0,
            "laps_remaining": 0,
            "pit_planned": False,
            "can_pit": False,
            "in_pits": False,
            "pit_stops": 0,
            "tire_compound": "Standard",
            "puncture": False,
            "tire_health": 1.0,
            "compound_picks_left": {c: None for c in bc_api.COMPOUNDS},
            "energy": 1.0,
            "strategy": None,
        }
        self.tire_screen_state: Optional[Dict[str, Any]] = None
        self.racing_line_points: List[Dict[str, Any]] = []
        self.ai_obs_state: Dict[str, Any] = {}
        self.ai_obs_by_car: Dict[int, Dict[str, Any]] = {}

        # Self-mapping circuit breadcrumbs (quantized spatial hash -> ordered trail)
        self.track_map_pts: Deque[Tuple[float, float, float]] = collections.deque(maxlen=420)
        self._last_map_pt: Optional[Tuple[float, float]] = None

        # High-rate oscilloscope trace & G-G circle trail for player's car
        self.trace_history: Deque[Dict[str, float]] = collections.deque(maxlen=150)
        self._last_trace_time = -1.0
        self.gg_trail: Deque[Tuple[float, float]] = collections.deque(maxlen=55)

        self._prev_weather_wet: Optional[bool] = None
        self._tire_milestones_fired: set[int] = set()
        self._prev_pit_planned: Optional[bool] = None
        self._last_picked_compound: Optional[str] = None
        self._last_picked_card_name: Optional[str] = None
        self._last_picked_card_fac: Optional[str] = None
        self._last_tire_callout_wall = -999.0
        self.installed_counts: Dict[str, int] = {}
        self.facility_xp: Dict[str, int] = {"Speed": 0, "Cornering": 0, "Performance": 0, "Boost": 0, "Fuel": 0}

    def reload_p1_blueprints(self, results_dir: str = RESULTS_DIR_DEFAULT) -> None:
        self.p1_blueprints = card_strategist.load_p1_blueprints(results_dir)

    def get_active_p1_blueprint(self) -> Optional[Dict[str, Any]]:
        scene = str(self.session_info.get("scene") or "").lower().replace("_gp", "").replace(" ", "")
        by_trk = self.p1_blueprints.get("by_track") or {}
        for tk, info in by_trk.items():
            if tk and (tk in scene or scene in tk):
                return info
        return self.p1_blueprints.get("latest_logged_p1")

    def next_request_id(self) -> int:
        self._request_seq += 1
        return self._request_seq

    def emit_radio(self, key: str, message: str, priority: str = "INFO", cooldown_s: float = 18.0) -> None:
        now = time.monotonic()
        if now - self._radio_cooldowns.get(key, -999.0) < cooldown_s:
            return
        self._radio_cooldowns[key] = now
        self._radio_seq += 1
        clean_msg = human_speech(message)
        entry = {
            "id": self._radio_seq,
            "time_s": round(self.session_time, 2),
            "wall_ts": time.strftime("%H:%M:%S"),
            "priority": priority,
            "message": clean_msg,
        }
        self.radio_log.appendleft(entry)
        if self.on_radio_emitted is not None:
            try:
                self.on_radio_emitted(entry)
            except Exception:
                pass

    def record_packet_bytes(self, nbytes: int, is_live: bool) -> None:
        now = time.monotonic()
        self.packet_bytes_window.append((now, nbytes))
        if is_live:
            self.last_live_packet_wall = now

    def ingest(self, header: Dict[str, Any], body: Dict[str, Any], raw_size: int = 0) -> None:
        is_sim = bool(header.get("simulated", False))
        self.record_packet_bytes(raw_size, is_live=not is_sim)

        pkt = header["packet"]
        if pkt in ("hello", "ack", "error"):
            self._handle_reply(pkt, header, body)
            return

        suid = header["session_uid"]
        if suid != 0 and (suid != self.session_uid or self.simulated != is_sim):
            self.reset_session(suid, simulated=is_sim)
            self.emit_radio(
                "session_start",
                f"{'Simulator' if is_sim else 'Live telemetry'} locked on session. Radio check loud and clear.",
                "INFO",
                cooldown_s=3.0,
            )

        self.game_version = header["game_version"]
        self.num_cars = min(header["num_cars"], bc_api.MAX_CARS)
        self.frame = header["frame"]
        self.session_time = header["session_time"]
        seat0 = header["seat_car"][0]
        if seat0 != bc_api.NO_CAR and seat0 < self.num_cars:
            self.my_car_idx = seat0

        if pkt == "motion":
            self._on_motion(body)
        elif pkt == "car_telemetry":
            self._on_car_telemetry(body)
        elif pkt == "lap_data":
            self._on_lap_data(body)
        elif pkt == "car_status":
            self._on_car_status(body)
        elif pkt == "player":
            self._on_player(body)
        elif pkt == "session":
            self._on_session(body)
        elif pkt == "participants":
            self._on_participants(body)
        elif pkt == "event":
            self._on_event(body)
        elif pkt == "car_abilities":
            self._on_car_abilities(body)
        elif pkt == "racing_line":
            self._on_racing_line(body)
        elif pkt == "ai_observations":
            self._on_ai_observations(body)

        # Run 50 Hz autonomous co-pilot loops when motion/racing_line updates arrive
        if pkt == "racing_line":
            self._tick_50hz_controllers()

    def _handle_reply(self, pkt: str, header: Dict[str, Any], body: Dict[str, Any]) -> None:
        if pkt == "hello":
            self.hello_state = dict(body)
        else:
            self.command_log.appendleft({
                "type": pkt.upper(),
                "command": body.get("command", "?"),
                "reason": body.get("reason", "ok"),
                "request_id": body.get("request_id", 0),
                "wall_ts": time.strftime("%H:%M:%S"),
            })
            if pkt == "ack":
                cmd = body.get("command", "")
                if cmd == "pick_tire":
                    cname = self._last_picked_compound or "selected"
                    self.emit_radio(f"ack_tire_{body.get('request_id')}", f"Copy, {cname} compound confirmed.", "INFO", cooldown_s=1.0)
                elif cmd == "pick_card":
                    upg_lbl = self._last_picked_card_name or "upgrade"
                    if self._last_picked_card_name:
                        self.installed_counts[self._last_picked_card_name] = self.installed_counts.get(self._last_picked_card_name, 0) + 1
                        fac_key = self._last_picked_card_fac if self._last_picked_card_fac in self.facility_xp else card_strategist.UPGRADE_PRIMARY_FACILITY.get(self._last_picked_card_name, "")
                        if fac_key in self.facility_xp and self._last_picked_card_fac not in ("Redline",):
                            self.facility_xp[fac_key] = min(6, self.facility_xp[fac_key] + 1)
                    self.emit_radio(f"ack_card_{body.get('request_id')}", f"Copy, {upg_lbl} upgrade installed.", "INFO", cooldown_s=0.8)
                elif cmd == "ban_card":
                    self.emit_radio(f"ack_ban_{body.get('request_id')}", "Card banned.", "INFO", cooldown_s=1.5)
            elif pkt == "error":
                reason = body.get("reason", "")
                if reason == "input_disabled":
                    self.emit_radio("err_input_off", "Player input is switched off in telemetry settings.", "WARN", cooldown_s=10.0)
                elif reason == "assist_on":
                    cmd_err = body.get("command", "")
                    if cmd_err in ("pick_card", "ban_card"):
                        self.emit_radio("err_assist_card", "In-game Upgrade Assist is blocking Auto Card — turn off Upgrade Assist in game settings.", "WARN", cooldown_s=12.0)
                    else:
                        self.emit_radio("err_assist_on", "In-game assist is overriding PitWall commands — turn off assists in game settings.", "WARN", cooldown_s=12.0)
                elif reason == "public_lobby":
                    self.emit_radio("err_pub_lobby", "Commands are locked in public lobbies.", "WARN", cooldown_s=15.0)

    def _on_motion(self, body: Dict[str, Any]) -> None:
        cars_data = body["cars"]
        for i, m in enumerate(cars_data):
            c = self.cars[i]
            pos = m["position"]
            vel = m["velocity"]
            ang = m["angular_velocity"]
            if c.prev_vel_xyz is not None and c.prev_motion_session_time is not None:
                dt = self.session_time - c.prev_motion_session_time
                if 0.004 <= dt <= 0.25:
                    dvx = (vel[0] - c.prev_vel_xyz[0]) / dt
                    dvz = (vel[2] - c.prev_vel_xyz[2]) / dt
                    # Car frame: x right, z forward, ang[1] yaw rate (rad/s)
                    raw_long_g = dvz / GRAVITY
                    raw_lat_g = (dvx + vel[2] * ang[1]) / GRAVITY
                    raw_long_g = max(-6.0, min(6.0, raw_long_g))
                    raw_lat_g = max(-6.0, min(6.0, raw_lat_g))
                    c.long_g = c.long_g * 0.68 + raw_long_g * 0.32
                    c.lat_g = c.lat_g * 0.68 + raw_lat_g * 0.32
                    tot_g = math.hypot(c.long_g, c.lat_g)
                    if tot_g > c.peak_total_g:
                        c.peak_total_g = tot_g

            c.prev_vel_xyz = vel
            c.prev_motion_session_time = self.session_time
            c.position_xyz = pos
            c.velocity_xyz = vel
            c.angular_velocity = ang
            c.pitch = m["pitch"]
            c.roll = m["roll"]
            c.yaw = m["yaw"]

            # Self-map circuit centerline from player car (or car 0)
            map_idx = self.my_car_idx if self.my_car_idx != bc_api.NO_CAR else 0
            if i == map_idx and not c.in_pits:
                if self._last_map_pt is None or math.hypot(pos[0] - self._last_map_pt[0], pos[2] - self._last_map_pt[1]) >= 6.5:
                    self.track_map_pts.append((round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)))
                    self._last_map_pt = (pos[0], pos[2])

        if self.my_car_idx != bc_api.NO_CAR and self.my_car_idx < self.num_cars:
            mc = self.cars[self.my_car_idx]
            if self.frame % 2 == 0:
                self.gg_trail.append((round(mc.lat_g, 3), round(mc.long_g, 3)))

    def _on_car_telemetry(self, body: Dict[str, Any]) -> None:
        for i, t in enumerate(body["cars"]):
            c = self.cars[i]
            c.speed_kmh = t["speed_kmh"]
            if c.speed_kmh > c.top_speed_kmh:
                c.top_speed_kmh = c.speed_kmh
            c.pedal = t["pedal"]
            c.steer = t["steer"]
            c.wheels = t["wheels"]
            c.tire_compound = str(t["tire_compound"])
            c.prev_puncture = c.puncture
            c.puncture = t["puncture"]
            new_health = t["tire_health"]

            # Detect tire reset (pit stop completed)
            if new_health > c.tire_health + 0.15:
                c.stint_laps = 0
                c.lap_start_tire_health = new_health
                c.health_samples.clear()
                if i == self.my_car_idx:
                    self._tire_milestones_fired.clear()

            c.tire_health = new_health
            c.energy = t["energy"]

            # Rolling wear per second
            if not c.in_pits and self.session_time > 1.0:
                if not c.health_samples or (self.session_time - c.health_samples[-1][0]) >= 0.25:
                    c.health_samples.append((self.session_time, new_health))
                    if len(c.health_samples) >= 6:
                        t0, h0 = c.health_samples[0]
                        t1, h1 = c.health_samples[-1]
                        if t1 > t0 + 0.8 and h0 >= h1:
                            c.wear_per_sec = (h0 - h1) / (t1 - t0)

            # 4-wheel slip balance & track limits
            fl, fr, rl, rr = c.wheels
            front_lat = (abs(fl["slip_sideways"]) + abs(fr["slip_sideways"])) * 0.5
            rear_lat = (abs(rl["slip_sideways"]) + abs(rr["slip_sideways"])) * 0.5
            c.understeer_index = c.understeer_index * 0.75 + (front_lat - rear_lat) * 0.25

            all_off = not any(w["on_track"] for w in c.wheels)
            if all_off and not c.was_off_track:
                c.off_track_count += 1
            c.was_off_track = all_off

            if not any(w["grounded"] for w in c.wheels) and c.speed_kmh > 20.0:
                c.airborne_ms += 20.0

            if i == self.my_car_idx and c.puncture and not c.prev_puncture:
                self.emit_radio(
                    "puncture_now",
                    "Puncture! We have a tire puncture! Box immediately!",
                    "CRITICAL",
                    cooldown_s=8.0,
                )

        # Record 20 Hz oscilloscope trace for player car
        if self.my_car_idx != bc_api.NO_CAR and (self.session_time - self._last_trace_time) >= 0.05:
            self._last_trace_time = self.session_time
            mc = self.cars[self.my_car_idx]
            max_slip = max(math.hypot(w["slip_forward"], w["slip_sideways"]) for w in mc.wheels)
            ai_act = self.ai_obs_state.get("action")
            self.trace_history.append({
                "t": round(self.session_time, 3),
                "speed": round(mc.speed_kmh, 1),
                "pedal": round(mc.pedal, 3),
                "steer": round(mc.steer, 3),
                "slip": round(min(1.5, max_slip), 3),
                "energy": round(mc.energy, 3),
                "ai_pedal": round(ai_act[0], 3) if ai_act else None,
                "ai_steer": round(ai_act[1], 3) if ai_act else None,
            })

    def _on_lap_data(self, body: Dict[str, Any]) -> None:
        for i, ld in enumerate(body["cars"]):
            c = self.cars[i]
            c.position = ld["position"]
            c.class_position = ld["class_position"]
            if c.start_grid is None and self.session_time < 5.0 and ld["position"] > 0:
                c.start_grid = ld["position"]

            new_lap = ld["lap"]
            if c.last_lap_change_session_time is None:
                c.last_lap_change_session_time = self.session_time
                c.lap_start_tire_health = c.tire_health
                c.lap = new_lap
            elif new_lap > c.lap:
                lap_dur = self.session_time - c.last_lap_change_session_time
                c.last_lap_change_session_time = self.session_time
                if 6.0 <= lap_dur <= 300.0:
                    c.last_lap_s = lap_dur
                    is_pb = c.best_lap_s is None or lap_dur < c.best_lap_s
                    if is_pb:
                        c.best_lap_s = lap_dur
                    is_purple = self.session_fastest_lap_s is None or lap_dur < self.session_fastest_lap_s
                    if is_purple:
                        self.session_fastest_lap_s = lap_dur
                        self.session_fastest_car = i
                        if i == self.my_car_idx:
                            self.emit_radio(
                                f"purple_{new_lap}",
                                f"Purple lap! Fastest on track: {lap_dur:.3f} seconds!",
                                "INFO",
                                cooldown_s=6.0,
                            )

                if c.lap_start_tire_health is not None and not c.in_pits:
                    dh = c.lap_start_tire_health - c.tire_health
                    if 0.002 <= dh <= 0.55:
                        c.measured_wear_per_lap = dh if c.measured_wear_per_lap is None else (0.35 * c.measured_wear_per_lap + 0.65 * dh)
                c.lap_start_tire_health = c.tire_health
                c.stint_laps += 1
                c.lap_history.append({
                    "lap": new_lap,
                    "time_s": round(lap_dur, 3) if 6.0 <= lap_dur <= 300.0 else None,
                    "pos": ld["position"],
                    "compound": c.tire_compound,
                    "tire_health": round(c.tire_health, 4),
                })
                c.lap = new_lap

            if c.last_lap_change_session_time is not None:
                c.current_lap_elapsed_s = max(0.0, self.session_time - c.last_lap_change_session_time)

            c.prev_in_pits = c.in_pits
            c.in_pits = ld["in_pits"]
            if c.in_pits and not c.prev_in_pits and i != self.my_car_idx and c.position <= 4:
                self.emit_radio(
                    f"rival_pit_{i}_{c.lap}",
                    f"Rival alert: P{c.position} {c.name} just entered the pit lane!",
                    "STRATEGY",
                    cooldown_s=10.0,
                )

            c.finished = ld["finished"]
            c.pit_planned = ld["pit_planned"]
            c.api_driving = ld["api_driving"]
            c.pit_stops = ld["pit_stops"]
            c.gap_to_leader = ld["gap_to_leader"]
            c.interval_ahead = ld["interval_ahead"]
            c.interval_behind = abs(ld["interval_behind"])

            if not c.gap_samples or (self.session_time - c.gap_samples[-1][0]) >= 0.25:
                c.gap_samples.append((self.session_time, c.gap_to_leader))
                if len(c.gap_samples) >= 6:
                    t0, g0 = c.gap_samples[0]
                    t1, g1 = c.gap_samples[-1]
                    if t1 > t0 + 0.8:
                        c.gap_rate_s_per_s = (g1 - g0) / (t1 - t0)

    def _on_car_status(self, body: Dict[str, Any]) -> None:
        for i, st in enumerate(body["cars"]):
            self.cars[i].performance = dict(st["performance"])
            self.cars[i].has_performance = True

    def _on_player(self, body: Dict[str, Any]) -> None:
        if body["seat"] != 0:
            return
        self.player_state = dict(body)
        strat = body.get("strategy")
        if strat and self.my_car_idx != bc_api.NO_CAR:
            mc = self.cars[self.my_car_idx]
            if strat.get("start_grid_position"):
                mc.start_grid = strat["start_grid_position"]
            mc.stint_laps = strat.get("tire_age_laps", mc.stint_laps)

        # Instant audio confirmation when pit_planned toggles (from UI OR controller!)
        cur_pit_planned = bool(body["pit_planned"])
        in_pits_now = bool(body["in_pits"])
        if self._prev_pit_planned is not None and cur_pit_planned != self._prev_pit_planned:
            stint_now = self.compute_stint_strategy()
            if cur_pit_planned:
                self.emit_radio(
                    f"pit_confirm_on_{self.frame}",
                    f"Box this lap confirmed — rejoin P{stint_now['rejoin_position']}.",
                    "STRATEGY",
                    cooldown_s=1.0,
                )
            elif not in_pits_now:
                self.emit_radio(
                    f"pit_confirm_off_{self.frame}",
                    f"Stay out confirmed — tires {stint_now['tire_health_pct']:.0f} percent.",
                    "STRATEGY",
                    cooldown_s=1.0,
                )
        self._prev_pit_planned = cur_pit_planned

        # Proactive Tire Health Milestone Callouts (75%, 50%, 35%, 25%, 15%)
        cliff = self.compute_stint_strategy()
        th_pct = body["tire_health"] * 100.0
        comp_name = body.get("tire_compound", "current")
        if not in_pits_now and self.session_time > 8.0 and body.get("laps_remaining", 1) > 0:
            for mark in (75, 50, 35, 25, 15):
                # Trigger once when health crosses below mark (but skip higher marks if stint started below them)
                if th_pct <= mark and mark not in self._tire_milestones_fired:
                    self._tire_milestones_fired.add(mark)
                    if th_pct < mark - 8:
                        continue  # Already well below this mark at session/demo start
                    if mark == 75:
                        self.emit_radio(
                            "th_m75",
                            f"Tires 75 percent, deg {cliff['wear_per_lap_pct']:.1f} a lap.",
                            "INFO",
                            cooldown_s=8.0,
                        )
                    elif mark == 50:
                        self.emit_radio(
                            "th_m50",
                            f"Half tire life, 50 percent — {cliff['laps_to_cliff']:.1f} laps to cliff.",
                            "INFO",
                            cooldown_s=8.0,
                        )
                    elif mark == 35:
                        self.emit_radio(
                            "th_m35",
                            f"Tires 35 percent! Pit window open, rejoin P{cliff['rejoin_position']}.",
                            "STRATEGY",
                            cooldown_s=8.0,
                        )
                    elif mark == 25:
                        msg_25 = (
                            "Tires 25 percent — box confirmed this lap."
                            if cur_pit_planned
                            else "Tires 25 percent — recommend boxing soon!"
                        )
                        self.emit_radio("th_m25", msg_25, "STRATEGY", cooldown_s=8.0)
                    elif mark == 15:
                        self.emit_radio(
                            "th_m15",
                            "Critical tires, 15 percent — box, box, box!",
                            "CRITICAL",
                            cooldown_s=6.0,
                        )
                    self._last_tire_callout_wall = time.monotonic()
                    break

        # Evaluate critical auto-pit & repeated cliff reminder (ONLY when current tires are actually worn to cliff!)
        if (
            cliff["risk_level"] in ("CRITICAL", "PUNCTURE")
            and not cur_pit_planned
            and not in_pits_now
            and body["can_pit"]
            and body["laps_remaining"] >= 1
            and self.session_time > 8.0
            and (body.get("puncture") or th_pct <= cliff["cliff_pct"] + 4.5)
        ):
            if (time.monotonic() - self._last_tire_callout_wall) > 8.0:
                self._last_tire_callout_wall = time.monotonic()
                self.emit_radio(
                    "cliff_critical",
                    f"Box, box! Tire health {th_pct:.0f} percent — at the {cliff['cliff_pct']:.0f} percent cliff, box this lap!",
                    "CRITICAL",
                    cooldown_s=22.0,
                )
            if self.copilot["auto_pit"] and (time.monotonic() - self._last_autopit_wall) > 2.0:
                self.try_auto_pit(force=True)

        # Explicit Fuel-race low-fuel warning (never triggers in ERS Boost races)
        if (
            self.session_info.get("energy") == "fuel"
            and not in_pits_now
            and not cur_pit_planned
            and body.get("can_pit")
            and body.get("laps_remaining", 0) >= 1
            and self.session_time > 12.0
            and body.get("energy", 1.0) <= 0.12
        ):
            self.emit_radio(
                "fuel_critical",
                f"Low fuel warning, {body['energy']*100:.0f} percent fuel remaining — box this lap to refuel!",
                "CRITICAL",
                cooldown_s=22.0,
            )

        # Continuously evaluate Auto-Card & Auto-Tire on live player state (handles multi-point hands & mid-race toggles!)
        if self.copilot["auto_card"] and body.get("points", 0) > 0 and body.get("hand"):
            self.try_auto_card(force=False)
        if self.copilot["auto_tire"] and (self.tire_screen_state is not None or in_pits_now):
            self.try_auto_tire(force=False)

    def _on_session(self, body: Dict[str, Any]) -> None:
        self.session_info = dict(body)
        w = body["weather"]
        if not self.weather_samples or (self.session_time - self.weather_samples[-1][0]) >= 0.5:
            self.weather_samples.append((self.session_time, w))
            if len(self.weather_samples) >= 4:
                t0, w0 = self.weather_samples[0]
                t1, w1 = self.weather_samples[-1]
                if t1 > t0 + 1.5:
                    self.weather_slope_per_min = ((w1 - w0) / (t1 - t0)) * 60.0

        is_wet = w > 0.0
        if self._prev_weather_wet is not None and is_wet != self._prev_weather_wet:
            if is_wet:
                self.emit_radio("rain_start", "Rain on track — Wet tires optimal!", "CRITICAL", cooldown_s=20.0)
            else:
                self.emit_radio("rain_stop", "Track drying — Slicks optimal!", "STRATEGY", cooldown_s=20.0)
        self._prev_weather_wet = is_wet

    def _on_participants(self, body: Dict[str, Any]) -> None:
        for i, p in enumerate(body["cars"]):
            c = self.cars[i]
            c.player_id = p["player_id"]
            c.car_type = str(p["car_type"])
            c.kind = str(p["kind"])
            if p["name"]:
                c.name = p["name"]

    def _on_event(self, body: Dict[str, Any]) -> None:
        code = body["code"]
        ev_entry = {"code": code, "time_s": round(self.session_time, 2), "details": dict(body)}
        self.event_log.appendleft(ev_entry)

        if body.get("seat") not in (None, 0):
            return

        if code == "TIRE":
            self.tire_screen_state = dict(body)
            rec = self.recommend_compound(body.get("allowed", bc_api.COMPOUNDS), body.get("picks_left", {}))
            self.emit_radio("tire_open", f"Tire menu open — recommend {rec['compound']} compound.", "STRATEGY", cooldown_s=4.0)
            if self.copilot["auto_tire"] and rec["compound"]:
                self._last_picked_compound = rec["compound"]
                self.send_command("pick_tire", {"compound": rec["compound"], "request_id": self.next_request_id()})
        elif code == "PITI":
            self.emit_radio(f"piti_{self.frame}", "In the pit lane, limiter active.", "INFO", cooldown_s=5.0)
        elif code == "PITO":
            self.tire_screen_state = None
            self._tire_milestones_fired.clear()
            comp_now = self.player_state.get("tire_compound", "fresh")
            self.emit_radio(
                f"pito_{self.frame}",
                f"Pit exit clear! Fresh {comp_now} tires on at 100 percent — push now!",
                "STRATEGY",
                cooldown_s=4.0,
            )
        elif code == "CARD":
            scored = self.evaluate_cards(body.get("hand", []))
            playable = [c for c in scored if not c["banned"]]
            if playable:
                best = max(playable, key=lambda x: x["ev_score"])
                if self.copilot["auto_card"]:
                    self._last_picked_card_name = str(best["upgrade"])
                    self._last_picked_card_fac = str(best.get("facility", ""))
                    self._last_autocard_wall = time.monotonic()
                    self.send_command("pick_card", {"index": best["index"], "request_id": self.next_request_id()})
                else:
                    self.emit_radio(
                        f"card_{self.frame}",
                        f"Upgrade ready — top call is {best['upgrade']}.",
                        "STRATEGY",
                        cooldown_s=6.0,
                    )
        elif code == "LAPC":
            laps_rem = self.player_state.get("laps_remaining", 99)
            th = self.player_state.get("tire_health", 1.0) * 100.0
            comp_now = self.player_state.get("tire_compound", "Standard")
            w_now = self.session_info.get("weather", 0.0)
            pit_plan = self.player_state.get("pit_planned", False)
            cliff = self.compute_stint_strategy()
            pos_now = body.get("position", "?")
            lap_num = body.get("lap", 0)

            need_wets = (
                (w_now > 0.09 and comp_now not in ("Wet", "Golden", "Standard"))
                or (w_now > 0.28 and comp_now != "Wet")
            )
            if need_wets and not pit_plan and laps_rem >= 1:
                self.emit_radio(
                    f"wet_mismatch_{lap_num}",
                    f"Lap {lap_num}, P{pos_now}. Rain intensity rising on {comp_now}s — recommend boxing for Wet tires!",
                    "STRATEGY",
                    cooldown_s=14.0,
                )
            elif w_now < -0.08 and comp_now == "Wet" and not pit_plan and laps_rem >= 1:
                self.emit_radio(
                    f"dry_mismatch_{lap_num}",
                    f"Lap {lap_num}, P{pos_now}. Track is dry, overheating Wets at {th:.0f} percent — box for slicks!",
                    "STRATEGY",
                    cooldown_s=8.0,
                )
            elif laps_rem == 1:
                end_note = (
                    "plenty of tire to attack to the flag"
                    if cliff["projected_finish_pct"] >= 18
                    else "tires are right on the limit, manage wheelspin"
                )
                self.emit_radio(
                    "final_lap",
                    f"Final lap! P{pos_now}, {comp_now} tires at {th:.0f} percent — {end_note}!",
                    "STRATEGY",
                    cooldown_s=8.0,
                )
            elif lap_num >= 1 and (time.monotonic() - self._last_tire_callout_wall) > 7.0:
                self._last_tire_callout_wall = time.monotonic()
                stint_note = (
                    "good to the flag"
                    if cliff["projected_finish_pct"] >= 20
                    else (f"{cliff['laps_to_cliff']:.1f} laps to cliff" if cliff["laps_to_cliff"] >= 1.0 else "in the cliff window, box soon")
                )
                self.emit_radio(
                    f"lapc_th_{lap_num}",
                    f"Lap {lap_num}, P{pos_now}. {comp_now} tires {th:.0f} percent, deg {cliff['wear_per_lap_pct']:.1f} a lap — {stint_note}.",
                    "INFO",
                    cooldown_s=7.0,
                )
        elif code == "FINI":
            self.emit_radio("fini_flag", f"Checkered flag! P{body.get('position')} finish, bring her back to parc ferme.", "INFO", cooldown_s=5.0)
        elif code == "PITW":
            cliff = self.compute_stint_strategy()
            cur_h = float(self.player_state.get("tire_health", 1.0))
            cliff_thr = float(self.copilot["pit_cliff_threshold"])
            if self.copilot["auto_pit"] and body.get("can_pit"):
                should_pit = (
                    bool(self.player_state.get("puncture"))
                    or (
                        cur_h <= cliff_thr + 0.04
                        and cliff["projected_next_lap_health"] < cliff_thr
                        and self.player_state.get("laps_remaining", 0) >= 1
                    )
                )
                if should_pit and not body.get("pit_planned", False):
                    self.send_command("set_pit", {"pit": True, "request_id": self.next_request_id()})

    def _on_car_abilities(self, body: Dict[str, Any]) -> None:
        for i, ab in enumerate(body["cars"]):
            self.cars[i].abilities = dict(ab)

    def _on_racing_line(self, body: Dict[str, Any]) -> None:
        if body["seat"] == 0:
            self.racing_line_points = body["points"]

    def _on_ai_observations(self, body: Dict[str, Any]) -> None:
        cidx = int(body.get("car", -1))
        if cidx < 0 or cidx >= len(self.cars):
            return
        car_obj = self.cars[cidx]
        entry = {
            "car": cidx,
            "driver_name": car_obj.name,
            "pos": car_obj.position,
            "policy": body.get("policy", ""),
            "policy_name": body.get("policy_name", ""),
            "obs_frame": body.get("obs_frame", 0),
            "action": body.get("action", [0.0, 0.0]),
        }
        self.ai_obs_by_car[cidx] = entry
        # Sync oscilloscope ghost overlay to player car (if AI-driven) OR locked Target Rival / P1 Race Leader!
        rv = self._resolve_rival_car()
        target_idx = self.my_car_idx if self.my_car_idx in self.ai_obs_by_car else (rv.index if rv.index in self.ai_obs_by_car else cidx)
        self.ai_obs_state = self.ai_obs_by_car.get(target_idx, entry)

    # ------------------------------------------------------------------ Autonomous Co-Pilot Evaluators

    def apply_extreme_ai_sync(self, active: bool, results_dir: str = RESULTS_DIR_DEFAULT) -> Dict[str, Any]:
        """Syncs SWOOZ PitWall to Backseat Champions' 80,721-race `extreme_ai_models` + latest P1 blueprint."""
        self.p1_blueprints = card_strategist.load_p1_blueprints(results_dir)
        self.extreme_ai_meta = card_strategist.load_extreme_ai_manifest()
        if active:
            self.copilot.update({
                "extreme_ai_sync": True,
                "lendurance_mode": False,
                "pace_mode": "attack",
                "push_profile": "super_comms",
                "card_strategy": "extreme_ai",
                "pit_cliff_threshold": 0.26,
                "auto_pit": True,
                "auto_tire": True,
                "auto_card": True,
                "auto_boost": True,
            })
        else:
            self.copilot.update({
                "extreme_ai_sync": False,
                "pace_mode": "balanced",
                "card_strategy": "p1_mimic",
                "pit_cliff_threshold": 0.22,
            })
        return dict(self.copilot)

    def apply_lendurance_preset(self, active: bool) -> Dict[str, Any]:
        """Dials in (or disengages) Dom_Swooz's L'Endurance (LeMans) G3->P1 (+1.901s) race package."""
        if active:
            self.copilot.update({
                "lendurance_mode": True,
                "extreme_ai_sync": False,
                "pace_mode": "balanced",
                "push_profile": "slingshot",
                "card_strategy": "lendurance",
                "pit_cliff_threshold": 0.10,
                "auto_pit": True,
                "auto_tire": True,
                "auto_card": True,
                "auto_boost": True,
            })
        else:
            self.copilot.update({
                "lendurance_mode": False,
                "push_profile": "k1_super",
                "card_strategy": "p1_mimic",
                "pit_cliff_threshold": 0.22,
            })
        return dict(self.copilot)

    def try_auto_pit(self, force: bool = False) -> bool:
        if not self.copilot.get("auto_pit"):
            return False
        now = time.monotonic()
        if not force and (now - self._last_autopit_wall) < 2.0:
            return False
        can_pit = bool(self.player_state.get("can_pit", True))
        pit_planned = bool(self.player_state.get("pit_planned", False))
        in_pits = bool(self.player_state.get("in_pits", False))
        laps_rem = int(self.player_state.get("laps_remaining", 1))
        if not can_pit or pit_planned or in_pits or laps_rem < 1:
            return False
        cliff = self.compute_stint_strategy()
        cur_h = float(self.player_state.get("tire_health", 1.0))
        cliff_thr = float(self.copilot.get("pit_cliff_threshold", 0.22))
        mode = str(self.copilot.get("pace_mode", "balanced"))
        mc = self.cars[self.my_car_idx] if self.my_car_idx != bc_api.NO_CAR else self.cars[0]
        air_status = str(cliff.get("air_status", ""))

        # Mode-specific tactical pit intelligence:
        # - Conserve Overcut Filter: if rejoin is heavy TRAFFIC, stretch down to 12% to jump traffic!
        # - Balanced Clean-Air Undercut: if trapped <0.85s behind rival at <=26% and rejoin is CLEAN AIR, undercut early!
        # - Attack Aggressive Undercut: if held up <0.95s behind rival at <=32% and rejoin is not heavy TRAFFIC, undercut now!
        undercut_reason = ""
        if bool(self.player_state.get("puncture")):
            should_pit = True
            undercut_reason = "puncture emergency"
        elif self.copilot.get("lendurance_mode"):
            # Dom's L'Endurance P1 Stint Rule: 15.87s pit lane + 5.85km laps!
            # Never pit on final lap if projected finish >= 4% (Dom won P1 crossing at 8.6%!),
            # otherwise stretch stint deep into the 7.5%-10% cliff window to save a full 15.87s stop!
            if laps_rem <= 1 and float(cliff.get("projected_finish_pct", 0.0)) >= 4.0:
                should_pit = False
            elif cur_h <= 0.13 and cliff["projected_next_lap_health"] < 0.095:
                should_pit = True
                undercut_reason = "L'Endurance deep-stint 10 percent window"
            else:
                should_pit = False
        elif mode == "conserve" and "TRAFFIC" in air_status and cur_h > 0.125:
            should_pit = False
        elif mode == "balanced" and 0.05 < mc.interval_ahead < 0.85 and cur_h <= 0.26 and air_status == "CLEAN AIR" and laps_rem >= 2:
            should_pit = True
            undercut_reason = "clean-air undercut"
        elif mode == "attack" and 0.05 < mc.interval_ahead < 0.95 and cur_h <= 0.32 and "TRAFFIC" not in air_status and laps_rem >= 2:
            should_pit = True
            undercut_reason = "aggressive undercut"
        else:
            should_pit = cur_h <= cliff_thr + 0.04 and cliff["projected_next_lap_health"] < cliff_thr

        if should_pit:
            self._last_autopit_wall = now
            self.send_command("set_pit", {"pit": True, "request_id": self.next_request_id()})
            why = f" ({undercut_reason})" if undercut_reason else ""
            self.emit_radio("autopit_exec", f"Pit Guard armed box this lap{why} at {cur_h*100:.0f} percent tire health.", "STRATEGY", cooldown_s=12.0)
            return True
        return False

    def try_auto_tire(self, force: bool = False) -> bool:
        if not self.copilot.get("auto_tire"):
            return False
        now = time.monotonic()
        if not force and (now - self._last_autotire_wall) < 1.5:
            return False
        allowed = (self.tire_screen_state or {}).get("allowed", bc_api.COMPOUNDS)
        picks_left = self.player_state.get("compound_picks_left", {})
        rec = self.recommend_compound(allowed, picks_left)
        comp = rec.get("compound")
        if not comp:
            return False
        # Only dispatch if tire screen is open, car is in pits, or simulator is active (where pre-selecting next_compound is supported)
        if self.tire_screen_state is not None or self.player_state.get("in_pits") or self.simulated:
            if not force and self._last_picked_compound == comp:
                return False
            self._last_autotire_wall = now
            self._last_picked_compound = comp
            self.send_command("pick_tire", {"compound": comp, "request_id": self.next_request_id()})
            return True
        return False

    def try_auto_card(self, force: bool = False) -> bool:
        if not self.copilot.get("auto_card"):
            return False
        now = time.monotonic()
        if not force and (now - self._last_autocard_wall) < 0.65:
            return False
        pts = int(self.player_state.get("points", 0))
        hand = self.player_state.get("hand") or []
        if pts <= 0 or not hand:
            return False
        scored = self.evaluate_cards(hand)
        playable = [c for c in scored if not c.get("banned")]
        if not playable:
            return False
        my_idx = self.my_car_idx if self.my_car_idx != bc_api.NO_CAR else 0
        ban_tokens = int(self.cars[my_idx].abilities.get("ban_tokens", 0))
        best = max(playable, key=lambda x: x["ev_score"])
        worst = min(playable, key=lambda x: x["ev_score"])
        mode = str(self.copilot.get("pace_mode", "balanced"))
        ban_ceil = 58.0 if mode == "hammer" else (55.0 if mode == "attack" else 52.0)
        # Smart Ban: mode-aware threshold so Hammer/Attack aggressively clear low-tempo cards for power upgrades!
        if ban_tokens > 0 and len(playable) > 1 and best["ev_score"] < ban_ceil and worst["ev_score"] < (ban_ceil - 4.0):
            self._last_autocard_wall = now
            self.send_command("ban_card", {"index": int(worst["index"]), "request_id": self.next_request_id()})
            return True
        self._last_autocard_wall = now
        self._last_picked_card_name = str(best["upgrade"])
        self._last_picked_card_fac = str(best.get("facility", ""))
        self.send_command("pick_card", {"index": int(best["index"]), "request_id": self.next_request_id()})
        return True

    # ------------------------------------------------------------------ 50 Hz Autonomous & Tactical Push Controllers

    def trigger_tactical_push(
        self,
        profile: Optional[str] = None,
        hold: Optional[bool] = None,
        active: bool = True,
        duration_s: Optional[float] = None,
        custom_flags: Optional[Tuple[bool, bool, bool]] = None,
    ) -> Dict[str, Any]:
        """Engage, hold, or cancel a 50 Hz Tactical Overtake / Super-Boost Push profile."""
        now = time.monotonic()
        if not active:
            was_on = self.push_state.get("active") or self.push_state.get("hold")
            self.push_state["active"] = False
            self.push_state["hold"] = False
            self.push_state["until_mono"] = 0.0
            self.push_state["custom_flags"] = None
            if was_on:
                self._was_auto_boosting = False
                self.send_command("boost", {"buttons": 0, "request_id": 0})
            return dict(self.push_state)

        raw_prof = (profile or self.copilot.get("push_profile") or "k1_super")
        slot_cfg = self.loadout_mgr.get_push_slot(raw_prof)
        prof = str(slot_cfg["id"])
        dur = float(duration_s) if duration_s is not None else float(slot_cfg.get("duration_s", 3.0))
        is_hold = bool(hold) if hold is not None else False
        self.push_state.update({
            "active": True,
            "hold": is_hold,
            "profile": prof,
            "duration_s": dur,
            "until_mono": (now + 30.0) if is_hold else (now + dur),
            "custom_flags": custom_flags,
        })
        return dict(self.push_state)

    def _tick_50hz_controllers(self) -> None:
        if self.my_car_idx == bc_api.NO_CAR or self.my_car_idx >= self.num_cars:
            return
        mc = self.cars[self.my_car_idx]
        mode = str(self.copilot.get("pace_mode", "balanced"))

        # 1) Pure-Pursuit + Curvature Speed Controller (50 Hz AI Driver — Pace-Mode Tuned!)
        if self.copilot["auto_drive"] and self.racing_line_points:
            pts = self.racing_line_points
            cx, _, cz = mc.position_xyz
            speed_mps = max(mc.velocity_xyz[2], mc.speed_kmh / 3.6)

            look_idx = min(len(pts) - 1, max(1, int(speed_mps / 14.0)))
            tx, _, tz = pts[look_idx]["racing_line"]
            target_yaw = math.degrees(math.atan2(tx - cx, tz - cz))
            yaw_err = (target_yaw - mc.yaw + 180.0) % 360.0 - 180.0
            steer_cmd = max(-1.0, min(1.0, (yaw_err / 24.0) - mc.angular_velocity[1] * 0.045))

            max_angle_change = 0.0
            for k in range(min(len(pts) - 2, 12)):
                p0 = pts[k]["racing_line"]
                p1 = pts[k + 1]["racing_line"]
                p2 = pts[k + 2]["racing_line"]
                a1 = math.atan2(p1[0] - p0[0], p1[2] - p0[2])
                a2 = math.atan2(p2[0] - p1[0], p2[2] - p1[2])
                da = abs((a2 - a1 + math.pi) % (2.0 * math.pi) - math.pi)
                seg_d = math.hypot(p1[0] - p0[0], p1[2] - p0[2])
                curv = da / max(seg_d, 1.0)
                if curv > max_angle_change:
                    max_angle_change = curv

            pace_corner_mult = {"conserve": 0.96, "balanced": 1.00, "attack": 1.035, "hammer": 1.06}.get(mode, 1.0)
            grip_scale = (0.85 + 0.15 * mc.tire_health) * pace_corner_mult
            if self.session_info.get("weather", 0.0) > 0.02 and mc.tire_compound != "Wet":
                grip_scale *= 0.82
            max_top = 90.0 if mode in ("attack", "hammer") else (85.0 if mode == "conserve" else 88.0)
            target_speed_mps = max_top if max_angle_change < 0.004 else min(max_top, (24.0 / math.sqrt(max_angle_change)) * grip_scale)

            speed_err = target_speed_mps - speed_mps
            if speed_err >= 0:
                rear_spin = max(mc.wheels[2]["slip_forward"], mc.wheels[3]["slip_forward"])
                spin_tol = 0.28 if mode == "conserve" else (0.42 if mode == "hammer" else 0.35)
                tc_trim = max(0.35, 1.0 - max(0.0, rear_spin - spin_tol) * 1.4)
                pedal_cmd = min(1.0, (0.35 + speed_err * 0.12) * tc_trim)
            else:
                front_lock = abs(min(mc.wheels[0]["slip_forward"], mc.wheels[1]["slip_forward"], 0.0))
                abs_trim = max(0.4, 1.0 - max(0.0, front_lock - 0.25) * 1.5)
                pedal_cmd = max(-1.0, (speed_err * 0.14) * abs_trim)

            self.send_command("drive", {"pedal": pedal_cmd, "steer": steer_cmd, "request_id": 0})

        # 2) Unified 50 Hz Tactical PUSH Override + Pace-Mode ERS / Party-Mode Controller
        now = time.monotonic()
        ab = mc.abilities
        energy_type = self.session_info.get("energy", "boost")
        buttons = 0

        # 2a) Active Manual PUSH / Hold-Both-Boosts Tactical Profile (highest priority!)
        if self.push_state.get("active"):
            prof = str(self.push_state.get("profile", "k1_super"))
            slot_cfg = self.loadout_mgr.get_push_slot(prof)
            e_floor = max(0.015, float(slot_cfg.get("energy_floor", 0.02)) * 0.75)
            if now >= float(self.push_state.get("until_mono", 0.0)) or mc.in_pits or (energy_type == "boost" and mc.energy <= e_floor):
                self.push_state["active"] = False
                self.push_state["hold"] = False
                self.push_state["custom_flags"] = None
            elif not ab.get("recharging"):
                cflags = self.push_state.get("custom_flags")
                if cflags is not None:
                    sp, co, pa = cflags
                    buttons = (bc_api.BOOST_SPEED if sp else 0) | (bc_api.BOOST_CORNERING if co else 0) | (bc_api.BOOST_PARTY_MODE if pa else 0)
                else:
                    buttons = loadout_manager.compute_push_buttons(slot_cfg, mc, ab, energy_type)

        # 2b) Autonomous Pace-Mode ERS / Party-Mode Deployment (when manual PUSH isn't overriding)
        if buttons == 0 and self.copilot["auto_boost"] and not self.push_state.get("active"):
            if not ab.get("recharging") and not mc.in_pits:
                in_hunt_window = 0.03 < mc.interval_ahead < 1.80
                under_threat = 0.03 < mc.interval_behind < 0.85
                if energy_type == "boost":
                    if self.copilot.get("lendurance_mode"):
                        # L'Endurance Mulsanne Straight Sniper (99.8% straight, 6 DRS zones):
                        # Zero boost wasted in the 6 tight 12.5m/s chicanes; full straight-line deploy above 18% reserve!
                        if mc.energy > 0.18 and abs(mc.steer) < 0.13 and mc.pedal > 0.82:
                            buttons |= bc_api.BOOST_SPEED
                            if ab.get("super_boost_unlocked") and abs(mc.steer) < 0.08 and (mc.energy > 0.28 or in_hunt_window or under_threat):
                                buttons |= bc_api.BOOST_CORNERING
                    else:
                        reserves = {"conserve": 0.55, "balanced": 0.28, "attack": 0.12, "hammer": 0.02}
                        min_e = reserves.get(mode, 0.28)
                        if mc.energy > min_e:
                            if mode == "conserve":
                                # Lift & Coast / Tow Harvest: straight-line draft (>20%) or defending <0.65s behind ONLY!
                                if abs(mc.steer) < 0.09 and mc.pedal > 0.85 and (ab.get("slipstream", 0.0) > 0.20 or (0.01 < mc.interval_behind < 0.65)):
                                    buttons |= bc_api.BOOST_SPEED
                            elif mode == "balanced":
                                # Optimal ROI + Closing Assist (<1.4s ahead unlocks dual Super Boost above 42% charge)
                                if abs(mc.steer) < 0.14 and mc.pedal > 0.78:
                                    buttons |= bc_api.BOOST_SPEED
                                    if ab.get("super_boost_unlocked") and (mc.energy > 0.48 or (mc.energy > 0.40 and 0.03 < mc.interval_ahead < 1.40)):
                                        buttons |= bc_api.BOOST_CORNERING
                                elif abs(mc.lat_g) > 1.45 and mc.pedal > 0.40 and mc.energy > 0.40:
                                    buttons |= bc_api.BOOST_CORNERING
                            elif mode == "attack":
                                # Predatory Gap Hunter: escalates to Dual Super Boost on exits whenever hunting (<1.8s) or defending (<0.85s)!
                                thr_gate = 0.48 if (in_hunt_window or under_threat) else 0.58
                                if abs(mc.steer) < 0.24 and mc.pedal > thr_gate:
                                    buttons |= bc_api.BOOST_SPEED
                                    if ab.get("super_boost_unlocked") and (mc.energy > 0.20 or in_hunt_window or under_threat):
                                        buttons |= bc_api.BOOST_CORNERING
                                elif abs(mc.lat_g) > 0.92 and mc.pedal > 0.28:
                                    buttons |= bc_api.BOOST_CORNERING
                            elif mode == "hammer":
                                # Bono, Empty The Tank: Q3 Sprint — pins Both Boosts on any throttle & Cornering through every apex!
                                if mc.pedal > 0.26:
                                    buttons |= bc_api.BOOST_SPEED | bc_api.BOOST_CORNERING
                                elif abs(mc.lat_g) > 0.58:
                                    buttons |= bc_api.BOOST_CORNERING
                elif energy_type == "fuel" and ab.get("party_mode_unlocked"):
                    if mode == "balanced" and mc.energy > 0.55 and 0.03 < mc.interval_ahead < 1.10 and mc.pedal > 0.75:
                        buttons |= bc_api.BOOST_PARTY_MODE
                    elif mode == "attack" and mc.energy > 0.30 and mc.pedal > 0.60:
                        buttons |= bc_api.BOOST_PARTY_MODE
                    elif mode == "hammer" and mc.energy > 0.10 and mc.pedal > 0.30:
                        buttons |= bc_api.BOOST_PARTY_MODE

        if buttons != 0:
            self._was_auto_boosting = True
            self.send_command("boost", {"buttons": buttons, "request_id": 0})
        elif self._was_auto_boosting:
            self._was_auto_boosting = False
            self.send_command("boost", {"buttons": 0, "request_id": 0})

    # ------------------------------------------------------------------ Strategy & Analytics Models

    def get_reference_lap_s(self) -> float:
        if self.my_car_idx != bc_api.NO_CAR:
            mc = self.cars[self.my_car_idx]
            if mc.last_lap_s and 8.0 <= mc.last_lap_s <= 240.0:
                return mc.last_lap_s
            if mc.best_lap_s:
                return mc.best_lap_s
        strat = self.player_state.get("strategy")
        if strat and strat.get("reference_lap_s", 0) > 5.0:
            return strat["reference_lap_s"]
        trk = self.session_info.get("track")
        if trk and trk.get("lap_time_est_s", 0) > 5.0:
            return trk["lap_time_est_s"]
        return 28.0

    def compute_stint_strategy(self) -> Dict[str, Any]:
        ref_lap_s = self.get_reference_lap_s()
        mc = self.cars[self.my_car_idx] if self.my_car_idx != bc_api.NO_CAR else self.cars[0]
        health = self.player_state.get("tire_health", mc.tire_health)
        total_laps = self.player_state.get("total_laps") or self.session_info.get("total_laps") or 0
        laps_rem_int = self.player_state.get("laps_remaining", max(0, total_laps - mc.lap))
        lap_frac = min(0.99, mc.current_lap_elapsed_s / max(ref_lap_s, 5.0)) if laps_rem_int > 0 else 0.0
        laps_rem_exact = max(0.0, laps_rem_int - lap_frac + (1.0 if laps_rem_int > 0 and lap_frac > 0 else 0.0))
        if total_laps > 0:
            laps_rem_exact = max(0.0, float(total_laps) - (mc.lap + lap_frac))

        # Combine measured lap wear, rolling wear/sec * ref_lap_s, and track base_tire_wear_rate * wear_mult
        trk = self.session_info.get("track") or {}
        wear_mult = float(self.copilot.get("wear_mult", 1.0))
        base_wear = (trk.get("base_tire_wear_rate") or 0.075) * wear_mult
        sec_wear_lap = mc.wear_per_sec * ref_lap_s if mc.wear_per_sec > 0.0002 else None

        if mc.measured_wear_per_lap is not None and sec_wear_lap is not None:
            wear_per_lap = 0.65 * mc.measured_wear_per_lap + 0.35 * sec_wear_lap
            wear_source = "Measured Lap + Live Rate"
        elif mc.measured_wear_per_lap is not None:
            wear_per_lap = mc.measured_wear_per_lap
            wear_source = "Measured Lap Delta"
        elif sec_wear_lap is not None:
            wear_per_lap = sec_wear_lap
            wear_source = "Live 50Hz Slope"
        else:
            wear_per_lap = base_wear
            wear_source = f"Track Base ({wear_mult:.2f}x)"

        mode = str(self.copilot.get("pace_mode", "balanced"))
        is_lend = bool(self.copilot.get("lendurance_mode"))
        mode_cliffs = {"conserve": 0.15, "balanced": 0.22, "attack": 0.28, "hammer": 0.32}
        cliff_level = mode_cliffs.get(mode, 0.22)
        if is_lend:
            # Dom's L'Endurance P1 Cliff: 10% deep stint (7.5% L3 box), 4% final-lap hold (8.6% L5 win!)
            cliff_level = 0.04 if laps_rem_exact <= 1.08 else 0.10
        elif mode == "hammer" and laps_rem_exact <= 2.05:
            cliff_level = 0.14
        self.copilot["pit_cliff_threshold"] = cliff_level

        wear_per_lap = max(0.005, wear_per_lap)
        laps_to_zero = health / wear_per_lap
        laps_to_cliff = max(0.0, (health - cliff_level) / wear_per_lap)
        proj_finish_health = health - wear_per_lap * laps_rem_exact
        proj_next_lap_health = health - wear_per_lap * (1.0 - lap_frac + 0.15)
        mode_tag = "L'ENDURANCE" if is_lend else mode.upper()

        if mc.puncture:
            risk = "PUNCTURE"
            verdict = "PUNCTURE ACTIVE — BOX IMMEDIATELY!"
        elif laps_rem_exact > 0.25 and (
            health <= cliff_level
            or health <= min(0.16, cliff_level + 0.01)
            or (health <= cliff_level + 0.04 and proj_next_lap_health < cliff_level)
        ):
            risk = "CRITICAL"
            verdict = f"BOX THIS LAP! [{mode_tag}] Tires {health*100:.0f}% (Cliff {cliff_level*100:.0f}%)"
        elif laps_rem_exact > 0.35 and (health <= cliff_level + 0.10 or laps_to_cliff <= 1.5):
            risk = "CAUTION"
            verdict = f"PIT WINDOW OPEN [{mode_tag}] — ~{laps_to_cliff:.1f}L to {cliff_level*100:.0f}% cliff"
        elif proj_finish_health >= cliff_level or laps_rem_exact <= 0.35:
            risk = "NOMINAL"
            verdict = f"[{mode_tag}] CLEAR TO FLAG — Proj {max(0.0, proj_finish_health)*100:.0f}% at finish"
        else:
            risk = "NOMINAL"
            stint_cap = max(1.5, (1.0 - cliff_level) / wear_per_lap)
            stops_est = max(1, math.ceil(max(0.1, laps_rem_exact - laps_to_cliff) / stint_cap))
            verdict = f"[{mode_tag}] {stops_est}-STOP PACE — Box in ~{laps_to_cliff:.1f}L (Cliff {cliff_level*100:.0f}%)"

        # Pit Rejoin Simulation using exact gap_to_leader + pit_lane_time_loss_s
        pit_loss_s = trk.get("pit_lane_time_loss_s") or 6.500
        my_gap = mc.gap_to_leader
        post_pit_gap = my_gap + pit_loss_s

        active_cars = sorted(self.cars[:self.num_cars], key=lambda x: x.position)
        others = [x for x in active_cars if x.index != mc.index]
        cars_ahead_after = [x for x in others if x.gap_to_leader < post_pit_gap]
        cars_behind_after = [x for x in others if x.gap_to_leader >= post_pit_gap]

        rejoin_pos = len(cars_ahead_after) + 1
        ahead_car = cars_ahead_after[-1] if cars_ahead_after else None
        behind_car = cars_behind_after[0] if cars_behind_after else None
        margin_ahead_s = (post_pit_gap - ahead_car.gap_to_leader) if ahead_car else None
        margin_behind_s = (behind_car.gap_to_leader - post_pit_gap) if behind_car else None

        nearby_traffic = sum(1 for x in others if abs(x.gap_to_leader - post_pit_gap) <= 2.2)
        if nearby_traffic == 0:
            air_status = "CLEAN AIR"
        elif nearby_traffic == 1:
            air_status = "SINGLE RIVAL"
        else:
            air_status = f"TRAFFIC ({nearby_traffic} CARS)"

        return {
            "tire_health_pct": round(health * 100.0, 2),
            "wear_per_lap_pct": round(wear_per_lap * 100.0, 2),
            "cliff_pct": round(cliff_level * 100.0, 0),
            "pace_mode": mode,
            "wear_source": wear_source,
            "laps_remaining_exact": round(laps_rem_exact, 2),
            "laps_to_cliff": round(laps_to_cliff, 2),
            "laps_to_zero": round(laps_to_zero, 2),
            "projected_finish_pct": round(proj_finish_health * 100.0, 1),
            "projected_next_lap_health": round(proj_next_lap_health, 4),
            "risk_level": risk,
            "verdict": verdict,
            "pit_loss_s": round(pit_loss_s, 3),
            "rejoin_position": rejoin_pos,
            "positions_lost": max(0, rejoin_pos - mc.position),
            "rejoin_ahead": {"name": ahead_car.name, "pos": ahead_car.position, "gap_s": round(margin_ahead_s, 3)} if ahead_car and margin_ahead_s is not None else None,
            "rejoin_behind": {"name": behind_car.name, "pos": behind_car.position, "gap_s": round(margin_behind_s, 3)} if behind_car and margin_behind_s is not None else None,
            "air_status": air_status,
        }

    def build_compound_profiles(
        self, allowed: List[str], picks_left: Dict[str, Optional[int]]
    ) -> List[Dict[str, Any]]:
        """Computes live +/- pace delta, stint life, wear/lap, and suitability for all 7 compounds."""
        w = self.session_info.get("weather", 0.0)
        slope = self.weather_slope_per_min
        energy_mode = self.session_info.get("energy", "boost")
        ref_lap_s = self.get_reference_lap_s()
        total_laps = max(1, self.player_state.get("total_laps") or self.session_info.get("total_laps") or 12)
        laps_rem = max(1, self.player_state.get("laps_remaining") or (total_laps - (self.cars[self.my_car_idx].lap if self.my_car_idx != bc_api.NO_CAR else 0)))
        race_frac_left = laps_rem / total_laps

        trk = self.session_info.get("track") or {}
        wear_mult_hint = float(self.copilot.get("wear_mult", 1.0))
        base_std_wear = (trk.get("base_tire_wear_rate") or 0.075) * wear_mult_hint

        mc = self.cars[self.my_car_idx] if self.my_car_idx != bc_api.NO_CAR else self.cars[0]
        # Normalize live measured wear back to Standard 1.0x baseline if we already have track data
        cur_wear_factors = {
            "Standard": 1.00, "Fast": 1.42, "Durable": 0.56, "Boost": 0.94,
            "Experimental": 1.06, "Wet": (0.92 if w > 0.02 else min(5.0, 1.5 + abs(w) * 3.5)), "Golden": 0.96,
        }
        if mc.measured_wear_per_lap and mc.measured_wear_per_lap > 0.01:
            cf = cur_wear_factors.get(mc.tire_compound, 1.0)
            base_std_wear = max(0.02, min(0.35, mc.measured_wear_per_lap / cf))

        mode = str(self.copilot.get("pace_mode", "balanced"))
        fcst = str(self.copilot.get("rain_forecast", "auto"))
        strat = self.player_state.get("strategy") or {}
        battling = (strat.get("cars_within_5s_ahead", 0) + strat.get("cars_within_5s_behind", 0)) >= 2

        profiles: List[Dict[str, Any]] = []
        for comp in bc_api.COMPOUNDS:
            pl = picks_left.get(comp)
            usable = (comp in allowed) and (pl is None or pl > 0)
            pros: List[str] = []
            cons: List[str] = []

            if comp == "Standard":
                pace_s = 0.0 if w <= 0.0 else -(w * 0.65)
                w_factor = 1.00
                wet_tag = "LIGHT WET OK"
                pros = ["+Slight grip in light rain", "+Unlimited sets · safe 1-stop baseline"]
                cons = ["-Slowest dry compound", "-No XP, boost, or upgrade buffs"]
                opt = 54.0 + (12.0 if 0.0 < w <= 0.18 else 0.0) + (8.0 if mode == "balanced" else 0.0)

            elif comp == "Fast":
                # Patch 0.88.2 Balance: Slightly reduced base speed + wears MORE while battling in traffic!
                dry_gain = -0.024 * ref_lap_s
                pace_s = dry_gain if w <= 0.0 else (dry_gain + w * 4.2)
                w_factor = 1.62 if battling else 1.45
                wet_tag = "0% WET GRIP"
                pros = [
                    "+#1 Fastest dry sprint compound",
                    "+Bonus XP on every overtake",
                ]
                cons = [
                    "-Wears FASTER in traffic battles (v0.88.2!)" if battling else "-Wears more while battling (v0.88.2)",
                    "-Shortest lifespan (extra pit stop)",
                    "-Zero grip in rain" if w > -0.02 else "-High degradation per lap",
                ]
                opt = 71.0 + (20.0 if mode in ("attack", "hammer") else (-18.0 if mode == "conserve" else 0.0))
                if battling:
                    opt -= 14.0
                if self.copilot.get("lendurance_mode") and laps_rem >= 2:
                    opt -= 24.0
                    cons.insert(0, "-L'Endurance: 5.85km lap burns Softs -> +15.87s extra stop")
                elif laps_rem <= 4 and w <= 0.02:
                    opt += 18.0
                if w > 0.03:
                    opt -= 55.0

            elif comp == "Durable":
                dry_loss = +0.012 * ref_lap_s
                pace_s = dry_loss if w <= 0.0 else (dry_loss + w * 3.9)
                w_factor = 0.56
                wet_tag = "0% WET GRIP"
                pros = [
                    "+Longest life (no-stop / overcut)",
                    "+Gains tire life, fuel & XP when rivals pit",
                    "+Recharges boost every lap",
                ]
                cons = ["-One of the slowest raw compounds", "-Zero wet-weather grip"]
                opt = 62.0 + (28.0 if mode == "conserve" else (-20.0 if mode in ("attack", "hammer") else 0.0))
                if self.copilot.get("lendurance_mode") and laps_rem >= 2 and w <= 0.02:
                    opt += 20.0
                elif laps_rem * base_std_wear > 0.72 and w <= 0.02 and fcst != "rain_soon":
                    opt += 18.0
                if fcst == "rain_soon" and w <= 0.02:
                    opt -= 22.0
                    cons.insert(0, "-Rain soon: wastes Durable stint")
                if w > 0.03:
                    opt -= 55.0

            elif comp == "Boost":
                dry_gain = -0.014 * ref_lap_s
                pace_s = dry_gain if w <= 0.0 else (dry_gain + w * 3.7)
                w_factor = 0.93
                wet_tag = "0% WET GRIP"
                if energy_mode == "fuel":
                    pros = ["++Boosts Fuel Performance & Party Mode", "+Consistent pace & solid tire life"]
                else:
                    pros = ["++Boost capacity, regen & strength", "+Consistent pace & solid tire life"]
                cons = ["-No extra XP multiplier", "-Zero wet-weather grip"]
                opt = 68.0 + (10.0 if mode in ("balanced", "attack") else 0.0)
                if self.copilot.get("lendurance_mode") and w <= 0.02:
                    opt += 25.0
                    pros.insert(0, "+Dom's L'Endurance P1 Winning Compound (6-DRS Mulsanne!)")
                if w > 0.03:
                    opt -= 52.0

            elif comp == "Experimental":
                dry_loss = +0.009 * ref_lap_s
                pace_s = dry_loss if w <= 0.0 else (dry_loss + w * 3.9)
                w_factor = 1.06
                wet_tag = "0% WET GRIP"
                pros = ["+++Massive XP gain while driving", "+Early-race upgrade slingshot (stacks w/ Sensor)"]
                cons = ["-2nd slowest tire (trades pos for XP)", "-Low value late in race" if race_frac_left < 0.4 else "-Zero wet grip"]
                opt = 60.0 + (22.0 if race_frac_left > 0.62 and w <= 0.02 else -18.0)
                if mode == "hammer":
                    opt -= 16.0
                if w > 0.03:
                    opt -= 55.0

            elif comp == "Wet":
                if w > 0.02:
                    pace_s = -(0.65 + w * 3.1)
                    w_factor = 0.90
                else:
                    pace_s = +(0.60 + abs(w) * 1.5)
                    w_factor = min(5.0, 1.55 + abs(w) * 3.45)
                wet_tag = "HEAVY RAIN KING"
                pros = ["+#1 Fastest in rain", "+More XP the harder it rains", "+Unlimited sets"]
                cons = [f"-Burns {w_factor:.1f}x faster on dry asphalt!" if w <= 0.02 else "-Overheats fast once track dries"]
                if w > 0.12:
                    opt = 97.0
                elif w > 0.02 or (w > -0.05 and (slope > 0.08 or fcst == "rain_soon")):
                    opt = 88.0
                else:
                    opt = 12.0

            else:  # Golden
                if w <= 0.0:
                    pace_s = -0.013 * ref_lap_s
                elif w <= 0.32:
                    pace_s = -(0.45 + w * 1.8)
                else:
                    pace_s = -(0.20) + (w - 0.32) * 1.9
                w_factor = 0.95
                wet_tag = "GREAT LIGHT RAIN"
                pros = [
                    "++Extends Golden Upgrade duration",
                    "+Great grip in light / changeable rain",
                    "+Moderately buffs Boost & Fuel",
                ]
                cons = ["-Requires maxed Performance facility", "-Beaten by Wets in heavy storms"]
                opt = 78.0 + (14.0 if 0.0 <= w <= 0.28 else 0.0) + (10.0 if mode in ("attack", "hammer") and w <= 0.25 else 0.0)
                if w > 0.38:
                    opt -= 24.0

            wear_lap = max(0.015, base_std_wear * w_factor)
            est_laps = round(1.0 / wear_lap, 1)
            cliff_lvl = float(self.copilot.get("pit_cliff_threshold", 0.22))
            safe_laps = round(max(0.0, (1.0 - cliff_lvl) / wear_lap), 1)
            makes_flag = safe_laps >= laps_rem

            if not usable:
                opt = max(0.0, opt - 40.0)

            profiles.append({
                "compound": comp,
                "usable": usable,
                "picks_left": pl,
                "pace_delta_s": round(pace_s, 2),
                "wear_pct_lap": round(wear_lap * 100.0, 1),
                "est_laps": est_laps,
                "safe_laps": safe_laps,
                "makes_flag": makes_flag,
                "wet_tag": wet_tag,
                "optimal_score": round(max(2.0, min(99.0, opt)), 0),
                "pros": pros,
                "cons": cons,
            })

        return profiles

    def recommend_compound(self, allowed: List[str], picks_left: Dict[str, Optional[int]]) -> Dict[str, str]:
        w = self.session_info.get("weather", 0.0)
        slope = self.weather_slope_per_min
        laps_rem = self.player_state.get("laps_remaining", 8)
        trk = self.session_info.get("track") or {}
        wear_mult = float(self.copilot.get("wear_mult", 1.0))
        base_wear = (trk.get("base_tire_wear_rate") or 0.07) * wear_mult
        mode = str(self.copilot.get("pace_mode", "balanced"))
        fcst = str(self.copilot.get("rain_forecast", "auto"))

        def can_use(c: str) -> bool:
            if c not in allowed:
                return False
            pl = picks_left.get(c)
            return pl is None or pl > 0

        # 1) Wet weather or forecast crossovers
        if (w > 0.02 or (w > -0.05 and (slope > 0.08 or fcst == "rain_soon"))) and can_use("Wet"):
            if fcst != "drying" or w > 0.14:
                return {"compound": "Wet", "reason": "Wet conditions active"}

        # If pre-race forecast says rain arriving soon while still dry, don't burn a Durable set!
        if fcst == "rain_soon" and w <= 0.02:
            for short_c in ("Fast", "Standard", "Boost", "Experimental"):
                if can_use(short_c):
                    return {"compound": short_c, "reason": "Short dry stint before rain"}

        # 1b) Dom's L'Endurance (LeMans 5.85km) Dry Compound Lock: Boost -> Durable (saves 15.87s extra stop!)
        if self.copilot.get("lendurance_mode"):
            if laps_rem <= 1:
                for sp_c in ("Golden", "Fast", "Boost", "Standard"):
                    if can_use(sp_c):
                        return {"compound": sp_c, "reason": "L'Endurance final-lap sprint"}
            for end_c in ("Boost", "Durable", "Golden", "Standard"):
                if can_use(end_c):
                    return {"compound": end_c, "reason": "Dom's L'Endurance P1 Mulsanne compound"}

        # 2) Mode-driven Dry Compound Strategy (Conserve <-> Hammer Time)
        if mode == "conserve":
            if laps_rem <= 2:
                for sprint_c in ("Golden", "Fast", "Standard", "Durable"):
                    if can_use(sprint_c):
                        return {"compound": sprint_c, "reason": "Final 2L sprint"}
            for long_c in ("Durable", "Standard", "Golden", "Boost", "Fast"):
                if can_use(long_c):
                    return {"compound": long_c, "reason": "Conserve mode — max stint life"}

        if mode in ("attack", "hammer"):
            order = ("Golden", "Fast", "Experimental", "Boost", "Standard", "Durable")
            for agg_c in order:
                if can_use(agg_c):
                    lbl = "Hammer max grip" if mode == "hammer" else "Attack undercut pace"
                    return {"compound": agg_c, "reason": lbl}

        # Balanced mode
        if laps_rem <= 4:
            for fast_c in ("Golden", "Fast", "Boost", "Experimental"):
                if can_use(fast_c):
                    return {"compound": fast_c, "reason": f"Short {laps_rem}L sprint to flag"}
        if laps_rem * base_wear > 0.72 and can_use("Durable"):
            return {"compound": "Durable", "reason": "High total stint wear"}
        for pref in ("Golden", "Standard", "Boost", "Fast", "Durable"):
            if can_use(pref):
                return {"compound": pref, "reason": "Balanced pace & life"}
        return {"compound": allowed[0] if allowed else "Standard", "reason": "Available set"}

    def evaluate_cards(self, hand: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        trk = self.session_info.get("track") or {}
        straight_ratio = trk.get("straight_ratio", 0.55)
        wear_rate = trk.get("base_tire_wear_rate", 0.07)
        weather = self.session_info.get("weather", 0.0)
        energy_mode = self.session_info.get("energy", "boost")
        total_laps = max(1, self.player_state.get("total_laps") or 15)
        laps_rem = self.player_state.get("laps_remaining", 8)
        race_frac_left = laps_rem / total_laps

        mc = self.cars[self.my_car_idx] if self.my_car_idx != bc_api.NO_CAR else self.cars[0]
        rival = self._resolve_rival_car()
        active_cars = self.cars[:max(1, self.num_cars)]

        stat_map = {
            "EnginePower": "EngineTorque",
            "TurboCharger": "Acceleration",
            "Gearbox": "Acceleration",
            "DragReduction": "Drag",
            "Downforce": "Downforce",
            "Suspension": "Suspension",
            "TireGrip": "TractionControl",
            "TractionControl": "TractionControl",
            "WeightReduction": "Weight",
        }

        scored = []
        for card in hand:
            upg = str(card["upgrade"])
            fac = str(card["facility"])
            tier = int(card["tier"])
            score = 56.0 + tier * 12.0
            reasons = []

            # 1) Check real-time .0001 stat balance vs Rival & Field Average (prevents over-stacking Drag!)
            mapped_stat = stat_map.get(upg)
            if mapped_stat and mc.has_performance:
                my_v = mc.performance.get(mapped_stat, 0.0)
                rv_v = rival.performance.get(mapped_stat, 0.0)
                avg_v = sum(c.performance.get(mapped_stat, 0.0) for c in active_cars) / len(active_cars)
                deficit_rv = my_v - rv_v
                lead_avg = my_v - avg_v
                if deficit_rv < -0.025:
                    score += min(20.0, abs(deficit_rv) * 130.0)
                    reasons.append(f"Fixes {deficit_rv:+.3f} {mapped_stat} gap")
                elif lead_avg > 0.085:
                    score -= 18.0
                    reasons.append(f"Already +{lead_avg:.2f} above avg")

            # 2) Track layout & live rain conditions
            if weather > 0.02:
                if upg in ("TireGrip", "TractionControl", "Downforce", "Suspension"):
                    score += 17.0
                    reasons.append("Critical wet-weather grip")
                elif upg == "DragReduction":
                    score -= 10.0

            if upg in ("EnginePower", "TurboCharger", "Gearbox"):
                score += (straight_ratio - 0.45) * 26.0
                if straight_ratio > 0.70 and weather <= 0.02:
                    reasons.append("Power track")
            elif upg == "DragReduction":
                score += (straight_ratio - 0.50) * 20.0
            elif upg in ("Downforce", "Suspension", "TireGrip", "TractionControl", "EngineBraking"):
                score += (0.72 - straight_ratio) * 26.0

            if upg == "WeightReduction":
                score += 12.0
                if not reasons:
                    reasons.append("All-sector pace & tire life")
            if upg == "TireSaving":
                if wear_rate * float(self.copilot.get("wear_mult", 1.0)) > 0.072 or mc.tire_health < 0.48:
                    score += 15.0
                    reasons.append("Extends stint window")

            # 3) Deep Strategy Pace Mode Card Bias (Conserve <-> Hammer)
            mode = str(self.copilot.get("pace_mode", "balanced"))
            if mode == "conserve":
                if upg in ("TireSaving", "FuelEfficiency"):
                    score += 24.0
                    reasons.append("Conserve 1-stop priority")
                elif upg in ("WeightReduction", "Suspension", "TractionControl"):
                    score += 12.0
                elif upg == "BoostOverspeed":
                    score -= 12.0
            elif mode == "attack":
                if upg in ("EnginePower", "TurboCharger", "TireGrip", "Downforce", "BoostRechargeSpeed", "FuelPerformance"):
                    score += 18.0
                    reasons.append("Attack undercut weapon")
            elif mode == "hammer":
                if upg in ("TurboCharger", "EnginePower", "BoostOverspeed", "TireGrip", "FuelPerformance"):
                    score += 26.0
                    reasons.append("Hammer Q3 sprint max")
                elif upg in ("ExperienceGain", "TireSaving"):
                    score -= 25.0
            if upg == "ExperienceGain":
                if race_frac_left > 0.60:
                    score += 19.0
                    reasons.append("Early XP snowball")
                elif race_frac_left < 0.28:
                    score -= 26.0
                    reasons.append("Too late in race")
            if fac in ("Redline", "Augment"):
                score += 6.0
                reasons.append(f"{fac} synergy")
            if upg in ("BoostCapacity", "BoostPerSector", "BoostRechargeSpeed", "BoostOverspeed"):
                score += 10.0 if energy_mode == "boost" else -28.0
            if upg in ("FuelCapacity", "FuelEfficiency", "FuelPerformance", "RefuelSpeed", "FuelWeight"):
                score += 12.0 if energy_mode == "fuel" else -28.0
            if upg == "Reroll":
                score -= 14.0

            # 4) In-Depth Auto-Card Build Archetype & Last-P1 Podium Blueprint Engine!
            c_strat = str(self.copilot.get("card_strategy", "p1_mimic"))
            c_slot = None if c_strat == "lendurance" else self.loadout_mgr.get_card_slot(c_strat)
            strat_bonus, strat_notes = card_strategist.apply_card_strategy_bonus(
                upg=upg,
                fac=fac,
                tier=tier,
                strategy=c_strat,
                race_frac_left=race_frac_left,
                energy_mode=energy_mode,
                weather=weather,
                facility_xp=self.facility_xp,
                installed_counts=self.installed_counts,
                active_p1=self.get_active_p1_blueprint(),
                custom_slot=c_slot,
            )
            score += strat_bonus
            # Put strategy/blueprint rationale first so the UI card tag clearly shows why it's picked!
            combined_reasons = strat_notes + reasons

            ev = round(max(5.0, min(99.0, score)), 1)
            scored.append({
                **card,
                "ev_score": ev,
                "reason": " · ".join(combined_reasons[:2]) if combined_reasons else f"{fac} Tier {tier + 1}",
            })

        playable = [c for c in scored if not c["banned"]]
        best_idx = max(playable, key=lambda x: x["ev_score"])["index"] if playable else None
        worst_idx = min(playable, key=lambda x: x["ev_score"])["index"] if len(playable) > 1 else None
        for c in scored:
            c["recommended"] = c["index"] == best_idx
            c["ban_candidate"] = c["index"] == worst_idx and c["ev_score"] < 58.0
        return scored

    def _resolve_rival_car(self) -> CarAnalytics:
        my_idx = self.my_car_idx if self.my_car_idx != bc_api.NO_CAR else 0
        if self.selected_rival_car is not None and 0 <= self.selected_rival_car < self.num_cars and self.selected_rival_car != my_idx:
            return self.cars[self.selected_rival_car]
        mc = self.cars[my_idx]
        target_pos = 2 if mc.position == 1 else max(1, mc.position - 1)
        for c in self.cars[:self.num_cars]:
            if c.position == target_pos and c.index != my_idx:
                return c
        return self.cars[(my_idx + 1) % max(1, self.num_cars)]

    def build_hardware_comparison(self) -> Dict[str, Any]:
        my_idx = self.my_car_idx if self.my_car_idx != bc_api.NO_CAR else 0
        mc = self.cars[my_idx]
        rival = self._resolve_rival_car()
        active = self.cars[:self.num_cars]

        areas_out = []
        for area in bc_api.PERFORMANCE_AREAS:
            vals = [c.performance.get(area, 0.0) for c in active]
            field_max = max(vals) if vals else 0.0
            field_avg = (sum(vals) / len(vals)) if vals else 0.0
            my_val = mc.performance.get(area, 0.0)
            rv_val = rival.performance.get(area, 0.0)
            rank = 1 + sum(1 for v in vals if v > my_val + 1e-7)
            areas_out.append({
                "area": area,
                "mine": round(my_val, 4),
                "rival": round(rv_val, 4),
                "delta_vs_rival": round(my_val - rv_val, 4),
                "delta_vs_best": round(my_val - field_max, 4),
                "field_best": round(field_max, 4),
                "field_avg": round(field_avg, 4),
                "rank": rank,
            })

        return {
            "my_car": {"index": mc.index, "name": mc.name, "pos": mc.position},
            "rival_car": {"index": rival.index, "name": rival.name, "pos": rival.position, "locked": self.selected_rival_car is not None},
            "areas": areas_out,
        }

    def snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        # Prune bandwidth window to last 2.0s
        while self.packet_bytes_window and now - self.packet_bytes_window[0][0] > 2.0:
            self.packet_bytes_window.popleft()
        window_span = max(0.5, (now - self.packet_bytes_window[0][0]) if len(self.packet_bytes_window) > 1 else 1.0)
        kbps = sum(b for _, b in self.packet_bytes_window) / window_span / 1024.0
        pps = len(self.packet_bytes_window) / window_span
        live_connected = (now - self.last_live_packet_wall) < 2.5

        my_idx = self.my_car_idx if self.my_car_idx != bc_api.NO_CAR else 0
        mc = self.cars[my_idx]
        ref_lap = self.get_reference_lap_s()

        # Weather forecast
        w = self.session_info.get("weather", 0.0)
        slope = self.weather_slope_per_min
        rain_eta_s: Optional[float] = None
        if w <= 0.0 and slope > 0.015:
            rain_eta_s = round(((0.0 - w) / slope) * 60.0, 1)
        elif w > 0.0 and slope < -0.015:
            rain_eta_s = round(((w - 0.0) / abs(slope)) * 60.0, 1)

        standings = []
        for c in sorted(self.cars[:self.num_cars], key=lambda x: (x.position if x.position > 0 else 99, x.index)):
            rel_gap_rate_lap = (c.gap_rate_s_per_s - mc.gap_rate_s_per_s) * ref_lap
            standings.append({
                "index": c.index,
                "is_me": c.index == my_idx,
                "is_rival": c.index == self._resolve_rival_car().index,
                "pos": c.position,
                "grid_delta": (c.start_grid - c.position) if c.start_grid else 0,
                "name": c.name,
                "kind": c.kind,
                "car_type": c.car_type,
                "lap": c.lap,
                "last_lap_s": round(c.last_lap_s, 3) if c.last_lap_s else None,
                "best_lap_s": round(c.best_lap_s, 3) if c.best_lap_s else None,
                "is_purple": self.session_fastest_car == c.index and self.session_fastest_lap_s is not None,
                "gap_to_leader": round(c.gap_to_leader, 3),
                "interval_ahead": round(c.interval_ahead, 3),
                "interval_behind": round(c.interval_behind, 3),
                "closing_s_per_lap": round(rel_gap_rate_lap, 3),
                "compound": c.tire_compound,
                "tire_health_pct": round(c.tire_health * 100.0, 2),
                "puncture": c.puncture,
                "stint_laps": c.stint_laps,
                "pit_stops": c.pit_stops,
                "in_pits": c.in_pits,
                "pit_planned": c.pit_planned,
                "api_driving": c.api_driving,
                "speed_kmh": round(c.speed_kmh, 1),
                "energy_pct": round(c.energy * 100.0, 1),
                "drs": c.abilities.get("drs", False),
                "boost": any(c.abilities.get(k, False) for k in ("speed_boost", "cornering_boost", "super_boost", "party_mode")),
                "slipstream": round(c.abilities.get("slipstream", 0.0), 2),
                "weight_diff": round(c.performance.get("Weight", 0.0) - mc.performance.get("Weight", 0.0), 4),
                "torque_diff": round(c.performance.get("EngineTorque", 0.0) - mc.performance.get("EngineTorque", 0.0), 4),
                "performance": {k: round(v, 4) for k, v in c.performance.items()},
                "xyz": [round(c.position_xyz[0], 2), round(c.position_xyz[1], 2), round(c.position_xyz[2], 2)],
                "yaw": round(c.yaw, 1),
            })

        return {
            "connection": {
                "mode": "LIVE_UDP" if (live_connected and not self.simulated) else ("SIM_DEMO" if self.simulated else "WAITING"),
                "live_connected": live_connected,
                "simulated": self.simulated,
                "game_version": self.hello_state.get("game_version") or self.game_version,
                "kbps": round(kbps, 1),
                "pps": round(pps, 0),
                "hello": self.hello_state,
            },
            "session": {
                **self.session_info,
                "session_uid": self.session_uid,
                "frame": self.frame,
                "session_time": round(self.session_time, 3),
                "weather": round(w, 4),
                "weather_slope_per_min": round(slope, 4),
                "rain_eta_s": rain_eta_s,
                "fastest_lap_s": round(self.session_fastest_lap_s, 3) if self.session_fastest_lap_s else None,
                "fastest_driver": self.cars[self.session_fastest_car].name if self.session_fastest_car is not None else None,
            },
            "telemetry": {
                "car_index": mc.index,
                "name": mc.name,
                "pos": mc.position,
                "lap": mc.lap,
                "current_lap_s": round(mc.current_lap_elapsed_s, 3),
                "last_lap_s": round(mc.last_lap_s, 3) if mc.last_lap_s else None,
                "best_lap_s": round(mc.best_lap_s, 3) if mc.best_lap_s else None,
                "speed_kmh": round(mc.speed_kmh, 2),
                "top_speed_kmh": round(mc.top_speed_kmh, 1),
                "pedal": round(mc.pedal, 4),
                "steer": round(mc.steer, 4),
                "long_g": round(mc.long_g, 3),
                "lat_g": round(mc.lat_g, 3),
                "total_g": round(math.hypot(mc.long_g, mc.lat_g), 3),
                "peak_g": round(mc.peak_total_g, 2),
                "pitch": round(mc.pitch, 2),
                "roll": round(mc.roll, 2),
                "yaw": round(mc.yaw, 2),
                "wheels": [
                    {
                        "on_track": w_item["on_track"],
                        "grounded": w_item["grounded"],
                        "slip_f": round(w_item["slip_forward"], 3),
                        "slip_s": round(w_item["slip_sideways"], 3),
                    }
                    for w_item in mc.wheels
                ],
                "understeer_index": round(mc.understeer_index, 4),
                "off_track_count": mc.off_track_count,
                "airborne_ms": round(mc.airborne_ms, 0),
                "energy_pct": round(mc.energy * 100.0, 2),
                "abilities": mc.abilities,
                "lap_history": mc.lap_history[-16:],
                "gg_trail": list(self.gg_trail),
                "traces": list(self.trace_history)[-90:],
                "ai_obs": self.ai_obs_state,
            },
            "stint": self.compute_stint_strategy(),
            "hardware": self.build_hardware_comparison(),
            "cards": {
                "points": self.player_state.get("points", 0),
                "upgrades_applied": self.player_state.get("upgrades_applied", 0),
                "ban_tokens": mc.abilities.get("ban_tokens", 0),
                "hand": self.evaluate_cards(self.player_state.get("hand", [])),
                "strategy": self.copilot.get("card_strategy", "p1_mimic"),
                "facility_xp": dict(self.facility_xp),
                "p1_blueprint": self.get_active_p1_blueprint(),
                "human_p1": self.p1_blueprints.get("latest_human_p1"),
                "lendurance_profile": card_strategist.LENDURANCE_P1_PROFILE,
                "castellet_profile": card_strategist.CASTELLET_P1_PROFILE,
                "extreme_ai": self.extreme_ai_meta,
            },
            "tires": {
                "current": mc.tire_compound,
                "queued": self._last_picked_compound,
                "picks_left": self.player_state.get("compound_picks_left", {}),
                "modal": self.tire_screen_state,
                "profiles": self.build_compound_profiles(
                    (self.tire_screen_state or {}).get("allowed", bc_api.COMPOUNDS),
                    self.player_state.get("compound_picks_left", {}),
                ),
                "recommendation": self.recommend_compound(
                    (self.tire_screen_state or {}).get("allowed", bc_api.COMPOUNDS),
                    self.player_state.get("compound_picks_left", {}),
                ),
            },
            "pit": {
                "pit_planned": self.player_state.get("pit_planned", mc.pit_planned),
                "can_pit": self.player_state.get("can_pit", True),
                "in_pits": self.player_state.get("in_pits", mc.in_pits),
                "pit_stops": mc.pit_stops,
            },
            "map": {
                "track_pts": list(self.track_map_pts),
                "racing_line": [
                    {
                        "c": [round(p["racing_line"][0], 2), round(p["racing_line"][2], 2)],
                        "l": [round(p["left"][0], 2), round(p["left"][2], 2)],
                        "r": [round(p["right"][0], 2), round(p["right"][2], 2)],
                    }
                    for p in self.racing_line_points
                ],
            },
            "standings": standings,
            "copilot": {
                **self.copilot,
                "push_active": bool(self.push_state.get("active") and now < float(self.push_state.get("until_mono", 0.0))),
                "push_hold": bool(self.push_state.get("hold")),
                "push_remaining_s": round(max(0.0, float(self.push_state.get("until_mono", 0.0)) - now), 2) if self.push_state.get("active") else 0.0,
                "push_active_profile": self.push_state.get("profile", self.copilot.get("push_profile", "k1_super")),
            },
            "loadouts": self.loadout_mgr.get_state(),
            "radio": list(self.radio_log)[:18],
            "commands": list(self.command_log)[:12],
            "events": list(self.event_log)[:18],
        }
