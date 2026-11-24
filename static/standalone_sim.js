/* Standalone 50Hz Client-Side F1 Pit Wall Engine for iPhone / Vercel / Static Web Hosting
 * Automatically activates when no Python WebSocket backend is present, providing 100% feature parity:
 * - 16 cars, dynamic weather & rain forecast crossovers, tire cliffs & puncture physics, .0001 diffs
 * - Full Autonomous Co-Pilot: AUTO CARD (with smart ban + multi-point queue), AUTO TIRE, PIT GUARD, ERS AUTO-DEPLOY
 * - Dynamic .0001 Card EV Evaluator, 4-Stage Pace Modes (Conserve / Balanced / Attack / Hammer)
 * - Proactive F1 Race Engineer Radio Milestones (75/50/35/25/15%), Event & Command Logs, & Post-Race Debrief!
 */
(() => {
  const DRIVERS = [
    "Dom_Swooz", "Thruster", "Pole", "Circler", "Arizona", "DeFranco",
    "Valkyrie", "Mystic", "Strider", "Jaguar", "Drift", "Nacho",
    "The Serpent", "Apexia", "Vortex", "Kowalski",
  ];
  const COMPOUNDS = ["Standard", "Boost", "Experimental", "Fast", "Durable", "Wet", "Golden"];
  const PERF_AREAS = ["Suspension", "EngineTorque", "Downforce", "Acceleration", "Drag", "AngularDrag", "TractionControl", "Weight"];

  const COMP_SPEED = { Golden: 1.028, Fast: 1.036, Boost: 1.018, Experimental: 0.990, Standard: 1.000, Durable: 0.986, Wet: 0.962 };
  const COMP_WEAR = { Golden: 0.96, Fast: 1.45, Boost: 0.93, Experimental: 1.06, Standard: 1.00, Durable: 0.56, Wet: 0.92 };

  const CARD_POOL = [
    { upgrade: "WeightReduction", facility: "Performance", tier: 2 },
    { upgrade: "EnginePower", facility: "Speed", tier: 2 },
    { upgrade: "TireSaving", facility: "Cornering", tier: 2 },
    { upgrade: "Downforce", facility: "Cornering", tier: 2 },
    { upgrade: "TurboCharger", facility: "Redline", tier: 2 },
    { upgrade: "BoostRechargeSpeed", facility: "Boost", tier: 1 },
    { upgrade: "TireGrip", facility: "Cornering", tier: 2 },
    { upgrade: "DragReduction", facility: "Speed", tier: 1 },
    { upgrade: "Suspension", facility: "Cornering", tier: 1 },
    { upgrade: "BoostOverspeed", facility: "Redline", tier: 2 },
    { upgrade: "ExperienceGain", facility: "Augment", tier: 1 },
    { upgrade: "TractionControl", facility: "Cornering", tier: 1 },
  ];

  const STAT_MAP = {
    EnginePower: "EngineTorque",
    TurboCharger: "Acceleration",
    DragReduction: "Drag",
    Downforce: "Downforce",
    Suspension: "Suspension",
    TireGrip: "TractionControl",
    TractionControl: "TractionControl",
    WeightReduction: "Weight",
    TireSaving: "Suspension",
  };

  const DEFAULT_LOADOUTS = {
    max_slots: 5,
    push_slots: [
      { slot: 0, id: "k1_super", label: "K1 BOTH", title: "K1 Super Boost (Hold Both)", mode: "both", duration_s: 3.0, max_steer: 1.0, min_pedal: 0.0, energy_floor: 0.02, call: "K1 Super Boost deployed — holding both boosts!" },
      { slot: 1, id: "slingshot", label: "SLINGSHOT", title: "Straight-Line Slingshot", mode: "straight_super", duration_s: 4.5, max_steer: 0.14, min_pedal: 0.20, energy_floor: 0.02, call: "Straight-line Slingshot armed — send it down the straight!" },
      { slot: 2, id: "apex_vector", label: "APEX EXIT", title: "Apex Exit Vector", mode: "corner_to_both", duration_s: 3.5, max_steer: 0.12, min_pedal: 0.28, energy_floor: 0.02, call: "Apex Corner-Exit Grip boost engaged!" },
      { slot: 3, id: "overtake_dump", label: "7s DUMP", title: "7s Overtake Dump", mode: "smart_dump", duration_s: 7.0, max_steer: 0.25, min_pedal: 0.22, energy_floor: 0.04, call: "Full-sector Overtake Dump engaged!" },
      { slot: 4, id: "super_comms", label: "SUPER COMMS", style: "golden_pixel", title: "★ SUPER COMMS — Castellet Golden 5x Stack Hybrid Vector", mode: "super_comms", duration_s: 5.2, max_steer: 0.16, min_pedal: 0.18, energy_floor: 0.05, call: "Super Comms engaged — golden stack pinned, send it!" },
    ],
    card_slots: [
      { slot: 0, id: "p1_mimic", label: "P1 MIMIC", name: "Last P1 Podium Mimic", summary: "3-Phase P1 Clone", base_archetype: "p1_mimic", rush_facilities: ["Speed", "Boost"], priority_upgrades: ["PitSpeed", "DragReduction", "Suspension", "BoostCapacity"], late_upgrades: ["TemporaryUpgradeDuration"], avoid_upgrades: ["Reroll"], call: "Auto-Card blueprint locked: P1 Podium Mimic!" },
      { slot: 1, id: "super_boost", label: "BOOST 6/6", name: "Super-Boost Rocket", summary: "Rushes Boost 6/6 FIRST", base_archetype: "super_boost", rush_facilities: ["Boost", "Speed"], priority_upgrades: ["BoostPerSector", "BoostCapacity", "BoostRechargeSpeed", "TurboCharger", "DragReduction"], late_upgrades: ["BoostOverspeed"], avoid_upgrades: ["Reroll"], call: "Auto-Card blueprint locked: Super-Boost 6 of 6 Rush!" },
      { slot: 2, id: "apex_grip", label: "APEX GRIP", name: "Apex & Wet Dominator", summary: "Rushes Cornering 6/6 + Golden Tires", base_archetype: "apex_grip", rush_facilities: ["Cornering", "Performance"], priority_upgrades: ["Suspension", "Downforce", "TireGrip", "TractionControl", "WeightReduction"], late_upgrades: ["PitSpeed"], avoid_upgrades: ["Reroll"], call: "Auto-Card blueprint locked: Apex Grip!" },
      { slot: 3, id: "xp_snowball", label: "SNOWBALL", name: "42-Tier Hyper-Snowball", summary: "Early ExperienceGain + SensorQuality", base_archetype: "xp_snowball", rush_facilities: ["Performance", "Boost"], priority_upgrades: ["ExperienceGain", "SensorQuality", "PitSpeed"], late_upgrades: ["TemporaryUpgradeDuration", "TurboCharger"], avoid_upgrades: ["Reroll"], call: "Auto-Card blueprint locked: Hyper X P Snowball!" },
      { slot: 4, id: "ironman", label: "CASTELLET", style: "golden_pixel", name: "Dom's Castellet Golden Grand Slam", summary: "10/10 Laps Led · -26.5s Pit Delta · 5x Golden Stack", base_archetype: "castellet_comms", rush_facilities: ["Performance", "Boost", "Speed"], priority_upgrades: ["PitSpeed", "TireSaving", "TurboCharger", "DragReduction", "BoostRechargeSpeed", "BoostOverspeed"], late_upgrades: ["TemporaryUpgradeDuration", "TireGrip"], avoid_upgrades: ["Reroll"], call: "Auto-Card blueprint locked: Castellet Golden Grand Slam!" },
    ],
    catalog: {
      facilities: ["Speed", "Cornering", "Performance", "Boost", "Fuel"],
      upgrades: ["EnginePower", "DragReduction", "TireGrip", "TemporaryUpgradeDuration", "TractionControl", "Downforce", "TireSaving", "PitSpeed", "BoostCapacity", "WeightReduction", "BoostPerSector", "BoostRechargeSpeed", "ExperienceGain", "SensorQuality", "TurboCharger", "Suspension", "Cooling", "BoostOverspeed", "KineticRegen", "Reroll"],
    },
  };

  class StandalonePitWallSim {
    constructor(onSnapshot) {
      this.onSnapshot = onSnapshot;
      this.running = false;
      this.paused = false;
      this.timer = null;
      this.overlayCfg = { game_refocus: true, global_hotkeys: true, mouse_buttons: true, pin_top: false, mini_hud: false };
      this.loadouts = JSON.parse(localStorage.getItem("bc_loadouts_v1") || "null") || JSON.parse(JSON.stringify(DEFAULT_LOADOUTS));
      this.reset();
    }

    setLoadouts(st) {
      if (st && st.push_slots && st.card_slots) {
        this.loadouts = st;
        try { localStorage.setItem("bc_loadouts_v1", JSON.stringify(st)); } catch (_) {}
      }
    }

    applyLoadoutMutation(payload) {
      const act = payload?.action;
      const idx = Math.max(0, Math.min(4, Number(payload?.slot || 0)));
      if (act === "update_push_slot" && payload.data) {
        const d = payload.data;
        this.loadouts.push_slots[idx] = {
          ...this.loadouts.push_slots[idx],
          ...d,
          label: String(d.label || "PUSH").toUpperCase().slice(0, 12),
        };
      } else if (act === "update_card_slot" && payload.data) {
        const d = payload.data;
        this.loadouts.card_slots[idx] = {
          ...this.loadouts.card_slots[idx],
          ...d,
          label: String(d.label || "CUSTOM").toUpperCase().slice(0, 12),
        };
      } else if (act === "reset_push_slot") {
        if (payload.slot == null) this.loadouts.push_slots = JSON.parse(JSON.stringify(DEFAULT_LOADOUTS.push_slots));
        else this.loadouts.push_slots[idx] = JSON.parse(JSON.stringify(DEFAULT_LOADOUTS.push_slots[idx]));
      } else if (act === "reset_card_slot") {
        if (payload.slot == null) this.loadouts.card_slots = JSON.parse(JSON.stringify(DEFAULT_LOADOUTS.card_slots));
        else this.loadouts.card_slots[idx] = JSON.parse(JSON.stringify(DEFAULT_LOADOUTS.card_slots[idx]));
      } else if (act === "reset_all") {
        this.loadouts = JSON.parse(JSON.stringify(DEFAULT_LOADOUTS));
      }
      try { localStorage.setItem("bc_loadouts_v1", JSON.stringify(this.loadouts)); } catch (_) {}
      return this.loadouts;
    }

    reset() {
      this.frame = 0;
      this.sessionTime = 8 * 28.2;
      this.totalLaps = 18;
      this.weather = -0.22;
      this.weatherVel = 0.0042;
      this.prevWet = false;
      this.selectedRival = null;
      this.radioSeq = 1;
      this.reqSeq = 100;
      this.lastAutoCardMs = 0;
      this.lastAutoPitMs = 0;
      this.milestonesFired = new Set([75, 50]);

      this.radioLog = [{
        id: 1,
        time_s: this.sessionTime,
        priority: "INFO",
        message: "Pit Wall telemetry online! Tap any car to lock rival, or arm Auto Card, Auto Tire, Pit Guard, and Pace Modes below.",
      }];
      this.eventLog = [
        { code: "SSTA", time_s: 0.0, details: { scene: "California_GP", laps: 18 } },
        { code: "CARD", time_s: this.sessionTime - 2.4, details: { points: 3, cards: 4 } },
        { code: "LAPC", time_s: this.sessionTime - 18.0, details: { lap: 8, position: 1 } },
      ];
      this.cmdLog = [
        { wall_ts: this.wallClock(), type: "ACK", command: "hello", reason: "ok", request_id: 100 },
      ];

      this.copilot = {
        lendurance_mode: false,
        pace_mode: "balanced",
        push_profile: "k1_super",
        card_strategy: "p1_mimic",
        wear_mult: 1.0,
        rain_forecast: "auto",
        auto_pit: true,
        pit_cliff_threshold: 0.22,
        auto_tire: true,
        auto_card: false,
        auto_boost: false,
        auto_drive: false,
      };
      this.facilityXp = { Speed: 2, Cornering: 2, Performance: 1, Boost: 3, Fuel: 0 };
      this.p1Blueprint = {
        track: "Belgium",
        winner: "Maxie",
        grid: 8,
        laps: 10,
        best_lap_s: 69.941,
        total_cards_picked: 49,
        fac_completions: 4,
        top_upgrades: ["BoostOverspeed ×6", "EnginePower ×4", "BoostRechargeSpeed ×4", "Suspension ×4", "TurboCharger ×4"],
        final_stats: {
          total_perm_tiers: 42,
          facilities_maxed: 4,
          power_kw: 420.3,
          mass_kg: 1657.8,
          downforce: 1.0576,
          traction: 1.126,
          boost_recharge_mult: 1.483,
          boost_overspeed_mult: 1.296,
        },
      };
      this.humanP1 = {
        track: "JapanShort",
        winner: "Dom_Swooz",
        grid: 8,
        laps: 25,
        best_lap_s: 18.395,
        win_margin_s: 14.113,
        final_stats: { total_perm_tiers: 33, end_tire_health_pct: 53.1 },
      };
      this.pushState = {
        active: false,
        hold: false,
        profile: "k1_super",
        untilMs: 0,
        customFlags: null,
      };
      this.points = 3;
      this.banTokens = 2;
      this.upgradesApplied = 5;
      this.picksLeft = { Standard: null, Boost: 2, Experimental: 2, Fast: 2, Durable: 2, Wet: null, Golden: 1 };
      this.boostUntil = 0;
      this.fastestLapS = 27.842;
      this.fastestCar = 1;
      this.activeCamera = "Chase";
      this.publicLobby = false;
      this.copilot = Object.assign(this.copilot || {}, { public_spotter: true, tv_director: false });

      // Build 180-waypoint technical circuit
      this.N = 180;
      this.trackPts = [];
      this.leftPts = [];
      this.rightPts = [];
      this.curv = [];
      this.totalLen = 0;
      for (let i = 0; i < this.N; i++) {
        const t = (i / this.N) * Math.PI * 2;
        const x = 255 * Math.cos(t) + 72 * Math.sin(2 * t) - 34 * Math.cos(3 * t);
        const z = 170 * Math.sin(t) + 52 * Math.cos(2 * t) + 28 * Math.sin(4 * t);
        const y = 12 * Math.sin(t - 0.5);
        this.trackPts.push([x, y, z]);
      }
      for (let i = 0; i < this.N; i++) {
        const p0 = this.trackPts[(i - 1 + this.N) % this.N];
        const p1 = this.trackPts[i];
        const p2 = this.trackPts[(i + 1) % this.N];
        const dx = p2[0] - p0[0], dz = p2[2] - p0[2];
        const len = Math.hypot(dx, dz) || 1;
        const lx = -dz / len, lz = dx / len;
        this.leftPts.push([p1[0] + lx * 6.8, p1[1], p1[2] + lz * 6.8]);
        this.rightPts.push([p1[0] - lx * 6.8, p1[1], p1[2] - lz * 6.8]);
        const seg = Math.hypot(p2[0] - p1[0], p2[2] - p1[2]);
        this.totalLen += seg;
        const a1 = Math.atan2(p1[0] - p0[0], p1[2] - p0[2]);
        const a2 = Math.atan2(p2[0] - p1[0], p2[2] - p1[2]);
        let da = (a2 - a1 + Math.PI) % (Math.PI * 2) - Math.PI;
        if (da < -Math.PI) da += Math.PI * 2;
        this.curv.push(Math.abs(da) / Math.max(seg, 0.5));
      }

      this.cars = DRIVERS.map((name, idx) => {
        const isMe = idx === 0;
        const off = idx === 0 ? 0 : idx === 1 ? -0.017 : -(idx * 0.043);
        const s0 = ((0.64 + off) % 1 + 1) % 1;
        const lap0 = 8 + Math.floor(0.64 + off);
        const perf = {
          Suspension: 0.885 + (Math.sin(idx * 1.7) * 0.035),
          EngineTorque: 0.825 + (Math.cos(idx * 1.3) * 0.042),
          Downforce: 0.905 + (Math.sin(idx * 2.1) * 0.038),
          Acceleration: 0.930 + (Math.cos(idx * 2.9) * 0.028),
          Drag: 0.780 + (Math.sin(idx * 0.9) * 0.036),
          AngularDrag: 1.155 + (Math.cos(idx * 1.1) * 0.020),
          TractionControl: 0.945 + (Math.sin(idx * 3.1) * 0.032),
          Weight: 0.848 + (Math.cos(idx * 2.4) * 0.028),
        };
        if (isMe) {
          Object.assign(perf, { Weight: 0.8612, EngineTorque: 0.8540, Downforce: 0.9215, Acceleration: 0.9480, Drag: 0.7910, Suspension: 0.9105, TractionControl: 0.9620 });
        } else if (idx === 1) {
          Object.assign(perf, { Weight: 0.8726, EngineTorque: 0.8615, Downforce: 0.9040, Acceleration: 0.9510, Drag: 0.8025 });
        }
        return {
          index: idx,
          name,
          kind: isMe ? "local" : "ai",
          car_type: "ModernFormula",
          grid: isMe ? 4 : idx + 1,
          pos: idx + 1,
          s: s0,
          lap: lap0,
          lapStartT: this.sessionTime - s0 * 28.2,
          lastLapS: isMe ? 28.019 : 28.15 + idx * 0.14,
          bestLapS: isMe ? 27.988 : (idx === 1 ? 27.842 : 28.05 + idx * 0.11),
          speedMps: 56,
          topKmh: 268.4,
          pedal: 0.92,
          steer: 0,
          latG: 0,
          longG: 0,
          peakG: 3.6,
          yaw: 0,
          compound: isMe ? "Fast" : ["Standard", "Fast", "Durable", "Boost"][idx % 4],
          nextCompound: isMe ? "Golden" : null,
          health: isMe ? 0.42 : 0.44 + (idx % 5) * 0.10,
          puncture: false,
          stintLaps: isMe ? 4 : 2 + (idx % 4),
          pitStops: idx % 3 === 0 ? 1 : 0,
          pitPlanned: false,
          inPits: false,
          pitTimer: 0,
          energy: isMe ? 0.78 : 0.65,
          recharging: false,
          drs: false,
          speedBoost: false,
          cornerBoost: false,
          boost: false,
          slipstream: 0,
          gap: idx * 0.95,
          intAhead: idx === 0 ? 0 : 0.95,
          perf,
        };
      });

      this.hand = this.dealHand();
      this.traces = [];
      this.ggTrail = [];
      this.lapHistory = [
        { lap: 7, time_s: 28.412, pos: 2, compound: "Fast", tire_health: 0.56 },
        { lap: 8, time_s: 28.019, pos: 1, compound: "Fast", tire_health: 0.44 },
      ];
    }

    wallClock() {
      return new Date().toTimeString().slice(0, 8);
    }

    logEvent(code, details) {
      this.eventLog.unshift({ code, time_s: Number(this.sessionTime.toFixed(2)), details });
      if (this.eventLog.length > 24) this.eventLog.pop();
    }

    logCmd(type, command, reason = "ok") {
      this.reqSeq += 1;
      this.cmdLog.unshift({ wall_ts: this.wallClock(), type, command, reason, request_id: this.reqSeq });
      if (this.cmdLog.length > 18) this.cmdLog.pop();
    }

    dealHand() {
      const shuffled = [...CARD_POOL].sort(() => Math.random() - 0.5);
      return shuffled.slice(0, 4).map((c, i) => ({ ...c, index: i, banned: false }));
    }

    emitRadio(message, priority = "INFO") {
      this.radioSeq += 1;
      this.radioLog.unshift({
        id: this.radioSeq,
        time_s: this.sessionTime,
        priority,
        message,
      });
      if (this.radioLog.length > 20) this.radioLog.pop();
    }

    resolveRival() {
      const sorted = [...this.cars].sort((a, b) => a.pos - b.pos);
      if (this.selectedRival != null && this.cars[this.selectedRival] && this.selectedRival !== 0) {
        return this.cars[this.selectedRival];
      }
      const me = this.cars[0];
      const targetPos = me.pos === 1 ? 2 : Math.max(1, me.pos - 1);
      return sorted.find((c) => c.pos === targetPos && c.index !== 0) || sorted.find((c) => c.index !== 0) || this.cars[1];
    }

    evaluateCards() {
      const me = this.cars[0];
      const rival = this.resolveRival();
      const w = this.weather;
      const mode = this.copilot.pace_mode;
      const lapsRem = Math.max(1, this.totalLaps - me.lap);
      const raceFracLeft = lapsRem / this.totalLaps;

      const scored = this.hand.map((card) => {
        const upg = card.upgrade;
        let score = 56 + card.tier * 12;
        const reasons = [];

        const mapped = STAT_MAP[upg];
        if (mapped) {
          const myV = me.perf[mapped] || 0;
          const rvV = rival.perf[mapped] || 0;
          const avgV = this.cars.reduce((s, x) => s + (x.perf[mapped] || 0), 0) / this.cars.length;
          const defRv = myV - rvV;
          const leadAvg = myV - avgV;
          if (defRv < -0.008) {
            score += Math.min(20, Math.abs(defRv) * 450);
            reasons.push(`Closes ${defRv.toFixed(3)} ${mapped} deficit`);
          } else if (leadAvg > 0.085) {
            score -= 16;
            reasons.push(`Already +${leadAvg.toFixed(2)} above grid`);
          }
        }

        if (w > 0.02) {
          if (["TireGrip", "TractionControl", "Downforce", "Suspension"].includes(upg)) {
            score += 17;
            reasons.push("Wet-track grip priority");
          } else if (upg === "DragReduction") {
            score -= 10;
          }
        }

        if (upg === "WeightReduction") {
          score += 12;
          if (!reasons.length) reasons.push("All-sector pace & tire life");
        }
        if (upg === "TireSaving" && (this.copilot.wear_mult > 1.05 || me.health < 0.48)) {
          score += 15;
          reasons.push("Extends stint window");
        }

        if (mode === "conserve") {
          if (upg === "TireSaving") { score += 22; reasons.push("Conserve mode #1 pick"); }
          else if (["WeightReduction", "Suspension", "TractionControl"].includes(upg)) score += 10;
        } else if (mode === "attack") {
          if (["EnginePower", "TurboCharger", "TireGrip", "Downforce", "BoostRechargeSpeed"].includes(upg)) {
            score += 15;
            reasons.push("Attack undercut pace");
          }
        } else if (mode === "hammer") {
          if (["TurboCharger", "EnginePower", "BoostOverspeed", "TireGrip"].includes(upg)) {
            score += 24;
            reasons.push("Hammer sprint power");
          } else if (["ExperienceGain", "TireSaving"].includes(upg)) {
            score -= 22;
          }
        }

        if (upg === "ExperienceGain") {
          if (raceFracLeft > 0.55) { score += 18; reasons.push("Early XP snowball"); }
          else if (raceFracLeft < 0.30) { score -= 24; reasons.push("Late race — low XP value"); }
        }
        if (["Redline", "Augment"].includes(card.facility)) {
          score += 5;
          if (reasons.length < 2) reasons.push(`${card.facility} synergy`);
        }

        // 4) In-Depth Auto-Card Strategy Archetype & Last-P1 Podium Blueprint Engine
        const cs = this.copilot.card_strategy || "p1_mimic";
        const prog = 1.0 - Math.max(0, Math.min(1, raceFracLeft));
        const stratNotes = [];
        if (cs === "p1_mimic") {
          if (prog < 0.38) {
            if (["EnginePower", "DragReduction", "TurboCharger", "BoostOverspeed", "BoostPerSector", "Suspension", "Downforce"].includes(upg)) {
              score += 18;
              stratNotes.push("P1 L1-3 6/6 Facility Rush");
            }
            if (upg === "TemporaryUpgradeDuration") score -= 22;
          } else if (prog < 0.72) {
            if (["Redline", "Augment"].includes(card.facility)) { score += 17; stratNotes.push("P1 Redline Surge"); }
            if (upg === "PitSpeed") { score += 19; stratNotes.push("1.87x P1 PitSpeed edge"); }
            if (["BoostOverspeed", "BoostPerSector", "TurboCharger", "DragReduction"].includes(upg)) score += 13;
          } else {
            if (upg === "TemporaryUpgradeDuration") { score += 25; stratNotes.push("1.83x P1 Late Duration"); }
            else if (card.facility === "Redline") { score += 18; stratNotes.push("Final-stint Redline"); }
            else if (upg === "ExperienceGain") score -= 32;
          }
        } else if (cs === "super_boost") {
          if (["BoostPerSector", "BoostCapacity", "BoostRechargeSpeed", "BoostOverspeed"].includes(upg)) {
            score += 30;
            stratNotes.push("Rushes Super Boost 6/6!");
          } else if (["TurboCharger", "DragReduction", "EnginePower"].includes(upg)) {
            score += 17;
            stratNotes.push("Super Boost top-end");
          }
        } else if (cs === "apex_grip") {
          if (["Suspension", "Downforce", "TireGrip", "TractionControl", "WeightReduction"].includes(upg)) {
            score += 26;
            stratNotes.push("Apex / Golden Tire rush");
          }
        } else if (cs === "xp_snowball") {
          if (prog < 0.48) {
            if (upg === "ExperienceGain") { score += 34; stratNotes.push("Hyper-Snowball XP"); }
            else if (upg === "SensorQuality") { score += 19; stratNotes.push("High-tier roll boost"); }
          } else if (upg === "TemporaryUpgradeDuration" || ["Redline", "Augment"].includes(card.facility)) {
            score += 22;
            stratNotes.push("Snowball T3 payoff");
          }
        } else if (cs === "ironman") {
          if (["TireSaving", "Suspension", "WeightReduction", "PitSpeed"].includes(upg)) {
            score += 26;
            stratNotes.push("Dom P1 Ironman 1-Stop");
          }
        } else if (cs === "lendurance") {
          if (upg === "DragReduction") {
            score += 34;
            stratNotes.push("L'Endurance 99.8% Mulsanne #1 king");
          } else if (["EnginePower", "TurboCharger", "BoostOverspeed", "BoostRechargeSpeed", "BoostPerSector", "PitSpeed", "TireSaving"].includes(upg)) {
            score += 27;
            stratNotes.push("L'Endurance P1 Mulsanne + 15.87s Pit Save");
          }
        }
        const mergedReasons = [...stratNotes, ...reasons];

        const ev = Math.round(Math.max(8, Math.min(99, score)));
        return {
          ...card,
          ev_score: ev,
          reason: mergedReasons.slice(0, 2).join(" · ") || `${card.facility} Tier ${card.tier + 1}`,
        };
      });

      const playable = scored.filter((c) => !c.banned);
      const best = playable.length ? playable.reduce((a, b) => (b.ev_score > a.ev_score ? b : a)) : null;
      const worst = playable.length > 1 ? playable.reduce((a, b) => (b.ev_score < a.ev_score ? b : a)) : null;
      return scored.map((c) => ({
        ...c,
        recommended: best ? c.index === best.index : false,
        ban_candidate: worst ? (c.index === worst.index && c.ev_score < 56) : false,
      }));
    }

    recommendCompound() {
      const profiles = this.buildCompoundProfiles();
      const usable = profiles.filter((p) => p.usable);
      const pool = usable.length ? usable : profiles;
      const best = [...pool].sort((a, b) => b.optimal_score - a.optimal_score)[0];
      const w = this.weather;
      const fcst = this.copilot.rain_forecast;
      let reason = `${this.copilot.pace_mode.toUpperCase()} optimal`;
      if (best.compound === "Wet") reason = w > 0.02 ? "Wet track active" : "Rain forecast crossover";
      else if (fcst === "rain_soon" && w <= 0.02) reason = "Short dry stint before rain";
      else if (this.copilot.pace_mode === "conserve" && best.compound === "Durable") reason = "Conserve max stint life";
      else if (["attack", "hammer"].includes(this.copilot.pace_mode)) reason = `${this.copilot.pace_mode.toUpperCase()} max grip`;
      return { compound: best.compound, reason };
    }

    installCardByIndex(idx, isAuto = false) {
      const me = this.cars[0];
      const c = this.hand[idx];
      if (!c || c.banned || this.points <= 0) {
        this.logCmd("ERROR", "pick_card", "cards_unavailable");
        return false;
      }
      const boostAmt = 0.0145 * (1 + c.tier * 0.4);
      const targetStat = STAT_MAP[c.upgrade] || "Acceleration";
      me.perf[targetStat] = (me.perf[targetStat] || 0.85) + boostAmt;
      if (c.upgrade === "WeightReduction") me.perf.Acceleration += 0.004;
      this.points = Math.max(0, this.points - 1);
      this.upgradesApplied += 1;
      this.hand = this.points > 0 ? this.dealHand() : [];
      this.logCmd("ACK", "pick_card", "ok");
      this.emitRadio(
        isAuto
          ? `Auto Card installed ${c.upgrade} — ${targetStat} upgraded!`
          : `Copy, ${c.upgrade} upgrade installed.`,
        "INFO"
      );
      return true;
    }

    tryAutoCard(force = false) {
      if (!this.copilot.auto_card || this.points <= 0 || !this.hand.length) return false;
      const now = performance.now();
      if (!force && now - this.lastAutoCardMs < 700) return false;
      const scored = this.evaluateCards();
      const playable = scored.filter((c) => !c.banned);
      if (!playable.length) return false;
      const best = playable.reduce((a, b) => (b.ev_score > a.ev_score ? b : a));
      const worst = playable.reduce((a, b) => (b.ev_score < a.ev_score ? b : a));
      if (this.banTokens > 0 && playable.length > 1 && best.ev_score < 54 && worst.ev_score < 50) {
        this.hand[worst.index].banned = true;
        this.banTokens -= 1;
        this.lastAutoCardMs = now;
        this.logCmd("ACK", "ban_card", "ok");
        this.emitRadio(`Auto Card banned low-value ${worst.upgrade}.`, "INFO");
        return true;
      }
      this.lastAutoCardMs = now;
      return this.installCardByIndex(best.index, true);
    }

    tryAutoTire(announce = false) {
      if (!this.copilot.auto_tire) return false;
      const me = this.cars[0];
      const rec = this.recommendCompound();
      if (!rec.compound) return false;
      const changed = me.nextCompound !== rec.compound;
      me.nextCompound = rec.compound;
      if (me.inPits) me.compound = rec.compound;
      if (changed) {
        this.logCmd("ACK", "pick_tire", "ok");
        if (announce) {
          this.emitRadio(`Auto Tire queued ${rec.compound} compound (${rec.reason}).`, "STRATEGY");
        }
      }
      return changed;
    }

    tryAutoPit(force = false) {
      if (!this.copilot.auto_pit) return false;
      const me = this.cars[0];
      const now = performance.now();
      if (!force && now - this.lastAutoPitMs < 2000) return false;
      const lapsRem = this.totalLaps - me.lap;
      if (me.pitPlanned || me.inPits || lapsRem < 1) return false;
      const mode = this.copilot.pace_mode || "balanced";
      let effCliff = this.copilot.pit_cliff_threshold;
      if (mode === "hammer" && lapsRem <= 2) effCliff = 0.14;
      const postGap = me.gap + 6.31;
      const trafficCount = this.cars.filter((x) => x.index !== 0 && Math.abs((x.gap || 0) - postGap) <= 2.2).length;

      let shouldPit = false;
      let why = "";
      if (me.puncture) {
        shouldPit = true;
        why = " (puncture emergency)";
      } else if (mode === "conserve" && trafficCount >= 2 && me.health > 0.125) {
        shouldPit = false;
      } else if (mode === "balanced" && me.intAhead > 0.05 && me.intAhead < 0.85 && me.health <= 0.26 && trafficCount === 0 && lapsRem >= 2) {
        shouldPit = true;
        why = " (clean-air undercut)";
      } else if (mode === "attack" && me.intAhead > 0.05 && me.intAhead < 0.95 && me.health <= 0.32 && trafficCount <= 1 && lapsRem >= 2) {
        shouldPit = true;
        why = " (aggressive undercut)";
      } else if (me.health <= effCliff) {
        shouldPit = true;
      }
      if (shouldPit) {
        me.pitPlanned = true;
        this.lastAutoPitMs = now;
        this.logCmd("ACK", "set_pit", "ok");
        this.emitRadio(
          `Pit Guard armed box this lap${why} at ${(me.health * 100).toFixed(0)} percent tire health.`,
          "STRATEGY"
        );
        return true;
      }
      return false;
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.timer = setInterval(() => {
        if (!this.paused) this.step(0.05);
        this.onSnapshot(this.buildSnapshot());
      }, 50);
    }

    stop() {
      this.running = false;
      if (this.timer) clearInterval(this.timer);
      this.timer = null;
    }

    handleAction(msg) {
      const a = msg.action;
      const me = this.cars[0];
      if (a === "set_pit") {
        me.pitPlanned = Boolean(msg.pit);
        this.logCmd("ACK", "set_pit", "ok");
        this.emitRadio(
          me.pitPlanned
            ? "Copy, box this lap confirmed! Pit crew ready."
            : "Copy, staying out — pit call cancelled.",
          "STRATEGY"
        );
      } else if (a === "pick_tire") {
        const comp = msg.compound || "Standard";
        const pl = this.picksLeft[comp];
        if (pl !== null && pl <= 0) {
          this.logCmd("ERROR", "pick_tire", "compound_refused");
          this.emitRadio(`No ${comp} sets remaining in allocation!`, "CRITICAL");
          return;
        }
        me.nextCompound = comp;
        if (me.inPits) me.compound = comp;
        this.logCmd("ACK", "pick_tire", "ok");
        this.emitRadio(`Copy, ${comp} compound locked in for pit stop.`, "INFO");
      } else if (a === "pick_card") {
        this.installCardByIndex(Number(msg.index), false);
      } else if (a === "ban_card") {
        const c = this.hand[msg.index];
        if (c && !c.banned && this.banTokens > 0 && this.hand.filter((x) => !x.banned).length > 1) {
          c.banned = true;
          this.banTokens -= 1;
          this.logCmd("ACK", "ban_card", "ok");
          this.emitRadio(`Banned ${c.upgrade}.`, "INFO");
        } else {
          this.logCmd("ERROR", "ban_card", "ban_refused");
        }
      } else if (a === "manual_boost") {
        let active = msg.active !== undefined ? Boolean(msg.active) : true;
        const hold = Boolean(msg.hold);
        let customFlags = null;
        if ((msg.speed !== undefined || msg.cornering !== undefined || msg.party !== undefined) && !msg.profile) {
          const sp = Boolean(msg.speed), co = Boolean(msg.cornering), pa = Boolean(msg.party);
          if (!sp && !co && !pa) active = false;
          else customFlags = [sp, co, pa];
        }
        if (active && !hold && !customFlags && msg.toggle_if_active && this.pushState.active && !this.pushState.hold) {
          active = false;
        }
        if (!active) {
          this.pushState.active = false;
          this.pushState.hold = false;
          this.pushState.untilMs = 0;
          this.pushState.customFlags = null;
          this.boostUntil = 0;
          this.logCmd("ACK", "boost", "off");
        } else {
          const prof = msg.profile || this.copilot.push_profile || "k1_super";
          const ps = (this.loadouts?.push_slots || []).find((x) => x.id === prof) || { duration_s: 3.0, call: "Overtake push deployed!" };
          const dur = Number(msg.duration_s || ps.duration_s || 3.0);
          this.pushState = {
            active: true,
            hold,
            profile: prof,
            untilMs: performance.now() + (hold ? 30000 : dur * 1000),
            customFlags,
          };
          this.boostUntil = this.pushState.untilMs;
          this.logCmd("ACK", "boost", prof);
          if (!hold) {
            const call = customFlags
              ? (customFlags[0] && customFlags[1] ? "Super Boost deployed!" : (customFlags[0] ? "Speed Boost pulse!" : "Cornering Grip pulse!"))
              : (ps.call || "Overtake push deployed!");
            this.emitRadio(call, "INFO");
          }
        }
      } else if (a === "set_camera") {
        this.activeCamera = msg.camera || "Chase";
        if (!msg.from_director) this.copilot.tv_director = false;
        this.logCmd("ACK", "set_camera", "ok");
        this.emitRadio(`Camera switched to ${this.activeCamera}.`, "INFO");
      } else if (a === "crew_callout") {
        const cmsg = String(msg.message || "").trim().slice(0, 180);
        const sender = String(msg.sender || "Crew Chief").trim().slice(0, 28);
        if (cmsg) this.emitRadio(`${sender}: ${cmsg}`, "CRITICAL");
      } else if (a === "set_sim_public") {
        this.publicLobby = msg.public_lobby !== undefined ? Boolean(msg.public_lobby) : !this.publicLobby;
        if (this.publicLobby) {
          this.copilot.public_spotter = true;
          this.emitRadio("Public lobby mode active — auto-inputs shielded for fair play. Three-D Blind-Spot Radar, Rival Spy, Instant Card Callouts, and Camera Control are live!", "STRATEGY");
        } else {
          this.emitRadio("Custom lobby mode restored — full fifty-hertz Co-Pilot inputs unlocked.", "INFO");
        }
      } else if (a === "ping") {
        this.logCmd("ACK", "ping", "ok");
        this.emitRadio("UDP telemetry ping acknowledged — 50 hertz link nominal.", "INFO");
      } else if (a === "set_preset") {
        if (msg.preset === "extreme_ai") {
          const want = msg.active == null ? !this.copilot.extreme_ai_sync : Boolean(msg.active);
          if (want) {
            Object.assign(this.copilot, {
              extreme_ai_sync: true,
              lendurance_mode: false,
              pace_mode: "attack",
              push_profile: "super_comms",
              card_strategy: "p1_mimic",
              pit_cliff_threshold: 0.26,
              auto_pit: true,
              auto_tire: true,
              auto_card: true,
              auto_boost: true,
            });
            this.emitRadio("Extreme A I synced! Eighty-thousand-race model weights, Quad six-of-six facility rush, and Super Comms armed!", "STRATEGY");
            this.tryAutoTire(true);
            this.tryAutoCard(true);
          } else {
            Object.assign(this.copilot, {
              extreme_ai_sync: false,
              pace_mode: "balanced",
              pit_cliff_threshold: 0.22,
            });
            this.emitRadio("Extreme A I sync disengaged — restored Balanced manual baseline.", "INFO");
          }
        } else if (msg.preset === "lendurance") {
          const nextOn = msg.active === undefined ? !this.copilot.lendurance_mode : Boolean(msg.active);
          if (nextOn) {
            Object.assign(this.copilot, {
              lendurance_mode: true,
              pace_mode: "balanced",
              push_profile: "slingshot",
              card_strategy: "lendurance",
              pit_cliff_threshold: 0.10,
              auto_pit: true,
              auto_tire: true,
              auto_card: true,
              auto_boost: true,
            });
            this.emitRadio(
              "L'Endurance P1 package dialed in! Ten percent deep-stint cliff for the sixteen-second pit lane, Slingshot Mulsanne boost, Boost compound priority, and Drag-plus-Pit-Speed card build armed!",
              "STRATEGY"
            );
            this.tryAutoTire(true);
            this.tryAutoCard(true);
          } else {
            Object.assign(this.copilot, {
              lendurance_mode: false,
              push_profile: "k1_super",
              card_strategy: "p1_mimic",
              pit_cliff_threshold: 0.22,
            });
            this.emitRadio("L'Endurance package disengaged — restored twenty-two percent Balanced crossover.", "INFO");
          }
        }
      } else if (a === "set_rival") {
        this.selectedRival = msg.car_index;
        if (msg.car_index != null && this.cars[msg.car_index]) {
          const rc = this.cars[msg.car_index];
          this.emitRadio(
            `Telemetry locked on P${rc.pos} ${rc.name}, ${rc.compound} tires at ${(rc.health * 100).toFixed(0)} percent.`,
            "INFO"
          );
        }
      } else if (a === "reset_sim") {
        this.reset();
      } else if (a === "start_race") {
        this.paused = false;
        this.reset();
        this.logCmd("ACK", "start_race", "hold_space_2.2s");
        this.emitRadio("Copy that — holding grid launch! Lights out and away we go!", "INFO");
      } else if (a === "toggle_sim") {
        this.paused = !this.paused;
      } else if (a === "set_overlay") {
        const ok = msg.key;
        if (ok && ok in this.overlayCfg) {
          this.overlayCfg[ok] = "value" in msg ? Boolean(msg.value) : !this.overlayCfg[ok];
        }
      } else if (a === "refocus_game") {
        // No-op in standalone web demo
      } else if (a === "test_radio") {
        const wearLap = 0.082 * (COMP_WEAR[me.compound] || 1.0) * this.copilot.wear_mult;
        const lapsToCliff = Math.max(0, (me.health - this.copilot.pit_cliff_threshold) / wearLap);
        this.emitRadio(
          `Tire check copy! P${me.pos || 1}, ${me.compound} tires at ${(me.health * 100).toFixed(0)} percent, ${lapsToCliff.toFixed(1)} laps to cliff.`,
          "INFO"
        );
      } else if (a === "set_copilot") {
        const k = msg.key, v = msg.value;
        this.copilot[k] = v;
        if (k === "pace_mode") {
          const cliffs = { conserve: 0.15, balanced: 0.22, attack: 0.28, hammer: 0.32 };
          this.copilot.pit_cliff_threshold = cliffs[v] || 0.22;
          const rec = this.recommendCompound();
          const lines = {
            conserve: `Copy, Conserve mode. Lift and coast, 15 percent cliff, overcut traffic filter active — targeting ${rec.compound}s and 55 percent battery reserve.`,
            balanced: `Copy, Balanced pace. Optimal 22 percent crossover and clean-air undercut armed — targeting ${rec.compound} compound.`,
            attack: `Copy, Attack mode engaged! Predatory rival hunter active, 28 percent early undercut, favoring ${rec.compound} grip!`,
            hammer: `Copy that — Hammer Time! Empty the tank, both boosts pinned, 32 percent sprint cliff on ${rec.compound}s!`,
          };
          this.emitRadio(lines[v] || `Copy, ${v} strategy mode active.`, "STRATEGY");
          this.tryAutoTire(false);
          this.tryAutoPit(true);
          this.tryAutoCard(true);
        } else if (k === "push_profile") {
          const ps = (this.loadouts?.push_slots || []).find((x) => x.id === v);
          this.emitRadio(ps ? `Push button armed to ${ps.label} — ${ps.call}` : "Push profile updated.", "INFO");
        } else if (k === "card_strategy") {
          const cs = (this.loadouts?.card_slots || []).find((x) => x.id === v);
          this.emitRadio(cs ? (cs.call || `Auto-Card blueprint locked: ${cs.label}!`) : "Card strategy updated.", "STRATEGY");
          this.tryAutoCard(true);
        } else if (k === "wear_mult") {
          this.emitRadio(`Pre-race tire wear multiplier set to ${Number(v).toFixed(2)}x.`, "INFO");
          this.tryAutoTire(false);
        } else if (k === "rain_forecast") {
          const rfLines = {
            auto: "Weather forecast set to live radar.",
            rain_soon: "Copy, rain expected shortly — holding durable sets for later.",
            drying: "Copy, track forecast drying — preparing slicks crossover.",
          };
          this.emitRadio(rfLines[v] || "Weather forecast updated.", "INFO");
          this.tryAutoTire(true);
        } else {
          const labels = {
            auto_pit: "Pit cliff guard",
            auto_tire: "Auto tire compound",
            auto_card: "Auto card strategist",
            auto_boost: "E R S auto deploy",
          };
          const lbl = labels[k] || k;
          const armed = Boolean(v);
          this.emitRadio(`Copy, ${lbl} ${armed ? "armed" : "disengaged"}.`, "INFO");
          if (armed) {
            if (k === "auto_card") this.tryAutoCard(true);
            else if (k === "auto_tire") this.tryAutoTire(true);
            else if (k === "auto_pit") this.tryAutoPit(true);
          }
        }
      }
    }

    sampleTrack(sNorm) {
      const f = (((sNorm % 1) + 1) % 1) * this.N;
      const idx = Math.floor(f) % this.N;
      const frac = f - Math.floor(f);
      const p0 = this.trackPts[idx];
      const p1 = this.trackPts[(idx + 1) % this.N];
      return {
        xyz: [p0[0] + (p1[0] - p0[0]) * frac, p0[1] + (p1[1] - p0[1]) * frac, p0[2] + (p1[2] - p0[2]) * frac],
        yaw: Math.atan2(p1[0] - p0[0], p1[2] - p0[2]) * (180 / Math.PI),
        curv: this.curv[idx],
        idx,
      };
    }

    step(dt) {
      this.frame += 1;
      this.sessionTime += dt;

      // Weather evolution + rain/dry crossover radio alerts
      this.weather += this.weatherVel * dt;
      if (this.weather > 0.36) this.weatherVel = -0.0042;
      if (this.weather < -0.40) this.weatherVel = 0.0042;
      const isWet = this.weather > 0.0;
      if (isWet !== this.prevWet) {
        this.prevWet = isWet;
        this.emitRadio(
          isWet
            ? "Rain is falling on circuit! Weather crossed zero — Wet tires active."
            : "Track is drying out! Slick compounds optimal.",
          "STRATEGY"
        );
        this.tryAutoTire(true);
      }

      // Autonomous Co-Pilot continuous checks (handles multi-point hands cleanly!)
      this.tryAutoCard(false);
      this.tryAutoPit(false);

      for (const c of this.cars) {
        const isMe = c.index === 0;
        const st = this.sampleTrack(c.s);
        const ahead = this.sampleTrack(c.s + 0.032);

        if (c.inPits) {
          c.pitTimer -= dt;
          c.speedMps = 23;
          c.pedal = 0.25;
          c.steer = 0;
          if (c.pitTimer <= 0) {
            c.inPits = false;
            let chosen = c.nextCompound;
            if (!chosen) {
              chosen = isMe && this.copilot.auto_tire
                ? this.recommendCompound().compound
                : (this.weather > 0.04 ? "Wet" : "Standard");
            }
            if (isMe && this.picksLeft[chosen] != null) {
              if (this.picksLeft[chosen] > 0) this.picksLeft[chosen] -= 1;
              else chosen = this.weather > 0.04 ? "Wet" : "Standard";
            }
            c.compound = chosen;
            c.nextCompound = isMe && this.copilot.auto_tire ? this.recommendCompound().compound : null;
            c.health = 1.0;
            c.puncture = false;
            c.stintLaps = 0;
            c.pitStops += 1;
            if (isMe) {
              this.milestonesFired.clear();
              this.logEvent("PITO", { compound: c.compound });
              this.emitRadio(`Pit exit clear! Fresh ${c.compound} tires at 100 percent — push now!`, "STRATEGY");
            }
          }
        } else {
          let grip = (0.58 + 0.42 * c.perf.Downforce) * (COMP_SPEED[c.compound] || 1.0);
          if (this.weather > 0.03 && c.compound !== "Wet" && c.compound !== "Golden") grip *= 0.82;
          if (c.puncture) grip *= 0.56;
          else if (c.health < 0.20) grip *= 0.84 + 0.75 * c.health;

          c.drs = (st.idx >= 162 || st.idx <= 20) && st.curv < 0.012;

          // Unified Tactical PUSH Profile + Pace-Mode-Aware ERS deployment for player
          let spdBoost = false, crnBoost = false;
          if (isMe) {
            const nowMs = performance.now();
            if (this.pushState.active && (nowMs >= this.pushState.untilMs || c.inPits || c.energy <= 0.015)) {
              this.pushState.active = false;
              this.pushState.hold = false;
              this.pushState.customFlags = null;
            }
            if (this.pushState.active && !c.recharging && c.energy > 0.015) {
              const cf = this.pushState.customFlags;
              const prof = this.pushState.profile || "k1_super";
              if (cf) {
                spdBoost = Boolean(cf[0]);
                crnBoost = Boolean(cf[1]);
              } else if (prof === "k1_super") {
                spdBoost = true;
                crnBoost = true;
              } else if (prof === "slingshot") {
                if (Math.abs(c.steer) < 0.14 && c.pedal >= 0.20) {
                  spdBoost = true;
                  if (Math.abs(c.steer) < 0.08) crnBoost = true;
                }
              } else if (prof === "apex_vector") {
                if (Math.abs(c.steer) >= 0.11 || Math.abs(c.latG) > 0.65) crnBoost = true;
                else if (c.pedal > 0.30) { spdBoost = true; crnBoost = true; }
              } else if (prof === "overtake_dump") {
                if (c.energy > 0.04) {
                  if (c.pedal <= 0.22 || Math.abs(c.steer) > 0.25) crnBoost = true;
                  else { spdBoost = true; crnBoost = true; }
                }
              }
            } else if (this.copilot.auto_boost && !c.recharging) {
              const mode = this.copilot.pace_mode;
              const minE = { conserve: 0.55, balanced: 0.28, attack: 0.12, hammer: 0.02 }[mode] ?? 0.28;
              const inHunt = c.intAhead > 0.03 && c.intAhead < 1.8;
              if (c.energy > minE) {
                if (mode === "conserve") {
                  if (Math.abs(c.steer) < 0.09 && c.pedal > 0.82 && (c.drs || c.slipstream > 0.2)) spdBoost = true;
                } else if (mode === "balanced") {
                  if (Math.abs(c.steer) < 0.15 && c.pedal > 0.75) { spdBoost = true; if (c.energy > 0.45 || (c.energy > 0.40 && inHunt)) crnBoost = true; }
                  else if (Math.abs(c.latG) > 1.4 && c.energy > 0.40) crnBoost = true;
                } else if (mode === "attack") {
                  if (Math.abs(c.steer) < 0.24 && c.pedal > (inHunt ? 0.46 : 0.55)) { spdBoost = true; if (c.energy > 0.20 || inHunt) crnBoost = true; }
                  else if (Math.abs(c.latG) > 0.92) crnBoost = true;
                } else if (mode === "hammer") {
                  if (c.pedal > 0.26) { spdBoost = true; crnBoost = true; }
                  else if (Math.abs(c.latG) > 0.58) crnBoost = true;
                }
              }
            }
          } else if (c.drs && !c.recharging && c.energy > 0.4) {
            spdBoost = true;
          }

          c.speedBoost = spdBoost;
          c.cornerBoost = crnBoost;
          c.boost = spdBoost || crnBoost;
          if (c.boost) {
            c.energy = Math.max(0.0, c.energy - 0.14 * dt);
            if (c.energy <= 0.01) c.recharging = true;
          } else {
            c.energy = Math.min(1.0, c.energy + 0.05 * dt);
            if (c.recharging && c.energy >= 0.25) c.recharging = false;
          }

          let maxV = (68 + 15 * c.perf.EngineTorque + 7 * c.perf.Weight + 5 * (c.perf.Drag - 0.78)) * (isMe ? 1.008 : 1.0 - c.index * 0.002);
          if (c.puncture) maxV *= 0.62;
          const cornerV = Math.min(maxV, (25.5 / Math.sqrt(Math.max(ahead.curv, 0.0035))) * grip * (crnBoost ? 1.035 : 1.0));
          const targetV = cornerV * (c.drs ? 1.05 : 1.0) * (spdBoost ? 1.06 : 1.0);

          const prevV = c.speedMps;
          c.speedMps = Math.max(18, c.speedMps + (targetV - c.speedMps) * 3.5 * dt);
          if (c.speedMps * 3.6 > c.topKmh) c.topKmh = c.speedMps * 3.6;
          c.pedal = Math.max(-1, Math.min(1, (targetV - prevV) * 0.18));
          const dyaw = ((ahead.yaw - st.yaw + 540) % 360) - 180;
          c.steer = Math.max(-1, Math.min(1, dyaw / 24));
          c.yaw = st.yaw;
          c.longG = ((c.speedMps - prevV) / dt) / 9.81;
          c.latG = (c.steer * (c.speedMps / 22)) * 1.45;
          c.peakG = Math.max(c.peakG, Math.hypot(c.longG, c.latG));

          const ds = (c.speedMps * dt) / this.totalLen;
          const susTrim = 1.10 - 0.12 * (c.perf.Suspension || 0.9);
          const wf = (c.compound === "Wet" && this.weather < 0 ? 2.4 : (COMP_WEAR[c.compound] || 1.0)) * susTrim;
          c.health = Math.max(0.01, c.health - ds * 0.082 * wf * this.copilot.wear_mult);

          if (!c.puncture && c.health < 0.06 && Math.random() < 0.005) {
            c.puncture = true;
            if (isMe) this.emitRadio("Puncture! We have a tire puncture — box immediately!", "CRITICAL");
          }

          if (isMe) {
            const thPct = c.health * 100;
            for (const mark of [75, 50, 35, 25, 15]) {
              if (thPct <= mark && !this.milestonesFired.has(mark)) {
                this.milestonesFired.add(mark);
                if (thPct >= mark - 6) {
                  const prio = mark <= 15 ? "CRITICAL" : mark <= 35 ? "STRATEGY" : "INFO";
                  const note = mark === 15
                    ? "Critical tire wear, 15 percent! High puncture danger — box, box!"
                    : `Tire update: ${mark} percent health on ${c.compound}s.`;
                  this.emitRadio(note, prio);
                }
                break;
              }
            }
          } else if (c.health < 0.21) {
            c.pitPlanned = true;
          }
        }

        const ds = (c.speedMps * dt) / this.totalLen;
        if (c.s + ds >= 1.0) {
          c.s = (c.s + ds) - 1.0;
          c.lap += 1;
          c.stintLaps += 1;
          const lapDur = this.sessionTime - c.lapStartT;
          c.lapStartT = this.sessionTime;
          if (lapDur > 12 && lapDur < 90) {
            c.lastLapS = lapDur;
            if (!c.bestLapS || lapDur < c.bestLapS) c.bestLapS = lapDur;
            if (lapDur < this.fastestLapS) {
              this.fastestLapS = lapDur;
              this.fastestCar = c.index;
              if (isMe) this.emitRadio(`Purple lap! Fastest on track: ${lapDur.toFixed(3)} seconds!`, "INFO");
            }
          }
          if (c.pitPlanned) {
            c.inPits = true;
            c.pitPlanned = false;
            c.pitTimer = 6.31;
            if (isMe) {
              this.logEvent("PITI", { lap: c.lap });
              this.logEvent("TIRE", { current: c.compound });
              this.tryAutoTire(true);
            }
          }
          if (isMe) {
            this.lapHistory.push({ lap: c.lap, time_s: c.lastLapS, pos: c.pos || 1, compound: c.compound, tire_health: c.health });
            this.logEvent("LAPC", { lap: c.lap, position: c.pos || 1 });
            if (c.lap >= this.totalLaps) {
              for (const rc of this.cars) rc.lap = 8;
            }
            if (c.lap % 2 === 0) {
              this.points = Math.min(4, this.points + 1);
              this.hand = this.dealHand();
              this.logEvent("CARD", { points: this.points, cards: this.hand.length });
              if (!this.copilot.auto_card) {
                const topCard = this.evaluateCards().find((x) => x.recommended);
                if (topCard) this.emitRadio(`Upgrade ready — top call is ${topCard.upgrade}.`, "STRATEGY");
              } else {
                this.tryAutoCard(true);
              }
            }
          }
        } else {
          c.s += ds;
        }
        c.xyz = st.xyz;
        c.totalDist = (c.lap + c.s) * this.totalLen;
      }

      const sorted = [...this.cars].sort((a, b) => b.totalDist - a.totalDist);
      const leadD = sorted[0].totalDist;
      sorted.forEach((c, idx) => {
        c.pos = idx + 1;
        c.gap = idx === 0 ? 0 : (leadD - c.totalDist) / 55;
        c.intAhead = idx === 0 ? 0 : (sorted[idx - 1].totalDist - c.totalDist) / 55;
        c.slipstream = idx > 0 && c.intAhead < 0.85 ? 1 - c.intAhead / 0.85 : 0;
      });

      const me = this.cars[0];
      this.ggTrail.push([me.latG, me.longG]);
      if (this.ggTrail.length > 45) this.ggTrail.shift();
      this.traces.push({
        t: this.sessionTime,
        speed: me.speedMps * 3.6,
        pedal: me.pedal,
        steer: me.steer,
        slip: Math.abs(me.steer) * 0.35,
        energy: me.energy,
      });
      if (this.traces.length > 85) this.traces.shift();
    }

    buildCompoundProfiles() {
      const w = this.weather;
      const mode = this.copilot.pace_mode;
      const fcst = this.copilot.rain_forecast;
      const lapsRem = Math.max(1, this.totalLaps - this.cars[0].lap);
      const baseW = 0.082 * this.copilot.wear_mult;
      return COMPOUNDS.map((comp) => {
        const pl = this.picksLeft[comp];
        const usable = pl == null || pl > 0;
        let pace = 0, wf = 1.0, opt = 60, pros = [], cons = [];
        if (comp === "Standard") {
          pace = w > 0 ? -0.25 : 0; wf = 1.0; opt = 56 + (mode === "balanced" ? 8 : 0);
          pros = ["+Slight grip in light rain", "+Unlimited sets · safe baseline"];
          cons = ["-Slowest dry compound", "-No XP or boost buffs"];
        } else if (comp === "Fast") {
          pace = w > 0 ? 1.85 : -0.68; wf = 1.54;
          opt = w > 0.03 ? 18 : (mode === "attack" || mode === "hammer" ? 90 : mode === "conserve" ? 48 : 72);
          if (fcst === "rain_soon" && w <= 0.02) opt = Math.max(opt, 86);
          pros = ["+#1 Fastest dry sprint compound", "+Extra XP per overtake"];
          cons = ["-Wears MORE while battling (v0.88.2)", "-Shortest lifespan", "-Zero grip in rain"];
        } else if (comp === "Durable") {
          pace = w > 0 ? 1.95 : 0.34; wf = 0.56;
          opt = w > 0.03 ? 16 : (mode === "conserve" ? 95 : mode === "balanced" ? 78 : 46);
          if (fcst === "rain_soon" && w <= 0.02) {
            opt -= 26;
            cons.push("-Rain soon: wastes Durable stint");
          }
          pros = ["+Longest life (no-stop / overcut)", "+Gains tire life, fuel & XP when rivals pit"];
          cons.push("-Slower raw pace", "-Zero grip in rain");
        } else if (comp === "Boost") {
          pace = w > 0 ? 1.70 : -0.41; wf = 0.93;
          opt = w > 0.03 ? 20 : 75;
          pros = ["++Boost capacity, regen & strength", "+Consistent pace & solid life"];
          cons = ["-No extra XP multiplier", "-Zero wet grip"];
        } else if (comp === "Experimental") {
          pace = w > 0 ? 1.80 : 0.24; wf = 1.06;
          opt = w > 0.03 ? 15 : 68;
          pros = ["+++Massive XP gain while driving", "+Early-race upgrade slingshot"];
          cons = ["-2nd slowest tire (trades pos for XP)", "-Zero wet grip"];
        } else if (comp === "Wet") {
          pace = w > 0.02 ? -(0.75 + w * 2.8) : 1.35;
          wf = w > 0.02 ? 0.90 : 3.2;
          opt = w > 0.02 ? (fcst === "drying" && w < 0.14 ? 62 : 97) : (fcst === "rain_soon" && w > -0.06 ? 88 : 12);
          pros = ["+#1 Fastest in rain", "+More XP the harder it rains"];
          cons = ["-Burns up to 5x faster on dry asphalt!"];
        } else {
          pace = w > 0.02 ? -0.85 : -0.38; wf = 0.95;
          opt = w > 0.02 && w < 0.30 ? 91 : (mode === "attack" || mode === "hammer" ? 89 : 82);
          pros = ["++Extends Golden Upgrade duration", "+Great grip in light / mixed rain"];
          cons = ["-Requires maxed Performance facility", "-Beaten by Wets in storms"];
        }
        if (!usable) opt = Math.max(4, opt - 45);
        const wearLap = baseW * wf;
        const safeLaps = Math.max(0, (1.0 - this.copilot.pit_cliff_threshold) / wearLap);
        return {
          compound: comp,
          usable,
          picks_left: pl,
          pace_delta_s: pace,
          wear_pct_lap: wearLap * 100,
          est_laps: 1.0 / wearLap,
          safe_laps: safeLaps,
          makes_flag: safeLaps >= lapsRem,
          optimal_score: opt,
          pros,
          cons,
        };
      });
    }

    buildSnapshot() {
      const me = this.cars[0];
      const sorted = [...this.cars].sort((a, b) => a.pos - b.pos);
      const rival = this.resolveRival();

      const wearLap = 0.082 * (COMP_WEAR[me.compound] || 1.0) * this.copilot.wear_mult;
      const lapsRem = Math.max(0, this.totalLaps - me.lap);
      const cliff = this.copilot.pit_cliff_threshold;
      const projFinish = (me.health - wearLap * lapsRem) * 100;
      const postGap = me.gap + 6.31;
      const aheadAfter = sorted.filter((x) => x.index !== 0 && x.gap < postGap);
      const behindAfter = sorted.filter((x) => x.index !== 0 && x.gap >= postGap);
      const rjPos = aheadAfter.length + 1;

      const profiles = this.buildCompoundProfiles();
      const rec = this.recommendCompound();
      const evaluatedHand = this.evaluateCards();

      const { idx: wpIdx } = this.sampleTrack(me.s);
      const rline = [];
      for (let k = 1; k <= 20; k++) {
        const p = (wpIdx + k * 2) % this.N;
        rline.push({
          c: [this.trackPts[p][0], this.trackPts[p][2]],
          l: [this.leftPts[p][0], this.leftPts[p][2]],
          r: [this.rightPts[p][0], this.rightPts[p][2]],
        });
      }

      const lapsToCliff = Math.max(0, (me.health - cliff) / wearLap);
      const riskLevel = me.puncture
        ? "PUNCTURE"
        : me.health <= cliff
        ? "CRITICAL"
        : me.health <= cliff + 0.10 || lapsToCliff <= 1.5
        ? "CAUTION"
        : "NOMINAL";

      return {
        connection: {
          mode: this.paused ? "STANDBY" : "SIM_DEMO",
          live_connected: false,
          simulated: !this.paused,
          game_version: "MOBILE-50HZ",
          kbps: this.paused ? 0 : 196.4,
          pps: this.paused ? 0 : 240,
          hello: { game_version: "0.88.2", rate_hz: 50, driver_data: true, player_data: true, decision_events: true, player_input: true, driver_input: true },
        },
        session: {
          session_type: "Race",
          session_time: this.sessionTime,
          energy: "boost",
          total_laps: this.totalLaps,
          player_input: !this.publicLobby,
          driver_input: !this.publicLobby,
          public_lobby: Boolean(this.publicLobby),
          weather: this.weather,
          rain_eta_s: this.weather < 0 && this.weatherVel > 0 ? Math.abs(this.weather / this.weatherVel) : null,
          scene: "California_GP",
          fastest_lap_s: this.fastestLapS,
          fastest_driver: this.cars[this.fastestCar].name,
          track: {
            length_km: this.totalLen / 1000,
            corner_count: 11,
            avg_corner_speed: 42.6,
            straight_ratio: 0.58,
            elevation_change: 54.8,
            base_tire_wear_rate: 0.082,
            overtake_difficulty: 0.44,
            pit_lane_time_loss_s: 6.31,
            width_mean: 13.4,
            width_min: 11.6,
            barrier_ratio: 0.12,
            drs_zone_count: 2,
            drs_coverage: 0.28,
            lap_time_est_s: 28.14,
          },
        },
        telemetry: {
          car_index: 0,
          name: me.name,
          pos: me.pos,
          lap: me.lap,
          current_lap_s: this.sessionTime - me.lapStartT,
          last_lap_s: me.lastLapS,
          best_lap_s: me.bestLapS,
          speed_kmh: me.speedMps * 3.6,
          top_speed_kmh: me.topKmh,
          pedal: me.pedal,
          steer: me.steer,
          long_g: me.longG,
          lat_g: me.latG,
          total_g: Math.hypot(me.longG, me.latG),
          peak_g: me.peakG,
          wheels: [0, 1, 2, 3].map((w) => ({
            on_track: true,
            grounded: true,
            slip_f: w >= 2 ? Math.max(0, me.pedal) * 0.22 : Math.min(0, me.pedal) * 0.16,
            slip_s: me.steer * (w >= 2 && me.health < 0.3 ? 0.28 : 0.18),
          })),
          understeer_index: me.health < 0.32 ? -0.025 : 0.008,
          off_track_count: 0,
          airborne_ms: 0,
          energy_pct: me.energy * 100,
          abilities: {
            drs: me.drs,
            speed_boost: me.speedBoost,
            cornering_boost: me.cornerBoost,
            super_boost: me.speedBoost && me.cornerBoost,
            party_mode: false,
            slipstream: me.slipstream,
          },
          lap_history: this.lapHistory.slice(-14),
          gg_trail: this.ggTrail,
          traces: this.traces,
          ai_obs: { policy_name: "AllCars.onnx" },
        },
        stint: {
          tire_health_pct: me.health * 100,
          wear_per_lap_pct: wearLap * 100,
          cliff_pct: cliff * 100,
          pace_mode: this.copilot.pace_mode,
          laps_remaining_exact: lapsRem,
          laps_to_cliff: Math.max(0, (me.health - cliff) / wearLap),
          laps_to_zero: me.health / wearLap,
          projected_finish_pct: projFinish,
          risk_level: riskLevel,
          verdict: me.puncture
            ? "PUNCTURE ACTIVE — BOX IMMEDIATELY!"
            : me.health <= cliff
            ? `BOX THIS LAP! [${this.copilot.pace_mode.toUpperCase()}] Below ${(cliff * 100).toFixed(0)}% cliff`
            : projFinish >= cliff * 100
            ? `[${this.copilot.pace_mode.toUpperCase()}] CLEAR TO FLAG — Proj ${projFinish.toFixed(0)}% at finish`
            : `[${this.copilot.pace_mode.toUpperCase()}] 1-STOP PACE — Box in ~${lapsToCliff.toFixed(1)}L (Cliff ${(cliff * 100).toFixed(0)}%)`,
          pit_loss_s: 6.31,
          rejoin_position: rjPos,
          rejoin_ahead: aheadAfter.length ? { name: aheadAfter[aheadAfter.length - 1].name, pos: aheadAfter[aheadAfter.length - 1].pos, gap_s: postGap - aheadAfter[aheadAfter.length - 1].gap } : null,
          rejoin_behind: behindAfter.length ? { name: behindAfter[0].name, pos: behindAfter[0].pos, gap_s: behindAfter[0].gap - postGap } : null,
          air_status: Math.abs(postGap - (aheadAfter[aheadAfter.length - 1]?.gap ?? -99)) < 2.0 ? "SINGLE RIVAL" : "CLEAN AIR",
        },
        hardware: {
          my_car: { index: 0, name: me.name, pos: me.pos },
          rival_car: { index: rival.index, name: rival.name, pos: rival.pos, locked: this.selectedRival != null },
          areas: PERF_AREAS.map((area) => {
            const vals = this.cars.map((x) => x.perf[area]);
            const mx = Math.max(...vals);
            return {
              area,
              mine: me.perf[area],
              rival: rival.perf[area],
              delta_vs_rival: me.perf[area] - rival.perf[area],
              field_best: mx,
              rank: 1 + vals.filter((v) => v > me.perf[area]).length,
            };
          }),
        },
        cards: {
          points: this.points,
          upgrades_applied: this.upgradesApplied,
          ban_tokens: this.banTokens,
          hand: evaluatedHand,
          strategy: this.copilot.card_strategy || "p1_mimic",
          facility_xp: this.facilityXp,
          p1_blueprint: this.p1Blueprint,
          human_p1: this.humanP1,
        },
        tires: {
          current: me.compound,
          queued: me.nextCompound || null,
          picks_left: this.picksLeft,
          profiles,
          recommendation: rec,
        },
        pit: { pit_planned: me.pitPlanned, can_pit: true, in_pits: me.inPits, pit_stops: me.pitStops },
        map: { track_pts: this.trackPts, racing_line: rline },
        standings: sorted.map((c) => ({
          index: c.index,
          is_me: c.index === 0,
          is_rival: c.index === rival.index,
          pos: c.pos,
          grid_delta: c.grid - c.pos,
          name: c.name,
          kind: c.kind,
          car_type: c.car_type,
          lap: c.lap,
          last_lap_s: c.lastLapS,
          best_lap_s: c.bestLapS,
          is_purple: c.index === this.fastestCar,
          gap_to_leader: c.gap,
          interval_ahead: c.intAhead,
          interval_behind: 0.4,
          closing_s_per_lap: c.index === 0 ? 0 : ((c.index % 2 ? 0.14 : -0.11)),
          compound: c.compound,
          tire_health_pct: c.health * 100,
          puncture: c.puncture,
          stint_laps: c.stintLaps,
          pit_stops: c.pitStops,
          in_pits: c.inPits,
          pit_planned: c.pitPlanned,
          drs: c.drs,
          boost: c.boost,
          weight_diff: c.perf.Weight - me.perf.Weight,
          performance: c.perf,
          xyz: c.xyz,
        })),
        copilot: {
          ...this.copilot,
          push_active: Boolean(this.pushState.active && performance.now() < this.pushState.untilMs),
          push_hold: Boolean(this.pushState.hold),
          push_remaining_s: this.pushState.active ? Math.max(0, (this.pushState.untilMs - performance.now()) / 1000) : 0,
          push_active_profile: this.pushState.profile || this.copilot.push_profile || "k1_super",
        },
        loadouts: this.loadouts,
        public_suite: (() => {
          const tPhase = this.sessionTime * 0.65;
          const rz1 = Math.sin(tPhase) * 7.2 - 1.8;
          const rx1 = -2.4 + Math.cos(tPhase * 0.7) * 0.6;
          const rz2 = -6.8 + Math.cos(tPhase * 0.85) * 4.5;
          const rx2 = 2.6 + Math.sin(tPhase * 0.5) * 0.7;
          const c1Overlap = Math.abs(rz1) <= 4.6;
          const c2Overlap = Math.abs(rz2) <= 4.6;
          let rStatus = "CLEAR";
          if (c1Overlap && c2Overlap) rStatus = "3-WIDE";
          else if (c1Overlap) rStatus = "CAR LEFT";
          else if (c2Overlap) rStatus = "CAR RIGHT";
          else if (rz2 > -11 && rz2 < -4.6) rStatus = "DIVE RIGHT";
          const topCard = evaluatedHand.find((c) => c.recommended && !c.banned);
          const carAhead = sorted.find((c) => c.pos === me.pos - 1) || null;
          const carBehind = sorted.find((c) => c.pos === me.pos + 1) || sorted[1] || null;
          return {
            public_lobby_locked: Boolean(this.publicLobby),
            spotter_active: Boolean(this.copilot.public_spotter !== false || this.publicLobby),
            tv_director: Boolean(this.copilot.tv_director),
            active_camera: this.activeCamera || "Chase",
            radar: {
              status: rStatus,
              left_state: c1Overlap ? "OVERLAP" : "CLEAR",
              right_state: c2Overlap ? "OVERLAP" : (rStatus === "DIVE RIGHT" ? "DIVE" : "CLEAR"),
              nearest_m: Number(Math.min(Math.hypot(rx1, rz1), Math.hypot(rx2, rz2)).toFixed(1)),
              contacts: [
                { index: 1, name: this.cars[1].name, pos: this.cars[1].pos, kind: "remote", compound: this.cars[1].compound, rel_x: Number(rx1.toFixed(2)), rel_z: Number(rz1.toFixed(2)), dist_m: Number(Math.hypot(rx1, rz1).toFixed(1)), closing_mps: 2.4, threat: c1Overlap ? "OVERLAP" : "NEAR" },
                { index: 2, name: this.cars[2].name, pos: this.cars[2].pos, kind: "remote", compound: this.cars[2].compound, rel_x: Number(rx2.toFixed(2)), rel_z: Number(rz2.toFixed(2)), dist_m: Number(Math.hypot(rx2, rz2).toFixed(1)), closing_mps: 4.6, threat: c2Overlap ? "OVERLAP" : (rStatus === "DIVE RIGHT" ? "DIVEBOMB" : "NEAR") },
              ],
            },
            rival_spy: {
              ahead: carAhead ? {
                role: "AHEAD", pos: carAhead.pos, name: carAhead.name, gap_s: Number((me.intAhead || 0.62).toFixed(2)),
                compound: carAhead.compound, tire_pct: Math.round(this.cars[carAhead.index].health * 100),
                energy_pct: Math.round(this.cars[carAhead.index].energy * 100),
                weapons: ["DRS", "SUPER BOOST"], straight_delta_pct: -1.8, corner_delta_pct: 0.9,
                tip: "WE HAVE +1.8% STRAIGHT SPEED — PASS ON EXIT",
              } : null,
              behind: carBehind ? {
                role: "BEHIND", pos: carBehind.pos, name: carBehind.name, gap_s: 0.58,
                compound: carBehind.compound, tire_pct: Math.round(this.cars[carBehind.index].health * 100),
                energy_pct: Math.round(this.cars[carBehind.index].energy * 100),
                weapons: ["SUPER BOOST", "DRS"], straight_delta_pct: 1.6, corner_delta_pct: -1.4,
                tip: "DANGER: SUPER BOOST LOADED — DEFEND INSIDE LINE!",
              } : null,
              field_unlocks: [
                { index: 1, pos: this.cars[1].pos, name: this.cars[1].name, weapons: ["SuperBoost", "DRS"] },
                { index: 2, pos: this.cars[2].pos, name: this.cars[2].name, weapons: ["DRS"] },
              ],
            },
            spotter_call: (this.points > 0 && topCard) ? {
              kind: "CARD",
              slot: topCard.index + 1,
              label: `PRESS [${topCard.index + 1}] → ${topCard.upgrade.toUpperCase()} (${topCard.ev_score} EV)`,
              sub: topCard.reason || "",
            } : null,
          };
        })(),
        overlay: { ...this.overlayCfg },
        radio: this.radioLog,
        commands: this.cmdLog,
        events: this.eventLog,
      };
    }
  }

  window.StandalonePitWallSim = StandalonePitWallSim;
})();
