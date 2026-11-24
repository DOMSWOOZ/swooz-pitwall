"""Backseat Champions Game API: decodes the game's UDP packets and builds commands. Standard library only.

    import socket, bc_api
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 29770))
    while True:
        header, body = bc_api.decode(sock.recv(2048))

Every packet is packed little-endian with a fixed size per packet id; README.md lays each one out. decode()
returns the header and the body as plain dicts, with enum values turned into names where the game has them.
"""
import struct

PACKET_FORMAT = 1
PACKET_VERSION = 1
# Each packet type's layout version, by packet id; commands use PACKET_VERSION.
PACKET_VERSIONS = [1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1]
MAX_CARS = 16
NO_CAR = 255
NO_LIMIT = 255

(MOTION, CAR_TELEMETRY, LAP_DATA, CAR_STATUS, PLAYER, SESSION, PARTICIPANTS, EVENT, AI_OBSERVATIONS, ACK, ERROR, HELLO,
 CAR_ABILITIES, RACING_LINE) = range(14)
PACKET_NAMES = ["motion", "car_telemetry", "lap_data", "car_status", "player", "session", "participants", "event",
                "ai_observations", "ack", "error", "hello", "car_abilities", "racing_line"]
PACKET_SIZES = [792, 952, 312, 536, 1039, 123, 584, 47, 1432, 29, 30, 53, 200, 747]

PING, HELLO_COMMAND, PICK_CARD, SET_PIT, PICK_TIRE, DRIVE, RELEASE_DRIVE, BAN_CARD, BOOST, SET_CAMERA = range(10)
COMMAND_NAMES = ["ping", "hello", "pick_card", "set_pit", "pick_tire", "drive", "release_drive", "ban_card", "boost",
                 "set_camera"]
COMMAND_SIZES = [56, 56, 58, 58, 58, 65, 57, 58, 58, 58]

# boost() buttons, and set_camera() values past the camera types.
BOOST_SPEED, BOOST_CORNERING, BOOST_PARTY_MODE = 1, 2, 4
CAMERA_PREVIOUS, CAMERA_NEXT, CAMERA_AUTOMATIC = 253, 254, 255

COMPOUNDS = ["Standard", "Boost", "Experimental", "Fast", "Durable", "Wet", "Golden"]
UPGRADES = ["EnginePower", "DragReduction", "TireGrip", "TemporaryUpgradeDuration", "TractionControl", "Downforce",
            "TireSaving", "PitSpeed", "BoostCapacity", "WeightReduction", "BoostPerSector", "BoostRechargeSpeed",
            "ExperienceGain", "SensorQuality", "TurboCharger", "Suspension", "Cooling", "BoostOverspeed",
            "FuelCapacity", "FuelEfficiency", "FuelPerformance", "RefuelSpeed", "EngineBraking", "Gearbox", "FuelWeight",
            "KineticRegen", "Reroll"]
FACILITIES = ["Speed", "Cornering", "Performance", "Boost", "Fuel", "All", "Redline", "Augment"]
SESSION_TYPES = ["AITraining", "Practice", "Qualifying", "Race"]
CAR_TYPES = ["Formula", "ClassicFormula", "ModernFormula", "Endurance", "GT2", "Stock", "FormulaOldskool",
             "FormulaLegacy"]
PARTICIPANT_KINDS = ["ai", "local", "remote"]
CAMERA_TYPES = ["TrackOverview", "Helicopter", "TrackSide", "Drone", "Onboard_TCam", "Onboard_Rear", "Onboard_Front",
                "Onboard_Driver", "Onboard_TVAngle", "Chase", "Onboard_BattleCam"]
PERFORMANCE_AREAS = ["Suspension", "EngineTorque", "Downforce", "Acceleration", "Drag", "AngularDrag",
                     "TractionControl", "Weight"]
ERRORS = ["none", "invalid_packet", "unsupported_version", "unknown_command", "public_lobby", "input_disabled",
          "not_your_car", "no_player", "replay_playing", "no_points", "invalid_index", "cards_unavailable",
          "card_banned", "driver_decided", "refused", "invalid_compound", "tire_select_closed", "compound_refused",
          "not_host", "invalid_axis", "internal_error", "ban_refused", "assist_on", "camera_unavailable"]

HEADER = struct.Struct("<HBB3BBIIf4B")
MOTION_CAR = struct.Struct("<12f")
TELEMETRY_CAR = struct.Struct("<3f" + "Bff" * 4 + "BBff")
LAP_CAR = struct.Struct("<BBHBBfff")
STATUS_CAR = struct.Struct("<8f")
HAND = struct.Struct("<B16B")
PLAYER_BODY = struct.Struct("<BBB17sHHHBBBBf7BfBBHHBBBB4f194f42f")
SESSION_BODY = struct.Struct("<BBHBfHI32sBfHfffffffffBff")
PARTICIPANT = struct.Struct("<BBB32s")
EVENT_BODY = struct.Struct("<4sB18s")
OBSERVATIONS_BODY = struct.Struct("<BB13s23sIffH339f")
ACK_BODY = struct.Struct("<BI")
ERROR_BODY = struct.Struct("<BIB")
HELLO_BODY = struct.Struct("<I16sBBBHI")
ABILITIES_CAR = struct.Struct("<BBBff")
LINE_POINT = struct.Struct("<9f")
COMMAND_HEADER = struct.Struct("<HBBI48s")


class PacketError(ValueError):
    pass


def name(table, index):
    return table[index] if 0 <= index < len(table) else index


def text(raw):
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def decode(data):
    """(header, body) for one datagram. Raises PacketError for anything that is not a well-formed packet."""
    if len(data) < HEADER.size:
        raise PacketError(f"{len(data)} bytes is shorter than the header")
    h = HEADER.unpack_from(data)
    header = {
        "packet_format": h[0], "packet_id": h[1], "packet_version": h[2], "game_version": f"{h[3]}.{h[4]}.{h[5]}",
        "num_cars": h[6], "session_uid": h[7], "frame": h[8], "session_time": h[9], "seat_car": list(h[10:14]),
    }
    if header["packet_format"] != PACKET_FORMAT:
        raise PacketError(f"packet format {header['packet_format']}, this decoder reads {PACKET_FORMAT}")
    pid = header["packet_id"]
    if pid >= len(PACKET_SIZES):
        raise PacketError(f"unknown packet id {pid}")
    if len(data) != PACKET_SIZES[pid]:
        raise PacketError(f"{PACKET_NAMES[pid]} is {len(data)} bytes, expected {PACKET_SIZES[pid]}")
    header["packet"] = PACKET_NAMES[pid]
    return header, DECODERS[pid](memoryview(data)[HEADER.size:], header["num_cars"])


def cars(body, layout, count, read):
    return [read(layout.unpack_from(body, i * layout.size)) for i in range(min(count, MAX_CARS))]


def motion(body, count):
    return {"cars": cars(body, MOTION_CAR, count, lambda v: {
        "position": v[0:3], "velocity": v[3:6], "angular_velocity": v[6:9], "pitch": v[9], "roll": v[10],
        "yaw": v[11]})}


def car_telemetry(body, count):
    def read(v):
        wheels = [{"on_track": bool(v[3 + w * 3] & 1), "grounded": bool(v[3 + w * 3] & 2),
                   "slip_forward": v[4 + w * 3], "slip_sideways": v[5 + w * 3]} for w in range(4)]
        return {"speed_kmh": v[0], "pedal": v[1], "steer": v[2], "wheels": wheels,
                "tire_compound": name(COMPOUNDS, v[15]), "puncture": bool(v[16] & 1), "tire_health": v[17],
                "energy": v[18]}
    return {"cars": cars(body, TELEMETRY_CAR, count, read)}


def lap_data(body, count):
    return {"cars": cars(body, LAP_CAR, count, lambda v: {
        "position": v[0], "class_position": v[1], "lap": v[2], "in_pits": bool(v[3] & 1), "finished": bool(v[3] & 2),
        "pit_planned": bool(v[3] & 4), "api_driving": bool(v[3] & 8), "pit_stops": v[4], "gap_to_leader": v[5],
        "interval_ahead": v[6], "interval_behind": v[7]})}


def car_status(body, count):
    return {"cars": cars(body, STATUS_CAR, count, lambda v: {"performance": dict(zip(PERFORMANCE_AREAS, v))})}


def hand(raw):
    v = HAND.unpack(raw)
    return [{"index": i, "upgrade": name(UPGRADES, v[1 + i * 4]), "facility": name(FACILITIES, v[2 + i * 4]),
             "tier": v[3 + i * 4], "banned": bool(v[4 + i * 4] & 1)} for i in range(min(v[0], 4))]


def picks_left(values):
    return {COMPOUNDS[c]: (None if values[c] == NO_LIMIT else values[c]) for c in range(len(COMPOUNDS))}


def player(body, count):
    v = PLAYER_BODY.unpack_from(body)
    return {
        "seat": v[0], "car": v[1], "points": v[2], "hand": hand(v[3]), "upgrades_applied": v[4], "total_laps": v[5],
        "laps_remaining": v[6], "pit_planned": bool(v[7] & 1), "can_pit": bool(v[7] & 2), "in_pits": bool(v[7] & 4),
        "pit_stops": v[8], "tire_compound": name(COMPOUNDS, v[9]), "puncture": bool(v[10] & 1), "tire_health": v[11],
        "compound_picks_left": picks_left(v[12:19]), "energy": v[19],
        "strategy": None if not v[20] else {
            "start_grid_position": v[21], "laps_since_pit": v[22], "tire_age_laps": v[23],
            "cars_within_5s_ahead": v[24], "cars_within_5s_behind": v[25], "class_position": v[26],
            "class_size": v[27], "class_gap_to_leader": v[28], "class_gap_to_ahead": v[29],
            "class_gap_to_behind": v[30], "reference_lap_s": v[31], "opponents": list(v[32:226]),
            "near": list(v[226:268])},
    }


def session(body, count):
    v = SESSION_BODY.unpack_from(body)
    return {
        "session_type": name(SESSION_TYPES, v[0]), "energy": "fuel" if v[1] else "boost", "total_laps": v[2],
        "player_input": bool(v[3] & 1), "driver_input": bool(v[3] & 2), "public_lobby": bool(v[3] & 4),
        "weather": v[4], "feature_schema_version": v[5], "feature_schema_hash": f"0x{v[6]:08X}", "scene": text(v[7]),
        "track": None if not v[8] else {
            "length_km": v[9], "corner_count": v[10], "avg_corner_speed": v[11], "straight_ratio": v[12],
            "elevation_change": v[13], "base_tire_wear_rate": v[14], "overtake_difficulty": v[15],
            "pit_lane_time_loss_s": v[16], "width_mean": v[17], "width_min": v[18], "barrier_ratio": v[19],
            "drs_zone_count": v[20], "drs_coverage": v[21], "lap_time_est_s": v[22]},
    }


def participants(body, count):
    return {"cars": cars(body, PARTICIPANT, count, lambda v: {
        "player_id": v[0], "car_type": name(CAR_TYPES, v[1]), "kind": name(PARTICIPANT_KINDS, v[2]),
        "name": text(v[3])})}


def event(body, count):
    code, seat, details = EVENT_BODY.unpack_from(body)
    code = code.decode("ascii", "replace")
    out = {"code": code, "seat": None if seat == NO_CAR else seat}
    if code == "CARD":
        out.update(points=details[0], hand=hand(details[1:18]))
    elif code == "TIRE":
        out.update(pre_race=bool(details[0]), current=name(COMPOUNDS, details[1]),
                   allowed=[COMPOUNDS[c] for c in range(len(COMPOUNDS)) if details[2] & (1 << c)],
                   picks_left=picks_left(details[3:10]))
    elif code == "LAPC":
        out.update(lap=details[0] | details[1] << 8, position=details[2])
    elif code == "PITW":
        out.update(lap=details[0] | details[1] << 8, pit_planned=bool(details[2]), can_pit=bool(details[3]))
    elif code == "FINI":
        out.update(position=details[0])
    return out


def ai_observations(body, count):
    v = OBSERVATIONS_BODY.unpack_from(body)
    return {"car": v[0], "api_driving": bool(v[1] & 1), "policy": text(v[2]), "policy_name": text(v[3]),
            "obs_frame": v[4], "action": [v[5], v[6]], "obs": list(v[8:8 + v[7]])}


def ack(body, count):
    v = ACK_BODY.unpack_from(body)
    return {"command": name(COMMAND_NAMES, v[0]), "request_id": v[1]}


def error(body, count):
    v = ERROR_BODY.unpack_from(body)
    return {"command": name(COMMAND_NAMES, v[0]), "request_id": v[1], "reason": name(ERRORS, v[2])}


def hello(body, count):
    v = HELLO_BODY.unpack_from(body)
    return {"request_id": v[0], "game_version": text(v[1]), "player_input": bool(v[2] & 1),
            "driver_input": bool(v[2] & 2), "public_lobby": bool(v[2] & 4), "driver_data": bool(v[3] & 1),
            "player_data": bool(v[3] & 2), "decision_events": bool(v[3] & 4), "ai_observations": bool(v[3] & 8),
            "rate_hz": v[4], "feature_schema_version": v[5], "feature_schema_hash": f"0x{v[6]:08X}"}


def car_abilities(body, count):
    return {"cars": cars(body, ABILITIES_CAR, count, lambda v: {
        "speed_boost": bool(v[0] & 1), "cornering_boost": bool(v[0] & 2), "super_boost": bool(v[0] & 4),
        "party_mode": bool(v[0] & 8), "drs": bool(v[0] & 16), "boost_overspeed": bool(v[0] & 32),
        "recharging": bool(v[0] & 64), "super_boost_unlocked": bool(v[1] & 1), "party_mode_unlocked": bool(v[1] & 2),
        "drs_unlocked": bool(v[1] & 4), "api_boosting": bool(v[1] & 8), "ban_tokens": v[2], "slipstream": v[3],
        "recharge_left": v[4]})}


def racing_line(body, count):
    seat, car, points = body[0], body[1], min(body[2], 20)
    line = []
    for i in range(points):
        v = LINE_POINT.unpack_from(body, 3 + i * LINE_POINT.size)
        line.append({"racing_line": v[0:3], "left": v[3:6], "right": v[6:9]})
    return {"seat": seat, "car": car, "points": line}


DECODERS = [motion, car_telemetry, lap_data, car_status, player, session, participants, event, ai_observations, ack,
            error, hello, car_abilities, racing_line]


# ---------------------------------------------------------------- commands

def command(command_id, payload=b"", request_id=0, token=""):
    """One command datagram. token is the game's Command Token, needed only from another machine."""
    encoded = token.encode("utf-8")
    if len(encoded) > 47:
        raise ValueError("the command token is at most 47 bytes")
    data = COMMAND_HEADER.pack(PACKET_FORMAT, command_id, PACKET_VERSION, request_id, encoded) + payload
    assert len(data) == COMMAND_SIZES[command_id]
    return data


def ping(request_id=0, token=""):
    return command(PING, b"", request_id, token)


def hello_command(request_id=0, token=""):
    return command(HELLO_COMMAND, b"", request_id, token)


def pick_card(index, seat=0, request_id=0, token=""):
    return command(PICK_CARD, struct.pack("<BB", seat, index), request_id, token)


def set_pit(pit, seat=0, request_id=0, token=""):
    return command(SET_PIT, struct.pack("<BB", seat, 1 if pit else 0), request_id, token)


def pick_tire(compound, seat=0, request_id=0, token=""):
    """compound is a name from COMPOUNDS or its index."""
    index = COMPOUNDS.index(compound) if isinstance(compound, str) else compound
    return command(PICK_TIRE, struct.pack("<BB", seat, index), request_id, token)


def drive(pedal, steer, seat=0, request_id=0, token=""):
    """pedal -1 (full brake) to 1 (full throttle), steer -1 (left) to 1 (right)."""
    return command(DRIVE, struct.pack("<Bff", seat, pedal, steer), request_id, token)


def release_drive(seat=0, request_id=0, token=""):
    return command(RELEASE_DRIVE, struct.pack("<B", seat), request_id, token)


def ban_card(index, seat=0, request_id=0, token=""):
    return command(BAN_CARD, struct.pack("<BB", seat, index), request_id, token)


def boost(speed=False, cornering=False, party_mode=False, seat=0, request_id=0, token=""):
    """Holds these boost buttons while you keep sending it, like drive(); all False lets go at once. Both speed and
    cornering together is a super boost once the car has it."""
    buttons = (BOOST_SPEED if speed else 0) | (BOOST_CORNERING if cornering else 0) | (BOOST_PARTY_MODE if party_mode else 0)
    return command(BOOST, struct.pack("<BB", seat, buttons), request_id, token)


def set_camera(camera, seat=0, request_id=0, token=""):
    """camera is a name from CAMERA_TYPES or its index, or CAMERA_NEXT, CAMERA_PREVIOUS or CAMERA_AUTOMATIC."""
    index = CAMERA_TYPES.index(camera) if isinstance(camera, str) else camera
    return command(SET_CAMERA, struct.pack("<BB", seat, index), request_id, token)


assert [s.size for s in (HEADER, MOTION_CAR, TELEMETRY_CAR, LAP_CAR, STATUS_CAR, PLAYER_BODY, SESSION_BODY,
                         PARTICIPANT, EVENT_BODY, OBSERVATIONS_BODY, ACK_BODY, ERROR_BODY, HELLO_BODY,
                         COMMAND_HEADER, ABILITIES_CAR, LINE_POINT)] == [24, 48, 58, 18, 32, 1015, 99, 35, 23, 1408, 5, 6,
                                                                       29, 56, 11, 36]
