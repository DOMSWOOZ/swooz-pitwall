/* Backseat Champions — FIA / ATLAS / MoTeC Pit Wall Mission Control */
(() => {
  const COMPOUNDS = ["Standard", "Fast", "Durable", "Boost", "Experimental", "Wet", "Golden"];
  const COMP_SHORT = { Standard: "S", Fast: "F", Durable: "D", Boost: "B", Experimental: "E", Wet: "W", Golden: "G" };
  const PERF_SHORT = {
    Weight: "Weight",
    EngineTorque: "Torque",
    Acceleration: "Accel",
    Downforce: "Downforce",
    Drag: "Drag",
    Suspension: "Suspens.",
    TractionControl: "Traction",
    AngularDrag: "Ang. Drag",
  };

  let ws = null;
  let localSim = null;
  let staticTtsUnavailable = false;
  let snap = null;
  let activeTab = "live";
  let voiceEnabled = true;
  let lastSpokenRadioId = 0;
  let lastCardsKey = "";
  let hoveredCompound = null;
  let lastRadioKey = "";
  let carScreenPositions = [];
  let wheelHeat = [0.35, 0.35, 0.42, 0.42];
  let pushLedUntil = 0;

  // Web Audio & Single-Voice Concurrency Lock
  let audioCtx = null;
  let radioAnalyser = null;
  let radioWaveData = null;
  let activeVoiceSource = null;
  let activeHissSource = null;
  let activeFetchAbort = null;
  let offlineSpeakingUntil = 0;
  let radioQueue = [];
  let radioPlaying = false;
  let currentTxPriority = "INFO";
  let engineerCurrentSpokenText = "";
  let lastTtsLatencyMs = 0;
  let lastTtsCacheTag = "";
  let lastTxFinishMs = 0;
  let txGen = 0;
  let isAudioLeader = true;

  // Hands-Free Voice Command & Tactical Hold State
  let micEnabled = false;
  let speechRec = null;
  let micStream = null;
  let micSource = null;
  let micAnalyser = null;
  let micWaveData = null;
  let micPeakEnv = 0.14;
  let lastLiveMicRms = 0;
  let micActiveUntil = 0;
  let speechInterimKickUntil = 0;
  let lastVoiceCmdMs = 0;
  let lastVoiceActionLabel = "";
  let voiceMatchResetTimer = null;
  let spaceHoldActive = false;
  let btnHoldActive = false;
  let btnPressDownMs = 0;
  let holdKeepaliveTimer = null;

  const PACE_DOCTRINE_INFO = {
    conserve: "ERS RSV 55% · TOW/DEFEND ONLY · 15% OVERCUT TRAFFIC FILTER · +24 EV TIRE/FUEL",
    balanced: "ERS RSV 28% · <1.4s CLOSING SUPER-BOOST · 22% CLEAN-AIR UNDERCUT · OPTIMAL EV",
    attack: "ERS RSV 12% · <1.8s RIVAL-HUNT SUPER-BOOST · 28% EARLY UNDERCUT · +18 EV PACE",
    hammer: "ERS FLOOR 2% · BOTH BOOSTS PINNED (Q3 SPRINT) · 32% SOFT / 2L FLAG OVERRIDE",
  };

  const PERSONA_TEST_LINES = {
    "en-GB-SoniaNeural": "Pit wall copy. Strategy window is live, watching the undercut closely.",
    "en-GB-RyanNeural": "Loud and clear mate! Get in there, tires looking good, push now!",
    "en-GB-ThomasNeural": "Radio check copy. Simply lovely pace, keep hitting your marks.",
    "it-IT-GiuseppeMultilingualNeural": "Copy, we are checking. Telemetry is online, stay focused, head down!",
    "fr-FR-RemyMultilingualNeural": "Radio check clear! Good pace through sector two, manage the tires.",
    "en-AU-WilliamMultilingualNeural": "Yeah copy mate, pit wall has full telemetry. Send it!",
    "en-IE-ConnorNeural": "Loud and clear! Gaps are stable, keep smooth on the exits.",
    "en-US-ChristopherNeural": "Ten-four driver! Clear all around, hammer down into turn one!",
    "en-US-AriaNeural": "Telemetry link synchronized at fifty hertz. All systems nominal.",
    "offline-zira": "Local telemetry channel locked and ready.",
    "offline-david": "Local pit wall radio check loud and clear.",
  };

  // Per-Persona Web Audio Formant/Detune & Presence EQ Trim (all profiles run 100% locally through 90s V10 / F1 FX!)
  const PERSONA_ACOUSTIC_TRIM = {
    "en-GB-SoniaNeural":                { detune: 35,  presHz: 2250, presDb: 3.2 }, // UK · HANNAH (Crisp Strategy)
    "en-GB-RyanNeural":                 { detune: 18,  presHz: 1750, presDb: 2.0 }, // UK · BONO
    "en-GB-ThomasNeural":               { detune: -28, presHz: 1350, presDb: 1.5 }, // UK · GP
    "it-IT-GiuseppeMultilingualNeural": { detune: 50,  presHz: 2100, presDb: 3.0 }, // IT · MARANELLO
    "fr-FR-RemyMultilingualNeural":     { detune: 25,  presHz: 1850, presDb: 2.2 }, // FR · ENSTONE
    "en-AU-WilliamMultilingualNeural":  { detune: -15, presHz: 1650, presDb: 2.4 }, // AU · MELBOURNE
    "en-IE-ConnorNeural":               { detune: 38,  presHz: 1950, presDb: 2.5 }, // IE · SILVERSTONE
    "en-US-ChristopherNeural":          { detune: -60, presHz: 1250, presDb: 3.5 }, // US · CREW CHIEF
    "en-US-AriaNeural":                 { detune: -18, presHz: 2450, presDb: 2.8 }, // US · ATLAS AI
    "offline-zira":                     { detune: 0,   presHz: 1800, presDb: 0.0 },
    "offline-david":                    { detune: 0,   presHz: 1600, presDb: 0.0 },
  };

  // Cross-tab/window single-voice mutex so a browser tab + Desktop App window can NEVER speak simultaneously!
  const tabInstanceId = Math.random().toString(36).slice(2);
  let audioMutexChannel = null;
  try {
    if ("BroadcastChannel" in window) {
      audioMutexChannel = new BroadcastChannel("swooz_pitwall_audio");
      audioMutexChannel.onmessage = (ev) => {
        if (ev.data && ev.data.sender !== tabInstanceId && ev.data.type === "claim_speak") {
          stopAllAudioNow();
        }
      };
    }
  } catch (_) {}

  const savedVoiceInit = localStorage.getItem("bc_voice");
  if (savedVoiceInit === "swooz-dom") {
    localStorage.setItem("bc_voice", "en-GB-SoniaNeural");
  }
  let voiceConfig = {
    voice: (!savedVoiceInit || savedVoiceInit === "swooz-dom") ? "en-GB-SoniaNeural" : savedVoiceInit,
    fx: localStorage.getItem("bc_fx") || "v10",
    ratePct: Number(localStorage.getItem("bc_rate") || 8),
    volume: Number(localStorage.getItem("bc_vol") || 88) / 100,
  };

  // ==================== RESPONSIVE COCKPIT FORM-FACTOR CONTROLLER (PHONE · FOLD · TABLET · PC) ====================
  const initUrlParams = new URLSearchParams(location.search);
  let obsOverlayActive = initUrlParams.get("obs") === "1";
  let obsSplitPanel = initUrlParams.get("obs_panel") || ""; // "right" | "bottom"
  let crewRoleActive = initUrlParams.get("role") === "crew";
  let prevSpotterState = "CLEAR";
  let lastSpatialBeepMs = 0;
  let obsWaveUntil = 0;
  let knownServerBootId = null;
  let leagueHumansOnly = false;

  let deviceModePref = localStorage.getItem("bc_device_mode") || "auto";
  if (!["auto", "slab", "fold", "tablet", "desktop"].includes(deviceModePref)) deviceModePref = "auto";
  let hudTierPref = localStorage.getItem("bc_hud_tier") || "clean";
  if (!["clean", "pro"].includes(hudTierPref)) hudTierPref = "clean";

  function applyHudTier() {
    if (obsSplitPanel || obsOverlayActive) {
      document.body.dataset.hud = "pro";
      return;
    }
    document.body.dataset.hud = hudTierPref;
    const hudBtn = document.getElementById("btn-hud-tier");
    if (hudBtn) {
      const isPro = hudTierPref === "pro";
      hudBtn.textContent = isPro ? "HUD: PRO" : "HUD: CLEAN";
      hudBtn.classList.toggle("active", isPro);
    }
    requestAnimationFrame(() => {
      if (snap) renderAll();
    });
  }

  function computeAutoDeviceMode() {
    const w = window.innerWidth || document.documentElement.clientWidth || 1280;
    const h = Math.max(1, window.innerHeight || document.documentElement.clientHeight || 800);
    const ar = w / h;
    const isTouch = Boolean(
      (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) ||
      (navigator.maxTouchPoints && navigator.maxTouchPoints > 0)
    );
    // Any bar smartphone / narrow portrait phone -> bottom thumb dock
    if (w < 640 || (isTouch && h > w && Math.min(w, h) < 620)) return "slab";
    // Landscape phone or unfolded foldable inner display (near-square split layout)
    if ((isTouch && h < 540 && w >= 640) || (w <= 980 && ar < 1.28)) return "fold";
    // Any capable tablet (portrait or landscape) or compact touch window
    if ((isTouch && w <= 1380) || w <= 1220) return "tablet";
    // Full widescreen desktop / Ultrawide broadcast cockpit
    return "desktop";
  }

  function applyDeviceMode() {
    applyHudTier();
    if (obsSplitPanel || obsOverlayActive) {
      document.body.dataset.device = "desktop";
      requestAnimationFrame(() => { if (snap) renderAll(); });
      return;
    }
    const effective = deviceModePref === "auto" ? computeAutoDeviceMode() : deviceModePref;
    document.body.dataset.device = effective;
    const btn = document.getElementById("btn-device-mode");
    if (btn) {
      const labelMap = { slab: "PHONE", fold: "FOLD", tablet: "TAB", desktop: "PC" };
      if (deviceModePref === "auto") {
        btn.textContent = `AUTO · ${labelMap[effective] || "PC"}`;
        btn.classList.remove("active");
      } else {
        btn.textContent = `VIEW: ${labelMap[deviceModePref] || "PC"}`;
        btn.classList.add("active");
      }
    }
    requestAnimationFrame(() => {
      if (snap) renderAll();
    });
  }

  function setSlabPane(paneName) {
    const liveEl = document.getElementById("tab-live");
    if (!liveEl) return;
    liveEl.dataset.slabPane = paneName;
    document.querySelectorAll(".slab-dock-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.slabTarget === paneName);
    });
    const gridEl = liveEl.querySelector(".pitwall-grid");
    if (gridEl) gridEl.scrollTop = 0;
    requestAnimationFrame(() => {
      if (snap) renderAll();
    });
  }

  // ==================== PUBLIC LOBBY SUITE: OBS OVERLAY, 2P CO-OP CREW & SPATIAL RADAR ====================
  function applySpecialRoleModes() {
    if (obsOverlayActive) {
      document.documentElement.dataset.obs = "1";
      document.body.dataset.obs = "1";
    } else {
      delete document.documentElement.dataset.obs;
      delete document.body.dataset.obs;
    }
    if (obsSplitPanel) {
      document.documentElement.dataset.obsPanel = obsSplitPanel;
      document.body.dataset.obsPanel = obsSplitPanel;
    } else {
      delete document.documentElement.dataset.obsPanel;
      delete document.body.dataset.obsPanel;
    }
    const obsHud = document.getElementById("obs-stream-hud");
    if (obsHud) obsHud.style.display = obsOverlayActive ? "block" : "none";
    const crewDock = document.getElementById("crew-chief-dock");
    if (crewDock) crewDock.style.display = (crewRoleActive && !obsOverlayActive && !obsSplitPanel) ? "flex" : "none";
  }

  function playSpatialSpotterTone(panVal = 0.0, isThreeWide = false) {
    if (!voiceEnabled || !isAudioLeader || obsOverlayActive || obsSplitPanel) return;
    const nowMs = performance.now();
    if (nowMs - lastSpatialBeepMs < 1600) return;
    lastSpatialBeepMs = nowMs;
    try {
      const ctx = ensureAudioCtx();
      const now = ctx.currentTime;
      const panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
      if (panner) panner.pan.value = Math.max(-1, Math.min(1, panVal));
      const notes = isThreeWide ? [660, 880] : [540];
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.value = freq;
        const vol = Math.max(0.025, voiceConfig.volume * 0.09);
        gain.gain.setValueAtTime(vol, now + idx * 0.07);
        gain.gain.exponentialRampToValueAtTime(0.0008, now + idx * 0.07 + 0.09);
        if (panner) {
          osc.connect(gain).connect(panner).connect(ctx.destination);
        } else {
          osc.connect(gain).connect(ctx.destination);
        }
        osc.start(now + idx * 0.07);
        osc.stop(now + idx * 0.07 + 0.095);
      });
    } catch (_) {}
  }

  // ==================== BUILD 16 CIRCULAR HONEYCOMB LED SHIFT-LIGHT LENSES ====================
  function initShiftLights() {
    const box = document.getElementById("shift-led-array");
    if (!box) return;
    let html = "";
    for (let i = 0; i < 16; i++) html += `<span class="sl-seg" id="sl-${i}"></span>`;
    box.innerHTML = html;
  }

  // ==================== AUDIO & F1 ENGINEER RADIO DSP + WAVEFORM ANALYSER ====================
  function ensureAudioCtx() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      radioAnalyser = audioCtx.createAnalyser();
      radioAnalyser.fftSize = 256;
      radioWaveData = new Uint8Array(radioAnalyser.frequencyBinCount);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  async function startMicWaveformCapture() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    try {
      const ctx = ensureAudioCtx();
      stopMicWaveformCapture();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (!micEnabled) {
        stream.getTracks().forEach((tr) => tr.stop());
        return;
      }
      micStream = stream;
      micAnalyser = ctx.createAnalyser();
      micAnalyser.fftSize = 256;
      micAnalyser.smoothingTimeConstant = 0.52;
      micWaveData = new Uint8Array(micAnalyser.frequencyBinCount);
      micSource = ctx.createMediaStreamSource(stream);
      // Connect ONLY to analyser (never ctx.destination) so zero mic echo/feedback!
      micSource.connect(micAnalyser);
    } catch (_) {}
  }

  function stopMicWaveformCapture() {
    if (micSource) {
      try { micSource.disconnect(); } catch (_) {}
      micSource = null;
    }
    if (micStream) {
      try { micStream.getTracks().forEach((tr) => tr.stop()); } catch (_) {}
      micStream = null;
    }
    micAnalyser = null;
    micWaveData = null;
    micActiveUntil = 0;
  }

  function makeSaturationCurve(amount) {
    const n = 512;
    const curve = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const x = (i * 2) / n - 1;
      curve[i] = ((3 + amount) * x * 20 * (Math.PI / 180)) / (Math.PI + amount * Math.abs(x));
    }
    return curve;
  }

  function playRadioBeep() {
    try {
      const ctx = ensureAudioCtx();
      const now = ctx.currentTime;
      const vol = Math.max(0.02, voiceConfig.volume * 0.08);
      [1420, 1840].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(vol, now + idx * 0.06);
        gain.gain.exponentialRampToValueAtTime(0.0008, now + idx * 0.06 + 0.055);
        osc.connect(gain);
        gain.connect(radioAnalyser);
        gain.connect(ctx.destination);
        osc.start(now + idx * 0.06);
        osc.stop(now + idx * 0.06 + 0.06);
      });
    } catch (_) {}
  }

  function playSquelchTail(intensity = 1.0) {
    try {
      const ctx = ensureAudioCtx();
      const len = Math.floor(ctx.sampleRate * 0.075);
      const buf = ctx.createBuffer(1, len, ctx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < len; i++) {
        d[i] = (Math.random() * 2 - 1) * Math.exp(-i / (len * 0.45));
      }
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.value = 1950;
      bp.Q.value = 1.6;
      const gain = ctx.createGain();
      gain.gain.value = 0.065 * voiceConfig.volume * intensity;
      src.connect(bp).connect(gain);
      gain.connect(radioAnalyser);
      gain.connect(ctx.destination);
      src.start();
    } catch (_) {}
  }

  function hardStopActiveSources() {
    if (activeHissSource) {
      try { activeHissSource.stop(); } catch (_) {}
      activeHissSource = null;
    }
    if (activeVoiceSource) {
      try { activeVoiceSource.onended = null; activeVoiceSource.stop(); } catch (_) {}
      activeVoiceSource = null;
    }
    if ("speechSynthesis" in window) {
      try { window.speechSynthesis.cancel(); } catch (_) {}
    }
    offlineSpeakingUntil = 0;
    engineerCurrentSpokenText = "";
  }

  function speakOfflineFallback(msg, onDoneCallback) {
    // Strictly used ONLY on static web demos (Vercel / iPhone standalone) where no local Python server exists!
    if (!("speechSynthesis" in window)) {
      if (onDoneCallback) onDoneCallback();
      return;
    }
    try {
      hardStopActiveSources();
      const u = new SpeechSynthesisUtterance(msg);
      const voices = window.speechSynthesis.getVoices() || [];
      const wantFemale = /sonia|aria|zira/i.test(voiceConfig.voice);
      if (wantFemale) {
        const fem = voices.find((v) => /hazel|susan|libby|sonia|samantha|zira|female/i.test(v.name)) ||
                    voices.find((v) => /en[-_]GB/i.test(v.lang || ""));
        if (fem) u.voice = fem;
      } else {
        const uk = voices.find((v) => /daniel|arthur|oliver|george|mark/i.test(v.name)) ||
                   voices.find((v) => /en[-_]GB/i.test(v.lang || "")) ||
                   voices.find((v) => /david|male/i.test(v.name));
        if (uk) u.voice = uk;
      }
      u.rate = Math.min(1.35, 1.04 + voiceConfig.ratePct / 100);
      u.volume = voiceConfig.volume;
      engineerCurrentSpokenText = msg.toLowerCase();
      offlineSpeakingUntil = performance.now() + Math.max(1400, msg.length * 68);
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        offlineSpeakingUntil = 0;
        engineerCurrentSpokenText = "";
        if (onDoneCallback) onDoneCallback();
      };
      u.onend = done;
      u.onerror = done;
      setTimeout(done, Math.max(2200, msg.length * 85));
      window.speechSynthesis.speak(u);
    } catch (_) {
      if (onDoneCallback) onDoneCallback();
    }
  }

  function stopAllAudioNow() {
    txGen += 1;
    radioQueue = [];
    radioPlaying = false;
    currentTxPriority = "INFO";
    if (activeFetchAbort) {
      try { activeFetchAbort.abort(); } catch (_) {}
      activeFetchAbort = null;
    }
    hardStopActiveSources();
  }

  function speakEngineer(msg, priority = "INFO", explicitSlotId = "") {
    if (!voiceEnabled || !isAudioLeader || obsOverlayActive || obsSplitPanel) return;
    const isSimOnly = Boolean((localSim && localSim.running) || snap?.connection?.simulated);
    if (isSimOnly && document.hidden) return;
    if (priority === "CRITICAL" || (priority === "STRATEGY" && radioPlaying && currentTxPriority === "INFO")) {
      stopAllAudioNow();
      playSingleTransmission(msg, priority, explicitSlotId);
      return;
    }
    radioQueue = [{ msg, priority, explicitSlotId }];
    drainRadioQueue();
  }

  function drainRadioQueue() {
    if (radioPlaying || !radioQueue.length || !voiceEnabled || !isAudioLeader) return;
    const next = radioQueue.shift();
    playSingleTransmission(next.msg, next.priority, next.explicitSlotId || "");
  }

  async function playSingleTransmission(rawMsg, priority = "INFO", explicitSlotId = "") {
    if (!voiceEnabled || !isAudioLeader) return;
    const msg = String(rawMsg || "")
      .replace(/_/g, " ")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/\s+/g, " ")
      .trim();
    if (!msg) return;

    const myGen = ++txGen;
    radioPlaying = true;
    currentTxPriority = priority;
    const reqStartMs = performance.now();

    // Silence any other open Pit Wall tab/window on this PC immediately!
    if (audioMutexChannel) {
      try { audioMutexChannel.postMessage({ type: "claim_speak", sender: tabInstanceId }); } catch (_) {}
    }

    const finishTx = () => {
      if (myGen !== txGen) return;
      setTimeout(() => {
        if (myGen !== txGen) return;
        radioPlaying = false;
        currentTxPriority = "INFO";
        engineerCurrentSpokenText = "";
        lastTxFinishMs = performance.now();
        updateVoiceBarUI();
        drainRadioQueue();
      }, 65);
    };

    // Static web demo ONLY (Vercel / file:// with no local Python server):
    if (staticTtsUnavailable || (localSim && localSim.running)) {
      lastTtsLatencyMs = 4;
      lastTtsCacheTag = "STATIC";
      playRadioBeep();
      speakOfflineFallback(msg, finishTx);
      return;
    }

    // UNIFIED SINGLE-ENGINE LOCAL WINRT PIPELINE (~45ms WAV -> Full 90s V10 FX + Oscilloscope for ALL 11 Profiles!)
    const abortCtrl = new AbortController();
    activeFetchAbort = abortCtrl;

    try {
      const ctx = ensureAudioCtx();
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: msg,
          voice: voiceConfig.voice,
          rate_pct: voiceConfig.ratePct,
          slot_id: explicitSlotId || "",
        }),
        signal: abortCtrl.signal,
      });
      if (!res.ok) {
        if (res.status === 404 || res.status === 405 || res.status === 503) staticTtsUnavailable = true;
        throw new Error("TTS HTTP error");
      }
      const cacheHdr = res.headers.get("X-TTS-Cache") || "LOCAL";
      const personaLineHdr = res.headers.get("X-Persona-Line");
      let customSpokenLine = "";
      if (personaLineHdr) {
        try { customSpokenLine = decodeURIComponent(personaLineHdr).trim(); } catch (_) { customSpokenLine = personaLineHdr.trim(); }
      }
      const arr = await res.arrayBuffer();
      if (myGen !== txGen || !voiceEnabled || !isAudioLeader) return;
      const audioBuf = await ctx.decodeAudioData(arr);
      if (myGen !== txGen || !voiceEnabled || !isAudioLeader) return;

      lastTtsLatencyMs = Math.round(performance.now() - reqStartMs);
      lastTtsCacheTag = cacheHdr === "SWOOZ-REC" ? "REC" : (cacheHdr === "HIT" ? "LOCAL-HIT" : "LOCAL");

      // Atomic stop of ALL audio sources (both Web Audio AND any stray browser speechSynthesis) -> ZERO overlap ever!
      hardStopActiveSources();
      playRadioBeep();

      const trim = PERSONA_ACOUSTIC_TRIM[voiceConfig.voice] || { detune: 0, presHz: 1800, presDb: 0 };
      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      if (src.detune && trim.detune) {
        src.detune.value = trim.detune;
      }
      activeVoiceSource = src;
      engineerCurrentSpokenText = (customSpokenLine || msg).toLowerCase();
      if (customSpokenLine) {
        const firstMsgEl = document.querySelector("#radio-feed .radio-msg");
        if (firstMsgEl && snap?.radio?.length) {
          snap.radio[0].message = customSpokenLine;
          firstMsgEl.innerHTML = `<strong>PIT [${fmtClock(snap.radio[0].time_s)}]:</strong> "${customSpokenLine}"`;
        }
      }

      const pres = ctx.createBiquadFilter();
      pres.type = "peaking";
      pres.frequency.value = trim.presHz || 1800;
      pres.Q.value = 1.1;
      pres.gain.value = trim.presDb || 0;

      const outGain = ctx.createGain();
      outGain.gain.value = voiceConfig.volume * (voiceConfig.fx === "clean" ? 1.0 : 1.28);

      if (voiceConfig.fx === "clean") {
        src.connect(pres).connect(outGain);
        outGain.connect(radioAnalyser);
        outGain.connect(ctx.destination);
        src.onended = () => {
          if (activeVoiceSource === src) activeVoiceSource = null;
          engineerCurrentSpokenText = "";
          finishTx();
        };
      } else {
        const isGrit = voiceConfig.fx === "v10";
        const hp = ctx.createBiquadFilter();
        hp.type = "highpass";
        hp.frequency.value = isGrit ? 520 : 360;

        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.value = isGrit ? 2550 : 3250;

        const mid = ctx.createBiquadFilter();
        mid.type = "peaking";
        mid.frequency.value = 1650;
        mid.Q.value = 1.2;
        mid.gain.value = isGrit ? 7.5 : 4.5;

        const shaper = ctx.createWaveShaper();
        shaper.curve = makeSaturationCurve(isGrit ? 26 : 9);
        shaper.oversample = "2x";

        const hissLen = Math.max(1, Math.floor(audioBuf.duration * ctx.sampleRate));
        const hissBuf = ctx.createBuffer(1, hissLen, ctx.sampleRate);
        const hd = hissBuf.getChannelData(0);
        for (let i = 0; i < hissLen; i++) hd[i] = Math.random() * 2 - 1;
        const hissSrc = ctx.createBufferSource();
        hissSrc.buffer = hissBuf;
        activeHissSource = hissSrc;
        const hissGain = ctx.createGain();
        hissGain.gain.value = (isGrit ? 0.020 : 0.007) * voiceConfig.volume;

        src.connect(pres).connect(hp).connect(mid).connect(shaper).connect(lp).connect(outGain);
        outGain.connect(radioAnalyser);
        outGain.connect(ctx.destination);
        hissSrc.connect(hissGain).connect(hp);
        hissSrc.start(ctx.currentTime + 0.015);
        src.onended = () => {
          try { hissSrc.stop(); } catch (_) {}
          if (activeHissSource === hissSrc) activeHissSource = null;
          playSquelchTail(isGrit ? 1.4 : 0.9);
          if (activeVoiceSource === src) activeVoiceSource = null;
          engineerCurrentSpokenText = "";
          finishTx();
        };
      }

      src.start(ctx.currentTime + 0.015);
    } catch (err) {
      if (err && err.name === "AbortError") return;
      if (myGen !== txGen || !voiceEnabled || !isAudioLeader) return;
      // Only reached if local Python server was shut down completely
      lastTtsLatencyMs = Math.round(performance.now() - reqStartMs);
      lastTtsCacheTag = "FALLBACK";
      playRadioBeep();
      speakOfflineFallback(msg, finishTx);
    }
  }

  // ==================== 60FPS DUAL-CHANNEL PIT-RADIO WAVEFORM LOOP (ENGINEER + DRIVER MIC) ====================
  function drawRadioWaveformLoop() {
    const vid = document.getElementById("pitcam-video");
    if (vid && vid.currentTime >= 2.55) {
      vid.currentTime = 0.05;
    }

    const canvas = document.getElementById("radio-wave-canvas");
    const stage = document.getElementById("pit-radio-stage");
    const tag = document.getElementById("pitcam-tag");
    const drvTag = document.getElementById("drivercam-tag");

    if (canvas && activeTab === "live") {
      const ctx = canvas.getContext("2d");
      const w = canvas.width, h = canvas.height;
      const midY = h / 2;
      ctx.clearRect(0, 0, w, h);

      const now = performance.now();

      // 1) Engineer Channel (Electric Blue)
      let engSamples = null;
      if (radioAnalyser && activeVoiceSource) {
        radioAnalyser.getByteTimeDomainData(radioWaveData);
        engSamples = radioWaveData;
      }
      const synthActive = now < offlineSpeakingUntil || ((obsOverlayActive || obsSplitPanel) && now < obsWaveUntil);
      const engSpeaking = Boolean(engSamples || synthActive);

      // 2) Driver Live Microphone Channel (SWOOZ Papaya-Orange)
      let drvSamples = null;
      let micRms = 0;
      if (micEnabled && micAnalyser && micWaveData) {
        micAnalyser.getByteTimeDomainData(micWaveData);
        drvSamples = micWaveData;
        let sqSum = 0;
        for (let i = 0; i < drvSamples.length; i++) {
          const v = (drvSamples[i] - 128) / 128.0;
          sqSum += v * v;
        }
        micRms = Math.sqrt(sqSum / drvSamples.length);
        // Smooth adaptive gain envelope so quiet & loud mics both look bold and crisp
        micPeakEnv = Math.max(0.055, Math.min(0.65, Math.max(micPeakEnv * 0.986, micRms * 2.35)));
      }
      lastLiveMicRms = micRms;
      const gateThresh = engSpeaking ? 0.042 : 0.013;
      if (micRms > gateThresh || now < speechInterimKickUntil) {
        micActiveUntil = Math.max(micActiveUntil, now + 180);
      }
      const drvSpeaking = Boolean(micEnabled && now < micActiveUntil);

      if (stage) {
        stage.classList.toggle("speaking", engSpeaking);
        stage.classList.toggle("driver-speaking", drvSpeaking);
      }
      if (tag) {
        const latBadge = lastTtsLatencyMs > 0 ? ` · ${lastTtsLatencyMs}ms ${lastTtsCacheTag}` : "";
        tag.textContent = engSpeaking ? `TX // ENGINEER${latBadge}` : "CAM // T1 APEX";
      }
      if (drvTag) {
        drvTag.classList.toggle("armed", Boolean(micEnabled && !drvSpeaking));
        drvTag.textContent = !micEnabled
          ? "YOU // MIC OFF [V]"
          : drvSpeaking
          ? "RX // DOM_SWOOZ"
          : "YOU // OPEN MIC";
      }

      const drawGlowSpline = (centerY, maxHalfH, outerCol, innerCol, sampleFn) => {
        const pts = 96;
        const buildPath = () => {
          ctx.beginPath();
          for (let i = 0; i < pts; i++) {
            const x = (i / (pts - 1)) * w;
            const env = Math.sin((i / (pts - 1)) * Math.PI);
            const rawDy = sampleFn(i, pts, env);
            const y = centerY + Math.max(-maxHalfH + 3, Math.min(maxHalfH - 3, rawDy));
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
        };
        ctx.save();
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        buildPath();
        ctx.shadowColor = outerCol;
        ctx.shadowBlur = 14;
        ctx.strokeStyle = outerCol;
        ctx.lineWidth = 4.0;
        ctx.stroke();

        buildPath();
        ctx.shadowBlur = 4;
        ctx.strokeStyle = innerCol;
        ctx.lineWidth = 1.55;
        ctx.stroke();
        ctx.restore();
      };

      const bothActive = engSpeaking && drvSpeaking;

      if (engSpeaking || drvSpeaking) {
        if (engSpeaking) {
          const cy = bothActive ? h * 0.34 : midY;
          const halfH = bothActive ? h * 0.30 : midY;
          drawGlowSpline(cy, halfH, "#0099ff", "#f2fbff", (i, pts, env) => {
            if (engSamples) {
              const idx = Math.floor((i / pts) * engSamples.length);
              return ((engSamples[idx] - 128) / 128.0) * (halfH * 1.65) * env;
            }
            return Math.sin(now * 0.032 + i * 0.45) * Math.cos(i * 0.22) * (halfH * 0.72) * env;
          });
        }

        if (drvSpeaking) {
          const cy = bothActive ? h * 0.68 : midY;
          const halfH = bothActive ? h * 0.28 : midY;
          const micGain = Math.min(5.2, 0.88 / micPeakEnv);
          drawGlowSpline(cy, halfH, "#ff7b00", "#fff4dc", (i, pts, env) => {
            if (drvSamples && micRms > 0.005) {
              const idx = Math.floor((i / pts) * drvSamples.length);
              const v = (drvSamples[idx] - 128) / 128.0;
              return v * micGain * (halfH * 1.18) * env;
            }
            return Math.sin(now * 0.038 + i * 0.52) * Math.cos(i * 0.27) * (halfH * 0.68) * env;
          });
        }
      } else {
        // Standby / Open-Mic Idle State
        if (!vid || vid.readyState < 2) {
          const bars = 56;
          const step = w / bars;
          ctx.beginPath();
          for (let i = 0; i < bars; i++) {
            const bx = i * step + step * 0.5;
            const env = Math.sin((i / (bars - 1)) * Math.PI);
            const amp = (1.5 + Math.abs(Math.sin(now * 0.0028 + i * 0.35)) * 6.5) * env;
            ctx.moveTo(bx, midY - amp);
            ctx.lineTo(bx, midY + amp);
          }
          ctx.strokeStyle = "rgba(181, 188, 201, 0.38)";
          ctx.lineWidth = 1.8;
          ctx.stroke();
        }

        if (micEnabled) {
          // Subtle live dual-carrier floor when mic is hot so driver sees live mic reactivity immediately
          const pts = 80;
          ctx.save();
          ctx.beginPath();
          for (let i = 0; i < pts; i++) {
            const x = (i / (pts - 1)) * w;
            const env = Math.sin((i / (pts - 1)) * Math.PI);
            let dy = Math.sin(now * 0.006 + i * 0.3) * 1.4 * env;
            if (drvSamples) {
              const idx = Math.floor((i / pts) * drvSamples.length);
              dy += ((drvSamples[idx] - 128) / 128.0) * 85 * env;
            }
            const y = midY + Math.max(-14, Math.min(14, dy));
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.strokeStyle = "rgba(255, 136, 0, 0.58)";
          ctx.shadowColor = "rgba(255, 128, 0, 0.45)";
          ctx.shadowBlur = 6;
          ctx.lineWidth = 1.5;
          ctx.stroke();
          ctx.restore();
        } else {
          ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
          ctx.setLineDash([3, 5]);
          ctx.beginPath();
          ctx.moveTo(12, midY);
          ctx.lineTo(w - 12, midY);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    }

    // Update PUSH LED & knob glow state
    const pushLed = document.getElementById("led-push");
    const pushKnob = document.getElementById("btn-boost-pulse");
    const pushActiveNow = Boolean(
      snap?.copilot?.push_active ||
      snap?.telemetry?.abilities?.super_boost ||
      snap?.telemetry?.abilities?.speed_boost ||
      spaceHoldActive ||
      btnHoldActive ||
      performance.now() < pushLedUntil
    );
    if (pushLed) pushLed.classList.toggle("on", pushActiveNow);
    if (pushKnob) pushKnob.classList.toggle("push-active", pushActiveNow);

    requestAnimationFrame(drawRadioWaveformLoop);
  }

  // ==================== WEBSOCKET + STANDALONE MOBILE SIM FALLBACK ====================
  function activateStandaloneSim() {
    if (localSim && localSim.running) return;
    if (!window.StandalonePitWallSim) return;
    if (!localSim) {
      localSim = new window.StandalonePitWallSim((s) => {
        snap = s;
        renderAll();
      });
    }
    localSim.start();
  }

  function sendAction(payload) {
    const msg = (obsOverlayActive || crewRoleActive || obsSplitPanel) ? { ...payload, spectator: true } : payload;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    } else if (localSim && localSim.running) {
      localSim.handleAction(msg);
    }
  }

  function connectWS() {
    if (location.protocol === "file:") {
      staticTtsUnavailable = true;
      activateStandaloneSim();
      return;
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let fallbackTimer = setTimeout(() => {
      if (!snap) activateStandaloneSim();
    }, 850);

    try {
      const specQs = (obsOverlayActive || crewRoleActive || obsSplitPanel) ? "?spectator=1" : "";
      ws = new WebSocket(`${proto}://${location.host}/ws${specQs}`);
    } catch (_) {
      activateStandaloneSim();
      return;
    }

    ws.onopen = () => {
      sendAction({ action: "prewarm_voice", voice: voiceConfig.voice, rate_pct: voiceConfig.ratePct });
    };

    ws.onmessage = (ev) => {
      clearTimeout(fallbackTimer);
      if (localSim && localSim.running) localSim.stop();
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot") {
          const bootId = msg.data?.connection?.server_boot_id || null;
          if (bootId) {
            if (knownServerBootId === null) knownServerBootId = bootId;
            else if (knownServerBootId !== bootId) {
              location.reload();
              return;
            }
          }
          const wasLeader = isAudioLeader;
          isAudioLeader = msg.audio_leader !== false && !obsOverlayActive && !obsSplitPanel;
          if (wasLeader && !isAudioLeader) {
            stopAllAudioNow();
          }
          snap = msg.data;
          renderAll();
        }
      } catch (_) {}
    };
    ws.onerror = () => {
      activateStandaloneSim();
    };
    ws.onclose = () => {
      if (!snap) activateStandaloneSim();
      setTimeout(connectWS, 2500);
    };
  }

  // ==================== FORMATTERS ====================
  function fmtClock(sec) {
    if (!sec || sec < 0) return "00:00.000";
    const m = Math.floor(sec / 60);
    const s = sec - m * 60;
    return `${String(m).padStart(2, "0")}:${s.toFixed(3).padStart(6, "0")}`;
  }

  function fmtLap(sec) {
    if (sec == null) return "—";
    if (sec >= 60) {
      const m = Math.floor(sec / 60);
      const rem = sec - m * 60;
      return `${m}:${rem.toFixed(3).padStart(6, "0")}`;
    }
    return sec.toFixed(3);
  }

  function drvTLA(name) {
    const clean = String(name || "DRV").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    return (clean.slice(0, 3) || "DRV").padEnd(3, "X");
  }

  function fmtSigned4(v) {
    if (Math.abs(v) < 0.00005) return `<span class="zero-diff">0.0000</span>`;
    const cls = v > 0 ? "pos-diff" : "neg-diff";
    const sign = v > 0 ? "+" : "";
    return `<span class="${cls}">${sign}${v.toFixed(4)}</span>`;
  }

  function healthColor(pct) {
    if (pct <= 18) return "#ff2438";
    if (pct <= 36) return "#f5b700";
    return "#00d26a";
  }

  // ==================== RENDER DISPATCH ====================
  function renderAll() {
    if (!snap) return;
    renderHeaderAndShiftLights();
    renderOverlayAndMiniHud();
    renderPublicLobbySuite();
    if (obsOverlayActive) return;
    if (activeTab === "live") {
      renderTimingTower();
      renderTrackCanvas();
      renderReticleAndThermalPatches();
      renderTraceCanvas();
      renderStintArcAndDiffs();
      renderCommandDeck();
      renderRadio();
    } else if (activeTab === "hardware") {
      renderHardwareMatrix();
      renderRadarCanvas();
      renderTrackSpecs();
    } else if (activeTab === "stints") {
      renderLapHistoryAndLogs();
    }
  }

  function drawProximityRadarOnCanvas(canvasId, radar) {
    const cv = document.getElementById(canvasId);
    if (!cv || !radar) return;
    const ctx = cv.getContext("2d");
    const w = cv.width, h = cv.height;
    const cx = w / 2, cy = h * 0.54;
    ctx.clearRect(0, 0, w, h);

    // Range rings (6m & 14m)
    ctx.strokeStyle = "rgba(148, 163, 184, 0.22)";
    ctx.lineWidth = 1;
    [16, 34].forEach((r) => {
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    });

    // Left / Right blind-spot warning arcs
    if (radar.left_state && radar.left_state !== "CLEAR") {
      ctx.strokeStyle = radar.status === "3-WIDE" ? "#ff2a2a" : "#ff9f1c";
      ctx.lineWidth = 3.5;
      ctx.beginPath();
      ctx.arc(cx, cy, 37, Math.PI * 0.68, Math.PI * 1.32);
      ctx.stroke();
    }
    if (radar.right_state && radar.right_state !== "CLEAR") {
      ctx.strokeStyle = radar.status === "3-WIDE" ? "#ff2a2a" : "#ff9f1c";
      ctx.lineWidth = 3.5;
      ctx.beginPath();
      ctx.arc(cx, cy, 37, -Math.PI * 0.32, Math.PI * 0.32);
      ctx.stroke();
    }

    // Player car silhouette in center
    ctx.fillStyle = "#ff7b00";
    ctx.fillRect(cx - 3.5, cy - 7, 7, 14);
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1;
    ctx.strokeRect(cx - 3.5, cy - 7, 7, 14);

    // Nearby rival contacts (scale: 1m lateral = 4.2px, 1m longitudinal = 2.4px)
    for (const c of (radar.contacts || [])) {
      const px = Math.max(6, Math.min(w - 6, cx + c.rel_x * 4.4));
      const py = Math.max(6, Math.min(h - 6, cy - c.rel_z * 2.4));
      ctx.fillStyle = c.threat === "OVERLAP" ? "#ff2a2a" : (c.threat === "DIVEBOMB" ? "#ffd166" : "#38bdf8");
      ctx.beginPath();
      ctx.arc(px, py, 4.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "700 7.5px 'Barlow Condensed', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(drvTLA(c.name), px, py - 5.5);
    }
  }

  function renderPublicLobbySuite() {
    const ps = snap.public_suite || {};
    const radar = ps.radar || { status: "CLEAR", left_state: "CLEAR", right_state: "CLEAR", contacts: [] };
    const pubBtn = document.getElementById("btn-pub-lobby");
    if (pubBtn) {
      if (ps.public_lobby_locked) {
        pubBtn.textContent = "PUB // SHIELD";
        pubBtn.classList.add("pub-locked", "active");
      } else {
        pubBtn.textContent = "PUB SPOTTER";
        pubBtn.classList.remove("pub-locked");
        pubBtn.classList.toggle("active", Boolean(ps.spotter_active));
      }
    }

    // Spatial Left/Right Ear Radar Tone on blind-spot transition
    if (radar.status !== prevSpotterState) {
      if (radar.status === "3-WIDE") playSpatialSpotterTone(0.0, true);
      else if (radar.status === "CAR LEFT" || radar.status === "DIVE LEFT") playSpatialSpotterTone(-0.88, false);
      else if (radar.status === "CAR RIGHT" || radar.status === "DIVE RIGHT") playSpatialSpotterTone(0.88, false);
      prevSpotterState = radar.status;
    }

    const hudBox = document.getElementById("heli-radar-hud");
    const pill = document.getElementById("radar-status-pill");
    if (hudBox && pill) {
      hudBox.classList.remove("warn-left", "warn-right", "warn-both");
      pill.className = "radar-status-pill mono";
      if (radar.status === "3-WIDE") {
        hudBox.classList.add("warn-both");
        pill.classList.add("crit");
      } else if (radar.status.includes("LEFT")) {
        hudBox.classList.add("warn-left");
        pill.classList.add("warn");
      } else if (radar.status.includes("RIGHT")) {
        hudBox.classList.add("warn-right");
        pill.classList.add("warn");
      }
      pill.textContent = radar.status;
      drawProximityRadarOnCanvas("heli-radar-canvas", radar);
    }

    // Instant <2ms Public-Lobby Spotter Banner
    const toast = document.getElementById("pub-spotter-toast");
    const pstBadge = document.getElementById("pst-badge");
    const pstMain = document.getElementById("pst-main");
    if (toast && pstMain) {
      const sc = ps.spotter_call;
      const showToast = Boolean(sc && (ps.public_lobby_locked || !snap.copilot?.auto_card));
      toast.style.display = showToast ? "flex" : "none";
      if (showToast && sc) {
        if (pstBadge) pstBadge.textContent = ps.public_lobby_locked ? "PUBLIC SPOTTER" : "SPOTTER";
        pstMain.textContent = sc.label;
      }
    }

    // Rival Build Spy + Camera Director
    const spyBox = document.getElementById("rival-spy-box");
    if (spyBox && ps.rival_spy) {
      const renderDossier = (d, cls) => {
        if (!d) return "";
        const wpns = (d.weapons || []).map((w) => `<span class="spy-wpn">${w}</span>`).join(" ");
        const strSign = d.straight_delta_pct >= 0 ? "+" : "";
        const crnSign = d.corner_delta_pct >= 0 ? "+" : "";
        return `<div class="spy-card ${cls}">
          <div class="spy-top">
            <span>${d.role}: P${d.pos} ${d.name} (${d.gap_s.toFixed(2)}s · ${d.compound[0]} ${d.tire_pct}%)</span>
            <span>${wpns || '<span class="muted">BASE</span>'}</span>
          </div>
          <div class="muted">RIVAL EDGE: STR ${strSign}${d.straight_delta_pct.toFixed(1)}% · CRN ${crnSign}${d.corner_delta_pct.toFixed(1)}% · ERS ${d.energy_pct}%</div>
          <div class="spy-tip">▸ ${d.tip}</div>
        </div>`;
      };
      const htmlSpy = renderDossier(ps.rival_spy.ahead, "ahead") + renderDossier(ps.rival_spy.behind, "behind");
      spyBox.innerHTML = htmlSpy || `<div class="muted">Clear air ahead &amp; behind — full field telemetry active.</div>`;
    }

    if (obsSplitPanel === "right") {
      const targetDeck = (snap.cards?.points || 0) > 0 ? "cards" : "spy";
      document.querySelectorAll(".deck-tab").forEach((t) => t.classList.toggle("active", t.dataset.deck === targetDeck));
      document.querySelectorAll(".deck-pane").forEach((p) => p.classList.toggle("active", p.id === `deck-${targetDeck}`));
    }

    const tvBtn = document.getElementById("btn-tv-director");
    if (tvBtn) {
      const tvOn = Boolean(ps.tv_director);
      tvBtn.classList.toggle("active", tvOn);
      tvBtn.textContent = tvOn ? `TV DIR // ${String(ps.active_camera || "AUTO").replace("Onboard_", "").toUpperCase()}` : "TV DIR // OFF";
    }
    document.querySelectorAll("button[data-cam]").forEach((b) => {
      b.classList.toggle("active", b.dataset.cam === ps.active_camera && !ps.tv_director);
    });

    // Transparent 1920x1080 OBS Studio Broadcast Overlay
    if (obsOverlayActive) {
      const sess = snap.session || {};
      const tel = snap.telemetry || {};
      const obsSess = document.getElementById("obs-session-lbl");
      const obsPub = document.getElementById("obs-pub-tag");
      if (obsSess) obsSess.textContent = `${String(sess.scene || "GRAND PRIX").toUpperCase()} · LAP ${tel.lap || 0}/${sess.total_laps || 0}`;
      if (obsPub) obsPub.textContent = ps.public_lobby_locked ? "PUBLIC // SHIELD" : "50HZ // LIVE";

      const obsTower = document.getElementById("obs-tower");
      if (obsTower) {
        obsTower.innerHTML = (snap.standings || []).slice(0, 10).map((c) => `
          <div class="obs-trow ${c.is_me ? "me" : ""}">
            <b>P${c.pos}</b>
            <span>${drvTLA(c.name)} ${c.is_purple ? "[FL]" : ""}</span>
            <span>${c.pos === 1 ? "LDR" : `+${c.gap_to_leader.toFixed(2)}`}</span>
            <span>${COMP_SHORT[c.compound] || "S"}</span>
          </div>
        `).join("");
      }
      const thrPct = Math.round(Math.max(0, Number(tel.pedal || 0)) * 100);
      const brkPct = Math.round(Math.max(0, -Number(tel.pedal || 0)) * 100);
      const ersPct = Math.round(Number(tel.energy_pct || 0));
      const elThr = document.getElementById("obs-thr");
      const elBrk = document.getElementById("obs-brk");
      const elErs = document.getElementById("obs-ers");
      if (elThr) elThr.style.width = `${thrPct}%`;
      if (elBrk) elBrk.style.width = `${brkPct}%`;
      if (elErs) elErs.style.width = `${ersPct}%`;
      const elKph = document.getElementById("obs-kph");
      const elTire = document.getElementById("obs-tire");
      if (elKph) elKph.textContent = String(Math.round(tel.speed_kmh || 0)).padStart(3, "0");
      if (elTire) elTire.textContent = `${COMP_SHORT[snap.tires?.current] || "S"} ${Math.round(snap.stint?.tire_health_pct || 100)}%`;
      const obsRadLbl = document.getElementById("obs-radar-lbl");
      if (obsRadLbl) obsRadLbl.textContent = radar.status;
      drawProximityRadarOnCanvas("obs-radar-canvas", radar);
      const latestR = (snap.radio || [])[0];
      const obsToast = document.getElementById("obs-radio-toast");
      if (obsToast && latestR?.message) {
        obsToast.textContent = `RADIO // "${latestR.message}"`;
      }
    }
  }

  async function loadOpenGpLeague() {
    const tbody = document.getElementById("league-standings-tbody");
    const recBox = document.getElementById("league-records-list");
    if (!tbody || !recBox) return;

    const renderLeague = (data) => {
      const cfg = data.config || {};
      const hdr = document.getElementById("league-title-hdr");
      if (hdr && cfg.league_name) hdr.textContent = `${cfg.league_name} // ${cfg.season_tag || "PUBLIC & OPEN STANDINGS"}`;
      const inpName = document.getElementById("inp-league-name");
      if (inpName && !inpName.value && cfg.league_name) inpName.value = cfg.league_name;
      const dStat = document.getElementById("league-discord-status");
      if (dStat) dStat.textContent = data.toast || (cfg.has_discord_webhook ? "WEBHOOK LINKED ✓" : "NO WEBHOOK SET");

      const rows = data.standings || [];
      tbody.innerHTML = rows.length ? rows.map((r) => {
        const climb = r.positions_gained >= 0 ? `<span class="pos-diff">+${r.positions_gained}</span>` : `<span class="neg-diff">${r.positions_gained}</span>`;
        return `<tr class="${r.rank === 1 ? "row-me" : ""}">
          <td class="mono"><b>#${r.rank}</b></td>
          <td><b>${r.name}</b>${r.is_human ? '<span class="hum-badge">HUMAN</span>' : ""}</td>
          <td class="mono"><b>${r.points}</b></td>
          <td class="mono"><span class="elo-pill">${r.elo}</span></td>
          <td class="mono">${r.races}</td>
          <td class="mono">${r.wins} (${r.win_pct}%)</td>
          <td class="mono">${r.podiums}</td>
          <td class="mono">${r.fastest_laps}</td>
          <td class="mono">P${r.avg_finish.toFixed(1)}</td>
          <td class="mono">${climb}</td>
          <td class="mono">${r.best_lap_s ? fmtLap(r.best_lap_s) : "—"}</td>
        </tr>`;
      }).join("") : `<tr><td colspan="11" class="muted">Host a Public or Custom Lobby with <code>http://127.0.0.1:8765/race-results</code> to rank drivers automatically!</td></tr>`;

      const recs = data.track_records || [];
      recBox.innerHTML = recs.length ? recs.map((rc) => `
        <div class="rec-row">
          <div><b>${rc.track}</b> <span class="muted">· ${rc.car_class}</span></div>
          <div><strong style="color:#d946ef">${fmtLap(rc.best_lap_s)}</strong> <span class="muted">(${rc.driver})</span></div>
        </div>
      `).join("") : `<div class="muted">No lap records recorded yet.</div>`;
    };

    try {
      const res = await fetch(`./api/league?humans=${leagueHumansOnly ? "1" : "0"}`);
      if (!res.ok) throw new Error("Static demo");
      renderLeague(await res.json());
    } catch (_) {
      renderLeague({
        config: { league_name: "SWOOZ OPEN GP CHAMPIONSHIP", season_tag: "SEASON 1 · SHOWCASE STANDINGS", has_discord_webhook: false },
        standings: [
          { rank: 1, name: "Dom_Swooz", is_human: true, points: 243, elo: 1742, races: 12, wins: 8, win_pct: 66.7, podiums: 11, fastest_laps: 6, avg_finish: 1.6, positions_gained: 31, best_lap_s: 18.395 },
          { rank: 2, name: "Thruster", is_human: true, points: 168, elo: 1638, races: 12, wins: 2, win_pct: 16.7, podiums: 8, fastest_laps: 3, avg_finish: 2.9, positions_gained: 14, best_lap_s: 18.512 },
          { rank: 3, name: "Pole", is_human: true, points: 142, elo: 1594, races: 12, wins: 1, win_pct: 8.3, podiums: 6, fastest_laps: 2, avg_finish: 3.8, positions_gained: 9, best_lap_s: 18.640 },
          { rank: 4, name: "Valkyrie", is_human: true, points: 119, elo: 1551, races: 11, wins: 1, win_pct: 9.1, podiums: 4, fastest_laps: 1, avg_finish: 4.5, positions_gained: 12, best_lap_s: 18.790 },
          { rank: 5, name: "Circler", is_human: false, points: 96, elo: 1512, races: 12, wins: 0, win_pct: 0.0, podiums: 3, fastest_laps: 0, avg_finish: 5.4, positions_gained: 4, best_lap_s: 18.905 },
        ],
        track_records: [
          { track: "JapanShort", car_class: "Formula", best_lap_s: 18.395, driver: "Dom_Swooz" },
          { track: "Castellet", car_class: "ModernFormula", best_lap_s: 26.840, driver: "Dom_Swooz" },
          { track: "LeMans_Endurance", car_class: "Endurance", best_lap_s: 100.150, driver: "Dom_Swooz" },
          { track: "California_GP", car_class: "Formula", best_lap_s: 27.791, driver: "Dom_Swooz" },
        ],
      });
    }
  }

  function renderOverlayAndMiniHud() {
    const ov = snap.overlay || { game_refocus: true, global_hotkeys: true, pin_top: false, mini_hud: false };
    const btnRef = document.getElementById("btn-game-refocus");
    const btnGhk = document.getElementById("btn-global-keys");
    const btnPin = document.getElementById("btn-pin-top");
    const btnMh = document.getElementById("btn-mini-hud");
    if (btnRef) {
      btnRef.classList.toggle("active", Boolean(ov.game_refocus));
      btnRef.textContent = `NO-ALT-TAB: ${ov.game_refocus ? "ON" : "OFF"}`;
    }
    if (btnGhk) {
      btnGhk.classList.toggle("active", Boolean(ov.global_hotkeys));
      btnGhk.textContent = `IN-GAME KEYS: ${ov.global_hotkeys ? "ON" : "OFF"}`;
    }
    if (btnPin) {
      btnPin.classList.toggle("active", Boolean(ov.pin_top));
      btnPin.textContent = ov.pin_top ? "PINNED ▲" : "PIN TOP";
    }
    if (btnMh) {
      btnMh.classList.toggle("active", Boolean(ov.mini_hud));
    }

    const isMini = Boolean(ov.mini_hud);
    document.body.classList.toggle("mini-hud-mode", isMini);
    if (!isMini) return;

    const tel = snap.telemetry || {};
    const stint = snap.stint || {};
    const cp = snap.copilot || {};
    const pit = snap.pit || {};
    const meRow = (snap.standings || []).find((r) => r.is_me);

    const posEl = document.getElementById("mh-pos");
    const gapEl = document.getElementById("mh-gap");
    if (posEl) posEl.textContent = `P${tel.pos || 1}`;
    if (gapEl) {
      gapEl.textContent = !meRow || meRow.pos === 1
        ? `LEADER · L${tel.lap || 0}`
        : `+${Number(meRow.gap_to_leader || 0).toFixed(3)}s · INT +${Number(meRow.interval_ahead || 0).toFixed(2)}s`;
    }

    const compEl = document.getElementById("mh-comp");
    const pctEl = document.getElementById("mh-tire-pct");
    const cliffEl = document.getElementById("mh-cliff");
    const callEl = document.getElementById("mh-call");
    const thPct = Number(stint.tire_health_pct ?? 100);
    if (compEl) compEl.textContent = String(snap.tires?.current || "STD").slice(0, 4).toUpperCase();
    if (pctEl) {
      pctEl.textContent = `${thPct.toFixed(0)}%`;
      pctEl.style.color = healthColor(thPct);
    }
    if (cliffEl) cliffEl.textContent = `${Number(stint.laps_to_cliff ?? 0).toFixed(1)}L TO CLIFF`;
    if (callEl) {
      const rl = String(stint.risk_level || "NOMINAL");
      callEl.textContent = pit.pit_planned ? "BOX ARMED" : rl;
      callEl.classList.toggle("warn", pit.pit_planned || rl === "CRITICAL" || rl === "PUNCTURE");
    }

    const activeProfId = cp.push_profile || "k1_super";
    const pSlot = (snap.loadouts?.push_slots || []).find((x) => x.id === activeProfId);
    const pLabel = pSlot ? pSlot.label : activeProfId.toUpperCase();
    const mhPush = document.getElementById("mh-btn-push");
    if (mhPush) {
      mhPush.textContent = `▸ ${pLabel} [F5]`;
      mhPush.classList.toggle("firing", Boolean(cp.push_active));
    }
    const mhBox = document.getElementById("mh-btn-box");
    if (mhBox) {
      mhBox.textContent = pit.pit_planned ? "STAY OUT [F6]" : "BOX [F6]";
      mhBox.classList.toggle("pit-armed", Boolean(pit.pit_planned));
    }
    document.getElementById("mh-btn-autocard")?.classList.toggle("active", Boolean(cp.auto_card));
    document.getElementById("mh-btn-autotire")?.classList.toggle("active", Boolean(cp.auto_tire));
    document.getElementById("mh-btn-pitguard")?.classList.toggle("active", Boolean(cp.auto_pit));
    const mhMic = document.getElementById("mh-btn-mic");
    if (mhMic) {
      mhMic.classList.toggle("active", Boolean(micEnabled));
      mhMic.textContent = micEnabled ? "MIC ON [V]" : "MIC OFF [V]";
    }

    const latestRadio = (snap.radio || [])[0];
    const mhRad = document.getElementById("mh-radio-text");
    if (mhRad && latestRadio?.text) {
      mhRad.textContent = latestRadio.text;
    }

    const hand = snap.cards?.hand || [];
    const strip = document.getElementById("mh-cards-strip");
    if (strip) {
      strip.innerHTML = hand
        .filter((c) => !c.banned)
        .map((c) => `<button class="mh-card-pill ${c.recommended ? "rec" : ""}" data-mhpick="${c.index}" title="Click or press Numpad ${c.index + 1}">[${c.index + 1}] ${c.recommended ? "★ " : ""}${c.upgrade}</button>`)
        .join("");
    }
  }

  // ==================== HEADER & 28-LED SHIFT-LIGHT BAR ====================
  function renderHeaderAndShiftLights() {
    const conn = snap.connection;
    const sess = snap.session;
    const tel = snap.telemetry;

    const badge = document.getElementById("conn-badge");
    const lbl = document.getElementById("conn-label");
    badge.className = "conn-tag " + (conn.mode === "LIVE_UDP" ? "live" : conn.mode === "SIM_DEMO" ? "sim" : "wait");
    lbl.textContent = conn.mode === "LIVE_UDP" ? "LIVE 50HZ" : conn.mode === "SIM_DEMO" ? "SIM 50HZ" : "STANDBY";

    document.getElementById("hdr-sub").textContent = `LIVE RACE ENGINEER · v${conn.game_version} · ${conn.pps.toFixed(0)}HZ`;
    document.getElementById("hdr-session-type").textContent = String(sess.session_type || "RACE").toUpperCase();
    document.getElementById("hdr-track").textContent = sess.scene || "—";

    const totLaps = sess.total_laps || 0;
    document.getElementById("hdr-lap").textContent = totLaps > 0 ? `${tel.lap}/${totLaps}` : `${tel.lap}`;
    document.getElementById("hdr-time").textContent = fmtClock(sess.session_time);
    document.getElementById("hdr-purple").textContent = sess.fastest_lap_s
      ? `${fmtLap(sess.fastest_lap_s)} (${drvTLA(sess.fastest_driver)})`
      : "—";

    const w = sess.weather;
    let wTxt = `${w >= 0 ? "+" : ""}${w.toFixed(2)} ${w > 0.35 ? "STORM" : w > 0 ? "WET" : w > -0.1 ? "DAMP" : "DRY"}`;
    if (sess.rain_eta_s != null && sess.rain_eta_s < 180) {
      wTxt += w <= 0 ? ` · RAIN ~${sess.rain_eta_s.toFixed(0)}s` : ` · DRY ~${sess.rain_eta_s.toFixed(0)}s`;
    }
    document.getElementById("hdr-weather").textContent = wTxt;
    document.getElementById("hdr-bw").textContent = `${conn.kbps.toFixed(1)} KB/S`;

    // 28-LED Shift-Light Array driven by Speed ratio + Throttle + Boost/DRS
    const topRef = Math.max(230, tel.top_speed_kmh || 245);
    const ab = tel.abilities || {};
    let rpmRatio = (tel.speed_kmh / topRef) * (tel.pedal >= 0 ? (0.86 + 0.14 * tel.pedal) : 0.78);
    if (ab.drs || ab.super_boost || ab.speed_boost) rpmRatio = Math.min(1.0, rpmRatio + 0.08);
    const litCount = Math.max(0, Math.min(16, Math.round(rpmRatio * 16)));

    for (let i = 0; i < 16; i++) {
      const seg = document.getElementById(`sl-${i}`);
      if (!seg) continue;
      if (i >= litCount) {
        seg.className = "sl-seg";
      } else if (i < 6) {
        seg.className = "sl-seg on-g";
      } else if (i < 11) {
        seg.className = "sl-seg on-y";
      } else if (i < 14) {
        seg.className = "sl-seg on-r";
      } else {
        seg.className = "sl-seg on-m";
      }
    }
    document.getElementById("hdr-rpm-spd").textContent = `${tel.speed_kmh.toFixed(0).padStart(3, "0")} KPH`;

    const simBtn = document.getElementById("btn-sim-toggle");
    simBtn.textContent = conn.simulated ? "SIM ON" : "SIM OFF";
    simBtn.classList.toggle("active", conn.simulated);

    const h = conn.hello || {};
    const fg = document.getElementById("flag-game");
    if (conn.udp_bind_error) {
      fg.textContent = "PORT BUSY";
      fg.className = "api-dot-item warn";
    } else if (h.game_version) {
      fg.textContent = `API ${h.rate_hz}HZ`;
      fg.className = "api-dot-item on";
    } else {
      fg.textContent = conn.simulated ? "SIM FEED" : "PROBING";
      fg.className = "api-dot-item";
    }
    const setDot = (id, on) => {
      const el = document.getElementById(id);
      if (el) el.className = "api-dot-item" + (on ? " on" : "");
    };
    setDot("flag-drv-data", h.driver_data ?? conn.simulated);
    setDot("flag-plr-data", h.player_data ?? conn.simulated);
    setDot("flag-events", h.decision_events ?? conn.simulated);
    setDot("flag-plr-in", sess.player_input || h.player_input);
    setDot("flag-drv-in", sess.driver_input || h.driver_input);
  }

  // ==================== 16-CAR FIA SLANTED TIMING TOWER ====================
  function renderTimingTower() {
    const container = document.getElementById("timing-tbody");
    const rv = snap.hardware.rival_car;
    document.getElementById("rival-lock-pill").textContent =
      `TGT: P${rv.pos} ${drvTLA(rv.name)}${rv.locked ? " [LOCKED]" : ""}`;

    let html = "";
    for (const c of snap.standings) {
      const rowCls = c.is_me ? "fia-row is-me" : c.is_rival ? "fia-row is-rival" : "fia-row";
      const slashCls = c.is_me ? "slash-me" : c.is_rival ? "slash-rival" : c.pos <= 3 ? "slash-top" : "";

      let badges = "";
      if (c.is_me) badges += `<span class="fia-badge b-you">YOU</span>`;
      else if (c.is_rival) badges += `<span class="fia-badge b-tgt">TGT</span>`;
      if (c.is_purple) badges += `<span class="fia-badge b-purp">FL</span>`;
      if (c.in_pits) badges += `<span class="fia-badge b-pit">PIT</span>`;
      else if (c.pit_planned) badges += `<span class="fia-badge b-box">BOX</span>`;
      if (c.drs) badges += `<span class="fia-badge b-drs">DRS</span>`;

      const gapMain = c.pos === 1 ? "LEADER" : `+${c.gap_to_leader.toFixed(3)}`;
      let paceSub = c.pos === 1 ? `L${c.lap}` : `INT +${c.interval_ahead.toFixed(3)}`;
      if (!c.is_me && Math.abs(c.closing_s_per_lap) >= 0.02) {
        const cls = c.closing_s_per_lap > 0 ? "pace-up" : "pace-dn";
        const sgn = c.closing_s_per_lap > 0 ? "+" : "";
        paceSub = `<span class="${cls}">${sgn}${c.closing_s_per_lap.toFixed(2)}/L</span>`;
      }

      const compChar = COMP_SHORT[c.compound] || "S";
      const thCol = c.puncture ? "#ff2438" : healthColor(c.tire_health_pct);
      const thTxt = c.puncture ? "PUNCTURE" : `${c.tire_health_pct.toFixed(0)}% · ${c.stint_laps}L`;
      const wtTxt = c.is_me ? `PITS: ${c.pit_stops}` : `${c.weight_diff >= 0 ? "+" : ""}${c.weight_diff.toFixed(4)}`;
      const wtCls = c.is_me ? "val-secondary" : c.weight_diff > 0.0001 ? "val-secondary pace-up" : c.weight_diff < -0.0001 ? "val-secondary pace-dn" : "val-secondary";

      html += `<div class="${rowCls}" data-car="${c.index}">
        <div class="pos-cluster">
          <div class="pos-trap ${c.pos === 1 ? "p1" : ""}"><span>${c.pos}</span></div>
          <div class="team-slash ${slashCls}"></div>
        </div>
        <div class="drv-block">
          <div class="drv-top-line">
            <span class="drv-tla">${drvTLA(c.name)}</span>
            ${badges}
          </div>
          <div class="drv-sub">${c.name}</div>
        </div>
        <div class="cell-r mono">
          <span class="val-primary">${gapMain}</span>
          <span class="val-secondary">${paceSub}</span>
        </div>
        <div class="cell-r mono">
          <span class="val-primary ${c.is_purple ? "purp" : ""}">${fmtLap(c.last_lap_s)}</span>
          <span class="val-secondary">${fmtLap(c.best_lap_s)}</span>
        </div>
        <div>
          <div class="pirelli-ring ring-${c.compound}" title="${c.compound}">${compChar}</div>
        </div>
        <div class="cell-r mono">
          <span class="val-primary" style="color:${thCol};font-size:10px">${thTxt}</span>
          <span class="${wtCls}">${wtTxt}</span>
        </div>
      </div>`;
    }
    container.innerHTML = html;
  }

  // ==================== ASPHALT & KERB CIRCUIT VECTOR MAP ====================
  function renderTrackCanvas() {
    const canvas = document.getElementById("track-canvas");
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(300, Math.floor(rect.width));
    const h = Math.max(180, Math.floor(rect.height));
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }
    const ctx = canvas.getContext("2d");
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // Subtle blueprint coordinate grid
    ctx.strokeStyle = "rgba(255, 255, 255, 0.025)";
    ctx.lineWidth = 1;
    for (let gx = 40; gx < w; gx += 40) { ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke(); }
    for (let gy = 40; gy < h; gy += 40) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke(); }

    const pts = [];
    for (const p of snap.map.track_pts) pts.push([p[0], p[2]]);
    for (const rl of snap.map.racing_line) pts.push(rl.c, rl.l, rl.r);
    for (const c of snap.standings) pts.push([c.xyz[0], c.xyz[2]]);
    if (pts.length < 2) { ctx.restore(); return; }

    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const [x, z] of pts) {
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
    }
    const pad = 28;
    const spanX = Math.max(20, maxX - minX);
    const spanZ = Math.max(20, maxZ - minZ);
    const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2 - 24) / spanZ);
    const offX = (w - spanX * scale) * 0.5;
    const offY = (h - 24 - spanZ * scale) * 0.5;
    const toScreen = (x, z) => [offX + (x - minX) * scale, h - 24 - (offY + (z - minZ) * scale)];

    // 1) Multi-layered FIA Broadcast Asphalt Ribbon + White Track Edges
    const tpts = snap.map.track_pts;
    if (tpts.length >= 3) {
      ctx.beginPath();
      tpts.forEach((p, idx) => {
        const [sx, sy] = toScreen(p[0], p[2]);
        if (idx === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      if (tpts.length > 60) {
        const dClose = Math.hypot(tpts[0][0] - tpts[tpts.length - 1][0], tpts[0][2] - tpts[tpts.length - 1][2]);
        if (dClose < 75) ctx.closePath();
      }
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      // Outer white edge
      ctx.strokeStyle = "rgba(230, 234, 242, 0.78)";
      ctx.lineWidth = 14;
      ctx.stroke();
      //Crimson kerb accent
      ctx.strokeStyle = "rgba(225, 6, 0, 0.55)";
      ctx.lineWidth = 11.5;
      ctx.stroke();
      // Dark asphalt core
      ctx.strokeStyle = "#1b1f28";
      ctx.lineWidth = 9;
      ctx.stroke();
    }

    // 2) Live 20-pt Racing Corridor & Optimal Line
    const rline = snap.map.racing_line;
    if (rline.length >= 2) {
      ctx.beginPath();
      rline.forEach((pt, idx) => {
        const [lx, ly] = toScreen(pt.l[0], pt.l[1]);
        if (idx === 0) ctx.moveTo(lx, ly); else ctx.lineTo(lx, ly);
      });
      for (let i = rline.length - 1; i >= 0; i--) {
        const [rx, ry] = toScreen(rline[i].r[0], rline[i].r[1]);
        ctx.lineTo(rx, ry);
      }
      ctx.closePath();
      ctx.fillStyle = "rgba(0, 210, 106, 0.16)";
      ctx.fill();

      ctx.beginPath();
      rline.forEach((pt, idx) => {
        const [cx, cy] = toScreen(pt.c[0], pt.c[1]);
        if (idx === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
      });
      ctx.strokeStyle = "#00d26a";
      ctx.lineWidth = 2.4;
      ctx.stroke();
    }

    // 3) Car Markers
    carScreenPositions = [];
    const ordered = [...snap.standings].sort((a, b) => (a.is_me ? 2 : a.is_rival ? 1 : 0) - (b.is_me ? 2 : b.is_rival ? 1 : 0));
    for (const c of ordered) {
      const [sx, sy] = toScreen(c.xyz[0], c.xyz[2]);
      carScreenPositions.push({ index: c.index, x: sx, y: sy });

      if (c.drs || c.in_pits) {
        ctx.beginPath();
        ctx.arc(sx, sy, c.is_me ? 11 : 8.5, 0, Math.PI * 2);
        ctx.strokeStyle = c.in_pits ? "#ffffff" : "#00d26a";
        ctx.lineWidth = 1.8;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(sx, sy, c.is_me ? 6.8 : c.is_rival ? 6.2 : 4.5, 0, Math.PI * 2);
      ctx.fillStyle = c.is_me ? "#ff8000" : c.is_rival ? "#e10600" : c.is_purple ? "#d900ff" : "#dce1eb";
      ctx.fill();
      ctx.strokeStyle = "#090a0c";
      ctx.lineWidth = 1.6;
      ctx.stroke();

      if (c.is_me || c.is_rival || c.pos === 1) {
        ctx.fillStyle = c.is_me ? "#ff9e3d" : c.is_rival ? "#ff5c58" : "#ffffff";
        ctx.font = "700 10px 'JetBrains Mono', Consolas, monospace";
        ctx.fillText(drvTLA(c.name), sx + 9, sy + 3);
      }
    }
    ctx.restore();

    // Floating Magenta Fastest-Lap tag
    const pBox = document.getElementById("map-purple-callout");
    if (snap.session.fastest_lap_s) {
      pBox.style.display = "flex";
      document.getElementById("map-purple-val").textContent =
        `${drvTLA(snap.session.fastest_driver)} ${fmtLap(snap.session.fastest_lap_s)}`;
    } else {
      pBox.style.display = "none";
    }

    const tel = snap.telemetry;
    const ab = tel.abilities || {};
    document.getElementById("hud-speed").textContent = tel.speed_kmh.toFixed(0);
    document.getElementById("hud-curlap").textContent = tel.current_lap_s.toFixed(3);
    document.getElementById("hud-lastlap").textContent = fmtLap(tel.last_lap_s);
    document.getElementById("hud-bestlap").textContent = fmtLap(tel.best_lap_s);
    document.getElementById("val-energy").textContent = `${tel.energy_pct.toFixed(0)}%`;
    document.getElementById("val-draft").textContent = `${((ab.slipstream || 0) * 100).toFixed(0)}%`;

    document.getElementById("ab-drs").classList.toggle("active", Boolean(ab.drs));
    document.getElementById("ab-speed").classList.toggle("active", Boolean(ab.speed_boost));
    document.getElementById("ab-corner").classList.toggle("active", Boolean(ab.cornering_boost));
    document.getElementById("ab-super").classList.toggle("active", Boolean(ab.super_boost));
    document.getElementById("ab-party").classList.toggle("active", Boolean(ab.party_mode));
  }

  // ==================== G-FORCE RETICLE & 4-WHEEL THERMAL CONTACT PATCHES ====================
  function drawThermalPatch(canvasId, heatNorm, latBias) {
    const c = document.getElementById(canvasId);
    if (!c) return;
    const ctx = c.getContext("2d");
    const w = c.width, h = c.height;
    ctx.clearRect(0, 0, w, h);

    // Base cool blue-teal tire carcass
    ctx.fillStyle = "#084b8a";
    ctx.fillRect(0, 0, w, h);

    const hx = w * (0.5 + Math.max(-0.22, Math.min(0.22, latBias * 0.5)));
    const hy = h * 0.5;
    const rOuter = Math.max(w, h) * 0.72;
    const grad = ctx.createRadialGradient(hx, hy, 2, hx, hy, rOuter);

    const t = Math.max(0.05, Math.min(1.0, heatNorm));
    if (t > 0.62) {
      grad.addColorStop(0.0, "#df0018");
      grad.addColorStop(0.28, "#ff4d00");
      grad.addColorStop(0.55, "#ffcf00");
      grad.addColorStop(0.80, "#1ad176");
      grad.addColorStop(1.0, "#0b5da8");
    } else if (t > 0.34) {
      grad.addColorStop(0.0, "#ff8800");
      grad.addColorStop(0.32, "#ffd900");
      grad.addColorStop(0.65, "#1fd678");
      grad.addColorStop(1.0, "#0b5da8");
    } else {
      grad.addColorStop(0.0, "#76e856");
      grad.addColorStop(0.45, "#00b89c");
      grad.addColorStop(1.0, "#084b8a");
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Subtle vertical tread/contact ribs
    ctx.strokeStyle = "rgba(0, 0, 0, 0.16)";
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75].forEach((f) => {
      ctx.beginPath(); ctx.moveTo(w * f, 0); ctx.lineTo(w * f, h); ctx.stroke();
    });
  }

  function renderReticleAndThermalPatches() {
    const tel = snap.telemetry;
    // Pedals & balance
    const thr = Math.max(0, tel.pedal) * 100;
    const brk = Math.max(0, -tel.pedal) * 100;
    document.getElementById("bar-throttle").style.width = `${thr.toFixed(1)}%`;
    document.getElementById("val-throttle").textContent = `${thr.toFixed(0)}%`;
    document.getElementById("bar-brake").style.width = `${brk.toFixed(1)}%`;
    document.getElementById("val-brake").textContent = `${brk.toFixed(0)}%`;

    const balBar = document.getElementById("bar-balance");
    const balPct = Math.min(50, Math.abs(tel.understeer_index) * 350);
    balBar.style.left = tel.understeer_index >= 0 ? "50%" : `${50 - balPct}%`;
    balBar.style.width = `${balPct}%`;
    document.getElementById("val-steer").textContent =
      tel.understeer_index > 0.015 ? "USTEER" : tel.understeer_index < -0.015 ? "OSTEER" : "NEUT";

    document.getElementById("st-topspeed").textContent = `${tel.top_speed_kmh.toFixed(0)}KPH`;
    document.getElementById("st-offtrack").textContent = tel.off_track_count;

    // 4-Wheel Thermal Contact Patches
    const wearFactor = 1.0 - (snap.stint.tire_health_pct / 100.0);
    tel.wheels.forEach((w, i) => {
      const slipMag = Math.hypot(w.slip_f, w.slip_s);
      const targetHeat = Math.min(1.0, 0.24 + slipMag * 1.15 + wearFactor * 0.34 + (i >= 2 ? 0.08 : 0));
      wheelHeat[i] = wheelHeat[i] * 0.82 + targetHeat * 0.18;
      const estTempC = Math.round(78 + wheelHeat[i] * 44);

      drawThermalPatch(`pc-${i}`, wheelHeat[i], w.slip_s);
      document.getElementById(`wt-${i}`).textContent = `${estTempC}°C`;
      const stEl = document.getElementById(`wf-${i}`);
      const unitEl = document.getElementById(`w-${i}`);
      unitEl.classList.toggle("off", !w.on_track);
      const stTxt = !w.grounded ? "AIR" : !w.on_track ? "OFF-TRK" : w.slip_f < -0.22 ? "LOCKUP" : w.slip_f > 0.30 ? "WHEELSPIN" : "OPTIMAL";
      stEl.textContent = stTxt;
      stEl.style.color = !w.on_track ? "#ff2438" : slipMag > 0.30 ? "#f5b700" : "#00d26a";
      document.getElementById(`ws-${i}`).textContent = `SLP ${slipMag.toFixed(2)}`;
    });

    // Precision G-Force Reticle Canvas
    const gg = document.getElementById("gg-canvas");
    const ctx = gg.getContext("2d");
    const cw = gg.width, ch = gg.height;
    const cx = cw / 2, cy = ch / 2, maxG = 4.0, rMax = cw * 0.39;
    ctx.clearRect(0, 0, cw, ch);

    ctx.strokeStyle = "#2b303c";
    ctx.lineWidth = 1;
    [0.33, 0.66, 1.0].forEach((f) => {
      ctx.beginPath(); ctx.arc(cx, cy, rMax * f, 0, Math.PI * 2); ctx.stroke();
    });
    ctx.beginPath();
    ctx.moveTo(cx - rMax - 6, cy); ctx.lineTo(cx + rMax + 6, cy);
    ctx.moveTo(cx, cy - rMax - 6); ctx.lineTo(cx, cy + rMax + 6);
    ctx.stroke();

    ctx.fillStyle = "#747d8f";
    ctx.font = "600 8.5px 'Barlow Condensed', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("LONG", cx, cy - rMax - 9);
    ctx.fillText("BRK", cx, cy + rMax + 15);
    ctx.fillText("L", cx - rMax - 11, cy + 3);
    ctx.fillText("R", cx + rMax + 11, cy + 3);

    const trail = tel.gg_trail || [];
    if (trail.length > 1) {
      ctx.beginPath();
      trail.forEach(([lg, ng], idx) => {
        const px = cx + (lg / maxG) * rMax;
        const py = cy - (ng / maxG) * rMax;
        if (idx === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = "rgba(255, 128, 0, 0.45)";
      ctx.lineWidth = 1.6;
      ctx.stroke();
    }

    const gx = cx + Math.max(-1, Math.min(1, tel.lat_g / maxG)) * rMax;
    const gy = cy - Math.max(-1, Math.min(1, tel.long_g / maxG)) * rMax;
    ctx.beginPath();
    ctx.arc(gx, gy, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#f3f4f6";
    ctx.fill();
    ctx.strokeStyle = "#ff8000";
    ctx.lineWidth = 2;
    ctx.stroke();

    document.getElementById("val-latg").textContent = `${tel.lat_g >= 0 ? "+" : ""}${tel.lat_g.toFixed(2)}G LAT`;
    document.getElementById("val-longg").textContent = `${tel.long_g >= 0 ? "+" : ""}${tel.long_g.toFixed(2)}G LNG`;
    document.getElementById("val-peakg").textContent = `PK ${tel.peak_g.toFixed(1)}G`;
  }

  // ==================== 4-LANE MULTI-OSCILLOSCOPE TRACE ====================
  function renderTraceCanvas() {
    const canvas = document.getElementById("trace-canvas");
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(260, Math.floor(rect.width));
    const h = Math.max(110, Math.floor(rect.height));
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }
    const ctx = canvas.getContext("2d");
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // Horizontal lane dividers & vertical time grid
    ctx.strokeStyle = "#1d212b";
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75].forEach((f) => {
      ctx.beginPath(); ctx.moveTo(0, h * f); ctx.lineTo(w, h * f); ctx.stroke();
    });
    for (let vx = 0; vx < w; vx += 48) {
      ctx.beginPath(); ctx.moveTo(vx, 0); ctx.lineTo(vx, h); ctx.stroke();
    }

    const traces = snap.telemetry.traces || [];
    if (traces.length < 2) { ctx.restore(); return; }

    const drawLane = (laneIdx, normFn, color, lw = 1.6) => {
      const laneTop = (laneIdx * 0.25) * h + 4;
      const laneH = h * 0.25 - 8;
      ctx.beginPath();
      traces.forEach((pt, idx) => {
        const x = (idx / (traces.length - 1)) * (w - 8);
        const v = Math.max(0, Math.min(1, normFn(pt)));
        const y = laneTop + (1.0 - v) * laneH;
        if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = lw;
      ctx.stroke();
    };

    const maxSpd = Math.max(250, snap.telemetry.top_speed_kmh || 250);
    drawLane(0, (p) => p.speed / maxSpd, "#f3f4f6", 1.8);
    drawLane(1, (p) => Math.max(0, p.pedal), "#00d26a", 1.6);
    drawLane(2, (p) => Math.max(0, -p.pedal), "#ff2438", 1.6);
    drawLane(3, (p) => (p.steer + 1.0) * 0.5, "#29d8ff", 1.5);

    const aiObs = snap.telemetry.ai_obs;
    const extMeta = snap.cards?.extreme_ai;
    const isExtSync = Boolean(snap.copilot?.extreme_ai_sync);
    const p1Win = snap.cards?.p1_blueprint?.winner || "BLITZ";
    const aiBadge = document.getElementById("ai-net-badge");
    if (aiBadge) {
      aiBadge.classList.toggle("synced", Boolean(isExtSync || (aiObs && aiObs.policy_name)));
      if (aiObs && aiObs.policy_name) {
        const who = aiObs.driver_name ? `P${aiObs.pos || 1} ${aiObs.driver_name.toUpperCase()} · ` : "";
        aiBadge.textContent = `EXTREME AI: ${who}${aiObs.policy_name}`;
        drawLane(1, (p) => p.ai_pedal != null ? Math.max(0, p.ai_pedal) : 0, "#e84cff", 1.25);
        drawLane(3, (p) => p.ai_steer != null ? (p.ai_steer + 1.0) * 0.5 : 0.5, "#c084fc", 1.1);
      } else if (isExtSync) {
        const kLogs = extMeta?.log_files ? `${(extMeta.log_files / 1000).toFixed(1)}K` : "80.7K";
        aiBadge.textContent = `EXTREME AI SYNC: ${kLogs} GBDT · ${p1Win.toUpperCase()} P1`;
      } else {
        aiBadge.textContent = "EXTREME AI // SYNC";
      }
    }

    // Live playhead scanline on right edge
    ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
    ctx.beginPath();
    ctx.moveTo(w - 8, 0);
    ctx.lineTo(w - 8, h);
    ctx.stroke();

    ctx.restore();
  }

  // ==================== SEMI-CIRCULAR STINT DEGRADATION ARC GAUGE & CENTER-ZERO COMPARATOR ====================
  function drawStintArcGauge(healthPct, cliffPct = 22) {
    const c = document.getElementById("stint-arc-canvas");
    if (!c) return;
    const ctx = c.getContext("2d");
    const w = c.width, h = c.height;
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2, cy = h - 8, r = Math.min(86, h - 22);
    const cFrac = Math.max(0.10, Math.min(0.45, cliffPct / 100.0));
    const warnFrac = Math.min(0.60, cFrac + 0.14);

    // Background track arc (PI to 2*PI)
    ctx.lineCap = "butt";
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI * 2);
    ctx.strokeStyle = "#222630";
    ctx.lineWidth = 12;
    ctx.stroke();

    // Dynamic Stint Zones shifted live by Pace Mode (Conserve 15% <-> Hammer 32%!)
    const zoneArc = (f0, f1, col) => {
      ctx.beginPath();
      ctx.arc(cx, cy, r - 11, Math.PI + f0 * Math.PI, Math.PI + f1 * Math.PI);
      ctx.strokeStyle = col;
      ctx.lineWidth = 3.5;
      ctx.stroke();
    };
    zoneArc(0.0, cFrac, "#d900ff");
    zoneArc(cFrac, warnFrac, "#f5b700");
    zoneArc(warnFrac, 1.0, "#4b5366");

    // Active Health Arc
    const frac = Math.max(0.01, Math.min(1.0, healthPct / 100.0));
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI + frac * Math.PI);
    ctx.strokeStyle = healthPct <= cliffPct ? "#e10600" : healthPct <= (warnFrac * 100) ? "#f5b700" : "#e8eaef";
    ctx.lineWidth = 12;
    ctx.stroke();

    // Cliff Threshold Marker Notch on Arc
    const cliffAng = Math.PI + cFrac * Math.PI;
    ctx.strokeStyle = "#ff8000";
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(cliffAng) * (r - 15), cy + Math.sin(cliffAng) * (r - 15));
    ctx.lineTo(cx + Math.cos(cliffAng) * (r + 8), cy + Math.sin(cliffAng) * (r + 8));
    ctx.stroke();

    // Outer precision tick marks
    ctx.strokeStyle = "#4b5366";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 20; i++) {
      const ang = Math.PI + (i / 20) * Math.PI;
      const r0 = r + 9;
      const r1 = r + (i % 5 === 0 ? 15 : 12);
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
      ctx.lineTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
      ctx.stroke();
    }

    // Pointer Needle
    const pAng = Math.PI + frac * Math.PI;
    const nx = cx + Math.cos(pAng) * (r - 16);
    const ny = cy + Math.sin(pAng) * (r - 16);
    ctx.beginPath();
    ctx.arc(nx, ny, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#ff8000";
    ctx.fill();
  }

  function renderStintArcAndDiffs() {
    const st = snap.stint;
    drawStintArcGauge(st.tire_health_pct, st.cliff_pct || 22);

    const pill = document.getElementById("stint-risk-pill");
    pill.textContent = st.risk_level;
    pill.className = `status-tag risk-${st.risk_level}`;

    document.getElementById("st-health").textContent = `${st.tire_health_pct.toFixed(1)}%`;
    document.getElementById("st-wear").textContent = `${st.wear_per_lap_pct.toFixed(1)}%`;
    document.getElementById("st-cliff-laps").textContent = `${st.laps_to_zero.toFixed(1)}L LEFT`;

    const fpEl = document.getElementById("st-flag-proj");
    fpEl.textContent = `${st.projected_finish_pct.toFixed(1)}% AT FLAG`;
    fpEl.style.color = st.projected_finish_pct <= 8 ? "#ff2438" : st.projected_finish_pct <= 20 ? "#f5b700" : "#00d26a";

    document.getElementById("rj-loss").textContent = st.pit_loss_s.toFixed(2);
    document.getElementById("rj-pos").textContent = `P${st.rejoin_position}`;
    const airEl = document.getElementById("rj-air");
    airEl.textContent = st.air_status;
    airEl.style.color = st.air_status === "CLEAN AIR" ? "#00d26a" : "#f5b700";

    const vLine = document.getElementById("stint-verdict");
    vLine.textContent = st.verdict;
    vLine.className = "stint-footer-line mono" + (st.risk_level === "CRITICAL" || st.risk_level === "PUNCTURE" ? " crit" : "");

    const ah = st.rejoin_ahead ? `P${st.rejoin_ahead.pos} ${drvTLA(st.rejoin_ahead.name)} (-${st.rejoin_ahead.gap_s.toFixed(2)}s)` : "CLEAR";
    const bh = st.rejoin_behind ? `P${st.rejoin_behind.pos} ${drvTLA(st.rejoin_behind.name)} (+${st.rejoin_behind.gap_s.toFixed(2)}s)` : "CLEAR";
    document.getElementById("rj-traffic").textContent = `EXIT GAP: AHEAD ${ah}  |  BEHIND ${bh}`;

    const pitBtn = document.getElementById("btn-pit-toggle");
    if (snap.pit.in_pits) {
      pitBtn.textContent = "IN PIT LANE";
      pitBtn.classList.add("planned");
    } else if (snap.pit.pit_planned) {
      pitBtn.textContent = "BOX CONFIRMED (CANCEL)";
      pitBtn.classList.add("planned");
    } else if (snap.telemetry.puncture) {
      pitBtn.textContent = "FORCED BOX · PUNCTURE!";
      pitBtn.classList.add("planned");
    } else if (!snap.pit.can_pit) {
      const remLaps = st.laps_remaining_exact ?? 2;
      pitBtn.textContent = remLaps <= 1.05 ? "NO PIT · FINAL LAP" : "PIT LOCKED";
      pitBtn.classList.remove("planned");
    } else {
      pitBtn.textContent = "BOX THIS LAP";
      pitBtn.classList.remove("planned");
    }

    // Center-Zero .0001 Hardware Delta Comparator Bars (Image 2 & 3 style!)
    const hw = snap.hardware;
    document.getElementById("diff-vs-label").textContent = `YOU VS P${hw.rival_car.pos} ${drvTLA(hw.rival_car.name)}`;
    let diffHtml = "";
    for (const a of hw.areas) {
      const d = a.delta_vs_rival;
      const pct = Math.min(48, Math.abs(d) * 320); // ±0.15 full scale
      const left = d >= 0 ? 50 : 50 - pct;
      const col = Math.abs(d) < 0.0001 ? "#4b5366" : d > 0 ? "#00d26a" : "#e10600";
      diffHtml += `<div class="comp-bar-row" title="You: ${a.mine.toFixed(4)} | Rival: ${a.rival.toFixed(4)} | Grid Rank: #${a.rank}/16">
        <span class="cbr-lbl">${PERF_SHORT[a.area] || a.area}</span>
        <div class="cbr-track">
          <div class="cbr-fill" style="left:${left.toFixed(1)}%;width:${pct.toFixed(1)}%;background:${col}"></div>
        </div>
        <span class="cbr-val mono">${fmtSigned4(d)}</span>
      </div>`;
    }
    document.getElementById("live-diff-list").innerHTML = diffHtml;
  }

  // ==================== CARDS, COMPOUNDS & TACTILE METALLIC SWITCHES ====================
  function renderCommandDeck() {
    const cards = snap.cards;
    document.getElementById("card-pts-badge").textContent = `${cards.points}`;

    const p1Top = document.getElementById("p1b-top");
    const p1Sub = document.getElementById("p1b-sub");
    if (p1Top && p1Sub) {
      const bp = cards.p1_blueprint;
      const hp = cards.human_p1;
      const fxp = cards.facility_xp || {};
      const cStrat = (snap.copilot?.card_strategy || cards.strategy || "p1_mimic").toUpperCase();
      const activeCardSlot = (snap.loadouts?.card_slots || []).find((x) => x.id.toUpperCase() === cStrat);
      const isCastelletSlot = activeCardSlot?.base_archetype === "castellet_comms" || activeCardSlot?.label === "CASTELLET";
      if (snap.copilot?.lendurance_mode || cStrat === "LENDURANCE") {
        p1Top.textContent = `P1 REF // [L'ENDURANCE] DOM_SWOOZ @ LE MANS (G3→P1 · +1.901s · 100.15s · 28T · 7.5% BOX / 8.6% FLAG)`;
        p1Sub.textContent = `FAC XP: SPD ${fxp.Speed || 0}/6 · CRN ${fxp.Cornering || 0}/6 · PRF ${fxp.Performance || 0}/6 · BST ${fxp.Boost || 0}/6 | 99.8% STR · 6 DRS · 15.87s PIT · BOOST TIRE`;
      } else if (isCastelletSlot) {
        p1Top.textContent = `P1 REF // [CASTELLET · SUPER COMMS] DOM_SWOOZ (10/10 LAPS LED · +5.257s · -26.54s PIT #1 · 37 UPG · 5x GOLDEN STACK)`;
        p1Sub.textContent = `FAC XP: PRF ${fxp.Performance || 0}/6 (GOLDEN) · BST ${fxp.Boost || 0}/6 · SPD ${fxp.Speed || 0}/6 | L3-7 DURA -> L8-10 GOLDEN (22.7% FLAG)`;
      } else if (bp) {
        const fs = bp.final_stats || {};
        const kw = fs.power_kw ? ` · ${fs.power_kw}kW` : "";
        const tiers = fs.total_perm_tiers ? ` · ${fs.total_perm_tiers}T` : "";
        const domTag = hp ? ` · DOM P1 ${hp.track.toUpperCase()} (+${hp.win_margin_s.toFixed(1)}s)` : "";
        p1Top.textContent = `P1 REF // [${cStrat}] ${bp.winner.toUpperCase()} @ ${bp.track.toUpperCase()} (G${bp.grid}→P1 · ${bp.best_lap_s.toFixed(2)}s${tiers}${kw})${domTag}`;
        const topUpgs = (bp.top_upgrades || []).slice(0, 3).join(", ");
        p1Sub.textContent = `FAC XP: SPD ${fxp.Speed || 0}/6 · CRN ${fxp.Cornering || 0}/6 · PRF ${fxp.Performance || 0}/6 · BST ${fxp.Boost || 0}/6 | P1 CORE: ${topUpgs}`;
      } else {
        p1Top.textContent = `P1 ENGINE // [${cStrat}] PitSpeed 1.87x · Duration 1.83x · Susp 1.63x · Drag 1.61x`;
        p1Sub.textContent = `FAC XP: SPD ${fxp.Speed || 0}/6 · CRN ${fxp.Cornering || 0}/6 · PRF ${fxp.Performance || 0}/6 · BST ${fxp.Boost || 0}/6`;
      }
    }

    const cKey = JSON.stringify([cards.points, cards.ban_tokens, cards.hand]);
    if (cKey !== lastCardsKey) {
      lastCardsKey = cKey;
      const box = document.getElementById("cards-container");
      if (!cards.hand || cards.hand.length === 0) {
        box.innerHTML = `<div class="muted" style="padding:4px 0">No upgrade hand active (${cards.upgrades_applied} upgrades installed).</div>`;
      } else {
        box.innerHTML = cards.hand.map((c) => `
          <div class="card-row ${c.recommended ? "rec" : ""} ${c.banned ? "banned" : ""}">
            <div>
              <div class="c-title">${c.recommended ? "[TOP EV] " : ""}${c.upgrade} <span class="muted">${c.facility} T${c.tier + 1}</span></div>
              <div class="c-meta">${c.reason}</div>
            </div>
            <div class="c-btns">
              <span class="c-ev mono">${c.ev_score.toFixed(0)}</span>
              ${!c.banned ? `<button class="btn-pick" data-pick="${c.index}">PICK</button>` : `<span class="muted">BANNED</span>`}
              ${!c.banned && cards.ban_tokens > 0 ? `<button class="btn-ban" data-ban="${c.index}">BAN</button>` : ""}
            </div>
          </div>
        `).join("");
      }
    }

    const tires = snap.tires;
    const recComp = tires.recommendation?.compound || "Standard";
    const qNote = tires.queued ? ` · NEXT BOX: ${tires.queued.toUpperCase()}` : "";
    document.getElementById("tire-rec-lbl").textContent =
      `OPTIMAL: ${recComp.toUpperCase()} — ${tires.recommendation?.reason || ""}${qNote}`;

    const profiles = tires.profiles || [];
    const stripEl = document.getElementById("compound-strip");
    if (stripEl && !stripEl.children.length) {
      stripEl.innerHTML = COMPOUNDS.map((comp) => `
        <button class="comp-btn" data-tire="${comp}">
          <span class="pirelli-ring ring-${comp}" style="width:18px;height:18px;font-size:10px">${COMP_SHORT[comp]}</span>
          <span>${comp.slice(0, 4).toUpperCase()}</span>
          <span class="cb-pace mono" id="cbp-${comp}">—</span>
          <span class="cb-stint mono" id="cbs-${comp}">—</span>
          <small class="mono" id="cbl-${comp}">UNL</small>
          <span class="cb-opt-bar" id="cbo-${comp}"></span>
        </button>
      `).join("");
    }

    const profMap = {};
    for (const p of profiles) profMap[p.compound] = p;
    const inspectTarget = hoveredCompound || recComp || tires.current || "Standard";

    for (const comp of COMPOUNDS) {
      const btn = stripEl?.querySelector(`button[data-tire="${comp}"]`);
      const p = profMap[comp];
      if (!btn || !p) continue;
      btn.className = [
        "comp-btn",
        tires.current === comp ? "active" : "",
        recComp === comp ? "rec" : "",
        inspectTarget === comp ? "inspected" : "",
        !p.usable ? "depleted" : "",
      ].filter(Boolean).join(" ");

      const paceEl = document.getElementById(`cbp-${comp}`);
      if (paceEl) {
        if (Math.abs(p.pace_delta_s) < 0.03) {
          paceEl.textContent = "BASE";
          paceEl.className = "cb-pace mono base";
        } else {
          // Negative seconds/lap = FASTER (green +gain!), Positive = SLOWER (red -loss!)
          const faster = p.pace_delta_s < 0;
          paceEl.textContent = `${p.pace_delta_s > 0 ? "+" : ""}${p.pace_delta_s.toFixed(2)}s`;
          paceEl.className = `cb-pace mono ${faster ? "gain" : "loss"}`;
        }
      }

      const stintEl = document.getElementById(`cbs-${comp}`);
      if (stintEl) {
        stintEl.textContent = p.makes_flag ? `✓${p.safe_laps.toFixed(0)}L` : `~${p.safe_laps.toFixed(0)}L`;
        stintEl.className = `cb-stint mono ${p.makes_flag ? "flag" : ""}`;
      }

      const leftEl = document.getElementById(`cbl-${comp}`);
      if (leftEl) {
        leftEl.textContent = p.picks_left == null ? "UNL" : `${p.picks_left}X`;
      }

      const barEl = document.getElementById(`cbo-${comp}`);
      if (barEl) {
        barEl.style.width = `${p.optimal_score}%`;
        barEl.style.backgroundColor = p.optimal_score >= 75 ? "#00d26a" : p.optimal_score >= 45 ? "#f5b700" : "#ff2438";
      }
    }

    // Live +/- Optimal Effects Inspector Box
    const inspEl = document.getElementById("compound-inspector");
    const ip = profMap[inspectTarget];
    if (inspEl && ip) {
      const paceFmt = Math.abs(ip.pace_delta_s) < 0.03
        ? "BASELINE PACE"
        : ip.pace_delta_s < 0
        ? `${ip.pace_delta_s.toFixed(2)}s/L FASTER`
        : `+${ip.pace_delta_s.toFixed(2)}s/L SLOWER`;
      inspEl.innerHTML = `
        <div class="ci-hdr">
          <span class="ci-title">${ip.compound.toUpperCase()} · ${ip.optimal_score.toFixed(0)}% OPTIMAL ${ip.makes_flag ? "· ✓ MAKES FLAG" : ""}</span>
          <span class="ci-stats mono">${paceFmt} · ${ip.wear_pct_lap.toFixed(1)}%/L (${ip.safe_laps.toFixed(1)}L SAFE)</span>
        </div>
        <div class="ci-effects">
          <div class="ci-pros">${ip.pros.map((t) => `<span>${t}</span>`).join("")}</div>
          <div class="ci-cons">${ip.cons.map((t) => `<span>${t}</span>`).join("")}</div>
        </div>
      `;
    }

    // Spun-Metal Pushbuttons + Recessed LED Indicators
    const cp = snap.copilot;
    ["auto_pit", "auto_tire", "auto_card"].forEach((k) => {
      const btn = document.getElementById(`cp-${k}`);
      const led = document.getElementById(`led-${k}`);
      if (btn) btn.classList.toggle("on", Boolean(cp[k]));
      if (led) led.classList.toggle("on", Boolean(cp[k]));
    });
    const boxKnob = document.getElementById("btn-metal-box");
    const boxLed = document.getElementById("led-box");
    const boxActive = Boolean(snap.pit.pit_planned || snap.pit.in_pits);
    if (boxKnob) boxKnob.classList.toggle("on", boxActive);
    if (boxLed) boxLed.classList.toggle("on", boxActive);

    const boostRocker = document.getElementById("cp-auto_boost");
    if (boostRocker) {
      boostRocker.classList.toggle("on", Boolean(cp.auto_boost));
      boostRocker.textContent = `ERS: ${cp.auto_boost ? "ARMED" : "OFF"}`;
    }

    // 4-Stage Strategy Pace Selector, Active Doctrine Strip & Tactical Push Bar
    const mode = cp.pace_mode || "balanced";
    const isLend = Boolean(cp.lendurance_mode);
    const isExtAi = Boolean(cp.extreme_ai_sync);
    const lendBtn = document.getElementById("btn-lendurance");
    const extBtn = document.getElementById("btn-extreme-ai");
    if (lendBtn) lendBtn.classList.toggle("active", isLend);
    if (extBtn) extBtn.classList.toggle("active", isExtAi);
    document.querySelectorAll(".pace-seg").forEach((el) => {
      el.classList.toggle("active", el.dataset.pace === mode);
    });
    const sumEl = document.getElementById("pace-mode-summary");
    if (sumEl) {
      sumEl.textContent = isExtAi
        ? `EXTREME AI · ${(snap.stint.cliff_pct || 26).toFixed(0)}% CLIFF`
        : isLend
        ? `L'END P1 · ${(snap.stint.cliff_pct || 10).toFixed(0)}% CLIFF`
        : `${mode.toUpperCase()} · ${(snap.stint.cliff_pct || 22).toFixed(0)}% CLIFF`;
    }
    const docStrip = document.getElementById("pace-doctrine-strip");
    if (docStrip) {
      const p1BpName = (snap.cards?.p1_blueprint?.winner || "BLITZ").toUpperCase();
      docStrip.className = `pace-doctrine-strip mono mode-${isExtAi ? "extreme" : isLend ? "lendurance" : mode}`;
      docStrip.textContent = isExtAi
        ? `EXTREME AI 80.7K // QUAD 6/6 RUSH · 26% CLIFF · SUPER COMMS · ${p1BpName} P1 CLONE`
        : isLend
        ? "L'ENDURANCE P1 // 10% DEEP CLIFF (15.87s PIT) · SLINGSHOT · BOOST TIRE · MULSANNE DRAG+BOOST"
        : (PACE_DOCTRINE_INFO[mode] || PACE_DOCTRINE_INFO.balanced);
    }

    const curProf = cp.push_profile || "k1_super";
    const pushSlots = snap.loadouts?.push_slots || [];
    document.querySelectorAll(".pp-chip").forEach((el, idx) => {
      const s = pushSlots[idx];
      if (s) {
        el.dataset.pprof = s.id;
        if (el.textContent !== s.label) el.textContent = s.label;
        el.title = `${s.title} (${s.duration_s}s · Voice: "${s.label}")`;
        const isGolden = s.style === "golden_pixel" || s.mode === "super_comms" || /super\s*comms/i.test(s.label);
        el.classList.toggle("golden-pixel", isGolden);
      }
      el.classList.toggle("active", el.dataset.pprof === curProf);
    });
    const pushKnobEl = document.getElementById("btn-boost-pulse");
    const activePushObj = pushSlots.find((x) => x.id === curProf);
    const isSuperCommsArmed = Boolean(
      curProf === "super_comms" || activePushObj?.mode === "super_comms" || activePushObj?.style === "golden_pixel"
    );
    if (pushKnobEl) pushKnobEl.classList.toggle("golden-comms-armed", isSuperCommsArmed);

    const curCStrat = cp.card_strategy || "p1_mimic";
    const cardSlots = snap.loadouts?.card_slots || [];
    document.querySelectorAll(".cs-chip").forEach((el, idx) => {
      const s = cardSlots[idx];
      if (s) {
        el.dataset.cstrat = s.id;
        if (el.textContent !== s.label) el.textContent = s.label;
        el.title = `${s.name}: ${s.summary} (Voice: "${s.label}")`;
        const isGoldenCard = s.style === "golden_pixel" || s.base_archetype === "castellet_comms" || /castellet/i.test(s.label);
        el.classList.toggle("golden-pixel", isGoldenCard);
      }
      el.classList.toggle("active", el.dataset.cstrat === curCStrat);
    });
    const pStatus = document.getElementById("push-status-lbl");
    if (pStatus) {
      pStatus.classList.toggle("golden-active", Boolean(isSuperCommsArmed && cp.push_active));
      if (spaceHoldActive || btnHoldActive || cp.push_hold) {
        pStatus.textContent = "HOLD BOTH:";
        pStatus.classList.add("active");
      } else if (cp.push_active && cp.push_remaining_s > 0.05) {
        pStatus.textContent = isSuperCommsArmed
          ? `★ COMMS ${Number(cp.push_remaining_s).toFixed(1)}s:`
          : `PUSH ${Number(cp.push_remaining_s).toFixed(1)}s:`;
        pStatus.classList.add("active");
      } else {
        pStatus.textContent = "PUSH MODE:";
        pStatus.classList.remove("active");
      }
    }
    updateVoiceBarUI();

    const wearBtn = document.getElementById("btn-cycle-wear");
    if (wearBtn) {
      const wm = Number(cp.wear_mult || 1.0);
      wearBtn.textContent = `WEAR: ${wm.toFixed(2)}x`;
      wearBtn.classList.toggle("warn", wm > 1.01);
    }

    const fcstBtn = document.getElementById("btn-cycle-fcst");
    if (fcstBtn) {
      const rf = cp.rain_forecast || "auto";
      const labels = { auto: "WX: AUTO", rain_soon: "WX: RAIN ▶", drying: "WX: DRY ◀" };
      fcstBtn.textContent = labels[rf] || "WX: AUTO";
      fcstBtn.classList.toggle("warn", rf !== "auto");
    }
  }

  // ==================== PIT-RADIO DIALOGUE TRANSCRIPT ====================
  function renderRadio() {
    const radio = snap.radio || [];
    if (radio.length > 0) {
      if (lastSpokenRadioId === 0 || radio[0].id < lastSpokenRadioId) {
        // Initial load or server restart: sync cursor to latest without replaying old backlog
        lastSpokenRadioId = radio[0].id;
      } else {
        const fresh = radio.filter((r) => r.id > lastSpokenRadioId).reverse();
        if (fresh.length > 0) {
          lastSpokenRadioId = fresh[fresh.length - 1].id;
          // Speak highest-priority or latest item cleanly without piling up duplicate updates
          const crit = fresh.find((r) => r.priority === "CRITICAL");
          const chosen = crit || fresh[fresh.length - 1];
          obsWaveUntil = performance.now() + Math.max(1500, Math.min(4800, String(chosen.message || "").length * 62));
          speakEngineer(chosen.message, chosen.priority);
        }
      }
    }
    const rKey = radio.map((r) => r.id).join(",");
    if (rKey !== lastRadioKey) {
      lastRadioKey = rKey;
      document.getElementById("radio-feed").innerHTML = radio.map((r) => `
        <div class="radio-msg ${r.priority}">
          <strong>PIT [${fmtClock(r.time_s)}]:</strong> "${r.message}"
        </div>
      `).join("");
    }
  }

  // ==================== TAB 2: .0001 HARDWARE MATRIX & RADAR ====================
  function renderHardwareMatrix() {
    const tbody = document.getElementById("hardware-matrix-tbody");
    const areas = ["Weight", "EngineTorque", "Acceleration", "Downforce", "Drag", "Suspension", "TractionControl", "AngularDrag"];
    const maxByArea = {};
    areas.forEach((a) => {
      maxByArea[a] = Math.max(...snap.standings.map((c) => c.performance[a] || 0));
    });

    tbody.innerHTML = snap.standings.map((c) => {
      const rowCls = c.is_me ? "row-me" : c.is_rival ? "row-rival" : "";
      const cell = (area) => {
        const val = c.performance[area] || 0;
        const isBest = Math.abs(val - maxByArea[area]) < 0.00015 && val > 0;
        return `<td class="mono ${isBest ? "best-stat" : ""}">${val.toFixed(4)}</td>`;
      };
      return `<tr class="${rowCls}" data-car="${c.index}">
        <td class="mono"><b>P${c.pos}</b></td>
        <td><b>${c.name}</b> ${c.is_me ? '<span class="fia-badge b-you">YOU</span>' : c.is_rival ? '<span class="fia-badge b-tgt">TGT</span>' : ""}</td>
        <td>${c.car_type}</td>
        ${cell("Weight")}
        <td class="mono">${c.is_me ? '<span class="muted">BASE</span>' : fmtSigned4(c.weight_diff)}</td>
        ${cell("EngineTorque")}
        ${cell("Acceleration")}
        ${cell("Downforce")}
        ${cell("Drag")}
        ${cell("Suspension")}
        ${cell("TractionControl")}
        ${cell("AngularDrag")}
      </tr>`;
    }).join("");
  }

  function renderRadarCanvas() {
    const canvas = document.getElementById("radar-canvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    const cx = w / 2, cy = h / 2, rad = Math.min(w, h) * 0.36;
    ctx.clearRect(0, 0, w, h);

    const areas = snap.hardware.areas;
    const n = areas.length;
    if (!n) return;

    document.getElementById("radar-subtitle").textContent =
      `YOU (${snap.hardware.my_car.name}) VS P${snap.hardware.rival_car.pos} ${snap.hardware.rival_car.name}`;

    ctx.strokeStyle = "#2b313e";
    ctx.lineWidth = 1;
    [0.33, 0.66, 1.0].forEach((f) => {
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
        const x = cx + Math.cos(ang) * rad * f;
        const y = cy + Math.sin(ang) * rad * f;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    });

    ctx.fillStyle = "#b5bcc9";
    ctx.font = "700 10px 'JetBrains Mono', monospace";
    areas.forEach((a, i) => {
      const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(ang) * rad, cy + Math.sin(ang) * rad);
      ctx.stroke();
      const lx = cx + Math.cos(ang) * (rad + 26) - 22;
      const ly = cy + Math.sin(ang) * (rad + 16) + 3;
      ctx.fillText(PERF_SHORT[a.area] || a.area, lx, ly);
    });

    const drawPoly = (key, stroke, fill) => {
      ctx.beginPath();
      areas.forEach((a, i) => {
        const norm = a.field_best > 0 ? Math.max(0.2, Math.min(1.0, a[key] / a.field_best)) : 0.5;
        const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
        const x = cx + Math.cos(ang) * rad * norm;
        const y = cy + Math.sin(ang) * rad * norm;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 2;
      ctx.stroke();
    };

    drawPoly("rival", "#e10600", "rgba(225, 6, 0, 0.16)");
    drawPoly("mine", "#ff8000", "rgba(255, 128, 0, 0.22)");
  }

  function renderTrackSpecs() {
    const trk = snap.session.track;
    const box = document.getElementById("track-specs-grid");
    if (!trk) {
      box.innerHTML = `<div class="muted">No measured track parameters in current session packet.</div>`;
      return;
    }
    const specs = [
      ["TRACK LENGTH", `${trk.length_km.toFixed(3)} km`],
      ["EST. LAP TIME", `${trk.lap_time_est_s.toFixed(3)} s`],
      ["PIT LANE TIME LOSS", `${trk.pit_lane_time_loss_s.toFixed(3)} s`],
      ["BASE TIRE WEAR", `${(trk.base_tire_wear_rate * 100).toFixed(2)}% / lap`],
      ["STRAIGHT RATIO", `${(trk.straight_ratio * 100).toFixed(1)}%`],
      ["CORNER COUNT", `${trk.corner_count} corners`],
      ["AVG CORNER SPEED", `${trk.avg_corner_speed.toFixed(1)} m/s`],
      ["ELEVATION CHANGE", `${trk.elevation_change.toFixed(1)} m`],
      ["DRS ZONES / COV", `${trk.drs_zone_count} (${(trk.drs_coverage * 100).toFixed(0)}%)`],
      ["OVERTAKE DIFF.", `${(trk.overtake_difficulty * 100).toFixed(1)}%`],
      ["TRACK WIDTH", `${trk.width_mean.toFixed(1)}m (min ${trk.width_min.toFixed(1)}m)`],
      ["BARRIER RATIO", `${(trk.barrier_ratio * 100).toFixed(1)}%`],
    ];
    box.innerHTML = specs.map(([k, v]) => `
      <div class="spec-card">
        <div class="s-lbl">${k}</div>
        <div class="s-val mono">${v}</div>
      </div>
    `).join("");
  }

  // ==================== TAB 3: LAPS & LOGS ====================
  function renderLapHistoryAndLogs() {
    const hist = snap.telemetry.lap_history || [];
    const best = snap.telemetry.best_lap_s;
    document.getElementById("lap-history-tbody").innerHTML = hist.slice().reverse().map((l) => {
      const delta = (l.time_s && best) ? l.time_s - best : null;
      return `<tr>
        <td class="mono"><b>L${l.lap}</b></td>
        <td class="mono">P${l.pos}</td>
        <td class="mono">${l.time_s ? fmtLap(l.time_s) : "—"}</td>
        <td class="mono">${delta != null ? (delta <= 0.0005 ? '<span class="pace-up">BEST</span>' : `+${delta.toFixed(3)}s`) : "—"}</td>
        <td><span class="pirelli-ring ring-${l.compound}" style="width:18px;height:18px;font-size:10px">${COMP_SHORT[l.compound] || "S"}</span> ${l.compound}</td>
        <td class="mono" style="color:${healthColor(l.tire_health * 100)}">${(l.tire_health * 100).toFixed(2)}%</td>
      </tr>`;
    }).join("") || `<tr><td colspan="6" class="muted">Complete a lap to record millisecond lap splits.</td></tr>`;

    document.getElementById("events-log-box").innerHTML = (snap.events || []).map((e) =>
      `<div class="log-line">[${fmtClock(e.time_s)}] <b style="color:#ff8000">${e.code}</b> ${JSON.stringify(e.details)}</div>`
    ).join("");

    document.getElementById("cmd-log-box").innerHTML = (snap.commands || []).map((c) =>
      `<div class="log-line">[${c.wall_ts}] <b style="color:${c.type === "ACK" ? "#00d26a" : "#ff2438"}">${c.type}</b> ${c.command} (${c.reason}) #${c.request_id}</div>`
    ).join("");
  }

  // ==================== TAB 4: POST-RACE DEBRIEF ====================
  async function loadDebriefArchive() {
    const box = document.getElementById("debrief-list");
    const renderItems = (items) => {
      box.innerHTML = items.map((w) => `
        <div class="fia-panel" style="padding:10px">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <b>WEEKEND #${w.id} · GAME v${w.game_version}</b>
            <span class="muted">${w.received_at}</span>
          </div>
          ${(w.sessions || []).map((s) => `
            <div style="margin-top:6px">
              <div class="sub-lbl" style="padding-left:0">${String(s.kind).toUpperCase()} · ${s.track} · ${s.total_decisions} AI DECISIONS</div>
              <table class="data-table">
                <thead><tr><th>POS</th><th>DRIVER</th><th>TYPE</th><th>LAPS</th><th>BEST LAP</th><th>GAP</th></tr></thead>
                <tbody>
                  ${(s.classification || []).map((c) => `
                    <tr>
                      <td class="mono">P${c.position}</td>
                      <td><b>${c.name}</b></td>
                      <td>${c.driver}</td>
                      <td class="mono">${c.laps}</td>
                      <td class="mono">${c.best_lap_s != null ? fmtLap(Number(c.best_lap_s)) : "—"}</td>
                      <td class="mono">${c.gap_to_leader_s != null ? "+" + Number(c.gap_to_leader_s).toFixed(3) + "s" : "LEADER"}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          `).join("")}
        </div>
      `).join("");
    };
    try {
      const res = await fetch("/api/results");
      if (!res.ok) throw new Error("Static host");
      const data = await res.json();
      const items = data.results || [];
      if (!items.length) {
        box.innerHTML = `<div class="muted" style="padding:8px">No archived race weekend uploads yet. Add <code>http://127.0.0.1:8765/race-results</code> in Settings → Telemetry → Race Results.</div>`;
        return;
      }
      renderItems(items);
    } catch (_) {
      renderItems([{
        id: "DEMO-GP-01",
        game_version: "0.88.2 · SHOWCASE ARCHIVE",
        received_at: "California_GP · 18 Laps",
        sessions: [{
          kind: "Race",
          track: "California_GP",
          total_decisions: 14,
          classification: [
            { position: 1, name: "Dom_Swooz", driver: "local", laps: 18, best_lap_s: 27.791, gap_to_leader_s: null },
            { position: 2, name: "Thruster", driver: "ai (AllCars.onnx)", laps: 18, best_lap_s: 27.842, gap_to_leader_s: 1.184 },
            { position: 3, name: "Pole", driver: "ai (AllCars.onnx)", laps: 18, best_lap_s: 27.965, gap_to_leader_s: 3.412 },
            { position: 4, name: "Circler", driver: "ai (AllCars.onnx)", laps: 18, best_lap_s: 28.044, gap_to_leader_s: 5.890 },
            { position: 5, name: "Arizona", driver: "ai (AllCars.onnx)", laps: 18, best_lap_s: 28.118, gap_to_leader_s: 8.205 },
          ],
        }],
      }]);
    }
  }

  // ==================== INTERACTIVE EVENT LISTENERS ====================
  function bindEvents() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.dataset.tab;
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
        document.querySelectorAll(".tab-view").forEach((v) => v.classList.toggle("active", v.id === `tab-${activeTab}`));
        if (activeTab === "debrief") loadDebriefArchive();
        if (activeTab === "league") loadOpenGpLeague();
        renderAll();
      });
    });

    // Comparator / Upgrades / Compounds Sub-Deck Tabs
    document.querySelectorAll(".deck-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.deck;
        document.querySelectorAll(".deck-tab").forEach((t) => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".deck-pane").forEach((p) => p.classList.toggle("active", p.id === `deck-${target}`));
      });
    });

    document.getElementById("btn-sim-toggle").addEventListener("click", () => sendAction({ action: "toggle_sim" }));
    document.getElementById("btn-sim-reset").addEventListener("click", () => sendAction({ action: "reset_sim" }));
    document.addEventListener("pointerdown", () => {
      if (!isAudioLeader) sendAction({ action: "claim_audio" });
    });

    document.getElementById("btn-voice-toggle").addEventListener("click", (e) => {
      voiceEnabled = !voiceEnabled;
      e.currentTarget.textContent = voiceEnabled ? "RADIO ON" : "RADIO MUTE";
      e.currentTarget.classList.toggle("active", voiceEnabled);
      if (voiceEnabled) {
        sendAction({ action: "claim_audio" });
        playRadioBeep();
      } else {
        stopAllAudioNow();
      }
    });
    document.getElementById("btn-radio-test").addEventListener("click", () => {
      sendAction({ action: "test_radio" });
    });

    // Responsive Form-Factor Switcher (AUTO · PHONE · FOLD · TABLET · PC) + HUD CLEAN/PRO + Thumb Dock
    const hudTierBtn = document.getElementById("btn-hud-tier");
    if (hudTierBtn) {
      hudTierBtn.addEventListener("click", () => {
        hudTierPref = hudTierPref === "clean" ? "pro" : "clean";
        try { localStorage.setItem("bc_hud_tier", hudTierPref); } catch (_) {}
        applyHudTier();
      });
    }
    const devModeBtn = document.getElementById("btn-device-mode");
    if (devModeBtn) {
      devModeBtn.addEventListener("click", () => {
        const order = ["auto", "slab", "fold", "tablet", "desktop"];
        deviceModePref = order[(order.indexOf(deviceModePref) + 1) % order.length];
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
      });
    }
    document.querySelectorAll(".slab-dock-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.slabTarget) setSlabPane(btn.dataset.slabTarget);
      });
    });
    window.addEventListener("resize", applyDeviceMode);
    window.addEventListener("orientationchange", () => setTimeout(applyDeviceMode, 120));

    // Voice Persona & Radio FX Studio Controls
    const selVoice = document.getElementById("sel-voice-persona");
    const selFx = document.getElementById("sel-radio-fx");
    const selSpd = document.getElementById("sel-voice-speed");
    const rngVol = document.getElementById("rng-voice-vol");

    if ([...selVoice.options].some((o) => o.value === voiceConfig.voice)) selVoice.value = voiceConfig.voice;
    if ([...selFx.options].some((o) => o.value === voiceConfig.fx)) selFx.value = voiceConfig.fx;
    if ([...selSpd.options].some((o) => Number(o.value) === voiceConfig.ratePct)) selSpd.value = String(voiceConfig.ratePct);
    rngVol.value = String(Math.round(voiceConfig.volume * 100));

    const auditionCurrentVoice = () => {
      const sample = PERSONA_TEST_LINES[voiceConfig.voice] || "Radio check loud and clear, telemetry locked!";
      speakEngineer(sample, "CRITICAL");
    };

    selVoice.addEventListener("change", () => {
      voiceConfig.voice = selVoice.value;
      localStorage.setItem("bc_voice", voiceConfig.voice);
      sendAction({ action: "prewarm_voice", voice: voiceConfig.voice, rate_pct: voiceConfig.ratePct });
      auditionCurrentVoice();
    });
    selFx.addEventListener("change", () => {
      voiceConfig.fx = selFx.value;
      localStorage.setItem("bc_fx", voiceConfig.fx);
      auditionCurrentVoice();
    });
    selSpd.addEventListener("change", () => {
      voiceConfig.ratePct = Number(selSpd.value);
      localStorage.setItem("bc_rate", String(voiceConfig.ratePct));
      sendAction({ action: "prewarm_voice", voice: voiceConfig.voice, rate_pct: voiceConfig.ratePct });
      auditionCurrentVoice();
    });
    rngVol.addEventListener("input", () => {
      voiceConfig.volume = Number(rngVol.value) / 100;
      localStorage.setItem("bc_vol", rngVol.value);
    });
    document.getElementById("btn-voice-sample").addEventListener("click", auditionCurrentVoice);

    // Rival Lock on Timing Tower & Matrix
    ["timing-tbody", "hardware-matrix-tbody"].forEach((id) => {
      document.getElementById(id).addEventListener("click", (e) => {
        const row = e.target.closest("[data-car]");
        if (row) sendAction({ action: "set_rival", car_index: Number(row.dataset.car) });
      });
    });
    document.getElementById("btn-clear-rival").addEventListener("click", () => {
      sendAction({ action: "set_rival", car_index: null });
    });

    // Rival Lock on 2D Circuit Map
    document.getElementById("track-canvas").addEventListener("click", (e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let best = null, bestD = 18;
      for (const cp of carScreenPositions) {
        const d = Math.hypot(cp.x - mx, cp.y - my);
        if (d < bestD) { bestD = d; best = cp; }
      }
      if (best) sendAction({ action: "set_rival", car_index: best.index });
    });

    // Pit Box Toggle (both Arc Gauge button and Spun-Metal BOX switch)
    ["btn-pit-toggle", "btn-metal-box"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("click", () => {
          if (!snap) return;
          sendAction({ action: "set_pit", pit: !snap.pit.pit_planned });
        });
      }
    });

    // Card Pick / Ban
    document.getElementById("cards-container").addEventListener("click", (e) => {
      const pickBtn = e.target.closest("button[data-pick]");
      if (pickBtn) { sendAction({ action: "pick_card", index: Number(pickBtn.dataset.pick) }); return; }
      const banBtn = e.target.closest("button[data-ban]");
      if (banBtn) sendAction({ action: "ban_card", index: Number(banBtn.dataset.ban) });
    });

    // Tire Compound Selector + Hover +/- Inspector
    const cStrip = document.getElementById("compound-strip");
    cStrip.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-tire]");
      if (btn) sendAction({ action: "pick_tire", compound: btn.dataset.tire });
    });
    cStrip.addEventListener("mouseover", (e) => {
      const btn = e.target.closest("button[data-tire]");
      if (btn && hoveredCompound !== btn.dataset.tire) {
        hoveredCompound = btn.dataset.tire;
        if (snap) renderCommandDeck();
      }
    });
    cStrip.addEventListener("mouseleave", () => {
      hoveredCompound = null;
      if (snap) renderCommandDeck();
    });

    // 4-Stage Strategy Pace Buttons + L'Endurance P1 Preset Button
    const lendPresetBtn = document.getElementById("btn-lendurance");
    if (lendPresetBtn) {
      lendPresetBtn.addEventListener("click", () => {
        sendAction({ action: "set_preset", preset: "lendurance" });
      });
    }
    document.querySelectorAll(".pace-seg").forEach((btn) => {
      btn.addEventListener("click", () => {
        sendAction({ action: "set_copilot", key: "pace_mode", value: btn.dataset.pace });
      });
    });

    // Pre-Race Start Race (Auto-Hold [SPACE]) + Wear Multiplier & Rain Forecast Cyclers
    let startHoldTimer = null;
    function triggerStartRace() {
      sendAction({ action: "start_race", duration_s: 2.2 });
      const sBtn = document.getElementById("btn-start-race");
      if (sBtn) {
        sBtn.classList.add("starting");
        sBtn.textContent = "HOLDING…";
        if (startHoldTimer) clearTimeout(startHoldTimer);
        startHoldTimer = setTimeout(() => {
          sBtn.classList.remove("starting");
          sBtn.textContent = "START RACE";
        }, 2250);
      }
    }
    const startBtn = document.getElementById("btn-start-race");
    if (startBtn) {
      startBtn.addEventListener("click", triggerStartRace);
    }

    const wearChip = document.getElementById("btn-cycle-wear");
    if (wearChip) {
      wearChip.addEventListener("click", () => {
        if (!snap) return;
        const seq = [1.0, 1.15, 1.3];
        const cur = Number(snap.copilot.wear_mult || 1.0);
        const nxt = seq[(seq.findIndex((v) => Math.abs(v - cur) < 0.02) + 1) % seq.length];
        sendAction({ action: "set_copilot", key: "wear_mult", value: nxt });
      });
    }
    const fcstChip = document.getElementById("btn-cycle-fcst");
    if (fcstChip) {
      fcstChip.addEventListener("click", () => {
        if (!snap) return;
        const seq = ["auto", "rain_soon", "drying"];
        const cur = snap.copilot.rain_forecast || "auto";
        const nxt = seq[(seq.indexOf(cur) + 1) % seq.length];
        sendAction({ action: "set_copilot", key: "rain_forecast", value: nxt });
      });
    }

    // Spun-Metal Co-Pilot Switches + ERS Rocker
    document.querySelectorAll("[data-cp]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!snap) return;
        const key = btn.dataset.cp;
        sendAction({ action: "set_copilot", key, value: !snap.copilot[key] });
      });
    });

    // ==================== HANDS-FREE ZERO-LAG BARGE-IN VOICE COMMAND ENGINE ====================
    let lastVoiceNormPhrase = "";

    function isEngineerAudioPhysicallyPlaying() {
      return Boolean(activeVoiceSource || performance.now() < offlineSpeakingUntil);
    }

    function isPureSpeakerEcho(normPhrase) {
      if (!isEngineerAudioPhysicallyPlaying() || !engineerCurrentSpokenText) return false;
      // If driver is speaking strongly into the mic, always allow Driver Priority Barge-In!
      if (lastLiveMicRms >= 0.065) return false;
      const engNorm = normVoice(engineerCurrentSpokenText);
      return Boolean(normPhrase.length >= 4 && engNorm && engNorm.includes(normPhrase));
    }

    window.updateVoiceBarUI = function updateVoiceBarUI(overrideState = null, heardText = null) {
      const bar = document.getElementById("voice-cmd-bar");
      const stLbl = document.getElementById("vc-state-lbl");
      const hdLbl = document.getElementById("vc-heard-lbl");
      const micBtn = document.getElementById("btn-mic-toggle");
      if (micBtn) {
        micBtn.classList.toggle("mic-live", micEnabled);
        if (overrideState === "matched" && heardText) {
          const cleanAct = String(heardText).replace(/^"[^"]+"\s*→\s*/, "");
          micBtn.textContent = (cleanAct || heardText).slice(0, 18);
        } else if (overrideState === "error" && heardText) {
          micBtn.textContent = heardText.slice(0, 22);
        } else {
          const isAnd = /Android/i.test(navigator.userAgent || "");
          micBtn.textContent = micEnabled ? (isAnd ? "LISTEN…" : "MIC LIVE [V]") : (isAnd ? "MIC PTT [V]" : "MIC OFF [V]");
        }
      }
      if (!bar || !stLbl || !hdLbl) return;
      if (!micEnabled) {
        bar.className = "voice-cmd-bar mono";
        stLbl.textContent = "VOICE MIC OFF [V]";
        if (heardText !== null) hdLbl.textContent = heardText;
        return;
      }
      if (overrideState === "matched") {
        bar.className = "voice-cmd-bar mono matched";
        stLbl.textContent = "CMD EXECUTED";
        if (heardText) hdLbl.textContent = heardText;
        return;
      }
      if (overrideState === "error") {
        bar.className = "voice-cmd-bar mono";
        stLbl.textContent = "VOICE ERROR";
        if (heardText !== null) hdLbl.textContent = heardText;
        return;
      }
      bar.className = "voice-cmd-bar mono listening";
      stLbl.textContent = isEngineerAudioPhysicallyPlaying() ? "OPEN MIC · BARGE-IN" : "OPEN MIC · READY";
      if (heardText !== null) hdLbl.textContent = heardText;
    };

    function pulseVoiceTarget(target) {
      if (!target) return;
      const el = typeof target === "string" ? document.querySelector(target) : target;
      if (!el) return;
      const flashEl = el.closest(".metal-switch-unit") || el;
      flashEl.classList.remove("voice-flash");
      void flashEl.offsetWidth;
      flashEl.classList.add("voice-flash");
      setTimeout(() => flashEl.classList.remove("voice-flash"), 780);
    }

    function flashVoiceMatch(transcript, actionLabel, target = null) {
      // Driver Priority PTT Barge-In: cut active engineer audio immediately when driver gives a command!
      if (isEngineerAudioPhysicallyPlaying() && !actionLabel.includes("SITREP") && !actionLabel.includes("TEST VOICE")) {
        stopAllAudioNow();
      }
      lastVoiceActionLabel = actionLabel;
      try { playRadioBeep(); } catch (_) {}
      pulseVoiceTarget(target);
      updateVoiceBarUI("matched", `"${transcript}" → ${actionLabel}`);
      if (voiceMatchResetTimer) clearTimeout(voiceMatchResetTimer);
      voiceMatchResetTimer = setTimeout(() => {
        updateVoiceBarUI(null, `Last: "${transcript}" → ${actionLabel}`);
      }, 2200);
    }

    function normVoice(raw) {
      let s = String(raw || "").toLowerCase();
      // Strip bracketed hotkey hints from button labels e.g. [V], [SPC], [T]
      s = s.replace(/\[[^\]]*\]/g, " ");
      s = s.replace(/&/g, " and ").replace(/\//g, " ");
      const numWords = [
        [/\bzero\b/g, "0"], [/\bone\b/g, "1"], [/\bwon\b/g, "1"],
        [/\btwo\b/g, "2"], [/\bto\b/g, "2"], [/\bthree\b/g, "3"],
        [/\bfour\b/g, "4"], [/\bfor\b/g, "4"], [/\bfive\b/g, "5"],
        [/\bsix\b/g, "6"], [/\bseven\b/g, "7"],
      ];
      for (const [rx, rep] of numWords) s = s.replace(rx, rep);
      s = s.replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
      s = s
        .replace(/\btyre\b/g, "tire")
        .replace(/\btyres\b/g, "tires")
        .replace(/\bautocards?\b/g, "auto card")
        .replace(/\bauto\s+carts?\b/g, "auto card")
        .replace(/\bautocarts?\b/g, "auto card")
        .replace(/\b(otto|audio|oughta)\s+cards?\b/g, "auto card")
        .replace(/\bautotires?\b/g, "auto tire")
        .replace(/\bautopit\b/g, "auto pit")
        .replace(/\bautoboost\b/g, "auto boost")
        .replace(/\bkay 1\b/g, "k1")
        .replace(/\bk 1\b/g, "k1")
        .replace(/\b(pee|pew)\s*1\b/g, "p1")
        .replace(/\bp 1\b/g, "p1")
        .replace(/\bb 1\b/g, "b1")
        .replace(/\b7 seconds?\b/g, "7s")
        .replace(/\b7 s\b/g, "7s")
        .replace(/\bboost 66\b/g, "boost 6 6")
        .replace(/\bboost 6 out of 6\b/g, "boost 6 6")
        .replace(/\bboost 6 slash 6\b/g, "boost 6 6")
        .replace(/\btee cam\b/g, "t cam")
        .replace(/\btcam\b/g, "t cam")
        .replace(/\bsit rep\b/g, "sitrep")
        .replace(/\bsling shot\b/g, "slingshot")
        .replace(/\bsnow ball\b/g, "snowball")
        .replace(/\bdown force\b/g, "downforce")
        .replace(/\bturbo charger\b/g, "turbocharger")
        .replace(/\bl endurance\b/g, "lendurance")
        .replace(/\bla endurance\b/g, "lendurance")
        .replace(/\ble mans\b/g, "lemans")
        .replace(/\bbucks bucks\b/g, "box box");
      return s.replace(/\s+/g, " ").trim();
    }

    function activateDeck(deckName) {
      const tab = document.querySelector(`.deck-tab[data-deck="${deckName}"]`);
      if (tab) tab.click();
      return tab;
    }

    function activateTopTab(tabName) {
      const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
      if (btn) btn.click();
      return btn;
    }

    function matchVisibleDomButton(normTranscript) {
      const buttons = document.querySelectorAll("button");
      for (const btn of buttons) {
        if (btn.id === "btn-mic-toggle") continue;
        if (btn.offsetParent === null) continue; // skip hidden tabs/modals
        const clone = btn.cloneNode(true);
        clone.querySelectorAll(".pts-pill, .cb-pace, .cb-stint, small, .pirelli-ring, .pace-sub").forEach((n) => n.remove());
        const lbl = normVoice(clone.textContent || "");
        if (lbl && lbl.length >= 2 && (normTranscript === lbl || normTranscript === `click ${lbl}`)) {
          btn.click();
          return { btn, label: (clone.textContent || "").trim().replace(/\s+/g, " ") };
        }
      }
      return null;
    }

    function executeVoiceCommand(rawText) {
      const t = normVoice(rawText);
      if (!t || t.length < 2) return false;
      if (isPureSpeakerEcho(t)) return false;
      const now = performance.now();
      // Duplicate-echo guard (950ms for identical phrase), but only 75ms across distinct rapid yells ("Box! Wet!")!
      if (t === lastVoiceNormPhrase && now - lastVoiceCmdMs < 950) return false;
      if (now - lastVoiceCmdMs < 75) return false;
      const prevNorm = lastVoiceNormPhrase;
      lastVoiceNormPhrase = t;

      const fail = () => {
        lastVoiceNormPhrase = prevNorm;
        return false;
      };

      const has = (...words) => words.some((w) => t.includes(w));
      const isExact = (...words) => words.includes(t);
      const hasWord = (w) => new RegExp(`\\b${w}\\b`).test(t);

      // 0) Modals, Start Race, Extreme AI Sync, L'Endurance P1 Preset, Header Pills & Utility Buttons
      if (has("extreme ai", "sync extreme", "extreme sync", "extreme mode", "blitz build") || isExact("extreme")) {
        lastVoiceCmdMs = now;
        const wantOff = hasWord("off") || has("disable", "disarm");
        const wantOn = hasWord("on") || has("enable", "arm", "sync");
        const nextActive = wantOff ? false : (wantOn ? true : !snap?.copilot?.extreme_ai_sync);
        sendAction({ action: "set_preset", preset: "extreme_ai", active: nextActive });
        flashVoiceMatch(rawText, nextActive ? "EXTREME AI // SYNCED" : "EXTREME AI // OFF", "#btn-extreme-ai");
        return true;
      }
      if (has("lendurance", "lemans") || isExact("endurance")) {
        lastVoiceCmdMs = now;
        const wantOff = hasWord("off") || has("disable", "disarm");
        const wantOn = hasWord("on") || has("enable", "arm");
        const nextActive = wantOff ? false : (wantOn ? true : !snap?.copilot?.lendurance_mode);
        sendAction({ action: "set_preset", preset: "lendurance", active: nextActive });
        flashVoiceMatch(rawText, nextActive ? "L'ENDURANCE P1 DIAL-IN" : "L'ENDURANCE OFF", "#btn-lendurance");
        return true;
      }
      if (has("start race", "start the race", "lights out", "ready up", "green light", "go racing") || isExact("start", "lights")) {
        lastVoiceCmdMs = now;
        triggerStartRace();
        flashVoiceMatch(rawText, "START RACE (HOLD SPACE)", "#btn-start-race");
        return true;
      }
      if (has("swooz studio", "record swooz", "swooz voice", "crew studio", "persona studio") || isExact("swooz", "crew")) {
        lastVoiceCmdMs = now;
        document.getElementById("btn-swooz-studio")?.click();
        flashVoiceMatch(rawText, "CREW STUDIO", "#btn-swooz-studio");
        return true;
      }
      if (has("5 slot", "slot lab", "strategy lab", "customize push", "customize card")) {
        lastVoiceCmdMs = now;
        document.getElementById("btn-loadout-studio")?.click();
        flashVoiceMatch(rawText, "5-SLOT LAB", "#btn-loadout-studio");
        return true;
      }
      if (isExact("close", "close modal")) {
        const lsm = document.getElementById("loadout-studio-modal");
        const swm = document.getElementById("swooz-studio-modal");
        const vhm = document.getElementById("voice-help-modal");
        const qrm = document.getElementById("qr-modal");
        if (lsm && lsm.style.display === "flex") { lsm.style.display = "none"; lastVoiceCmdMs = now; flashVoiceMatch(rawText, "CLOSE"); return true; }
        if (swm && swm.style.display === "flex") { swm.style.display = "none"; lastVoiceCmdMs = now; flashVoiceMatch(rawText, "CLOSE"); return true; }
        if (vhm && vhm.style.display === "flex") { vhm.style.display = "none"; lastVoiceCmdMs = now; flashVoiceMatch(rawText, "CLOSE"); return true; }
        if (qrm && qrm.style.display === "flex") { qrm.style.display = "none"; lastVoiceCmdMs = now; flashVoiceMatch(rawText, "CLOSE"); return true; }
      }
      if (has("cmds", "voice help", "cheat sheet") || isExact("commands", "help")) {
        const vhm = document.getElementById("voice-help-modal");
        if (vhm) vhm.style.display = vhm.style.display === "flex" ? "none" : "flex";
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "CMDS ?", "#btn-voice-help");
        return true;
      }
      if (has("test voice", "audition voice") || isExact("test")) {
        lastVoiceCmdMs = now;
        document.getElementById("btn-voice-sample")?.click();
        flashVoiceMatch(rawText, "TEST VOICE", "#btn-voice-sample");
        return true;
      }
      if (has("mic off", "voice mic off", "mute mic")) {
        lastVoiceCmdMs = now;
        if (micEnabled) toggleVoiceMic();
        return true;
      }
      if (has("sim on", "sim off", "toggle sim")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "toggle_sim" });
        flashVoiceMatch(rawText, "SIM TOGGLE", "#btn-sim-toggle");
        return true;
      }
      if (isExact("rst", "reset") || has("reset sim")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "reset_sim" });
        flashVoiceMatch(rawText, "RST SESSION", "#btn-sim-reset");
        return true;
      }
      if (has("radio on", "radio mute", "mute radio", "unmute radio")) {
        const wantOn = has("radio on", "unmute radio");
        const wantOff = has("radio mute", "mute radio");
        const btn = document.getElementById("btn-voice-toggle");
        if (btn && ((wantOn && !voiceEnabled) || (wantOff && voiceEnabled) || (!wantOn && !wantOff))) {
          btn.click();
        }
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, voiceEnabled ? "RADIO ON" : "RADIO MUTE", "#btn-voice-toggle");
        return true;
      }
      if (isExact("iphone") || has("open on phone", "open on tablet", "connect device", "mobile link", "qr code")) {
        lastVoiceCmdMs = now;
        document.getElementById("btn-iphone-share")?.click();
        flashVoiceMatch(rawText, "DEVICE QR", "#btn-iphone-share");
        return true;
      }
      if (has("send udp ping", "udp ping")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "ping" });
        flashVoiceMatch(rawText, "SEND UDP PING", "#btn-send-ping");
        return true;
      }
      if (has("refresh archive")) {
        lastVoiceCmdMs = now;
        loadDebriefArchive();
        flashVoiceMatch(rawText, "REFRESH ARCHIVE", "#btn-refresh-results");
        return true;
      }
      if (has("tgt auto", "target auto", "rival auto", "clear rival")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_rival", car_index: null });
        flashVoiceMatch(rawText, "TGT: AUTO", "#btn-clear-rival");
        return true;
      }
      if (has("full wall", "expand wall", "exit mini hud", "full hud")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_overlay", key: "mini_hud", value: false });
        flashVoiceMatch(rawText, "FULL PIT WALL", "#btn-mini-hud");
        return true;
      }
      if (has("mini hud", "compact hud", "overlay hud", "mini mode")) {
        lastVoiceCmdMs = now;
        const nextMh = hasWord("off") ? false : (hasWord("on") ? true : !snap?.overlay?.mini_hud);
        sendAction({ action: "set_overlay", key: "mini_hud", value: nextMh });
        flashVoiceMatch(rawText, `MINI HUD: ${nextMh ? "ON" : "OFF"}`, "#btn-mini-hud");
        return true;
      }
      if (has("clean mode", "clean hud", "simple mode", "minimal mode")) {
        lastVoiceCmdMs = now;
        hudTierPref = "clean";
        try { localStorage.setItem("bc_hud_tier", hudTierPref); } catch (_) {}
        applyHudTier();
        flashVoiceMatch(rawText, "HUD // CLEAN", "#btn-hud-tier");
        return true;
      }
      if (has("pro mode", "pro hud", "full telemetry", "engineer telemetry")) {
        lastVoiceCmdMs = now;
        hudTierPref = "pro";
        try { localStorage.setItem("bc_hud_tier", hudTierPref); } catch (_) {}
        applyHudTier();
        flashVoiceMatch(rawText, "HUD // PRO", "#btn-hud-tier");
        return true;
      }
      if (has("slab mode", "phone mode", "slab view", "phone view", "bar phone")) {
        lastVoiceCmdMs = now;
        deviceModePref = "slab";
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
        flashVoiceMatch(rawText, "VIEW // PHONE", "#btn-device-mode");
        return true;
      }
      if (has("battle cam", "battle camera")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_camera", camera: "Onboard_BattleCam" });
        flashVoiceMatch(rawText, "CAM: BATTLE CAM", 'button[data-cam="Onboard_BattleCam"]');
        return true;
      }
      if (has("rear view", "rear cam", "look back", "mirror cam")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_camera", camera: "Onboard_Rear" });
        flashVoiceMatch(rawText, "CAM: REAR VIEW", 'button[data-cam="Onboard_Rear"]');
        return true;
      }
      if (has("trackside", "track side")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_camera", camera: "TrackSide" });
        flashVoiceMatch(rawText, "CAM: TRACKSIDE", 'button[data-cam="TrackSide"]');
        return true;
      }
      if (has("drone cam", "drone view") || isExact("drone")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_camera", camera: "Drone" });
        flashVoiceMatch(rawText, "CAM: DRONE", 'button[data-cam="Drone"]');
        return true;
      }
      if (has("tv director", "broadcast director", "auto camera")) {
        lastVoiceCmdMs = now;
        const nextTv = hasWord("off") ? false : (hasWord("on") ? true : !snap?.copilot?.tv_director);
        sendAction({ action: "set_copilot", key: "tv_director", value: nextTv });
        flashVoiceMatch(rawText, `TV DIRECTOR: ${nextTv ? "ON" : "OFF"}`, "#btn-tv-director");
        return true;
      }
      if (has("public spotter", "public shield", "public lobby")) {
        lastVoiceCmdMs = now;
        document.getElementById("btn-pub-lobby")?.click();
        flashVoiceMatch(rawText, "PUBLIC LOBBY SPOTTER", "#btn-pub-lobby");
        return true;
      }
      if (has("open gp", "leaderboard", "league standings", "elo standings")) {
        lastVoiceCmdMs = now;
        activateTopTab("league");
        flashVoiceMatch(rawText, "OPEN GP // STANDINGS", '.tab-btn[data-tab="league"]');
        return true;
      }
      if (has("rival spy", "spy and cam", "spy deck")) {
        lastVoiceCmdMs = now;
        activateDeck("spy");
        flashVoiceMatch(rawText, "SPY // CAM", '.deck-tab[data-deck="spy"]');
        return true;
      }
      if (has("fold mode", "foldable mode", "fold view", "split view", "fold open")) {
        lastVoiceCmdMs = now;
        deviceModePref = "fold";
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
        flashVoiceMatch(rawText, "VIEW // FOLD", "#btn-device-mode");
        return true;
      }
      if (has("tablet mode", "tablet view", "ipad mode", "ipad view")) {
        lastVoiceCmdMs = now;
        deviceModePref = "tablet";
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
        flashVoiceMatch(rawText, "VIEW // TABLET", "#btn-device-mode");
        return true;
      }
      if (has("desktop mode", "desktop view", "pc mode", "widescreen mode")) {
        lastVoiceCmdMs = now;
        deviceModePref = "desktop";
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
        flashVoiceMatch(rawText, "VIEW // PC", "#btn-device-mode");
        return true;
      }
      if (has("auto view", "auto layout", "auto screen")) {
        lastVoiceCmdMs = now;
        deviceModePref = "auto";
        try { localStorage.setItem("bc_device_mode", deviceModePref); } catch (_) {}
        applyDeviceMode();
        flashVoiceMatch(rawText, "VIEW: AUTO DETECT", "#btn-device-mode");
        return true;
      }
      if (document.body.dataset.device === "slab") {
        if (has("engineer and radio", "engineer view", "engineer tab")) {
          lastVoiceCmdMs = now;
          setSlabPane("engineer");
          flashVoiceMatch(rawText, "SLAB: ENGINEER & RADIO", '.slab-dock-btn[data-slab-target="engineer"]');
          return true;
        }
        if (has("tower and map", "tower view", "track view")) {
          lastVoiceCmdMs = now;
          setSlabPane("track");
          flashVoiceMatch(rawText, "SLAB: TOWER & MAP", '.slab-dock-btn[data-slab-target="track"]');
          return true;
        }
        if (has("telemetry view", "telemetry tab") || isExact("telemetry")) {
          lastVoiceCmdMs = now;
          setSlabPane("telemetry");
          flashVoiceMatch(rawText, "SLAB: TELEMETRY", '.slab-dock-btn[data-slab-target="telemetry"]');
          return true;
        }
      }
      if (has("pin top", "pin on top", "always on top", "unpin")) {
        lastVoiceCmdMs = now;
        const nextPin = has("unpin") || hasWord("off") ? false : (hasWord("on") ? true : !snap?.overlay?.pin_top);
        sendAction({ action: "set_overlay", key: "pin_top", value: nextPin });
        flashVoiceMatch(rawText, `PIN TOP: ${nextPin ? "ON" : "OFF"}`, "#btn-pin-top");
        return true;
      }
      if (has("in game keys", "global keys", "global hotkeys")) {
        lastVoiceCmdMs = now;
        const nextGk = hasWord("off") ? false : (hasWord("on") ? true : !snap?.overlay?.global_hotkeys);
        sendAction({ action: "set_overlay", key: "global_hotkeys", value: nextGk });
        flashVoiceMatch(rawText, `IN-GAME KEYS: ${nextGk ? "ON" : "OFF"}`, "#btn-global-keys");
        return true;
      }
      if (has("no alt tab", "game focus", "auto focus")) {
        lastVoiceCmdMs = now;
        const nextGf = hasWord("off") ? false : (hasWord("on") ? true : !snap?.overlay?.game_refocus);
        sendAction({ action: "set_overlay", key: "game_refocus", value: nextGf });
        flashVoiceMatch(rawText, `NO-ALT-TAB: ${nextGf ? "ON" : "OFF"}`, "#btn-game-refocus");
        return true;
      }

      // 1) Top Navigation Tabs & Comparator Sub-Deck Tabs (Read-What-You-See)
      if (isExact("pit wall") || has("pit wall tab")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "TAB: PIT WALL", activateTopTab("live"));
        return true;
      }
      if (has("0001 matrix", "hardware matrix") || isExact("matrix")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "TAB: .0001 MATRIX", activateTopTab("hardware"));
        return true;
      }
      if (has("stints and logs", "stints logs") || isExact("stints", "logs")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "TAB: STINTS & LOGS", activateTopTab("stints"));
        return true;
      }
      if (isExact("debrief") || has("debrief tab", "post race debrief")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "TAB: DEBRIEF", activateTopTab("debrief"));
        return true;
      }
      if (has("hardware delta") || isExact("delta", "hardware")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "DECK: HARDWARE DELTA", activateDeck("delta"));
        return true;
      }
      if (isExact("upgrades") || has("upgrades tab", "upgrades deck")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "DECK: UPGRADES", activateDeck("cards"));
        return true;
      }
      if (isExact("compounds") || has("compounds tab", "compounds deck")) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, "DECK: COMPOUNDS", activateDeck("tires"));
        return true;
      }

      // 1b) Metallic Co-Pilot Switches ("AUTO CARD", "AUTO TIRE", "PIT GUARD", "ERS DEPLOY")
      // Checked BEFORE live card hand so saying "Auto Card" while 3 upgrade cards are open never collides!
      const swOff = hasWord("off") || has("disable", "disarm");
      const swOn = hasWord("on") || has("enable", "arm", "armed");
      if (has("auto card", "card auto", "auto upgrade", "auto pick", "card assist")) {
        lastVoiceCmdMs = now;
        const val = swOff ? false : (swOn ? true : !snap?.copilot?.auto_card);
        sendAction({ action: "set_copilot", key: "auto_card", value: val });
        flashVoiceMatch(rawText, `AUTO CARD: ${val ? "ON" : "OFF"}`, "#cp-auto_card");
        return true;
      }
      if (has("auto tire", "tire auto", "tire assist")) {
        lastVoiceCmdMs = now;
        const val = swOff ? false : (swOn ? true : !snap?.copilot?.auto_tire);
        sendAction({ action: "set_copilot", key: "auto_tire", value: val });
        flashVoiceMatch(rawText, `AUTO TIRE: ${val ? "ON" : "OFF"}`, "#cp-auto_tire");
        return true;
      }
      if (has("pit guard", "auto pit", "pit assist") || isExact("guard")) {
        lastVoiceCmdMs = now;
        const val = swOff ? false : (swOn ? true : !snap?.copilot?.auto_pit);
        sendAction({ action: "set_copilot", key: "auto_pit", value: val });
        flashVoiceMatch(rawText, `PIT GUARD: ${val ? "ON" : "OFF"}`, "#cp-auto_pit");
        return true;
      }
      if (has("ers deploy", "auto boost", "ers on", "ers off", "ers armed") || isExact("ers")) {
        lastVoiceCmdMs = now;
        const val = swOff ? false : (swOn ? true : !snap?.copilot?.auto_boost);
        sendAction({ action: "set_copilot", key: "auto_boost", value: val });
        flashVoiceMatch(rawText, `ERS DEPLOY: ${val ? "ARMED" : "OFF"}`, "#cp-auto_boost");
        return true;
      }

      // 2) Live Upgrade Cards: Read the Card's Actual Name, "PICK", "TOP EV", "BAN", or "CARD 1/2/3"
      const hand = snap?.cards?.hand || [];
      if (hand.length > 0) {
        const wantBan = hasWord("ban");
        for (const c of hand) {
          if (c.banned) continue;
          const spaced = normVoice(String(c.upgrade || "").replace(/([a-z])([A-Z])/g, "$1 $2"));
          const compact = normVoice(c.upgrade || "");
          if ((spaced && t.includes(spaced)) || (compact && t.includes(compact))) {
            lastVoiceCmdMs = now;
            activateDeck("cards");
            if (wantBan && (snap?.cards?.ban_tokens || 0) > 0) {
              sendAction({ action: "ban_card", index: Number(c.index) });
              flashVoiceMatch(rawText, `BAN: ${c.upgrade}`, `button[data-ban="${c.index}"]`);
            } else {
              sendAction({ action: "pick_card", index: Number(c.index) });
              flashVoiceMatch(rawText, `PICK: ${c.upgrade}`, `button[data-pick="${c.index}"]`);
            }
            return true;
          }
        }
        if (isExact("pick") || has("top ev", "best card", "top card", "recommended card")) {
          const best = hand.find((c) => c.recommended && !c.banned) || hand.find((c) => !c.banned);
          if (best) {
            lastVoiceCmdMs = now;
            activateDeck("cards");
            sendAction({ action: "pick_card", index: Number(best.index) });
            flashVoiceMatch(rawText, `PICK: ${best.upgrade}`, `button[data-pick="${best.index}"]`);
            return true;
          }
        }
        const banNums = [
          [["ban 1", "ban card 1", "ban first"], 0],
          [["ban 2", "ban card 2", "ban second"], 1],
          [["ban 3", "ban card 3", "ban third"], 2],
        ];
        for (const [keys, idx] of banNums) {
          if (has(...keys)) {
            lastVoiceCmdMs = now;
            activateDeck("cards");
            sendAction({ action: "ban_card", index: idx });
            flashVoiceMatch(rawText, `BAN CARD #${idx + 1}`, `button[data-ban="${idx}"]`);
            return true;
          }
        }
        if (isExact("ban") && (snap?.cards?.ban_tokens || 0) > 0) {
          const worst = [...hand].reverse().find((c) => !c.banned && !c.recommended) || hand.find((c) => !c.banned);
          if (worst) {
            lastVoiceCmdMs = now;
            activateDeck("cards");
            sendAction({ action: "ban_card", index: Number(worst.index) });
            flashVoiceMatch(rawText, `BAN: ${worst.upgrade}`, `button[data-ban="${worst.index}"]`);
            return true;
          }
        }
      }
      const cardNums = [
        [["card 1", "pick 1", "first card", "left card"], 0],
        [["card 2", "pick 2", "second card", "middle card"], 1],
        [["card 3", "pick 3", "third card", "right card"], 2],
      ];
      for (const [keys, idx] of cardNums) {
        if (has(...keys)) {
          lastVoiceCmdMs = now;
          activateDeck("cards");
          sendAction({ action: "pick_card", index: idx });
          flashVoiceMatch(rawText, `PICK CARD #${idx + 1}`, `button[data-pick="${idx}"]`);
          return true;
        }
      }

      // 3) DYNAMIC 5-SLOT CARD BUILD + 5-SLOT PUSH MODE LABELS (Read-What-You-See on ANY user-customized button!)
      const dynCardSlots = snap?.loadouts?.card_slots || [];
      const dynPushSlots = snap?.loadouts?.push_slots || [];
      const wordCounts = {};
      for (const s of [...dynCardSlots, ...dynPushSlots]) {
        const words = normVoice(s.label || "").split(" ").filter((w) => w.length >= 2);
        for (const w of words) wordCounts[w] = (wordCounts[w] || 0) + 1;
      }
      const reservedSingleWords = new Set([
        "push", "box", "pit", "pick", "ban", "auto", "start", "wear", "wx", "ers", "wet", "fast",
        "gold", "stan", "dura", "expe", "chase", "heli", "visor", "next", "attack", "hammer",
        "conserve", "balanced", "matrix", "debrief", "stints", "logs", "delta", "upgrades", "compounds",
      ]);

      for (const s of dynCardSlots) {
        const normLbl = normVoice(s.label || "");
        if (!normLbl) continue;
        const uniqWordHit = normLbl.split(" ").some((w) => w.length >= 3 && wordCounts[w] === 1 && !reservedSingleWords.has(w) && isExact(w));
        if (has(normLbl) || uniqWordHit) {
          lastVoiceCmdMs = now;
          sendAction({ action: "set_copilot", key: "card_strategy", value: s.id });
          flashVoiceMatch(rawText, `CARD BUILD: ${s.label}`, `[data-cstrat="${s.id}"]`);
          return true;
        }
      }

      if (has("stop boost", "cancel push", "cancel boost", "boost off")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "manual_boost", active: false });
        flashVoiceMatch(rawText, "BOOST CUT", "#btn-boost-pulse");
        return true;
      }

      for (const s of dynPushSlots) {
        const normLbl = normVoice(s.label || "");
        if (!normLbl) continue;
        const uniqWordHit = normLbl.split(" ").some((w) => w.length >= 2 && wordCounts[w] === 1 && !reservedSingleWords.has(w) && isExact(w));
        if (has(normLbl) || uniqWordHit) {
          lastVoiceCmdMs = now;
          pushLedUntil = now + (Number(s.duration_s || 3) * 1000);
          sendAction({ action: "set_copilot", key: "push_profile", value: s.id });
          sendAction({ action: "manual_boost", profile: s.id, active: true, duration_s: Number(s.duration_s || 3.0) });
          flashVoiceMatch(rawText, `PUSH: ${s.label}`, `[data-pprof="${s.id}"]`);
          return true;
        }
      }

      // Built-in Shorthand & Synonym Fallbacks for Default Card Builds ("P1" / "P1 MIMIC", "BOOST 6/6", "APEX GRIP", "SNOWBALL", "1-STOP")
      if (has("p1 mimic", "podium mimic", "podium build", "p1 build") || isExact("p1", "b1", "mimic")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "card_strategy", value: "p1_mimic" });
        flashVoiceMatch(rawText, "CARD BUILD: P1 MIMIC", '[data-cstrat="p1_mimic"]');
        return true;
      }
      if (has("boost 6 6", "boost 6", "6 6", "boost rush", "boost build", "super boost build") || isExact("66")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "card_strategy", value: "super_boost" });
        flashVoiceMatch(rawText, "CARD BUILD: BOOST 6/6", '[data-cstrat="super_boost"]');
        return true;
      }
      if (has("apex grip", "apex build", "grip build", "corner build") || isExact("grip")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "card_strategy", value: "apex_grip" });
        flashVoiceMatch(rawText, "CARD BUILD: APEX GRIP", '[data-cstrat="apex_grip"]');
        return true;
      }
      if (has("snowball", "xp build", "hyper snowball")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "card_strategy", value: "xp_snowball" });
        flashVoiceMatch(rawText, "CARD BUILD: SNOWBALL", '[data-cstrat="xp_snowball"]');
        return true;
      }
      if (has("castellet", "paul ricard", "golden build", "golden stack", "1 stop", "ironman", "dom build")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "card_strategy", value: "ironman" });
        flashVoiceMatch(rawText, "CARD BUILD: CASTELLET", '[data-cstrat="ironman"]');
        return true;
      }

      // 4) PUSH MODE Built-in Synonyms ("K1 BOTH" / "K1", "SLINGSHOT", "APEX EXIT", "7s DUMP", "SUPER COMMS", "PUSH")
      if (has("super comms", "supercoms", "super calm", "golden push") || isExact("comms", "coms")) {
        lastVoiceCmdMs = now;
        pushLedUntil = now + 5200;
        sendAction({ action: "set_copilot", key: "push_profile", value: "super_comms" });
        sendAction({ action: "manual_boost", profile: "super_comms", active: true, duration_s: 5.2 });
        flashVoiceMatch(rawText, "★ PUSH: SUPER COMMS", '[data-pprof="super_comms"]');
        return true;
      }
      if (has("defend", "defend pulse", "defensive boost")) {
        lastVoiceCmdMs = now;
        pushLedUntil = now + 2200;
        sendAction({ action: "set_copilot", key: "push_profile", value: "super_comms" });
        sendAction({ action: "manual_boost", profile: "super_comms", active: true });
        flashVoiceMatch(rawText, "PUSH: SUPER COMMS", '[data-pprof="super_comms"]');
        return true;
      }
      if (has("slingshot", "straight sniper")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "push_profile", value: "slingshot" });
        sendAction({ action: "manual_boost", profile: "slingshot", active: true });
        flashVoiceMatch(rawText, "PUSH: SLINGSHOT", '[data-pprof="slingshot"]');
        return true;
      }
      if (has("apex exit", "apex vector") || isExact("exit")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "push_profile", value: "apex_vector" });
        sendAction({ action: "manual_boost", profile: "apex_vector", active: true });
        flashVoiceMatch(rawText, "PUSH: APEX EXIT", '[data-pprof="apex_vector"]');
        return true;
      }
      if (has("7s dump", "7 dump", "overtake dump", "battery dump", "empty battery", "drain battery", "full deploy") || isExact("7s", "dump")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "push_profile", value: "overtake_dump" });
        sendAction({ action: "manual_boost", profile: "overtake_dump", active: true });
        flashVoiceMatch(rawText, "PUSH: 7s DUMP", '[data-pprof="overtake_dump"]');
        return true;
      }
      if (has("k1 both", "super boost", "superboost", "hold both", "both boost") || isExact("k1", "both")) {
        lastVoiceCmdMs = now;
        pushLedUntil = now + 3000;
        sendAction({ action: "set_copilot", key: "push_profile", value: "k1_super" });
        sendAction({ action: "manual_boost", profile: "k1_super", active: true, duration_s: 3.0 });
        flashVoiceMatch(rawText, "PUSH: K1 BOTH", '[data-pprof="k1_super"]');
        return true;
      }
      if (has("party mode")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "manual_boost", speed: false, cornering: false, party: true, duration_s: 4.0 });
        flashVoiceMatch(rawText, "PARTY MODE", "#btn-boost-pulse");
        return true;
      }
      if (has("speed boost", "straight boost")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "manual_boost", speed: true, cornering: false, party: false, duration_s: 2.5 });
        flashVoiceMatch(rawText, "SPEED BOOST", "#btn-boost-pulse");
        return true;
      }
      if (has("corner boost", "cornering boost", "grip boost")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "manual_boost", speed: false, cornering: true, party: false, duration_s: 2.5 });
        flashVoiceMatch(rawText, "CORNER BOOST", "#btn-boost-pulse");
        return true;
      }
      if (isExact("push") || has("push now", "overtake", "send it", "full send")) {
        lastVoiceCmdMs = now;
        const prof = snap?.copilot?.push_profile || "k1_super";
        pushLedUntil = now + 2800;
        sendAction({ action: "manual_boost", profile: prof, active: true, toggle_if_active: isExact("push") });
        flashVoiceMatch(rawText, `PUSH (${prof.toUpperCase()})`, "#btn-boost-pulse");
        return true;
      }

      // 5) Briefing Pills ("WEAR", "WX", "SITREP") — Metallic switches handled in 1b above
      if (hasWord("wear") || has("tire wear")) {
        lastVoiceCmdMs = now;
        if (has("1 3", "1 30")) {
          sendAction({ action: "set_copilot", key: "wear_mult", value: 1.3 });
          flashVoiceMatch(rawText, "WEAR: 1.30x", "#btn-cycle-wear");
        } else if (has("1 15")) {
          sendAction({ action: "set_copilot", key: "wear_mult", value: 1.15 });
          flashVoiceMatch(rawText, "WEAR: 1.15x", "#btn-cycle-wear");
        } else if (has("1 00", "1 0x") || isExact("wear 1")) {
          sendAction({ action: "set_copilot", key: "wear_mult", value: 1.0 });
          flashVoiceMatch(rawText, "WEAR: 1.00x", "#btn-cycle-wear");
        } else {
          document.getElementById("btn-cycle-wear")?.click();
          flashVoiceMatch(rawText, "CYCLE WEAR", "#btn-cycle-wear");
        }
        return true;
      }
      if (hasWord("wx") || has("weather forecast", "rain forecast")) {
        lastVoiceCmdMs = now;
        if (has("rain")) {
          sendAction({ action: "set_copilot", key: "rain_forecast", value: "rain_soon" });
          flashVoiceMatch(rawText, "WX: RAIN ▶", "#btn-cycle-fcst");
        } else if (has("dry")) {
          sendAction({ action: "set_copilot", key: "rain_forecast", value: "drying" });
          flashVoiceMatch(rawText, "WX: DRY ◀", "#btn-cycle-fcst");
        } else if (has("auto")) {
          sendAction({ action: "set_copilot", key: "rain_forecast", value: "auto" });
          flashVoiceMatch(rawText, "WX: AUTO", "#btn-cycle-fcst");
        } else {
          document.getElementById("btn-cycle-fcst")?.click();
          flashVoiceMatch(rawText, "CYCLE WX", "#btn-cycle-fcst");
        }
        return true;
      }
      if (has("sitrep", "tire check", "radio check") || isExact("status", "report")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "test_radio" });
        flashVoiceMatch(rawText, "SITREP [T]", "#btn-radio-test");
        return true;
      }

      // 6) Pit Calls ("BOX THIS LAP", "BOX CONFIRMED (CANCEL)", "BOX")
      if (has("box confirmed", "cancel box", "stay out", "cancel pit", "abort pit", "no pit", "keep going") || isExact("confirmed") || (isExact("cancel") && snap?.pit?.pit_planned)) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_pit", pit: false });
        flashVoiceMatch(rawText, "STAY OUT (PIT CANCELLED)", "#btn-pit-toggle");
        return true;
      }
      if (has("box this lap", "box box", "pit this lap", "pit now", "come in", "in in in")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_pit", pit: true });
        flashVoiceMatch(rawText, "BOX THIS LAP", "#btn-pit-toggle");
        return true;
      }
      if (isExact("box", "pit")) {
        lastVoiceCmdMs = now;
        const nextPit = !snap?.pit?.pit_planned;
        sendAction({ action: "set_pit", pit: nextPit });
        flashVoiceMatch(rawText, nextPit ? "BOX THIS LAP" : "STAY OUT", "#btn-metal-box");
        return true;
      }

      // 7) 4-Stage Strategy Pace Buttons ("CONSERVE", "BALANCED", "ATTACK", "HAMMER")
      if (has("hammer", "hammertime", "qualy mode", "qualifying mode")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "pace_mode", value: "hammer" });
        flashVoiceMatch(rawText, "PACE: HAMMER", "#pace-hammer");
        return true;
      }
      if (has("attack mode", "attack pace", "undercut mode") || isExact("attack")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "pace_mode", value: "attack" });
        flashVoiceMatch(rawText, "PACE: ATTACK", "#pace-attack");
        return true;
      }
      if (has("conserve", "save tire", "lift and coast")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "pace_mode", value: "conserve" });
        flashVoiceMatch(rawText, "PACE: CONSERVE", "#pace-conserve");
        return true;
      }
      if (has("balanced", "standard pace", "normal pace") || isExact("balance")) {
        lastVoiceCmdMs = now;
        sendAction({ action: "set_copilot", key: "pace_mode", value: "balanced" });
        flashVoiceMatch(rawText, "PACE: BALANCED", "#pace-balanced");
        return true;
      }

      // 8) Tire Compound Buttons (Both Full Names & 4-Letter Button Labels: STAN / FAST / DURA / BOOS / WET / EXPE / GOLD)
      const tiresDeckActive = document.getElementById("deck-tires")?.classList.contains("active");
      const tireMap = [
        [["golden", "gold tire"], ["gold"], "Golden"],
        [["wet", "rain tire", "inters"], [], "Wet"],
        [["durable", "hard tire", "hards"], ["dura"], "Durable"],
        [["fast tire", "soft tire", "softs"], ["fast"], "Fast"],
        [["experimental"], ["expe"], "Experimental"],
        [["boost tire", "boost compound"], tiresDeckActive ? ["boos", "boost"] : ["boos"], "Boost"],
        [["standard tire", "mediums", "standards"], ["standard", "stan"], "Standard"],
      ];
      for (const [substrs, exacts, comp] of tireMap) {
        if ((substrs.length && has(...substrs)) || (exacts.length && isExact(...exacts))) {
          lastVoiceCmdMs = now;
          sendAction({ action: "pick_tire", compound: comp });
          flashVoiceMatch(rawText, `COMPOUND: ${comp.toUpperCase()}`, `button[data-tire="${comp}"]`);
          return true;
        }
      }

      // 9) Camera Buttons ("CHASE", "T-CAM", "VISOR", "HELI", "NEXT")
      if (has("chase cam") || isExact("chase")) { lastVoiceCmdMs = now; sendAction({ action: "set_camera", camera: "Chase" }); flashVoiceMatch(rawText, "CAM: CHASE", '[data-cam="Chase"]'); return true; }
      if (has("t cam")) { lastVoiceCmdMs = now; sendAction({ action: "set_camera", camera: "Onboard_TCam" }); flashVoiceMatch(rawText, "CAM: T-CAM", '[data-cam="Onboard_TCam"]'); return true; }
      if (has("visor cam", "cockpit cam") || isExact("visor")) { lastVoiceCmdMs = now; sendAction({ action: "set_camera", camera: "Onboard_Driver" }); flashVoiceMatch(rawText, "CAM: VISOR", '[data-cam="Onboard_Driver"]'); return true; }
      if (has("helicopter", "heli cam") || isExact("heli")) { lastVoiceCmdMs = now; sendAction({ action: "set_camera", camera: "Helicopter" }); flashVoiceMatch(rawText, "CAM: HELI", '[data-cam="Helicopter"]'); return true; }
      if (has("next cam", "switch cam") || isExact("next")) { lastVoiceCmdMs = now; sendAction({ action: "set_camera", camera: "next" }); flashVoiceMatch(rawText, "CAM: NEXT", '[data-cam="next"]'); return true; }

      // 10) Universal Visible DOM <button> Label Matcher (catches any other button on screen verbatim)
      const domHit = matchVisibleDomButton(t);
      if (domHit) {
        lastVoiceCmdMs = now;
        flashVoiceMatch(rawText, domHit.label.toUpperCase(), domHit.btn);
        return true;
      }

      return fail();
    }

    function isInterimPrefixAmbiguous(low) {
      // Single-word prefixes that could continue into a 2-word command ("auto card", "pit guard", "pick 2"):
      // pure prefixes ("auto", "card") wait for the second word or isFinal; standalone 1-word commands get a 340ms settle window!
      if (["auto", "pit", "boost", "ers", "wear", "wx", "ban", "pick", "start", "card"].includes(low)) {
        return true;
      }
      if (low === "box" && snap?.pit?.pit_planned) {
        return true; // Could be starting to say "box confirmed" to cancel
      }
      return false;
    }

    function toggleVoiceMic() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        const msg = !window.isSecureContext
          ? "Mic blocked: open over localhost, HTTPS, or Chrome secure-origin flag."
          : "Speech recognition requires Chrome / Edge.";
        updateVoiceBarUI("error", msg);
        return;
      }
      try { ensureAudioCtx(); } catch (_) {}
      micEnabled = !micEnabled;
      try { localStorage.setItem("bc_mic_auto", micEnabled ? "1" : "0"); } catch (_) {}
      if (!micEnabled) {
        stopMicWaveformCapture();
        if (speechRec) {
          try { speechRec.onend = null; speechRec.stop(); } catch (_) {}
          speechRec = null;
        }
        updateVoiceBarUI(null, "Mic muted — press [V] to listen");
        return;
      }

      const ua = navigator.userAgent || "";
      const isAndroidUA = /Android/i.test(ua);
      const isMobileVoiceClient = isAndroidUA || /iPhone|iPad|iPod|Mobile/i.test(ua) || (navigator.maxTouchPoints > 1 && window.innerWidth <= 1100);
      // On Android / mobile browsers, getUserMedia holds exclusive hardware AudioRecord and starves SpeechRecognition.
      if (isMobileVoiceClient) {
        stopMicWaveformCapture();
      } else {
        startMicWaveformCapture();
      }

      const startRec = () => {
        if (!micEnabled) return;
        const rec = new SR();
        const executedSlots = new Set();
        let interimSettleTimer = null;
        let lastErrCode = "";
        let hadSpeechResult = false;
        let matchedAnyCmd = false;
        rec.lang = navigator.language && navigator.language.startsWith("en") ? navigator.language : "en-US";
        // Desktop Chrome/Edge supports quiet continuous open-mic; Android Chrome uses reliable single-shot PTT (no looping activation chimes).
        rec.continuous = !isAndroidUA;
        rec.interimResults = true;
        rec.maxAlternatives = 4;

        rec.onsoundstart = () => {
          speechInterimKickUntil = performance.now() + 750;
        };
        rec.onspeechstart = () => {
          speechInterimKickUntil = performance.now() + 1100;
          updateVoiceBarUI(null, "Listening… speak command");
        };

        rec.onresult = (ev) => {
          if (!micEnabled) return;
          hadSpeechResult = true;
          speechInterimKickUntil = performance.now() + 650;
          if (interimSettleTimer) {
            clearTimeout(interimSettleTimer);
            interimSettleTimer = null;
          }

          for (let i = ev.resultIndex; i < ev.results.length; i++) {
            if (executedSlots.has(i)) continue;
            const res = ev.results[i];
            const topPhrase = (res[0]?.transcript || "").trim();
            if (!topPhrase) continue;

            if (res.isFinal) {
              let matched = false;
              for (let a = 0; a < res.length; a++) {
                const alt = (res[a]?.transcript || "").trim();
                if (alt && executeVoiceCommand(alt)) {
                  executedSlots.add(i);
                  matchedAnyCmd = true;
                  matched = true;
                  break;
                }
              }
              if (!matched && !isPureSpeakerEcho(normVoice(topPhrase))) {
                updateVoiceBarUI(null, `Heard: "${topPhrase}"`);
              }
            } else {
              // ZERO-LAG INTERIM EXECUTION (~100ms): Fire any unambiguous race command immediately while speaking!
              const low = normVoice(topPhrase);
              if (!low || isPureSpeakerEcho(low)) continue;
              if (!isInterimPrefixAmbiguous(low)) {
                if (executeVoiceCommand(topPhrase)) {
                  executedSlots.add(i);
                  matchedAnyCmd = true;
                } else {
                  updateVoiceBarUI(null, `… "${topPhrase}"`);
                }
              } else {
                updateVoiceBarUI(null, `… "${topPhrase}"`);
                // Pure prefixes ("auto", "card") always wait for the next word or isFinal; standalone 1-word commands settle after 340ms.
                if (low !== "auto" && low !== "card") {
                  const slotIdx = i;
                  const snapPhrase = topPhrase;
                  interimSettleTimer = setTimeout(() => {
                    if (micEnabled && !executedSlots.has(slotIdx)) {
                      if (executeVoiceCommand(snapPhrase)) {
                        executedSlots.add(slotIdx);
                        matchedAnyCmd = true;
                      }
                    }
                  }, 340);
                }
              }
            }
          }
        };

        rec.onerror = (ev) => {
          lastErrCode = String(ev?.error || "");
          if (lastErrCode === "not-allowed" || lastErrCode === "service-not-allowed") {
            micEnabled = false;
            stopMicWaveformCapture();
            const msg = !window.isSecureContext
              ? "Blocked on LAN HTTP — add URL in chrome://flags"
              : "Mic permission blocked — allow microphone in browser.";
            updateVoiceBarUI("error", msg);
          } else if (lastErrCode === "audio-capture") {
            stopMicWaveformCapture();
            updateVoiceBarUI("error", "Mic hardware busy (audio-capture)");
          } else if (lastErrCode === "network") {
            updateVoiceBarUI("error", "Speech network err — check Google speech access");
          } else if (lastErrCode && lastErrCode !== "no-speech" && lastErrCode !== "aborted") {
            updateVoiceBarUI("error", `Speech err: ${lastErrCode}`);
          }
        };

        rec.onend = () => {
          if (interimSettleTimer) {
            clearTimeout(interimSettleTimer);
            interimSettleTimer = null;
          }
          if (!micEnabled) return;
          if (isAndroidUA) {
            // Single-shot PTT on Android: finish cleanly without looping Android's SpeechRecognizer chime.
            micEnabled = false;
            try { localStorage.setItem("bc_mic_auto", "0"); } catch (_) {}
            if (!matchedAnyCmd && !lastErrCode.startsWith("not-allowed")) {
              updateVoiceBarUI(null, hadSpeechResult ? "Tap MIC PTT [V] for next command" : "No command heard — tap MIC PTT [V]");
            } else {
              const micBtnEl = document.getElementById("btn-mic-toggle");
              if (micBtnEl) micBtnEl.classList.remove("mic-live");
            }
            return;
          }
          const delayMs = lastErrCode === "network" ? 1800 : !hadSpeechResult ? 900 : 120;
          setTimeout(() => {
            if (micEnabled) {
              try { startRec(); } catch (_) {}
            }
          }, delayMs);
        };

        speechRec = rec;
        try {
          rec.start();
          updateVoiceBarUI(null, isAndroidUA ? 'Listening — say one command ("Box", "Push", "Hammer"…)' : 'Voice Comms Active — say any button ("Box", "Push", "Hammer", "Wet"…)');
        } catch (err) {
          micEnabled = false;
          updateVoiceBarUI("error", `Mic start err: ${err?.message || err}`);
        }
      };

      startRec();
    }

    const micBtn = document.getElementById("btn-mic-toggle");
    if (micBtn) micBtn.addEventListener("click", toggleVoiceMic);
    const vcBar = document.getElementById("voice-cmd-bar");
    if (vcBar) vcBar.addEventListener("click", toggleVoiceMic);
    const drvTagBtn = document.getElementById("drivercam-tag");
    if (drvTagBtn) drvTagBtn.addEventListener("click", toggleVoiceMic);

    // Voice Help Cheat-Sheet Modal
    const vhModal = document.getElementById("voice-help-modal");
    const btnVhOpen = document.getElementById("btn-voice-help");
    const btnVhClose = document.getElementById("btn-close-voice-help");
    if (btnVhOpen && vhModal) {
      btnVhOpen.addEventListener("click", () => { vhModal.style.display = "flex"; });
    }
    if (btnVhClose && vhModal) {
      btnVhClose.addEventListener("click", () => { vhModal.style.display = "none"; });
      vhModal.addEventListener("click", (e) => { if (e.target === vhModal) vhModal.style.display = "none"; });
    }

    // ==================== 5-SLOT PUSH & CARD STRATEGY LAB + MULTI-PERSONA VOICE STUDIO ====================
    const lsModal = document.getElementById("loadout-studio-modal");
    const btnLsOpen = document.getElementById("btn-loadout-studio");
    const btnEditPush = document.getElementById("btn-edit-push-slots");
    const btnEditCard = document.getElementById("btn-edit-card-slots");
    const btnLsClose = document.getElementById("btn-close-loadout-studio");
    const btnLsResetAll = document.getElementById("btn-reset-all-loadouts");
    let lsState = null;
    let lsActiveTab = "push";
    let lsActivePushIdx = 0;
    let lsActiveCardIdx = 0;

    function escAttr(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    }

    function applyLoadoutStateToClient(state) {
      if (!state) return;
      lsState = state;
      if (snap) {
        snap.loadouts = state;
        renderCommandDeck();
      }
      if (localSim && typeof localSim.setLoadouts === "function") {
        localSim.setLoadouts(state);
      }
    }

    async function fetchLoadoutStudioState() {
      try {
        const res = await fetch("/api/loadouts");
        if (res.ok) {
          const st = await res.json();
          applyLoadoutStateToClient(st);
          return st;
        }
      } catch (_) {}
      // Standalone web demo fallback (localStorage-persisted 5-slot state!)
      const fallback = snap?.loadouts || lsState;
      if (fallback) {
        lsState = fallback;
      }
      return lsState;
    }

    function setLoadoutTab(tab) {
      lsActiveTab = tab === "card" ? "card" : "push";
      document.querySelectorAll(".ls-tab").forEach((b) => b.classList.toggle("active", b.dataset.lstab === lsActiveTab));
      const pPush = document.getElementById("ls-pane-push");
      const pCard = document.getElementById("ls-pane-card");
      if (pPush) pPush.style.display = lsActiveTab === "push" ? "flex" : "none";
      if (pCard) pCard.style.display = lsActiveTab === "card" ? "flex" : "none";
      renderLoadoutStudio();
    }

    function renderLoadoutStudio() {
      if (!lsState) return;
      const pushSlots = (lsState.push_slots || []).slice(0, 5);
      const cardSlots = (lsState.card_slots || []).slice(0, 5);
      const cat = lsState.catalog || {
        facilities: ["Speed", "Cornering", "Performance", "Boost", "Fuel"],
        upgrades: ["EnginePower", "DragReduction", "TireGrip", "TemporaryUpgradeDuration", "TractionControl", "Downforce", "TireSaving", "PitSpeed", "BoostCapacity", "WeightReduction", "BoostPerSector", "BoostRechargeSpeed", "ExperienceGain", "SensorQuality", "TurboCharger", "Suspension", "Cooling", "BoostOverspeed", "KineticRegen"],
      };

      // 1) Push Slots Strip & Editor
      const pStrip = document.getElementById("ls-push-slot-tabs");
      const pEdit = document.getElementById("ls-push-editor");
      if (pStrip && pEdit && pushSlots.length) {
        pStrip.innerHTML = pushSlots.map((s, idx) => `
          <button class="ls-slot-pill ${idx === lsActivePushIdx ? "active" : ""}" data-ls-pslot="${idx}">
            <small class="mono">SLOT 0${idx + 1} / 05</small>
            <strong>${escAttr(s.label)}</strong>
            <span class="ls-pill-sub mono">${Number(s.duration_s).toFixed(1)}s · ${escAttr(s.mode.toUpperCase())}</span>
          </button>
        `).join("");
        const ps = pushSlots[lsActivePushIdx] || pushSlots[0];
        const steerDeg = Math.round(Number(ps.max_steer) * 90);
        const modeOpts = [
          ["super_comms", "★ SUPER COMMS (Golden 5x Hybrid · Corner-Grip -> Straight Super-Boost + Party)"],
          ["both", "HOLD BOTH (Super Boost · Speed + Cornering)"],
          ["straight_super", "SLINGSHOT (Straight Sniper · Auto-cuts in corners)"],
          ["corner_to_both", "APEX VECTOR (Cornering Grip mid-turn -> Both on exit)"],
          ["smart_dump", "SMART DUMP (Full-Sector Drain · Cornering + Straight Both)"],
          ["speed_only", "SPEED BOOST ONLY (Top-end Straight Punch)"],
          ["corner_only", "CORNERING BOOST ONLY (Pure Apex Grip)"],
          ["party", "PARTY MODE + BOTH (Fuel / Qualy Max)"],
        ];
        pEdit.innerHTML = `
          <div class="ls-telemetry-banner mono">
            <span>VOICE TRIGGER // <b>"${escAttr(ps.label)}"</b></span>
            <span>50HZ GATE: <b>&le;${steerDeg}&deg; STEER</b> · <b>&ge;${Math.round(ps.min_pedal * 100)}% THR</b> · <b>${Math.round(ps.energy_floor * 100)}% ERS FLOOR</b></span>
          </div>
          <div class="ls-form-grid">
            <div class="ls-field">
              <label>BUTTON LABEL (MAX 12 CHARS · LIVE VOICE COMMAND!)</label>
              <input type="text" id="lsp-label" class="ls-input" maxlength="12" value="${escAttr(ps.label)}" />
            </div>
            <div class="ls-field">
              <label>50HZ BOOST CHANNEL CONTROLLER</label>
              <select id="lsp-mode" class="voice-select" style="padding:5px">
                ${modeOpts.map(([v, txt]) => `<option value="${v}" ${ps.mode === v ? "selected" : ""}>${txt}</option>`).join("")}
              </select>
            </div>
            <div class="ls-field">
              <label>BURST DURATION (0.8s – 12.0s)</label>
              <input type="number" id="lsp-dur" class="ls-input" step="0.1" min="0.8" max="12" value="${Number(ps.duration_s).toFixed(1)}" />
            </div>
            <div class="ls-field">
              <label>MAX STEER CONE (0.06 = Straight Only · 1.00 = Any Angle)</label>
              <input type="number" id="lsp-steer" class="ls-input" step="0.02" min="0.05" max="1.0" value="${Number(ps.max_steer).toFixed(2)}" />
            </div>
            <div class="ls-field">
              <label>MIN THROTTLE GATE (0.00 – 0.90)</label>
              <input type="number" id="lsp-pedal" class="ls-input" step="0.05" min="0.0" max="0.9" value="${Number(ps.min_pedal).toFixed(2)}" />
            </div>
            <div class="ls-field">
              <label>BATTERY RESERVE FLOOR (0.02 = 2% · 0.20 = Keep 20%)</label>
              <input type="number" id="lsp-floor" class="ls-input" step="0.02" min="0.0" max="0.6" value="${Number(ps.energy_floor).toFixed(2)}" />
            </div>
            <div class="ls-field full">
              <label>ENGINEER RADIO CALLOUT WHEN TRIGGERED</label>
              <input type="text" id="lsp-call" class="ls-input" maxlength="140" value="${escAttr(ps.call)}" />
            </div>
          </div>
          <div class="ls-actions-row">
            <button class="sw-btn" id="btn-lsp-reset">↺ RESET SLOT ${lsActivePushIdx + 1} TO DEFAULT</button>
            <div style="display:flex;gap:6px">
              <button class="sw-btn play" id="btn-lsp-save">SAVE PUSH SLOT ${lsActivePushIdx + 1}</button>
              <button class="micro-btn swooz-rec-btn" id="btn-lsp-arm">SAVE &amp; ARM ON PIT WALL</button>
            </div>
          </div>
        `;
      }

      // 2) Card Build Slots Strip & Editor
      const cStripEl = document.getElementById("ls-card-slot-tabs");
      const cEdit = document.getElementById("ls-card-editor");
      if (cStripEl && cEdit && cardSlots.length) {
        cStripEl.innerHTML = cardSlots.map((s, idx) => `
          <button class="ls-slot-pill ${idx === lsActiveCardIdx ? "active" : ""}" data-ls-cslot="${idx}">
            <small class="mono">SLOT 0${idx + 1} / 05</small>
            <strong>${escAttr(s.label)}</strong>
            <span class="ls-pill-sub mono">${(s.rush_facilities || []).join("+") || "CUSTOM"}</span>
          </button>
        `).join("");
        const cs = cardSlots[lsActiveCardIdx] || cardSlots[0];
        const archOpts = [
          ["castellet_comms", "★ CASTELLET GOLDEN GRAND SLAM (10/10 Laps Led · -26.5s Pit · 5x Golden Stack)"],
          ["custom", "CUSTOM RULE ENGINE (100% Driven by Your Facility & Upgrade Picks Below)"],
          ["p1_mimic", "P1 PODIUM MIMIC BASE + Your Custom Overrides"],
          ["super_boost", "SUPER-BOOST 6/6 ROCKET BASE + Your Custom Overrides"],
          ["apex_grip", "APEX & WET GRIP BASE + Your Custom Overrides"],
          ["xp_snowball", "42-TIER XP SNOWBALL BASE + Your Custom Overrides"],
          ["ironman", "DOM 1-STOP IRONMAN BASE + Your Custom Overrides"],
          ["lendurance", "L'ENDURANCE MULSANNE P1 BASE + Your Custom Overrides"],
        ];
        const archives = lsState.archived_races || [];
        const nFac = (cs.rush_facilities || []).length;
        const nPrio = (cs.priority_upgrades || []).length;
        const nLate = (cs.late_upgrades || []).length;
        const nAvoid = (cs.avoid_upgrades || []).length;
        cEdit.innerHTML = `
          <div class="ls-telemetry-banner mono">
            <span>VOICE TRIGGER // <b>"${escAttr(cs.label)}"</b></span>
            <span>BLUEPRINT: <b>${nFac}/3 RUSH</b> · <b>${nPrio}/7 CORE (+28 EV)</b> · <b>${nLate}/4 CLOSER</b> · <b>${nAvoid}/5 BAN</b></span>
          </div>
          ${archives.length ? `
          <div class="ls-import-row mono">
            <strong style="color:#ffd15c">IMPORT FROM P1 RACE ARCHIVE:</strong>
            <select id="lsc-archive-sel" class="voice-select" style="flex:1;min-width:200px">
              ${archives.map((a) => `<option value="${escAttr(a.archive)}">${escAttr(a.track)} — P1 ${escAttr(a.winner)} (G${a.grid}→P1 · +${Number(a.win_margin_s || 0).toFixed(2)}s)</option>`).join("")}
            </select>
            <button class="sw-btn play" id="btn-lsc-import-archive">LOAD INTO SLOT ${lsActiveCardIdx + 1}</button>
          </div>` : ""}
          <div class="ls-form-grid">
            <div class="ls-field">
              <label>BUTTON LABEL (MAX 12 CHARS · LIVE VOICE COMMAND!)</label>
              <input type="text" id="lsc-label" class="ls-input" maxlength="12" value="${escAttr(cs.label)}" />
            </div>
            <div class="ls-field">
              <label>STRATEGY ENGINE MODE</label>
              <select id="lsc-arch" class="voice-select" style="padding:5px">
                ${archOpts.map(([v, txt]) => `<option value="${v}" ${cs.base_archetype === v ? "selected" : ""}>${txt}</option>`).join("")}
              </select>
            </div>
            <div class="ls-field full">
              <label>STRATEGY SUMMARY / TOOLTIP</label>
              <input type="text" id="lsc-summary" class="ls-input" maxlength="150" value="${escAttr(cs.summary)}" />
            </div>
            <div class="ls-field full">
              <label>FACILITY 6/6 RUSH TARGETS (+22 EV EARLY UNTIL 6/6 UNLOCK) <span class="ls-cap-badge" id="cap-lsc-fac">${nFac} / 3</span></label>
              <div class="ls-chip-cloud" id="lsc-rush-cloud">
                ${(cat.facilities || []).map((f) => `<button type="button" class="ls-pick-chip ${(cs.rush_facilities || []).includes(f) ? "on" : ""}" data-lsc-fac="${f}">${f}</button>`).join("")}
              </div>
            </div>
            <div class="ls-field full">
              <label>CORE PRIORITY UPGRADES (+28 EV TOP PICK) <span class="ls-cap-badge" id="cap-lsc-prio">${nPrio} / 7</span></label>
              <div class="ls-chip-cloud" id="lsc-prio-cloud">
                ${(cat.upgrades || []).map((u) => `<button type="button" class="ls-pick-chip ${(cs.priority_upgrades || []).includes(u) ? "on" : ""}" data-lsc-prio="${u}">${u}</button>`).join("")}
              </div>
            </div>
            <div class="ls-field full">
              <label>LATE-RACE CLOSER UPGRADES (+24 EV IN FINAL 40% OF RACE) <span class="ls-cap-badge" id="cap-lsc-late">${nLate} / 4</span></label>
              <div class="ls-chip-cloud" id="lsc-late-cloud">
                ${(cat.upgrades || []).map((u) => `<button type="button" class="ls-pick-chip ${(cs.late_upgrades || []).includes(u) ? "on" : ""}" data-lsc-late="${u}">${u}</button>`).join("")}
              </div>
            </div>
            <div class="ls-field full">
              <label>AVOID / SMART-BAN CANDIDATES (-26 EV PENALTY) <span class="ls-cap-badge" id="cap-lsc-avoid">${nAvoid} / 5</span></label>
              <div class="ls-chip-cloud" id="lsc-avoid-cloud">
                ${(cat.upgrades || []).map((u) => `<button type="button" class="ls-pick-chip avoid ${(cs.avoid_upgrades || []).includes(u) ? "on" : ""}" data-lsc-avoid="${u}">${u}</button>`).join("")}
              </div>
            </div>
            <div class="ls-field full">
              <label>ENGINEER RADIO CALLOUT WHEN SELECTED</label>
              <input type="text" id="lsc-call" class="ls-input" maxlength="140" value="${escAttr(cs.call)}" />
            </div>
          </div>
          <div class="ls-actions-row">
            <button class="sw-btn" id="btn-lsc-reset">↺ RESET SLOT ${lsActiveCardIdx + 1} TO DEFAULT</button>
            <div style="display:flex;gap:6px">
              <button class="sw-btn play" id="btn-lsc-save">SAVE CARD SLOT ${lsActiveCardIdx + 1}</button>
              <button class="micro-btn swooz-rec-btn" id="btn-lsc-arm">SAVE &amp; ACTIVATE BUILD</button>
            </div>
          </div>
        `;
      }
    }

    async function postLoadoutAction(payload) {
      try {
        const res = await fetch("/api/loadouts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const st = await res.json();
          applyLoadoutStateToClient(st);
          renderLoadoutStudio();
          return st;
        }
      } catch (_) {}
      // Offline/Standalone fallback
      if (localSim && typeof localSim.applyLoadoutMutation === "function") {
        const st = localSim.applyLoadoutMutation(payload);
        applyLoadoutStateToClient(st);
        renderLoadoutStudio();
        return st;
      }
      return null;
    }

    async function saveCurrentPushSlot(andArm = false) {
      const data = {
        label: document.getElementById("lsp-label")?.value || "PUSH",
        mode: document.getElementById("lsp-mode")?.value || "both",
        duration_s: Number(document.getElementById("lsp-dur")?.value || 3.0),
        max_steer: Number(document.getElementById("lsp-steer")?.value || 0.2),
        min_pedal: Number(document.getElementById("lsp-pedal")?.value || 0.0),
        energy_floor: Number(document.getElementById("lsp-floor")?.value || 0.02),
        call: document.getElementById("lsp-call")?.value || "",
      };
      const st = await postLoadoutAction({ action: "update_push_slot", slot: lsActivePushIdx, data });
      if (andArm && st?.push_slots?.[lsActivePushIdx]) {
        sendAction({ action: "set_copilot", key: "push_profile", value: st.push_slots[lsActivePushIdx].id });
      }
    }

    async function saveCurrentCardSlot(andArm = false) {
      const pickSelected = (attr) => [...document.querySelectorAll(`[${attr}].on`)].map((el) => el.getAttribute(attr));
      const lbl = document.getElementById("lsc-label")?.value || "CUSTOM";
      const data = {
        label: lbl,
        name: lbl,
        base_archetype: document.getElementById("lsc-arch")?.value || "custom",
        summary: document.getElementById("lsc-summary")?.value || "",
        rush_facilities: pickSelected("data-lsc-fac"),
        priority_upgrades: pickSelected("data-lsc-prio"),
        late_upgrades: pickSelected("data-lsc-late"),
        avoid_upgrades: pickSelected("data-lsc-avoid"),
        call: document.getElementById("lsc-call")?.value || "",
      };
      const st = await postLoadoutAction({ action: "update_card_slot", slot: lsActiveCardIdx, data });
      if (andArm && st?.card_slots?.[lsActiveCardIdx]) {
        sendAction({ action: "set_copilot", key: "card_strategy", value: st.card_slots[lsActiveCardIdx].id });
      }
    }

    const openLoadoutStudio = async (tab = "push") => {
      if (!lsModal) return;
      lsModal.style.display = "flex";
      await fetchLoadoutStudioState();
      setLoadoutTab(tab);
    };
    if (btnLsOpen) btnLsOpen.addEventListener("click", () => openLoadoutStudio("push"));
    if (btnEditPush) btnEditPush.addEventListener("click", () => openLoadoutStudio("push"));
    if (btnEditCard) btnEditCard.addEventListener("click", () => openLoadoutStudio("card"));
    if (btnLsClose && lsModal) {
      btnLsClose.addEventListener("click", () => { lsModal.style.display = "none"; });
      lsModal.addEventListener("click", (e) => { if (e.target === lsModal) lsModal.style.display = "none"; });
    }
    if (btnLsResetAll) {
      btnLsResetAll.addEventListener("click", () => postLoadoutAction({ action: "reset_all" }));
    }
    document.querySelectorAll(".ls-tab").forEach((tb) => {
      tb.addEventListener("click", () => setLoadoutTab(tb.dataset.lstab));
    });
    if (lsModal) {
      lsModal.addEventListener("click", async (e) => {
        const psBtn = e.target.closest("[data-ls-pslot]");
        if (psBtn) { lsActivePushIdx = Number(psBtn.dataset.lsPslot); renderLoadoutStudio(); return; }
        const csBtn = e.target.closest("[data-ls-cslot]");
        if (csBtn) { lsActiveCardIdx = Number(csBtn.dataset.lsCslot); renderLoadoutStudio(); return; }

        const chip = e.target.closest(".ls-pick-chip");
        if (chip) {
          const capMap = [
            ["data-lsc-fac", 3, "cap-lsc-fac"],
            ["data-lsc-prio", 7, "cap-lsc-prio"],
            ["data-lsc-late", 4, "cap-lsc-late"],
            ["data-lsc-avoid", 5, "cap-lsc-avoid"],
          ];
          for (const [attr, cap, badgeId] of capMap) {
            if (chip.hasAttribute(attr)) {
              if (!chip.classList.contains("on") && document.querySelectorAll(`[${attr}].on`).length >= cap) return;
              chip.classList.toggle("on");
              const bEl = document.getElementById(badgeId);
              if (bEl) bEl.textContent = `${document.querySelectorAll(`[${attr}].on`).length} / ${cap}`;
              return;
            }
          }
        }

        if (e.target.id === "btn-lsp-save") await saveCurrentPushSlot(false);
        else if (e.target.id === "btn-lsp-arm") await saveCurrentPushSlot(true);
        else if (e.target.id === "btn-lsp-reset") await postLoadoutAction({ action: "reset_push_slot", slot: lsActivePushIdx });
        else if (e.target.id === "btn-lsc-save") await saveCurrentCardSlot(false);
        else if (e.target.id === "btn-lsc-arm") await saveCurrentCardSlot(true);
        else if (e.target.id === "btn-lsc-reset") await postLoadoutAction({ action: "reset_card_slot", slot: lsActiveCardIdx });
        else if (e.target.id === "btn-lsc-import-archive") {
          const arch = document.getElementById("lsc-archive-sel")?.value;
          if (arch) await postLoadoutAction({ action: "import_card_slot_from_archive", slot: lsActiveCardIdx, archive: arch });
        }
      });
    }

    // ==================== MULTI-PERSONA & SWOOZ VOICE STUDIO (FREESTYLE SPIN + .ZIP PACKS) ====================
    const swModal = document.getElementById("swooz-studio-modal");
    const btnSwOpen = document.getElementById("btn-swooz-studio");
    const btnSwClose = document.getElementById("btn-close-swooz-studio");
    const btnSwUse = document.getElementById("btn-use-swooz-voice");
    const swSlotsEl = document.getElementById("swooz-slots-list");
    const swProgEl = document.getElementById("swooz-studio-prog");
    const selStudioPersona = document.getElementById("sel-studio-persona");
    const btnNewPersona = document.getElementById("btn-new-persona");
    const btnExportPersona = document.getElementById("btn-export-persona");
    const inpImportZip = document.getElementById("inp-import-persona-zip");
    const btnDelPersona = document.getElementById("btn-delete-persona");
    const btnSavePersonaMeta = document.getElementById("btn-save-persona-meta");

    let activeStudioPersonaId = "";
    let studioRec = null;
    let studioRecSlot = null;
    let studioRecChunks = [];
    let studioStream = null;

    function syncMainPersonaDropdown(personasList) {
      if (!selVoice || !Array.isArray(personasList)) return;
      const prevVal = voiceConfig.voice;
      for (const p of personasList) {
        PERSONA_ACOUSTIC_TRIM[p.id] = {
          detune: Number(p.detune || 0),
          presHz: Number(p.pres_hz || 1900),
          presDb: Number(p.pres_db ?? 3.0),
        };
        const cRadio = p.custom_lines?.radio_check;
        PERSONA_TEST_LINES[p.id] = cRadio || `${p.name} on the pit wall — telemetry locked, loud and clear!`;

        let opt = [...selVoice.options].find((o) => o.value === p.id);
        const labelTxt = `★ ${p.name.toUpperCase()} (${p.recorded_count}/${p.total_count})`;
        if (!opt) {
          opt = document.createElement("option");
          opt.value = p.id;
          opt.dataset.customPersona = "1";
          const firstBuiltIn = [...selVoice.options].find((o) => !o.dataset.customPersona);
          if (firstBuiltIn) selVoice.insertBefore(opt, firstBuiltIn);
          else selVoice.appendChild(opt);
        }
        opt.textContent = labelTxt;
      }
      // Remove deleted custom options
      const validCustomIds = new Set(personasList.map((p) => p.id));
      [...selVoice.options].forEach((o) => {
        if (o.dataset.customPersona === "1" && !validCustomIds.has(o.value)) o.remove();
      });
      if ([...selVoice.options].some((o) => o.value === prevVal)) {
        selVoice.value = prevVal;
      } else {
        voiceConfig.voice = "en-GB-SoniaNeural";
        localStorage.setItem("bc_voice", "en-GB-SoniaNeural");
        selVoice.value = "en-GB-SoniaNeural";
      }
    }

    async function refreshPersonasListOnBoot() {
      try {
        const res = await fetch("/api/personas");
        if (res.ok) {
          const d = await res.json();
          syncMainPersonaDropdown(d.personas || []);
        }
      } catch (_) {}
    }
    refreshPersonasListOnBoot();

    function encodeTrimmedNormalizedWavBase64(audioBuf) {
      const targetRate = 24000;
      const srcRate = audioBuf.sampleRate;
      const ch0 = audioBuf.getChannelData(0);
      const ch1 = audioBuf.numberOfChannels > 1 ? audioBuf.getChannelData(1) : null;
      const ratio = srcRate / targetRate;
      const outLen = Math.max(1, Math.floor(audioBuf.length / ratio));
      const mono = new Float32Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const si = Math.min(ch0.length - 1, Math.floor(i * ratio));
        mono[i] = ch1 ? (ch0[si] + ch1[si]) * 0.5 : ch0[si];
      }

      // Trim leading & trailing silence (< 0.015) with 55ms breath pad
      const pad = Math.floor(targetRate * 0.055);
      let first = 0;
      while (first < outLen - 1 && Math.abs(mono[first]) < 0.015) first++;
      let last = outLen - 1;
      while (last > first && Math.abs(mono[last]) < 0.015) last--;
      first = Math.max(0, first - pad);
      last = Math.min(outLen - 1, last + pad);
      const trimmed = last > first + 1200 ? mono.subarray(first, last + 1) : mono;

      // Peak normalize to 0.92 (-0.7dB) so Arctis 7 & iPhone clips hit with uniform broadcast punch!
      let peak = 0.001;
      for (let i = 0; i < trimmed.length; i++) {
        const a = Math.abs(trimmed[i]);
        if (a > peak) peak = a;
      }
      const gain = Math.min(8.0, 0.92 / peak);

      const numSamples = trimmed.length;
      const dataBytes = numSamples * 2;
      const buf = new ArrayBuffer(44 + dataBytes);
      const view = new DataView(buf);
      const writeStr = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); };
      writeStr(0, "RIFF");
      view.setUint32(4, 36 + dataBytes, true);
      writeStr(8, "WAVE");
      writeStr(12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true); // PCM
      view.setUint16(22, 1, true); // Mono
      view.setUint32(24, targetRate, true);
      view.setUint32(28, targetRate * 2, true);
      view.setUint16(32, 2, true);
      view.setUint16(34, 16, true);
      writeStr(36, "data");
      view.setUint32(40, dataBytes, true);

      let off = 44;
      for (let i = 0; i < numSamples; i++) {
        const s = Math.max(-1, Math.min(1, trimmed[i] * gain));
        view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        off += 2;
      }

      const u8 = new Uint8Array(buf);
      let bin = "";
      const chunk = 0x8000;
      for (let i = 0; i < u8.length; i += chunk) {
        bin += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
      }
      return btoa(bin);
    }

    function renderSwoozManifest(manifest) {
      if (!swSlotsEl || !manifest) return;
      activeStudioPersonaId = manifest.persona_id || "";
      const hasSavedPersonas = Array.isArray(manifest.personas) && manifest.personas.length > 0;
      syncMainPersonaDropdown(manifest.personas || []);

      if (selStudioPersona) {
        if (hasSavedPersonas) {
          selStudioPersona.innerHTML = manifest.personas.map((p) =>
            `<option value="${escAttr(p.id)}" ${p.id === activeStudioPersonaId ? "selected" : ""}>${escAttr(p.name)} (${p.recorded_count}/${p.total_count} clips)</option>`
          ).join("");
        } else {
          selStudioPersona.innerHTML = `<option value="">(No custom persona yet — click + NEW PERSONA or ● REC below!)</option>`;
        }
      }
      const pMeta = manifest.persona || {};
      const nameIn = document.getElementById("inp-persona-name");
      const baseV = document.getElementById("sel-persona-base-voice");
      const pitchIn = document.getElementById("inp-persona-pitch");
      const detIn = document.getElementById("inp-persona-detune");
      if (nameIn) nameIn.value = pMeta.name || "My Custom Crew";
      if (baseV) baseV.value = pMeta.base_voice || "Mark";
      if (pitchIn) pitchIn.value = Number(pMeta.pitch_pct ?? 0);
      if (detIn) detIn.value = Number(pMeta.detune ?? 0);
      if (btnDelPersona) {
        btnDelPersona.disabled = !activeStudioPersonaId;
        btnDelPersona.style.opacity = activeStudioPersonaId ? "1" : "0.35";
      }
      if (btnExportPersona) {
        btnExportPersona.disabled = !activeStudioPersonaId;
        btnExportPersona.style.opacity = activeStudioPersonaId ? "1" : "0.35";
      }

      if (swProgEl) {
        swProgEl.textContent = `${manifest.recorded_count} / ${manifest.total_count} RECORDED`;
      }
      if (btnSwUse) {
        btnSwUse.disabled = !activeStudioPersonaId;
        btnSwUse.style.opacity = activeStudioPersonaId ? "1" : "0.45";
        btnSwUse.textContent = activeStudioPersonaId
          ? `ACTIVATE ${(pMeta.name || "PERSONA").slice(0, 16).toUpperCase()}`
          : "SAVE / RECORD FIRST";
      }

      swSlotsEl.innerHTML = (manifest.slots || []).map((s, idx) => `
        <div class="swooz-slot-row ${s.recorded ? "done" : ""} ${studioRecSlot === s.id ? "recording" : ""}" data-slot="${s.id}">
          <div>
            <div class="sw-slot-hdr mono">
              <span class="sw-slot-cat">#${String(idx + 1).padStart(2, "0")} · ${escAttr(s.cat)}</span>
              <span>— ${escAttr(s.title)}</span>
              <span class="sw-slot-badge ${s.recorded ? "ok" : ""}">${s.recorded ? `MIC WAV (${s.size_kb}KB)` : (s.custom_line ? "CUSTOM SPIN (SSML)" : "GUIDE (AUTO SSML)")}</span>
            </div>
            <div class="sw-guide-lbl"><i>TRIGGER:</i> ${escAttr(s.trigger_when || s.title)} · <i>VIBE GUIDE:</i> "${escAttr(s.script)}"</div>
            <div class="sw-spin-wrap">
              <input type="text" class="sw-spin-input" data-sw-spin="${s.id}" maxlength="190"
                placeholder="Optional: Type your custom spin / slang here (or just hit REC &amp; freestyle!)"
                value="${escAttr(s.custom_line || "")}" />
              <button class="sw-btn" data-sw-saveline="${s.id}" title="Save custom spin text (also works for unrecorded SSML fallback!)">SAVE LINE</button>
            </div>
          </div>
          <div class="sw-slot-actions">
            <button class="sw-btn rec ${studioRecSlot === s.id ? "active" : ""}" data-sw-rec="${s.id}">
              ${studioRecSlot === s.id ? "■ STOP" : "● REC"}
            </button>
            <button class="sw-btn play" data-sw-play="${s.id}" data-sw-script="${escAttr(s.effective_line || s.script)}" title="Audition through 90s V10 FX">▶ V10 TEST</button>
            <label class="sw-btn" title="Upload .wav / .m4a / .mp3 from phone, tablet, or PC">
              LOAD WAV
              <input type="file" accept="audio/*" data-sw-file="${s.id}" style="display:none" />
            </label>
            ${s.recorded ? `<button class="sw-btn del" data-sw-del="${s.id}" title="Clear recorded WAV clip">✕</button>` : ""}
          </div>
        </div>
      `).join("");
    }

    async function loadSwoozStudio(personaId = activeStudioPersonaId) {
      try {
        const res = await fetch(`/api/swooz-voice?persona_id=${encodeURIComponent(personaId || "")}`);
        if (res.ok) renderSwoozManifest(await res.json());
      } catch (_) {}
    }

    function activatePersonaSelection(pid) {
      voiceConfig.voice = pid;
      localStorage.setItem("bc_voice", pid);
      if (selVoice && [...selVoice.options].some((o) => o.value === pid)) {
        selVoice.value = pid;
      }
      sendAction({ action: "prewarm_voice", voice: pid, rate_pct: voiceConfig.ratePct });
    }

    async function saveDecodedSlotAudio(slotId, arrayBuf, scriptText, customLineText) {
      const ctx = ensureAudioCtx();
      const decoded = await ctx.decodeAudioData(arrayBuf);
      const wavB64 = encodeTrimmedNormalizedWavBase64(decoded);
      const res = await fetch("/api/swooz-voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          persona_id: activeStudioPersonaId,
          slot_id: slotId,
          wav_base64: wavB64,
          custom_line: customLineText !== undefined ? customLineText : undefined,
        }),
      });
      if (res.ok) {
        const manifest = await res.json();
        renderSwoozManifest(manifest);
        if (manifest.persona_id) activatePersonaSelection(manifest.persona_id);
        speakEngineer(customLineText || scriptText || "Voice clip locked!", "CRITICAL", slotId);
      }
    }

    async function toggleSlotRecord(slotId, scriptText, customLineText) {
      if (studioRec && studioRecSlot === slotId) {
        studioRec.stop();
        return;
      }
      if (studioRec) {
        try { studioRec.stop(); } catch (_) {}
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: false,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1,
          },
        });
        studioStream = stream;
        studioRecSlot = slotId;
        studioRecChunks = [];
        const mr = new MediaRecorder(stream);
        studioRec = mr;
        mr.ondataavailable = (ev) => {
          if (ev.data && ev.data.size > 0) studioRecChunks.push(ev.data);
        };
        mr.onstop = async () => {
          const finishedSlot = studioRecSlot;
          studioRec = null;
          studioRecSlot = null;
          if (studioStream) {
            studioStream.getTracks().forEach((tr) => tr.stop());
            studioStream = null;
          }
          try {
            const liveInputVal = swSlotsEl?.querySelector(`input[data-sw-spin="${finishedSlot}"]`)?.value;
            const blob = new Blob(studioRecChunks, { type: mr.mimeType || "audio/webm" });
            const ab = await blob.arrayBuffer();
            await saveDecodedSlotAudio(finishedSlot, ab, scriptText, liveInputVal ?? customLineText);
          } catch (_) {
            loadSwoozStudio(activeStudioPersonaId);
          }
        };
        mr.start();
        loadSwoozStudio(activeStudioPersonaId);
      } catch (_) {}
    }

    if (btnSwOpen && swModal) {
      btnSwOpen.addEventListener("click", () => {
        swModal.style.display = "flex";
        const startPid = voiceConfig.voice.startsWith("custom-") ? voiceConfig.voice : activeStudioPersonaId;
        loadSwoozStudio(startPid);
      });
    }
    if (btnSwClose && swModal) {
      btnSwClose.addEventListener("click", () => {
        if (studioRec) { try { studioRec.stop(); } catch (_) {} }
        swModal.style.display = "none";
      });
      swModal.addEventListener("click", (e) => {
        if (e.target === swModal) {
          if (studioRec) { try { studioRec.stop(); } catch (_) {} }
          swModal.style.display = "none";
        }
      });
    }
    if (selStudioPersona) {
      selStudioPersona.addEventListener("change", () => {
        loadSwoozStudio(selStudioPersona.value);
      });
    }
    if (btnNewPersona) {
      btnNewPersona.addEventListener("click", async () => {
        const rawName = window.prompt("Name your new Pit Wall Voice Persona (e.g. 'CREW CHIEF · MIKE' or 'SARAH · GT'):", "MY CREW CHIEF");
        if (!rawName || !rawName.trim()) return;
        const res = await fetch("/api/swooz-voice", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "save_persona",
            persona: { name: rawName.trim(), base_voice: "Mark", pitch_pct: 0, rate_offset: 3, detune: 0 },
          }),
        });
        if (res.ok) {
          const manifest = await res.json();
          renderSwoozManifest(manifest);
          activatePersonaSelection(manifest.persona_id);
        }
      });
    }
    if (btnSavePersonaMeta) {
      btnSavePersonaMeta.addEventListener("click", async () => {
        const persona = {
          id: activeStudioPersonaId,
          name: document.getElementById("inp-persona-name")?.value || "Custom Crew",
          base_voice: document.getElementById("sel-persona-base-voice")?.value || "Mark",
          pitch_pct: Number(document.getElementById("inp-persona-pitch")?.value || 0),
          detune: Number(document.getElementById("inp-persona-detune")?.value || 0),
        };
        const res = await fetch("/api/swooz-voice", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "save_persona", persona }),
        });
        if (res.ok) {
          const manifest = await res.json();
          renderSwoozManifest(manifest);
          activatePersonaSelection(manifest.persona_id);
          speakEngineer(PERSONA_TEST_LINES[manifest.persona_id], "CRITICAL", "radio_check");
        }
      });
    }
    if (btnExportPersona) {
      btnExportPersona.addEventListener("click", () => {
        window.location.href = `/api/personas/export?persona_id=${encodeURIComponent(activeStudioPersonaId)}`;
      });
    }
    if (inpImportZip) {
      inpImportZip.addEventListener("change", async () => {
        if (!inpImportZip.files || !inpImportZip.files[0]) return;
        try {
          const ab = await inpImportZip.files[0].arrayBuffer();
          const res = await fetch("/api/personas/import", {
            method: "POST",
            headers: { "Content-Type": "application/zip" },
            body: ab,
          });
          if (res.ok) {
            const manifest = await res.json();
            renderSwoozManifest(manifest);
            activatePersonaSelection(manifest.persona_id);
          }
        } catch (_) {}
        inpImportZip.value = "";
      });
    }
    if (btnDelPersona) {
      btnDelPersona.addEventListener("click", async () => {
        if (!activeStudioPersonaId) return;
        if (!window.confirm("Delete this custom voice persona and its recorded clips?")) return;
        const res = await fetch("/api/swooz-voice", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "delete_persona", persona_id: activeStudioPersonaId }),
        });
        if (res.ok) {
          const manifest = await res.json();
          renderSwoozManifest(manifest);
          activatePersonaSelection(manifest.persona_id || "en-GB-SoniaNeural");
        }
      });
    }
    if (btnSwUse) {
      btnSwUse.addEventListener("click", () => {
        if (!activeStudioPersonaId) return;
        activatePersonaSelection(activeStudioPersonaId);
        speakEngineer(PERSONA_TEST_LINES[activeStudioPersonaId] || PERSONA_TEST_LINES["en-GB-SoniaNeural"], "CRITICAL", "radio_check");
      });
    }
    if (swSlotsEl) {
      swSlotsEl.addEventListener("click", async (e) => {
        const saveLineBtn = e.target.closest("[data-sw-saveline]");
        if (saveLineBtn) {
          const sid = saveLineBtn.dataset.swSaveline;
          const spinInput = swSlotsEl.querySelector(`input[data-sw-spin="${sid}"]`);
          const res = await fetch("/api/swooz-voice", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "save_line",
              persona_id: activeStudioPersonaId,
              slot_id: sid,
              custom_line: spinInput ? spinInput.value : "",
            }),
          });
          if (res.ok) renderSwoozManifest(await res.json());
          return;
        }
        const delBtn = e.target.closest("[data-sw-del]");
        if (delBtn) {
          const sid = delBtn.dataset.swDel;
          const res = await fetch("/api/swooz-voice", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "delete_wav", persona_id: activeStudioPersonaId, slot_id: sid }),
          });
          if (res.ok) renderSwoozManifest(await res.json());
          return;
        }
        const recBtn = e.target.closest("[data-sw-rec]");
        if (recBtn) {
          const sid = recBtn.dataset.swRec;
          const spinVal = swSlotsEl.querySelector(`input[data-sw-spin="${sid}"]`)?.value || "";
          const playRef = swSlotsEl.querySelector(`[data-sw-play="${sid}"]`)?.dataset?.swScript || "";
          toggleSlotRecord(sid, playRef, spinVal);
          return;
        }
        const playBtn = e.target.closest("[data-sw-play]");
        if (playBtn) {
          const sid = playBtn.dataset.swPlay;
          const spinVal = swSlotsEl.querySelector(`input[data-sw-spin="${sid}"]`)?.value?.trim();
          const sc = spinVal || playBtn.dataset.swScript || "Radio check!";
          if (activeStudioPersonaId) activatePersonaSelection(activeStudioPersonaId);
          speakEngineer(sc, "CRITICAL", sid);
        }
      });
      swSlotsEl.addEventListener("keydown", async (e) => {
        if (e.key === "Enter" && e.target.matches("input[data-sw-spin]")) {
          e.preventDefault();
          const sid = e.target.dataset.swSpin;
          const btn = swSlotsEl.querySelector(`[data-sw-saveline="${sid}"]`);
          if (btn) btn.click();
        }
      });
      swSlotsEl.addEventListener("change", async (e) => {
        const fileIn = e.target.closest("input[data-sw-file]");
        if (fileIn && fileIn.files && fileIn.files[0]) {
          const sid = fileIn.dataset.swFile;
          const spinVal = swSlotsEl.querySelector(`input[data-sw-spin="${sid}"]`)?.value || "";
          const playRef = swSlotsEl.querySelector(`[data-sw-play="${sid}"]`)?.dataset?.swScript || "";
          const ab = await fileIn.files[0].arrayBuffer();
          await saveDecodedSlotAudio(sid, ab, playRef, spinVal);
        }
      });
    }

    // Tactical Push Profile & Auto-Card Build Archetype Selector Chips
    document.querySelectorAll(".pp-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const prof = chip.dataset.pprof;
        sendAction({ action: "set_copilot", key: "push_profile", value: prof });
      });
    });
    document.querySelectorAll(".cs-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const cs = chip.dataset.cstrat;
        sendAction({ action: "set_copilot", key: "card_strategy", value: cs });
      });
    });

    // Continuous Hold Keepalive Helper (for holding PUSH button or SPACEBAR -> Hold Both Boosts!)
    function startContinuousBothHold(source) {
      if (source === "space") spaceHoldActive = true;
      if (source === "btn") btnHoldActive = true;
      sendAction({ action: "manual_boost", profile: "k1_super", hold: true, active: true });
      if (!holdKeepaliveTimer) {
        holdKeepaliveTimer = setInterval(() => {
          if (spaceHoldActive || btnHoldActive) {
            sendAction({ action: "manual_boost", profile: "k1_super", hold: true, active: true });
          } else {
            clearInterval(holdKeepaliveTimer);
            holdKeepaliveTimer = null;
          }
        }, 4000);
      }
    }

    function stopContinuousBothHold(source) {
      if (source === "space") spaceHoldActive = false;
      if (source === "btn") btnHoldActive = false;
      if (!spaceHoldActive && !btnHoldActive) {
        if (holdKeepaliveTimer) {
          clearInterval(holdKeepaliveTimer);
          holdKeepaliveTimer = null;
        }
        sendAction({ action: "manual_boost", active: false });
      }
    }

    // Dark Recessed PUSH Switch: Quick Tap = Selected Tactical Push Profile | Press & Hold = Continuous Both Boosts!
    const pushBtn = document.getElementById("btn-boost-pulse");
    let holdPromoteTimer = null;
    if (pushBtn) {
      pushBtn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        btnPressDownMs = performance.now();
        if (holdPromoteTimer) clearTimeout(holdPromoteTimer);
        holdPromoteTimer = setTimeout(() => {
          startContinuousBothHold("btn");
        }, 220);
      });
      const endBtnPress = () => {
        if (holdPromoteTimer) {
          clearTimeout(holdPromoteTimer);
          holdPromoteTimer = null;
        }
        if (btnHoldActive) {
          stopContinuousBothHold("btn");
        } else if (btnPressDownMs > 0) {
          btnPressDownMs = 0;
          const prof = snap?.copilot?.push_profile || "k1_super";
          pushLedUntil = performance.now() + 2800;
          sendAction({ action: "manual_boost", profile: prof, active: true, toggle_if_active: true });
        }
      };
      pushBtn.addEventListener("pointerup", endBtnPress);
      pushBtn.addEventListener("pointercancel", endBtnPress);
      pushBtn.addEventListener("pointerleave", () => {
        if (btnHoldActive) stopContinuousBothHold("btn");
        btnPressDownMs = 0;
        if (holdPromoteTimer) { clearTimeout(holdPromoteTimer); holdPromoteTimer = null; }
      });
    }

    // Camera Buttons
    document.querySelectorAll("button[data-cam]").forEach((btn) => {
      btn.addEventListener("click", () => sendAction({ action: "set_camera", camera: btn.dataset.cam }));
    });

    document.getElementById("btn-send-ping").addEventListener("click", () => sendAction({ action: "ping" }));
    document.getElementById("btn-refresh-results").addEventListener("click", loadDebriefArchive);

    // Unlock iOS Safari Web Audio on first touch
    document.addEventListener("touchstart", () => {
      try { ensureAudioCtx(); } catch (_) {}
    }, { once: true, passive: true });

    // Mobile QR · 2P Co-Op Crew Chief · Transparent OBS Stream Hub Modal & Public Lobby Controls
    document.getElementById("btn-pub-lobby")?.addEventListener("click", () => {
      if (snap?.connection?.simulated) {
        sendAction({ action: "set_sim_public", public_lobby: !snap?.public_suite?.public_lobby_locked });
      } else {
        sendAction({ action: "set_copilot", key: "public_spotter", value: !snap?.copilot?.public_spotter });
      }
    });
    document.getElementById("btn-tv-director")?.addEventListener("click", () => {
      activateDeck("spy");
      sendAction({ action: "set_copilot", key: "tv_director", value: !snap?.copilot?.tv_director });
    });

    const qrModal = document.getElementById("qr-modal");
    const btnIphone = document.getElementById("btn-iphone-share");
    const btnCloseQr = document.getElementById("btn-close-qr");
    let hubLinks = {
      mobile: location.origin + location.pathname,
      crew: `${location.origin}${location.pathname}?role=crew`,
      obs: `${location.origin}${location.pathname}?obs=1`,
    };
    let activeHubMode = "mobile";

    const updateHubModalUI = () => {
      const targetUrl = hubLinks[activeHubMode] || hubLinks.mobile;
      const urlLbl = document.getElementById("qr-url-lbl");
      const qrImg = document.getElementById("qr-img");
      if (urlLbl) urlLbl.textContent = targetUrl;
      if (qrImg) qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(targetUrl)}`;
      document.querySelectorAll("[data-hub-mode]").forEach((b) => {
        b.classList.toggle("active", b.dataset.hubMode === activeHubMode);
      });
    };

    if (btnIphone && qrModal) {
      btnIphone.addEventListener("click", async () => {
        try {
          const r = await fetch("./api/lan-info");
          if (r.ok) {
            const d = await r.json();
            if (d.lan_url) {
              hubLinks = {
                mobile: d.lan_url,
                crew: d.crew_url || `${d.lan_url}/?role=crew`,
                obs: d.obs_url || "http://127.0.0.1:8765/?obs=1",
              };
            }
            const descEl = document.getElementById("qr-hub-desc");
            if (descEl && d.lan_ip) {
              const srcTxt = d.telemetry_source_ip ? `${d.telemetry_source_ip}:${d.command_port || 29771} (LIVE)` : `${d.cmd_host || "127.0.0.1"}:${d.command_port || 29771} (Auto)`;
              descEl.innerHTML =
                `<strong>Phones, Foldables &amp; Tablets:</strong> Open <code>${d.lan_url}</code> (or scan QR). Auto-adapts layout or tap <b>AUTO</b> in top bar.<br>` +
                `<strong>Remote Console / Handheld -> PitWall:</strong> Set <em>Telemetry Out</em> to <code>${d.lan_ip}:${d.telemetry_port || 29770}</code> &middot; Commands auto-lock: <code>${srcTxt}</code>`;
            }
          }
        } catch (_) {}
        updateHubModalUI();
        qrModal.style.display = "flex";
      });
    }
    document.querySelectorAll("[data-hub-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeHubMode = btn.dataset.hubMode || "mobile";
        updateHubModalUI();
      });
    });
    document.getElementById("btn-copy-hub-url")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const txt = document.getElementById("qr-url-lbl")?.textContent || "";
      try {
        await navigator.clipboard.writeText(txt);
        btn.textContent = "✓ COPIED!";
        setTimeout(() => { btn.textContent = "COPY URL"; }, 1400);
      } catch (_) {}
    });
    document.getElementById("btn-preview-crew")?.addEventListener("click", () => {
      crewRoleActive = !crewRoleActive;
      obsOverlayActive = false;
      applySpecialRoleModes();
      if (qrModal) qrModal.style.display = "none";
    });
    document.getElementById("btn-preview-obs")?.addEventListener("click", () => {
      obsOverlayActive = true;
      applySpecialRoleModes();
      if (qrModal) qrModal.style.display = "none";
      if (snap) renderAll();
    });
    document.getElementById("btn-exit-obs")?.addEventListener("click", () => {
      obsOverlayActive = false;
      applySpecialRoleModes();
      if (snap) renderAll();
    });
    if (btnCloseQr && qrModal) {
      btnCloseQr.addEventListener("click", () => { qrModal.style.display = "none"; });
      qrModal.addEventListener("click", (e) => { if (e.target === qrModal) qrModal.style.display = "none"; });
    }

    // 2P Co-Op Crew Chief Live Callout Buttons & Custom Transmit
    document.querySelectorAll(".ccd-btn[data-crew-call]").forEach((btn) => {
      btn.addEventListener("click", () => {
        sendAction({ action: "crew_callout", sender: "Crew Chief", message: btn.dataset.crewCall });
      });
    });
    const sendCustomCrewMsg = () => {
      const inp = document.getElementById("inp-crew-custom");
      const val = inp?.value?.trim();
      if (!val) return;
      sendAction({ action: "crew_callout", sender: "Crew Chief", message: val });
      inp.value = "";
    };
    document.getElementById("btn-send-crew-custom")?.addEventListener("click", sendCustomCrewMsg);
    document.getElementById("inp-crew-custom")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendCustomCrewMsg();
      }
    });

    // Tab 5: SWOOZ Open GP League Leaderboard & Discord Webhook Controls
    document.getElementById("btn-refresh-league")?.addEventListener("click", loadOpenGpLeague);
    document.getElementById("btn-league-humans")?.addEventListener("click", (e) => {
      leagueHumansOnly = !leagueHumansOnly;
      e.currentTarget.textContent = leagueHumansOnly ? "FILTER: HUMANS ONLY" : "FILTER: ALL DRIVERS";
      e.currentTarget.classList.toggle("active", leagueHumansOnly);
      loadOpenGpLeague();
    });
    const postLeagueAction = async (actName) => {
      const lName = document.getElementById("inp-league-name")?.value?.trim();
      const whUrl = document.getElementById("inp-discord-webhook")?.value?.trim();
      const payload = { action: actName };
      if (lName) payload.league_name = lName;
      if (whUrl) payload.discord_webhook_url = whUrl;
      try {
        const res = await fetch("./api/league", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        const stEl = document.getElementById("league-discord-status");
        if (stEl && data.toast) stEl.textContent = data.toast;
        loadOpenGpLeague();
      } catch (_) {
        const stEl = document.getElementById("league-discord-status");
        if (stEl) stEl.textContent = "Run local Desktop App to save Discord Webhook";
      }
    };
    document.getElementById("btn-save-league-cfg")?.addEventListener("click", () => postLeagueAction("save_config"));
    document.getElementById("btn-test-discord")?.addEventListener("click", () => postLeagueAction("test_discord"));

    // Zero-Alt-Tab Ribbon Pills & Floating Mini-HUD Controls
    document.getElementById("btn-game-refocus")?.addEventListener("click", () => {
      sendAction({ action: "set_overlay", key: "game_refocus", value: !snap?.overlay?.game_refocus });
    });
    document.getElementById("btn-global-keys")?.addEventListener("click", () => {
      sendAction({ action: "set_overlay", key: "global_hotkeys", value: !snap?.overlay?.global_hotkeys });
    });
    document.getElementById("btn-pin-top")?.addEventListener("click", () => {
      sendAction({ action: "set_overlay", key: "pin_top", value: !snap?.overlay?.pin_top });
    });
    document.getElementById("btn-mini-hud")?.addEventListener("click", () => {
      sendAction({ action: "set_overlay", key: "mini_hud", value: !snap?.overlay?.mini_hud });
    });
    document.getElementById("btn-exit-mini-hud")?.addEventListener("click", () => {
      sendAction({ action: "set_overlay", key: "mini_hud", value: false });
    });
    const triggerExtremeAiToggle = () => {
      sendAction({ action: "set_preset", preset: "extreme_ai", active: !snap?.copilot?.extreme_ai_sync });
    };
    document.getElementById("btn-extreme-ai")?.addEventListener("click", triggerExtremeAiToggle);
    document.getElementById("ai-net-badge")?.addEventListener("click", triggerExtremeAiToggle);
    document.getElementById("mh-btn-push")?.addEventListener("click", () => {
      const prof = snap?.copilot?.push_profile || "k1_super";
      pushLedUntil = performance.now() + 2800;
      sendAction({ action: "manual_boost", profile: prof, active: true, toggle_if_active: true });
    });
    document.getElementById("mh-btn-box")?.addEventListener("click", () => {
      sendAction({ action: "set_pit", pit: !snap?.pit?.pit_planned });
    });
    document.getElementById("mh-btn-autocard")?.addEventListener("click", () => {
      sendAction({ action: "set_copilot", key: "auto_card", value: !snap?.copilot?.auto_card });
    });
    document.getElementById("mh-btn-autotire")?.addEventListener("click", () => {
      sendAction({ action: "set_copilot", key: "auto_tire", value: !snap?.copilot?.auto_tire });
    });
    document.getElementById("mh-btn-pitguard")?.addEventListener("click", () => {
      sendAction({ action: "set_copilot", key: "auto_pit", value: !snap?.copilot?.auto_pit });
    });
    document.getElementById("mh-btn-mic")?.addEventListener("click", () => {
      toggleVoiceMic();
    });
    document.getElementById("mh-cards-strip")?.addEventListener("click", (e) => {
      const pill = e.target.closest("[data-mhpick]");
      if (pill) sendAction({ action: "pick_card", index: Number(pill.dataset.mhpick) });
    });

    // Zero-Alt-Tab Instant Game Refocus: Clicking any race switch/button hands focus back to Backseat Champions (~35ms)
    document.addEventListener("click", (e) => {
      if (snap?.overlay?.game_refocus === false || btnHoldActive) return;
      const anyModalOpen = ["loadout-studio-modal", "swooz-studio-modal", "voice-help-modal", "qr-modal"].some((id) => {
        const m = document.getElementById(id);
        return m && m.style.display === "flex";
      });
      if (anyModalOpen) return;
      if (e.target.closest("select, input, textarea, .qr-modal-card")) return;
      const hit = e.target.closest("button, .metal-knob, .pace-btn, .pp-chip, .cs-chip, .fia-row");
      if (!hit) return;
      const skipIds = new Set([
        "btn-loadout-studio", "btn-swooz-studio", "btn-voice-help", "btn-iphone-share",
        "btn-game-refocus", "btn-global-keys", "btn-pin-top", "btn-exit-mini-hud",
      ]);
      if (hit.id && skipIds.has(hit.id)) return;
      setTimeout(() => sendAction({ action: "refocus_game" }), 35);
    });

    // Hotkeys: SPACE = Hold Both Boosts (Super Boost), P / F5 / Num0 = Tactical Push, Q/E = Speed/Corner Boost,
    // B / F6 / Num. = Box Toggle, F7 / Num7 = Auto Card, F8 / Num8 = Sitrep, Num1-3 = Pick Card, Num9 = Mini-HUD!
    window.addEventListener("keydown", (e) => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (!e.repeat && !spaceHoldActive) startContinuousBothHold("space");
        return;
      }
      if (e.repeat) return;
      const code = e.code || "";
      const k = (e.key || "").toLowerCase();
      if (code === "F5" || code === "Numpad0") {
        e.preventDefault();
        const prof = snap?.copilot?.push_profile || "k1_super";
        pushLedUntil = performance.now() + 2800;
        sendAction({ action: "manual_boost", profile: prof, active: true, toggle_if_active: true });
        return;
      }
      if (code === "F6" || code === "NumpadDecimal") {
        e.preventDefault();
        sendAction({ action: "set_pit", pit: !snap?.pit?.pit_planned });
        return;
      }
      if (code === "F7" || code === "Numpad7") {
        e.preventDefault();
        sendAction({ action: "set_copilot", key: "auto_card", value: !snap?.copilot?.auto_card });
        return;
      }
      if (code === "F8" || code === "Numpad8") {
        e.preventDefault();
        sendAction({ action: "test_radio" });
        return;
      }
      if (code === "Numpad1" || code === "Numpad2" || code === "Numpad3") {
        e.preventDefault();
        sendAction({ action: "pick_card", index: Number(code.slice(-1)) - 1 });
        return;
      }
      if (code === "Numpad4") {
        e.preventDefault();
        const order = ["conserve", "balanced", "attack", "hammer"];
        const cur = snap?.copilot?.pace_mode || "balanced";
        sendAction({ action: "set_copilot", key: "pace_mode", value: order[(order.indexOf(cur) + 1) % 4] });
        return;
      }
      if (code === "Numpad5") {
        e.preventDefault();
        sendAction({ action: "set_copilot", key: "auto_tire", value: !snap?.copilot?.auto_tire });
        return;
      }
      if (code === "Numpad6") {
        e.preventDefault();
        sendAction({ action: "set_copilot", key: "auto_pit", value: !snap?.copilot?.auto_pit });
        return;
      }
      if (code === "Numpad9") {
        e.preventDefault();
        sendAction({ action: "set_overlay", key: "mini_hud", value: !snap?.overlay?.mini_hud });
        return;
      }
      if (k === "t") {
        sendAction({ action: "test_radio" });
      } else if (k === "v") {
        toggleVoiceMic();
      } else if (k === "p") {
        const prof = snap?.copilot?.push_profile || "k1_super";
        pushLedUntil = performance.now() + 2800;
        sendAction({ action: "manual_boost", profile: prof, active: true, toggle_if_active: true });
      } else if (k === "q") {
        pushLedUntil = performance.now() + 2000;
        sendAction({ action: "manual_boost", speed: true, cornering: false, party: false, duration_s: 2.0 });
      } else if (k === "e") {
        pushLedUntil = performance.now() + 2000;
        sendAction({ action: "manual_boost", speed: false, cornering: true, party: false, duration_s: 2.0 });
      } else if (k === "b") {
        const curPit = Boolean(snap?.pit?.pit_planned);
        sendAction({ action: "set_pit", pit: !curPit });
      } else if (k === "?" || (k === "/" && e.shiftKey)) {
        const vhm = document.getElementById("voice-help-modal");
        if (vhm) vhm.style.display = vhm.style.display === "flex" ? "none" : "flex";
      } else if (k === "escape") {
        const vhm = document.getElementById("voice-help-modal");
        if (vhm) vhm.style.display = "none";
      } else if (k === "1") {
        sendAction({ action: "set_copilot", key: "pace_mode", value: "conserve" });
      } else if (k === "2") {
        sendAction({ action: "set_copilot", key: "pace_mode", value: "balanced" });
      } else if (k === "3") {
        sendAction({ action: "set_copilot", key: "pace_mode", value: "attack" });
      } else if (k === "4") {
        sendAction({ action: "set_copilot", key: "pace_mode", value: "hammer" });
      }
    });

    window.addEventListener("keyup", (e) => {
      if (e.code === "Space" && spaceHoldActive) {
        e.preventDefault();
        stopContinuousBothHold("space");
      }
    });
    window.addEventListener("blur", () => {
      if (spaceHoldActive) stopContinuousBothHold("space");
      if (btnHoldActive) stopContinuousBothHold("btn");
    });
  }

  initShiftLights();
  applyDeviceMode();
  applySpecialRoleModes();
  bindEvents();
  if (typeof window.updateVoiceBarUI === "function") window.updateVoiceBarUI();
  connectWS();
  requestAnimationFrame(drawRadioWaveformLoop);

  // Auto-arm Hands-Free Voice Mic on Desktop launch (remembers preference; Android uses explicit clean 1-tap PTT)
  setTimeout(() => {
    try {
      const isAnd = /Android/i.test(navigator.userAgent || "");
      const savedMic = localStorage.getItem("bc_mic_auto");
      const isLocalApp = location.hostname === "127.0.0.1" || location.hostname === "localhost";
      if (!isAnd && !micEnabled && (savedMic === "1" || (savedMic === null && isLocalApp))) {
        toggleVoiceMic();
      }
    } catch (_) {}
  }, 420);
})();
