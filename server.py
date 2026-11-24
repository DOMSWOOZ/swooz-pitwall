"""Zero-dependency asyncio server for Backseat Champions F1 Pit Wall.

- UDP Telemetry In:    127.0.0.1:29770
- UDP Commands Out/In: 127.0.0.1:29771
- Web UI + WebSocket:  http://127.0.0.1:8765  (ws://127.0.0.1:8765/ws)
- Race Results Upload: http://127.0.0.1:8765/race-results
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import datetime
import ctypes
import glob
import hashlib
import io
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.parse
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import edge_tts
except ImportError:
    edge_tts = None  # type: ignore[assignment]

import bc_api
import loadout_manager
import public_suite
import swooz_persona
from engine import TelemetryEngine, human_speech
from simulator import DemoRaceSimulator

# 100% Local Zero-Latency WinRT OneCore Persona Profiles (routed into Web Audio 90s V10 / F1 Pit FX + Waveform!)
LOCAL_VOICE_PROFILES: Dict[str, Dict[str, Any]] = {
    "en-GB-SoniaNeural": {  # UK · HANNAH (STRATEGY) — Crisp British Strategy Female
        "voice": "Zira",
        "pitch_pct": 5,
        "rate_offset": 4,
        "contour": "(0%,+4%) (45%,+8%) (80%,+3%) (100%,-2%)",
    },
    "en-GB-RyanNeural": {   # UK · BONO (RYAN) — Upbeat Trackside Male
        "voice": "Mark",
        "pitch_pct": 2,
        "rate_offset": 3,
        "contour": "(0%,+3%) (50%,+6%) (100%,-3%)",
    },
    "en-GB-ThomasNeural": { # UK · GP (THOMAS) — Calm Dry Baritone
        "voice": "David",
        "pitch_pct": -4,
        "rate_offset": 0,
        "contour": "(0%,+1%) (60%,+2%) (100%,-5%)",
    },
    "it-IT-GiuseppeMultilingualNeural": {  # IT · MARANELLO (GIUSEPPE)
        "voice": "Mark",
        "pitch_pct": 8,
        "rate_offset": 6,
        "contour": "(0%,+6%) (35%,+14%) (70%,+4%) (100%,+8%)",
    },
    "fr-FR-RemyMultilingualNeural": {      # FR · ENSTONE (REMY)
        "voice": "Mark",
        "pitch_pct": 4,
        "rate_offset": 2,
        "contour": "(0%,+0%) (65%,+7%) (100%,+4%)",
    },
    "en-AU-WilliamMultilingualNeural": {   # AU · MELBOURNE (WILL)
        "voice": "Mark",
        "pitch_pct": -2,
        "rate_offset": 5,
        "contour": "(0%,+2%) (50%,+5%) (100%,+3%)",
    },
    "en-IE-ConnorNeural": {                # IE · SILVERSTONE (CONNOR)
        "voice": "Mark",
        "pitch_pct": 6,
        "rate_offset": 4,
        "contour": "(0%,+5%) (55%,+9%) (100%,-1%)",
    },
    "en-US-ChristopherNeural": {           # US · CREW CHIEF
        "voice": "David",
        "pitch_pct": -9,
        "rate_offset": 2,
        "contour": "(0%,+2%) (55%,+3%) (100%,-6%)",
    },
    "en-US-AriaNeural": {                  # US · ATLAS AI
        "voice": "Zira",
        "pitch_pct": -2,
        "rate_offset": 7,
        "contour": "(0%,+0%) (50%,+1%) (100%,+0%)",
    },
    "offline-zira": {                      # LOCAL · ZIRA
        "voice": "Zira",
        "pitch_pct": 0,
        "rate_offset": 0,
        "contour": "",
    },
    "offline-david": {                     # LOCAL · DAVID
        "voice": "David",
        "pitch_pct": 0,
        "rate_offset": 0,
        "contour": "",
    },
}

_WINRT_DAEMON_PS = r"""
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$voices = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
Write-Output "READY"
[Console]::Out.Flush()

while ($null -ne ($line = [Console]::In.ReadLine())) {
    try {
        $req = $line | ConvertFrom-Json
        $target = $req.voice
        $v = $voices | Where-Object { $_.DisplayName -match $target } | Select-Object -First 1
        if ($null -ne $v) { $synth.Voice = $v }
        $contourAttr = ""
        if ($req.contour) { $contourAttr = " contour='" + $req.contour + "'" }
        $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'><prosody rate='" + $req.rate + "' pitch='" + $req.pitch + "'" + $contourAttr + ">" + [System.Security.SecurityElement]::Escape($req.text) + "</prosody></speak>"
        $stream = Await ($synth.SynthesizeSsmlToStreamAsync($ssml)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
        $size = [int]$stream.Size
        $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
        $null = Await ($reader.LoadAsync($size)) ([uint32])
        $bytes = New-Object byte[] $size
        $reader.ReadBytes($bytes)
        $reader.Dispose()
        $stream.Dispose()
        Write-Output ("OK:" + [Convert]::ToBase64String($bytes))
    } catch {
        Write-Output ("ERR:" + $_.Exception.Message)
    }
    [Console]::Out.Flush()
}
"""

PREWARM_RACE_PHRASES = tuple(
    [
        "In the pit lane, limiter active.",
        "Rain on track — Wet tires optimal!",
        "Track drying — Slicks optimal!",
        "Critical tires, 15 percent — box, box, box!",
        "Tires 25 percent — recommend boxing soon!",
        "Tires 25 percent — box confirmed this lap.",
        "K1 Super Boost — holding both boosts!",
        "Straight-line Slingshot armed!",
        "Apex Corner-Exit Grip boost engaged!",
        "Full-sector Overtake Dump engaged!",
        "Super Boost deployed!",
        "Copy that — holding grid launch! Lights out and away we go!",
    ]
    + [f"Tire menu open — recommend {c} compound." for c in bc_api.COMPOUNDS]
    + [f"Pit exit clear! Fresh {c} tires on at 100 percent — push now!" for c in bc_api.COMPOUNDS]
    + [human_speech(f"Upgrade ready — top call is {u}.") for u in bc_api.UPGRADES]
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "static")
RESULTS_DIR = os.path.join(ROOT_DIR, "race-results")
TTS_DISK_DIR = os.path.join(ROOT_DIR, ".tts-cache")
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def disable_windows_udp_connreset(sock: socket.socket) -> None:
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass


_SPACE_HOLD_LOCK = threading.Lock()
_GAME_EXES = {"backseatchampions.exe", "backseat champions.exe"}


def _has_interactive_desktop() -> bool:
    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        if u32.GetForegroundWindow():
            return True
        cnt = [0]
        CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(_h: int, _l: int) -> bool:
            cnt[0] += 1
            return False

        u32.EnumWindows(CB(_cb), 0)
        return cnt[0] > 0
    except Exception:
        return False


def _find_backseat_hwnd() -> Tuple[bool, Optional[int]]:
    """Returns (game_process_running, game_window_hwnd)."""
    if sys.platform != "win32":
        return (False, None)
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    game_pids: Set[int] = set()
    snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap and snap != wintypes.HANDLE(-1).value:
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                while True:
                    if entry.szExeFile.lower() in _GAME_EXES:
                        game_pids.add(int(entry.th32ProcessID))
                    if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snap)

    if not game_pids:
        return (False, None)

    found_hwnd: List[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in game_pids and user32.GetWindowTextLengthW(hwnd) > 0:
            found_hwnd.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return (True, found_hwnd[0] if found_hwnd else None)


def hold_game_spacebar(duration_s: float = 2.2) -> str:
    """Focuses Backseat Champions on Windows and holds [SPACE] via 64-bit SendInput.
    Returns 'held', 'headless', or 'no_game'.
    """
    proc_running, hwnd = _find_backseat_hwnd()
    if not proc_running:
        return "no_game"
    if not hwnd:
        return "headless"

    def _worker() -> None:
        if not _SPACE_HOLD_LOCK.acquire(blocking=False):
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            class HARDWAREINPUT(ctypes.Structure):
                _fields_ = [
                    ("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD),
                ]

            class _INPUTunion(ctypes.Union):
                _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

            class INPUT(ctypes.Structure):
                _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

            VK_SPACE = 0x20
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            SW_RESTORE = 9
            scan_space = int(user32.MapVirtualKeyW(VK_SPACE, 0)) or 0x39

            def _send_key(vk: int, scan: int, flags: int) -> None:
                inp = INPUT()
                inp.type = 1  # INPUT_KEYBOARD
                inp.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

            # Bring Backseat Champions window cleanly to foreground
            fg_hwnd = user32.GetForegroundWindow()
            cur_tid = kernel32.GetCurrentThreadId()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            attached = False
            try:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                if fg_hwnd != hwnd:
                    if fg_tid and fg_tid != cur_tid:
                        attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
                    _send_key(VK_MENU, 0, KEYEVENTF_KEYUP)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_tid, cur_tid, False)

            time.sleep(0.10)

            # Hold SPACE continuously (initial press + hardware repeat pulses) and guarantee release
            try:
                _send_key(VK_SPACE, scan_space, 0)
                end_t = time.monotonic() + max(0.6, min(4.0, duration_s))
                while time.monotonic() < end_t:
                    time.sleep(0.08)
                    _send_key(VK_SPACE, scan_space, 0)
            finally:
                _send_key(VK_SPACE, scan_space, KEYEVENTF_KEYUP)
        except Exception:
            pass
        finally:
            _SPACE_HOLD_LOCK.release()

    threading.Thread(target=_worker, daemon=True).start()
    return "held"


def _get_backseat_pids() -> Set[int]:
    """Fast Win32 snapshot returning active BackseatChampions.exe PIDs."""
    if sys.platform != "win32":
        return set()
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    pids: Set[int] = set()
    snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap and snap != wintypes.HANDLE(-1).value:
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                while True:
                    if entry.szExeFile.lower() in _GAME_EXES:
                        pids.add(int(entry.th32ProcessID))
                    if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snap)
    return pids


def _focus_hwnd_instant(hwnd: int) -> None:
    """Hands keyboard/controller focus back to hwnd (~10ms) without minimizing Borderless games."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd == hwnd:
            return
        cur_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
        attached = False
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            if fg_tid and fg_tid != cur_tid:
                attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
            user32.BringWindowToTop(hwnd)
            if not user32.SetForegroundWindow(hwnd):
                # Fallback synthetic ALT keyup to satisfy Win32 foreground lock
                user32.keybd_event(0x12, 0, 0x0002, 0)
                user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_tid, cur_tid, False)
    except Exception:
        pass


def refocus_game_async() -> bool:
    """If BackseatChampions.exe has a visible window, immediately returns focus to it on a daemon thread."""
    proc_running, hwnd = _find_backseat_hwnd()
    if not proc_running or not hwnd:
        return False
    threading.Thread(target=_focus_hwnd_instant, args=(hwnd,), daemon=True).start()
    return True


def _find_pitwall_hwnd() -> Optional[int]:
    """Finds the visible SWOOZ PitWall desktop app/browser window."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: List[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        ln = user32.GetWindowTextLengthW(hwnd)
        if ln <= 0:
            return True
        buf = ctypes.create_unicode_buffer(ln + 1)
        user32.GetWindowTextW(hwnd, buf, ln + 1)
        title = buf.value.lower()
        if "swooz pitwall" in title or "backseat pitwall" in title:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found[0] if found else None


def apply_pitwall_window_mode(
    pin_top: bool,
    mini_hud: bool,
    prev_geom: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Applies Always-on-Top (HWND_TOPMOST) and/or single-monitor Compact Mini-HUD bar geometry."""
    if sys.platform != "win32":
        return prev_geom
    pw_hwnd = _find_pitwall_hwnd()
    if not pw_hwnd:
        return prev_geom
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            ctypes.c_ssize_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040

        if mini_hud:
            saved = prev_geom
            if saved is None:
                was_zoomed = bool(user32.IsZoomed(pw_hwnd))
                rc = RECT()
                user32.GetWindowRect(pw_hwnd, ctypes.byref(rc))
                saved = {
                    "x": int(rc.left),
                    "y": int(rc.top),
                    "w": max(960, int(rc.right - rc.left)),
                    "h": max(640, int(rc.bottom - rc.top)),
                    "zoomed": was_zoomed,
                }
            if user32.IsZoomed(pw_hwnd):
                user32.ShowWindow(pw_hwnd, 9)  # SW_RESTORE
            scr_w = int(user32.GetSystemMetrics(0)) or 1920
            w = min(1280, max(880, scr_w - 64))
            h = 136
            x = max(0, (scr_w - w) // 2)
            y = 4
            user32.SetWindowPos(pw_hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
            refocus_game_async()
            return saved
        else:
            z_flag = HWND_TOPMOST if pin_top else HWND_NOTOPMOST
            if prev_geom is not None:
                user32.SetWindowPos(
                    pw_hwnd,
                    z_flag,
                    int(prev_geom.get("x", 40)),
                    int(prev_geom.get("y", 20)),
                    int(prev_geom.get("w", 1600)),
                    int(prev_geom.get("h", 960)),
                    SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
                if prev_geom.get("zoomed"):
                    user32.ShowWindow(pw_hwnd, 3)  # SW_MAXIMIZE
                    user32.SetWindowPos(pw_hwnd, z_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                return None
            else:
                user32.SetWindowPos(pw_hwnd, z_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                return None
    except Exception:
        return prev_geom


class TelemetryUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub: "PitWallHub") -> None:
        self.hub = hub

    def datagram_received(self, data: bytes, addr: Any) -> None:
        self.hub.on_udp_datagram(data, is_reply_sock=False)

    def error_received(self, exc: Exception) -> None:
        pass


class CommandUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub: "PitWallHub") -> None:
        self.hub = hub
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: Any) -> None:
        self.hub.on_udp_datagram(data, is_reply_sock=True)

    def error_received(self, exc: Exception) -> None:
        pass


class WebSocketClient:
    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self.writer = writer
        self.closed = False

    async def send_json(self, payload: Dict[str, Any]) -> None:
        if self.closed:
            return
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        length = len(raw)
        header = bytearray([0x81])  # FIN + text frame
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        try:
            self.writer.write(bytes(header) + raw)
            await self.writer.drain()
        except (ConnectionError, OSError):
            self.closed = True


async def read_ws_frame(reader: asyncio.StreamReader) -> Optional[str]:
    try:
        head = await reader.readexactly(2)
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        return None
    opcode = head[0] & 0x0F
    masked = bool(head[1] & 0x80)
    length = head[1] & 0x7F
    if opcode == 0x8:  # Close
        return None
    if length == 126:
        ext = await reader.readexactly(2)
        length = struct.unpack("!H", ext)[0]
    elif length == 127:
        ext = await reader.readexactly(8)
        length = struct.unpack("!Q", ext)[0]
    if length > 1024 * 1024:
        return None
    mask_key = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    if masked:
        unmasked = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
    else:
        unmasked = payload
    if opcode == 0x9:  # Ping
        return ""
    return unmasked.decode("utf-8", "replace")


class PitWallHub:
    def __init__(self, host: str, tele_port: int, cmd_host: str, cmd_port: int, token: str) -> None:
        self.host = host
        self.tele_port = tele_port
        self.cmd_host = cmd_host
        self.cmd_port = cmd_port
        self.token = token

        self.sim = DemoRaceSimulator()
        self.sim_enabled = False
        self.udp_bind_error: Optional[str] = None
        self.cmd_proto: Optional[CommandUDPProtocol] = None
        self.clients: Set[WebSocketClient] = set()
        self.audio_leader: Optional[WebSocketClient] = None
        self.manual_boost_until = 0.0
        self.manual_boost_flags = (False, False, False)
        self.tts_cache: "collections.OrderedDict[Tuple[str, str, str], Tuple[bytes, str]]" = collections.OrderedDict()
        self._tts_inflight: Dict[Tuple[str, str, str], "asyncio.Task[Tuple[bytes, str]]"] = {}
        self._winrt_proc: Optional[asyncio.subprocess.Process] = None
        self._winrt_lock: Optional[asyncio.Lock] = None
        self.active_voice_id = "en-GB-SoniaNeural"
        self.active_rate_pct = 8
        self._urgent_ws_event: Optional[asyncio.Event] = None
        self.overlay_cfg: Dict[str, bool] = {
            "game_refocus": True,
            "global_hotkeys": True,
            "mouse_buttons": True,
            "pin_top": False,
            "mini_hud": False,
        }
        self._saved_window_geom: Optional[Dict[str, Any]] = None

        self.engine = TelemetryEngine(self.dispatch_command)
        self.engine.on_radio_emitted = self._on_engine_radio
        os.makedirs(RESULTS_DIR, exist_ok=True)
        self.league_mgr = public_suite.LeagueManager(RESULTS_DIR)

    def _build_snapshot(self) -> Dict[str, Any]:
        snap = self.engine.snapshot()
        snap["connection"]["udp_bind_error"] = self.udp_bind_error
        snap["overlay"] = dict(self.overlay_cfg)
        return snap

    def _on_engine_radio(self, _entry: Dict[str, Any]) -> None:
        if self._urgent_ws_event is not None:
            self._urgent_ws_event.set()

    async def _ensure_local_winrt_worker(self) -> Optional[asyncio.subprocess.Process]:
        if sys.platform != "win32":
            return None
        if self._winrt_proc is not None and self._winrt_proc.returncode is None:
            return self._winrt_proc
        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell",
                "-NoProfile",
                "-Command",
                _WINRT_DAEMON_PS,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=4 * 1024 * 1024,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            assert proc.stdout is not None
            ready = await asyncio.wait_for(proc.stdout.readline(), timeout=6.0)
            if ready.decode("utf-8", "replace").strip() != "READY":
                proc.kill()
                return None
            self._winrt_proc = proc
            return proc
        except Exception:
            self._winrt_proc = None
            return None

    def _resolve_voice_profile(self, voice_id: str) -> Dict[str, Any]:
        if swooz_persona.is_custom_persona(voice_id):
            meta = swooz_persona.load_persona_meta(voice_id)
            if meta:
                return {
                    "voice": meta.get("base_voice", "Mark"),
                    "pitch_pct": int(meta.get("pitch_pct", 1)),
                    "rate_offset": int(meta.get("rate_offset", 4)),
                    "contour": "(0%,+4%) (48%,+7%) (82%,+3%) (100%,-2%)",
                }
        return LOCAL_VOICE_PROFILES.get(voice_id, LOCAL_VOICE_PROFILES["en-GB-SoniaNeural"])

    async def _synthesize_local_winrt_wav(self, voice_id: str, rate_pct: int, text_in: str) -> bytes:
        if self._winrt_lock is None:
            self._winrt_lock = asyncio.Lock()
        prof = self._resolve_voice_profile(voice_id)
        eff_rate = max(-25, min(55, int(rate_pct) + int(prof["rate_offset"])))
        payload = json.dumps({
            "voice": prof["voice"],
            "pitch": f"{int(prof['pitch_pct']):+d}%",
            "rate": f"{eff_rate:+d}%",
            "contour": prof.get("contour", ""),
            "text": text_in,
        }) + "\n"

        async with self._winrt_lock:
            proc = await self._ensure_local_winrt_worker()
            if proc is None or proc.stdin is None or proc.stdout is None:
                raise RuntimeError("Local WinRT synthesizer unavailable")
            try:
                proc.stdin.write(payload.encode("utf-8"))
                await proc.stdin.drain()
                line = (await asyncio.wait_for(proc.stdout.readline(), timeout=3.0)).decode("ascii", "replace").strip()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                self._winrt_proc = None
                raise
            if not line.startswith("OK:"):
                raise RuntimeError(f"WinRT error: {line}")
            return base64.b64decode(line[3:])

    async def synthesize_tts_cached(self, voice_id: str, rate_pct: int, text_in: str) -> Tuple[bytes, str, bool]:
        if voice_id not in LOCAL_VOICE_PROFILES and not swooz_persona.is_custom_persona(voice_id):
            voice_id = "en-GB-SoniaNeural"
        rate_str = f"{rate_pct:+d}%"
        cache_key = (voice_id, rate_str, text_in)
        if cache_key in self.tts_cache:
            self.tts_cache.move_to_end(cache_key)
            audio_b, mime = self.tts_cache[cache_key]
            return audio_b, mime, True
        if cache_key in self._tts_inflight:
            audio_b, mime = await asyncio.shield(self._tts_inflight[cache_key])
            return audio_b, mime, True

        async def _build() -> Tuple[bytes, str]:
            try:
                # PRIMARY MAIN ENGINE: ~45ms 100% Local WinRT OneCore WAV (zero cloud lag, full 90s V10 FX!)
                wav_bytes = await self._synthesize_local_winrt_wav(voice_id, rate_pct, text_in)
                if wav_bytes:
                    out = (wav_bytes, "audio/wav")
                    self.tts_cache[cache_key] = out
                    if len(self.tts_cache) > 384:
                        self.tts_cache.popitem(last=False)
                    return out
                raise RuntimeError("Empty WAV")
            except Exception:
                # Non-Windows fallback only
                if edge_tts is None:
                    raise
                comm = edge_tts.Communicate(text_in, "en-GB-SoniaNeural", rate=rate_str, connect_timeout=4, receive_timeout=6)
                buf = bytearray()
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        buf.extend(chunk["data"])
                out = (bytes(buf), "audio/mpeg")
                if out[0]:
                    self.tts_cache[cache_key] = out
                return out
            finally:
                self._tts_inflight.pop(cache_key, None)

        task = asyncio.create_task(_build())
        self._tts_inflight[cache_key] = task
        audio_bytes, mime_out = await asyncio.shield(task)
        return audio_bytes, mime_out, False

    def schedule_voice_prewarm(self, voice_id: str, rate_pct: int) -> None:
        if voice_id not in LOCAL_VOICE_PROFILES and not swooz_persona.is_custom_persona(voice_id):
            voice_id = "en-GB-SoniaNeural"
        self.active_voice_id = voice_id
        self.active_rate_pct = max(-25, min(45, int(rate_pct)))
        rp = self.active_rate_pct

        async def _warm() -> None:
            for phrase in PREWARM_RACE_PHRASES[:18]:
                if (voice_id, f"{rp:+d}%", phrase) not in self.tts_cache:
                    try:
                        await self.synthesize_tts_cached(voice_id, rp, phrase)
                    except Exception:
                        break
                    await asyncio.sleep(0.005)

        try:
            asyncio.get_running_loop().create_task(_warm())
        except RuntimeError:
            pass

    async def tts_keepwarm_loop(self) -> None:
        # Boot & warm persistent Local WinRT worker immediately (<0.8s) so very first call is ~1ms-40ms!
        await asyncio.sleep(0.05)
        try:
            await self.synthesize_tts_cached("en-GB-SoniaNeural", self.active_rate_pct, "Copy.")
            self.schedule_voice_prewarm("en-GB-SoniaNeural", self.active_rate_pct)
        except Exception:
            pass
        while True:
            await asyncio.sleep(60.0)
            if self._winrt_proc is None or self._winrt_proc.returncode is not None:
                await self._ensure_local_winrt_worker()

    def on_udp_datagram(self, data: bytes, is_reply_sock: bool) -> None:
        try:
            header, body = bc_api.decode(data)
        except bc_api.PacketError:
            return
        # Auto-yield simulator immediately when real race telemetry arrives!
        if not is_reply_sock and self.sim_enabled:
            self.sim_enabled = False
        self.engine.ingest(header, body, raw_size=len(data))

    def dispatch_command(self, cmd_name: str, args: Dict[str, Any]) -> None:
        req_id = int(args.get("request_id", 0)) or self.engine.next_request_id()

        # In Simulator mode, route directly to DemoRaceSimulator
        if self.sim_enabled:
            reply_kind, reply_body = self.sim.handle_command(cmd_name, {**args, "request_id": req_id})
            if reply_kind != "none":
                pid = {"ack": bc_api.ACK, "error": bc_api.ERROR, "hello": bc_api.HELLO}[reply_kind]
                hdr = {
                    "packet_format": 1, "packet_id": pid, "packet_version": 1,
                    "game_version": "0.88.2-SIM", "num_cars": 16, "session_uid": self.sim.session_uid,
                    "frame": self.sim.frame, "session_time": self.sim.session_time,
                    "seat_car": [0, 255, 255, 255], "packet": reply_kind, "simulated": True,
                }
                self.engine.ingest(hdr, reply_body, raw_size=30)
            return

        if not self.cmd_proto or not self.cmd_proto.transport:
            return

        pkt: Optional[bytes] = None
        tok = self.token
        if cmd_name == "ping":
            pkt = bc_api.ping(req_id, tok)
        elif cmd_name == "hello":
            pkt = bc_api.hello_command(req_id, tok)
        elif cmd_name == "pick_card":
            pkt = bc_api.pick_card(int(args["index"]), seat=0, request_id=req_id, token=tok)
        elif cmd_name == "ban_card":
            pkt = bc_api.ban_card(int(args["index"]), seat=0, request_id=req_id, token=tok)
        elif cmd_name == "set_pit":
            pkt = bc_api.set_pit(bool(args["pit"]), seat=0, request_id=req_id, token=tok)
        elif cmd_name == "pick_tire":
            pkt = bc_api.pick_tire(args["compound"], seat=0, request_id=req_id, token=tok)
        elif cmd_name == "drive":
            pkt = bc_api.drive(float(args["pedal"]), float(args["steer"]), seat=0, request_id=req_id, token=tok)
        elif cmd_name == "release_drive":
            pkt = bc_api.release_drive(seat=0, request_id=req_id, token=tok)
        elif cmd_name == "boost":
            buttons = int(args.get("buttons", 0))
            pkt = bc_api.boost(
                speed=bool(buttons & bc_api.BOOST_SPEED),
                cornering=bool(buttons & bc_api.BOOST_CORNERING),
                party_mode=bool(buttons & bc_api.BOOST_PARTY_MODE),
                seat=0,
                request_id=req_id,
                token=tok,
            )
        elif cmd_name == "set_camera":
            cam = args["camera"]
            special = {"previous": bc_api.CAMERA_PREVIOUS, "next": bc_api.CAMERA_NEXT, "auto": bc_api.CAMERA_AUTOMATIC}
            cam_val = special.get(str(cam), int(cam) if str(cam).isdigit() else cam)
            pkt = bc_api.set_camera(cam_val, seat=0, request_id=req_id, token=tok)

        if pkt:
            try:
                self.cmd_proto.transport.sendto(pkt, (self.cmd_host, self.cmd_port))
            except OSError:
                pass

    def handle_ws_action(self, msg: Dict[str, Any]) -> None:
        action = msg.get("action")
        if action in ("pick_card", "ban_card", "set_pit", "pick_tire", "set_camera", "ping", "hello", "release_drive"):
            if action == "pick_tire":
                self.engine._last_picked_compound = str(msg.get("compound", ""))
            elif action == "pick_card":
                idx = int(msg.get("index", -1))
                hand = self.engine.player_state.get("hand") or []
                if 0 <= idx < len(hand):
                    self.engine._last_picked_card_name = str(hand[idx].get("upgrade", "upgrade"))
                    self.engine._last_picked_card_fac = str(hand[idx].get("facility", ""))
            elif action == "set_camera":
                cam_name = str(msg.get("camera", "Chase"))
                self.engine.copilot["active_camera"] = cam_name
                if not msg.get("from_director"):
                    self.engine.copilot["tv_director"] = False
                cam_spoken = {
                    "Onboard_BattleCam": "Battle cam.",
                    "Onboard_Rear": "Rear view mirror.",
                    "Onboard_TCam": "T cam.",
                    "Onboard_Driver": "Cockpit cam.",
                    "Onboard_TVAngle": "T V onboard.",
                    "Chase": "Chase cam.",
                    "Helicopter": "Helicopter cam.",
                    "TrackSide": "Trackside cam.",
                    "Drone": "Drone cam.",
                    "next": "Next camera.",
                    "previous": "Previous camera.",
                }.get(cam_name, f"{cam_name} camera.")
                self.engine.emit_radio(f"cam_{time.monotonic()}", cam_spoken, "INFO", cooldown_s=0.35)
            self.dispatch_command(action, msg)
        elif action == "crew_callout":
            crew_msg = str(msg.get("message", "")).strip()[:180]
            crew_tag = str(msg.get("sender", "Crew Chief")).strip()[:28]
            if crew_msg:
                self.engine.emit_radio(
                    f"crew_{time.monotonic()}",
                    f"{crew_tag}: {crew_msg}",
                    "CRITICAL",
                    cooldown_s=0.25,
                )
        elif action == "set_sim_public":
            pub_on = bool(msg.get("public_lobby", not getattr(self.sim, "public_lobby", False)))
            self.sim.public_lobby = pub_on
            self.engine.session_info["public_lobby"] = pub_on
            self.engine.hello_state["public_lobby"] = pub_on
            self.engine._announced_public_lobby = pub_on
            if pub_on:
                self.engine.copilot["public_spotter"] = True
                self.engine.emit_radio(
                    f"pubsim_{time.monotonic()}",
                    "Public lobby mode active — auto-inputs shielded for fair play. Three-D Blind-Spot Radar, Rival Spy, Instant Card Callouts, and Camera Control are live!",
                    "STRATEGY",
                    cooldown_s=0.4,
                )
            else:
                self.engine.emit_radio(
                    f"pubsim_{time.monotonic()}",
                    "Custom lobby mode restored — full fifty-hertz Co-Pilot inputs unlocked.",
                    "INFO",
                    cooldown_s=0.4,
                )
        elif action == "manual_boost":
            active = bool(msg.get("active", True))
            hold = msg.get("hold")
            prof = msg.get("profile")
            dur = msg.get("duration_s")
            custom = None
            if any(k in msg for k in ("speed", "cornering", "party")) and prof is None:
                sp = bool(msg.get("speed", False))
                co = bool(msg.get("cornering", False))
                pa = bool(msg.get("party", False))
                if not (sp or co or pa):
                    active = False
                else:
                    custom = (sp, co, pa)
            # Toggle off if user taps PUSH again while a non-hold burst is already active
            if active and not hold and custom is None and self.engine.push_state.get("active") and not self.engine.push_state.get("hold"):
                if msg.get("toggle_if_active", False):
                    active = False
            st = self.engine.trigger_tactical_push(
                profile=str(prof) if prof else None,
                hold=bool(hold) if hold is not None else None,
                active=active,
                duration_s=float(dur) if dur is not None else None,
                custom_flags=custom,
            )
            if st.get("active"):
                if custom is not None:
                    sp, co, pa = custom
                    call = "Party Mode engaged!" if pa and not (sp or co) else ("Super Boost deployed!" if (sp and co) else ("Speed Boost pulse!" if sp else "Cornering Grip pulse!"))
                else:
                    pslot = self.engine.loadout_mgr.get_push_slot(st.get("profile", "k1_super"))
                    call = str(pslot.get("call") or f"{pslot.get('label', 'Push')} deployed!")
                if not st.get("hold"):
                    self.engine.emit_radio(f"push_{time.monotonic()}", call, "INFO", cooldown_s=2.2)
            else:
                self.dispatch_command("boost", {"buttons": 0, "request_id": 0})
        elif action == "set_copilot":
            key = str(msg.get("key", ""))
            if key in self.engine.copilot:
                val = msg.get("value")
                if key == "pit_cliff_threshold":
                    self.engine.copilot[key] = max(0.05, min(0.65, float(val)))
                elif key == "push_profile":
                    pslot = self.engine.loadout_mgr.get_push_slot(val)
                    prof = str(pslot["id"])
                    self.engine.copilot["push_profile"] = prof
                    self.engine.emit_radio(
                        f"pprof_{time.monotonic()}",
                        f"Push button armed to {pslot['label']} — {pslot['call']}",
                        "INFO",
                        cooldown_s=0.3,
                    )
                elif key == "card_strategy":
                    cs_raw = str(val).strip().lower()
                    if cs_raw == "lendurance":
                        self.engine.copilot["card_strategy"] = "lendurance"
                        self.engine.copilot["extreme_ai_sync"] = False
                        self.engine.emit_radio(
                            f"cstrat_{time.monotonic()}",
                            "Auto Card set to Dom's L'Endurance P1 Blueprint — Mulsanne Drag, six-D R S Super Boost, and sixteen-second Pit Speed armor!",
                            "STRATEGY",
                            cooldown_s=0.3,
                        )
                        if self.engine.copilot.get("auto_card"):
                            self.engine.try_auto_card(force=True)
                    elif cs_raw == "extreme_ai":
                        self.engine.copilot["card_strategy"] = "extreme_ai"
                        self.engine.copilot["extreme_ai_sync"] = True
                        self.engine.emit_radio(
                            f"cstrat_{time.monotonic()}",
                            "Auto Card synced to Extreme A I — eighty-thousand-race model weights and Quad six-of-six facility rush!",
                            "STRATEGY",
                            cooldown_s=0.3,
                        )
                        if self.engine.copilot.get("auto_card"):
                            self.engine.try_auto_card(force=True)
                    else:
                        cslot = self.engine.loadout_mgr.get_card_slot(val)
                        if cslot is not None:
                            self.engine.copilot["card_strategy"] = str(cslot["id"])
                            self.engine.copilot["extreme_ai_sync"] = False
                            self.engine.emit_radio(
                                f"cstrat_{time.monotonic()}",
                                str(cslot.get("call") or f"Auto-Card blueprint locked: {cslot['label']}!"),
                                "STRATEGY",
                                cooldown_s=0.3,
                            )
                            if self.engine.copilot.get("auto_card"):
                                self.engine.try_auto_card(force=True)
                elif key == "pace_mode":
                    mode = str(val).lower()
                    if mode in ("conserve", "balanced", "attack", "hammer"):
                        self.engine.copilot["pace_mode"] = mode
                        rec = self.engine.recommend_compound(
                            (self.engine.tire_screen_state or {}).get("allowed", bc_api.COMPOUNDS),
                            self.engine.player_state.get("compound_picks_left", {}),
                        )
                        mode_lines = {
                            "conserve": f"Copy, Conserve mode. Lift and coast, 15 percent cliff, overcut traffic filter active — targeting {rec['compound']}s and 55 percent battery reserve.",
                            "balanced": f"Copy, Balanced pace. Optimal 22 percent crossover and clean-air undercut armed — targeting {rec['compound']} compound.",
                            "attack": f"Copy, Attack mode engaged! Predatory rival hunter active, 28 percent early undercut, favoring {rec['compound']} grip!",
                            "hammer": f"Copy that — Hammer Time! Empty the tank, both boosts pinned, 32 percent sprint cliff on {rec['compound']}s!",
                        }
                        self.engine.emit_radio(
                            f"pace_{mode}_{time.monotonic()}",
                            mode_lines[mode],
                            "STRATEGY",
                            cooldown_s=0.2,
                        )
                        if self.engine.copilot.get("auto_tire"):
                            self.engine.try_auto_tire(force=True)
                        if self.engine.copilot.get("auto_pit"):
                            self.engine.try_auto_pit(force=True)
                        if self.engine.copilot.get("auto_card"):
                            self.engine.try_auto_card(force=True)
                elif key == "wear_mult":
                    wm = float(val)
                    if wm in (1.0, 1.15, 1.3):
                        self.engine.copilot["wear_mult"] = wm
                        self.engine.emit_radio(
                            f"wm_{time.monotonic()}",
                            f"Pre-race tire wear set to {wm:.2f}x.",
                            "INFO",
                            cooldown_s=0.2,
                        )
                        if self.engine.copilot.get("auto_tire"):
                            self.engine.try_auto_tire(force=True)
                elif key == "rain_forecast":
                    rf = str(val)
                    if rf in ("auto", "rain_soon", "drying"):
                        self.engine.copilot["rain_forecast"] = rf
                        rf_lines = {
                            "auto": "Weather forecast set to live radar.",
                            "rain_soon": "Copy, rain expected shortly — holding durable sets for later.",
                            "drying": "Copy, track forecast drying — preparing slicks crossover.",
                        }
                        self.engine.emit_radio(f"rf_{time.monotonic()}", rf_lines[rf], "INFO", cooldown_s=0.2)
                        if self.engine.copilot.get("auto_tire"):
                            self.engine.try_auto_tire(force=True)
                else:
                    prev = self.engine.copilot[key]
                    on_val = bool(val)
                    self.engine.copilot[key] = on_val
                    if key == "auto_drive" and prev and not on_val:
                        self.dispatch_command("release_drive", {})
                    labels = {
                        "auto_pit": "Pit cliff guard",
                        "auto_tire": "Auto tire compound",
                        "auto_card": "Auto card strategist",
                        "auto_boost": "E R S auto deploy",
                        "auto_drive": "Fifty hertz A I driver",
                        "public_spotter": "Public lobby radar and rival spy",
                        "tv_director": "A I broadcast camera director",
                    }
                    lbl = labels.get(key, key)
                    self.engine.emit_radio(
                        f"cp_{key}_{time.monotonic()}",
                        f"Copy, {lbl} {'armed' if on_val else 'disengaged'}.",
                        "INFO",
                        cooldown_s=0.2,
                    )
                    if on_val:
                        if key == "auto_card":
                            self.engine.try_auto_card(force=True)
                        elif key == "auto_tire":
                            self.engine.try_auto_tire(force=True)
                        elif key == "auto_pit":
                            self.engine.try_auto_pit(force=True)
        elif action == "set_preset":
            preset = str(msg.get("preset", "")).lower()
            if preset == "extreme_ai":
                want = msg.get("active")
                next_on = (not bool(self.engine.copilot.get("extreme_ai_sync"))) if want is None else bool(want)
                self.engine.apply_extreme_ai_sync(next_on, RESULTS_DIR)
                p1_bp = self.engine.get_active_p1_blueprint() or {}
                p1_who = p1_bp.get("winner", "Blitz")
                if next_on:
                    self.engine.emit_radio(
                        f"ext_ai_{time.monotonic()}",
                        f"Extreme A I synced! Eighty-thousand-race model weights, Quad six-of-six facility rush, "
                        f"Super Comms boost, and {p1_who} P1 blueprint armed!",
                        "STRATEGY",
                        cooldown_s=0.3,
                    )
                    self.engine.try_auto_tire(force=True)
                    self.engine.try_auto_card(force=True)
                    self.engine.try_auto_pit(force=True)
                else:
                    self.engine.emit_radio(
                        f"ext_ai_off_{time.monotonic()}",
                        "Extreme A I sync disengaged — restored Balanced manual baseline.",
                        "INFO",
                        cooldown_s=0.3,
                    )
            elif preset == "lendurance":
                want = msg.get("active")
                next_on = (not bool(self.engine.copilot.get("lendurance_mode"))) if want is None else bool(want)
                self.engine.apply_lendurance_preset(next_on)
                if next_on:
                    self.engine.emit_radio(
                        f"lend_{time.monotonic()}",
                        "L'Endurance P1 package dialed in! Ten percent deep-stint cliff for the sixteen-second pit lane, "
                        "Slingshot Mulsanne boost, Boost compound priority, and Drag-plus-Pit-Speed card build armed!",
                        "STRATEGY",
                        cooldown_s=0.3,
                    )
                    self.engine.try_auto_tire(force=True)
                    self.engine.try_auto_card(force=True)
                    self.engine.try_auto_pit(force=True)
                else:
                    self.engine.emit_radio(
                        f"lend_off_{time.monotonic()}",
                        "L'Endurance package disengaged — restored standard twenty-two percent Balanced crossover.",
                        "INFO",
                        cooldown_s=0.3,
                    )
        elif action == "set_rival":
            car_idx = msg.get("car_index")
            self.engine.selected_rival_car = int(car_idx) if car_idx is not None else None
            if car_idx is not None and 0 <= int(car_idx) < self.engine.num_cars:
                rc = self.engine.cars[int(car_idx)]
                self.engine.emit_radio(
                    f"rvl_{time.monotonic()}",
                    f"Telemetry locked on P{rc.position} {rc.name}, tire health {rc.tire_health*100:.0f} percent.",
                    "INFO",
                    cooldown_s=0.3,
                )
        elif action == "toggle_sim":
            self.sim_enabled = not self.sim_enabled
            if self.sim_enabled:
                self.engine.reset_session(self.sim.session_uid, simulated=True)
        elif action == "reset_sim":
            self.sim = DemoRaceSimulator()
            self.sim_enabled = True
            self.engine.reset_session(self.sim.session_uid, simulated=True)
        elif action == "start_race":
            dur = float(msg.get("duration_s", 2.2))
            res_code = hold_game_spacebar(dur)
            if res_code == "held":
                self.engine.command_log.appendleft({
                    "wall_ts": datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "type": "ACK",
                    "command": "start_race",
                    "reason": f"hold_space_{dur:.1f}s",
                    "request_id": self.engine.next_request_id(),
                })
                self.engine.emit_radio(
                    f"start_{time.monotonic()}",
                    "Copy that — holding grid launch! Lights out and away we go!",
                    "INFO",
                    cooldown_s=1.0,
                )
            elif res_code == "headless":
                self.engine.emit_radio(
                    f"start_hl_{time.monotonic()}",
                    "Double-click your SWOOZ Pit Wall Desktop shortcut once to enable desktop Spacebar hold for Backseat Champions!",
                    "INFO",
                    cooldown_s=1.0,
                )
            else:
                self.sim = DemoRaceSimulator()
                self.sim_enabled = True
                self.engine.reset_session(self.sim.session_uid, simulated=True)
                self.engine.emit_radio(
                    f"start_sim_{time.monotonic()}",
                    "Demo race started — lights out and away we go!",
                    "INFO",
                    cooldown_s=1.0,
                )
        elif action == "prewarm_voice":
            vid = str(msg.get("voice", "en-GB-SoniaNeural"))
            rp = int(msg.get("rate_pct", 8))
            self.schedule_voice_prewarm(vid, rp)
        elif action == "test_radio":
            stint = self.engine.compute_stint_strategy()
            my_car = self.engine.cars[self.engine.my_car_idx if self.engine.my_car_idx != 255 else 0]
            self.engine.emit_radio(
                f"test_{time.monotonic()}",
                f"Tire check copy! P{my_car.position}, {my_car.tire_compound}s at {stint['tire_health_pct']:.0f} percent, "
                f"wearing {stint['wear_per_lap_pct']:.1f} per lap — {stint['laps_to_cliff']:.1f} laps to cliff, rejoin P{stint['rejoin_position']}.",
                "INFO",
                cooldown_s=0.1,
            )
        elif action == "refocus_game":
            if self.overlay_cfg.get("game_refocus", True):
                refocus_game_async()
        elif action == "set_overlay":
            key = str(msg.get("key", ""))
            if key in self.overlay_cfg:
                val = bool(msg.get("value")) if "value" in msg else (not self.overlay_cfg[key])
                self.overlay_cfg[key] = val
                if key == "mini_hud" and val:
                    # Mini-HUD automatically pins on top so it floats over Borderless Windowed game
                    self.overlay_cfg["pin_top"] = True
                if key in ("pin_top", "mini_hud"):
                    self._saved_window_geom = apply_pitwall_window_mode(
                        self.overlay_cfg["pin_top"],
                        self.overlay_cfg["mini_hud"],
                        self._saved_window_geom,
                    )
                if self._urgent_ws_event is not None:
                    self._urgent_ws_event.set()

    async def global_hotkey_loop(self) -> None:
        """Passive 40Hz GetAsyncKeyState reader — NEVER swallows or overrides game keys,
        and ONLY fires while BackseatChampions.exe is the active foreground window!
        """
        if sys.platform != "win32" or not _has_interactive_desktop():
            return
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        prev_down: Dict[int, bool] = {}
        tracked_vks = (
            0x74, 0x75, 0x76, 0x77,              # F5 (Push), F6 (Box), F7 (Auto Card), F8 (Sitrep)
            0x60, 0x6E,                          # Numpad 0 (Push), Numpad . (Box)
            0x61, 0x62, 0x63,                    # Numpad 1/2/3 (Pick Card 1/2/3)
            0x64, 0x65, 0x66, 0x67, 0x68, 0x69,  # Numpad 4..9 (Pace, Auto Tire, Pit Guard, Auto Card, Sitrep, Mini-HUD)
            0x05, 0x06,                          # Mouse 4 (XBUTTON1 -> Box), Mouse 5 (XBUTTON2 -> Push)
        )
        game_pids: Set[int] = set()
        next_pid_scan = 0.0

        while True:
            await asyncio.sleep(0.025)
            if not self.overlay_cfg.get("global_hotkeys", True):
                prev_down.clear()
                await asyncio.sleep(0.20)
                continue

            now = time.monotonic()
            if now >= next_pid_scan:
                game_pids = _get_backseat_pids()
                next_pid_scan = now + 1.5

            if not game_pids:
                prev_down.clear()
                await asyncio.sleep(0.25)
                continue

            fg_hwnd = user32.GetForegroundWindow()
            fg_pid = wintypes.DWORD(0)
            if fg_hwnd:
                user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid))
            in_game_fg = int(fg_pid.value) in game_pids

            allow_mouse = self.overlay_cfg.get("mouse_buttons", True)
            fired = False

            for vk in tracked_vks:
                is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                was_down = prev_down.get(vk, False)
                prev_down[vk] = is_down
                if not (is_down and not was_down and in_game_fg):
                    continue
                if vk in (0x05, 0x06) and not allow_mouse:
                    continue

                fired = True
                if vk in (0x74, 0x60, 0x06):  # F5 / Numpad 0 / Mouse 5 -> Active Push Mode
                    prof = str(self.engine.copilot.get("push_profile", "k1_super"))
                    self.handle_ws_action({"action": "manual_boost", "profile": prof, "active": True, "toggle_if_active": True})
                elif vk in (0x75, 0x6E, 0x05):  # F6 / Numpad . / Mouse 4 -> Toggle Box This Lap
                    mc = self.engine.cars[self.engine.my_car_idx if self.engine.my_car_idx != 255 else 0]
                    cur_pit = bool(self.engine.player_state.get("pit_planned", mc.pit_planned))
                    next_pit = not cur_pit
                    self.handle_ws_action({"action": "set_pit", "pit": next_pit})
                    self.engine.emit_radio(
                        f"ghk_pit_{now}",
                        "Copy that, box this lap!" if next_pit else "Copy, staying out — pit cancelled.",
                        "STRATEGY",
                        cooldown_s=0.3,
                    )
                elif vk in (0x76, 0x67):  # F7 / Numpad 7 -> Toggle Auto Card
                    self.handle_ws_action({"action": "set_copilot", "key": "auto_card", "value": not bool(self.engine.copilot.get("auto_card"))})
                elif vk in (0x77, 0x68):  # F8 / Numpad 8 -> Sitrep
                    self.handle_ws_action({"action": "test_radio"})
                elif vk in (0x61, 0x62, 0x63):  # Numpad 1/2/3 -> Pick Card 1/2/3
                    self.handle_ws_action({"action": "pick_card", "index": vk - 0x61})
                elif vk == 0x64:  # Numpad 4 -> Cycle Pace
                    order = ["conserve", "balanced", "attack", "hammer"]
                    cur = str(self.engine.copilot.get("pace_mode", "balanced"))
                    nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "balanced"
                    self.handle_ws_action({"action": "set_copilot", "key": "pace_mode", "value": nxt})
                elif vk == 0x65:  # Numpad 5 -> Toggle Auto Tire
                    self.handle_ws_action({"action": "set_copilot", "key": "auto_tire", "value": not bool(self.engine.copilot.get("auto_tire"))})
                elif vk == 0x66:  # Numpad 6 -> Toggle Pit Guard
                    self.handle_ws_action({"action": "set_copilot", "key": "auto_pit", "value": not bool(self.engine.copilot.get("auto_pit"))})
                elif vk == 0x69:  # Numpad 9 -> Toggle Mini-HUD Overlay
                    self.handle_ws_action({"action": "set_overlay", "key": "mini_hud", "value": not bool(self.overlay_cfg.get("mini_hud"))})

            if fired and self._urgent_ws_event is not None:
                self._urgent_ws_event.set()

    async def simulation_and_boost_loop(self) -> None:
        while True:
            t0 = time.monotonic()
            if self.sim_enabled:
                for hdr, body in self.sim.step(0.02):
                    raw_sz = bc_api.PACKET_SIZES[hdr["packet_id"]]
                    self.engine.ingest(hdr, body, raw_size=raw_sz)
            elif self.engine.push_state.get("active"):
                # Ensure 50Hz push controller also ticks cleanly if live telemetry pauses briefly
                self.engine._tick_50hz_controllers()

            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.002, 0.02 - elapsed))

    async def hello_probe_loop(self) -> None:
        while True:
            # Always probe real game UDP on 29771 even while sim is running so we detect game readiness!
            if self.cmd_proto and self.cmd_proto.transport:
                try:
                    self.cmd_proto.transport.sendto(bc_api.hello_command(1, self.token), (self.cmd_host, self.cmd_port))
                except OSError:
                    pass
            await asyncio.sleep(2.5)

    async def broadcast_loop(self) -> None:
        self._urgent_ws_event = asyncio.Event()
        while True:
            if self.clients:
                if self.audio_leader not in self.clients:
                    self.audio_leader = next(iter(self.clients), None)
                snap = self._build_snapshot()
                dead = []
                for ws in list(self.clients):
                    await ws.send_json({"type": "snapshot", "audio_leader": ws is self.audio_leader, "data": snap})
                    if ws.closed:
                        dead.append(ws)
                for ws in dead:
                    self.clients.discard(ws)
                    if self.audio_leader is ws:
                        self.audio_leader = next(iter(self.clients), None)
            self._urgent_ws_event.clear()
            try:
                await asyncio.wait_for(self._urgent_ws_event.wait(), timeout=0.045)
            except asyncio.TimeoutError:
                pass

    def list_saved_results(self) -> Any:
        items = []
        for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.summary.json")), reverse=True)[:25]:
            try:
                with open(path, encoding="utf-8") as f:
                    items.append(json.load(f))
            except OSError:
                pass
        return items

    def save_race_results_upload(self, headers: Dict[str, str], body: bytes) -> Dict[str, Any]:
        ctype = headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype == "application/zip":
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                raw_json = zf.read("results.json").decode("utf-8")
        else:
            raw_json = body.decode("utf-8")

        doc = json.loads(raw_json)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(RESULTS_DIR, f"{stamp}.results.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)

        sessions_summary = []
        for s in doc.get("sessions", []):
            decisions = s.get("decisions") or []
            by_type = {"card": 0, "pit": 0, "tire": 0}
            for d in decisions:
                dt = d.get("decision_type")
                if dt in by_type:
                    by_type[dt] += 1
            sessions_summary.append({
                "kind": s.get("kind", "session"),
                "track": s.get("track", ""),
                "classification": (s.get("classification") or [])[:16],
                "decision_counts": by_type,
                "total_decisions": len(decisions),
            })

        summary = {
            "id": stamp,
            "received_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game_version": headers.get("x-bc-game-version", doc.get("game_version", "")),
            "public_lobby": doc.get("public_lobby", False),
            "sessions": sessions_summary,
        }
        with open(os.path.join(RESULTS_DIR, f"{stamp}.summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        return summary

    async def handle_http_or_ws(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            req_data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
        except Exception:
            writer.close()
            return

        lines = req_data.decode("latin-1").split("\r\n")
        if not lines or " " not in lines[0]:
            writer.close()
            return
        parts = lines[0].split(" ")
        method, raw_path = parts[0], parts[1]
        if "?" in raw_path:
            path, raw_qs = raw_path.split("?", 1)
            query_params = dict(urllib.parse.parse_qsl(raw_qs))
        else:
            path, query_params = raw_path, {}

        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        # 1) WebSocket Upgrade (/ws)
        if path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
            key = headers.get("sec-websocket-key", "")
            accept = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()).decode("ascii")
            handshake = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            )
            writer.write(handshake.encode("ascii"))
            await writer.drain()

            ws = WebSocketClient(writer)
            is_spectator_ws = query_params.get("spectator") == "1"
            self.clients.add(ws)
            if not is_spectator_ws or self.audio_leader is None:
                self.audio_leader = ws
            await ws.send_json({"type": "snapshot", "audio_leader": ws is self.audio_leader, "data": self._build_snapshot()})
            try:
                while not ws.closed:
                    msg_txt = await read_ws_frame(reader)
                    if msg_txt is None:
                        break
                    if not msg_txt:
                        continue
                    try:
                        msg_obj = json.loads(msg_txt)
                        if isinstance(msg_obj, dict):
                            if not is_spectator_ws and not msg_obj.get("spectator"):
                                self.audio_leader = ws
                            if msg_obj.get("action") != "claim_audio":
                                self.handle_ws_action(msg_obj)
                    except json.JSONDecodeError:
                        pass
            finally:
                ws.closed = True
                self.clients.discard(ws)
                if self.audio_leader is ws:
                    self.audio_leader = next(iter(self.clients), None)
                writer.close()
            return

        # 2) Race Results POST Endpoint (/race-results)
        if method == "POST" and path in ("/race-results", "/race-results/"):
            if headers.get("origin") is not None or headers.get("x-bc-format") is None:
                await self._send_http(writer, 403, "text/plain", b"Forbidden: missing X-BC-Format")
                return
            clen = int(headers.get("content-length", "0") or "0")
            if clen <= 0 or clen > 16 * 1024 * 1024:
                await self._send_http(writer, 413, "text/plain", b"Payload size invalid")
                return
            body = await reader.readexactly(clen)
            try:
                summary = self.save_race_results_upload(headers, body)
                self.engine.reload_p1_blueprints(RESULTS_DIR)
                if self.league_mgr.config.get("auto_post_discord") and self.league_mgr.config.get("discord_webhook_url", "").strip():
                    asyncio.get_running_loop().run_in_executor(None, self.league_mgr.post_to_discord, summary)
                self.engine.emit_radio(
                    f"res_{summary['id']}",
                    "Race weekend results uploaded — Open G P Leaderboard and Debrief updated!",
                    "INFO",
                    cooldown_s=1.0,
                )
                await self._send_http(writer, 200, "application/json", json.dumps({"ok": True}).encode("utf-8"))
            except Exception as exc:
                await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
            return

        # 3) Saved Race Results API (/api/results) & Open GP League Leaderboard API (/api/league)
        if method == "GET" and path == "/api/results":
            payload = json.dumps({"results": self.list_saved_results()}).encode("utf-8")
            await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
            return

        if path == "/api/league":
            if method == "GET":
                h_only = True if query_params.get("humans") == "1" else (False if query_params.get("humans") == "0" else None)
                payload = json.dumps(self.league_mgr.build_leaderboard(humans_only=h_only)).encode("utf-8")
                await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
                return
            if method == "POST":
                clen = int(headers.get("content-length", "0") or "0")
                if clen <= 0 or clen > 64 * 1024:
                    await self._send_http(writer, 413, "text/plain", b"Invalid size")
                    return
                body = await reader.readexactly(clen)
                try:
                    req = json.loads(body.decode("utf-8"))
                    act = str(req.get("action", "")).strip()
                    if act == "save_config":
                        self.league_mgr.update_config(req)
                        lb = self.league_mgr.build_leaderboard()
                        lb["toast"] = "Saved League & Discord Webhook settings."
                        await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(lb).encode("utf-8"))
                    elif act == "test_discord":
                        if "discord_webhook_url" in req:
                            self.league_mgr.update_config(req)
                        ok, msg_txt = await asyncio.get_running_loop().run_in_executor(None, self.league_mgr.post_to_discord, None)
                        lb = self.league_mgr.build_leaderboard()
                        lb["discord_ok"] = ok
                        lb["toast"] = msg_txt
                        await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(lb).encode("utf-8"))
                    else:
                        raise ValueError(f"Unknown league action: {act}")
                except Exception as exc:
                    await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
                return

        # 4) Snapshot REST fallback (/api/snapshot)
        if method == "GET" and path == "/api/snapshot":
            payload = json.dumps(self._build_snapshot()).encode("utf-8")
            await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
            return

        # 4b) Local Wi-Fi / LAN URL helper for iPhone & Co-Op Engineer QR scanning (/api/lan-info)
        if method == "GET" and path == "/api/lan-info":
            lan_ip = detect_lan_ip()
            base_url = f"http://{lan_ip}:8765"
            payload = json.dumps({
                "lan_ip": lan_ip,
                "lan_url": base_url,
                "crew_url": f"{base_url}/?role=crew",
                "obs_url": "http://127.0.0.1:8765/?obs=1",
                "interactive_desktop": _has_interactive_desktop(),
                "pitwall_build": "2.4.0-public-lobby-suite",
            }).encode("utf-8")
            await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
            return

        # 4c) 5-Slot Push & Card Loadout Customizer API (/api/loadouts)
        if path == "/api/loadouts":
            if method == "GET":
                state = self.engine.loadout_mgr.get_state()
                state["archived_races"] = loadout_manager.list_archived_p1_races(RESULTS_DIR)
                await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(state).encode("utf-8"))
                return
            if method == "POST":
                clen = int(headers.get("content-length", "0") or "0")
                if clen <= 0 or clen > 256 * 1024:
                    await self._send_http(writer, 413, "text/plain", b"Invalid size")
                    return
                body = await reader.readexactly(clen)
                try:
                    req = json.loads(body.decode("utf-8"))
                    act = str(req.get("action", "")).strip()
                    if act == "update_push_slot":
                        self.engine.loadout_mgr.update_push_slot(int(req["slot"]), dict(req.get("data") or {}))
                    elif act == "update_card_slot":
                        self.engine.loadout_mgr.update_card_slot(int(req["slot"]), dict(req.get("data") or {}))
                        if self.engine.copilot.get("auto_card"):
                            self.engine.try_auto_card(force=True)
                    elif act == "import_card_slot_from_archive":
                        s_idx = int(req["slot"])
                        arch_fn = str(req.get("archive", ""))
                        built = loadout_manager.build_card_slot_from_archive(RESULTS_DIR, arch_fn, s_idx)
                        if built is None:
                            raise ValueError(f"Could not extract P1 build from {arch_fn}")
                        self.engine.loadout_mgr.update_card_slot(s_idx, built)
                    elif act == "reset_push_slot":
                        s_raw = req.get("slot")
                        self.engine.loadout_mgr.reset_push_slot(int(s_raw) if s_raw is not None else None)
                    elif act == "reset_card_slot":
                        s_raw = req.get("slot")
                        self.engine.loadout_mgr.reset_card_slot(int(s_raw) if s_raw is not None else None)
                    elif act == "reset_all":
                        self.engine.loadout_mgr.reset_push_slot(None)
                        self.engine.loadout_mgr.reset_card_slot(None)
                    else:
                        raise ValueError(f"Unknown loadout action: {act}")
                    if self._urgent_ws_event is not None:
                        self._urgent_ws_event.set()
                    state = self.engine.loadout_mgr.get_state()
                    state["archived_races"] = loadout_manager.list_archived_p1_races(RESULTS_DIR)
                    await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(state).encode("utf-8"))
                except Exception as exc:
                    await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
                return

        # 4d) Multi-Persona Voice Studio & Pack Export/Import API (/api/swooz-voice, /api/personas/*)
        if method == "GET" and path == "/api/personas":
            payload = json.dumps({"personas": swooz_persona.list_personas()}).encode("utf-8")
            await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
            return

        if method == "GET" and path == "/api/personas/export":
            pid = query_params.get("persona_id", swooz_persona.DEFAULT_PERSONA_ID)
            try:
                fname, zip_bytes = swooz_persona.export_persona_zip(pid)
                await self._send_http(
                    writer,
                    200,
                    "application/zip",
                    zip_bytes,
                    extra_hdr=f'Content-Disposition: attachment; filename="{fname}"\r\n',
                )
            except Exception as exc:
                await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
            return

        if method == "POST" and path == "/api/personas/import":
            clen = int(headers.get("content-length", "0") or "0")
            if clen <= 0 or clen > 65 * 1024 * 1024:
                await self._send_http(writer, 413, "text/plain", b"Invalid voice pack size")
                return
            body = await reader.readexactly(clen)
            try:
                ctype = headers.get("content-type", "").lower()
                if "application/json" in ctype:
                    req = json.loads(body.decode("utf-8"))
                    zip_bytes = base64.b64decode(str(req.get("zip_base64", "")))
                else:
                    zip_bytes = body
                manifest = swooz_persona.import_persona_zip(zip_bytes)
                await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(manifest).encode("utf-8"))
            except Exception as exc:
                await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
            return

        if path == "/api/swooz-voice":
            if method == "GET":
                pid = query_params.get("persona_id", "")
                payload = json.dumps(swooz_persona.get_studio_manifest(pid)).encode("utf-8")
                await self._send_http(writer, 200, "application/json; charset=utf-8", payload)
                return
            if method == "POST":
                clen = int(headers.get("content-length", "0") or "0")
                if clen <= 0 or clen > 16 * 1024 * 1024:
                    await self._send_http(writer, 413, "text/plain", b"Invalid size")
                    return
                body = await reader.readexactly(clen)
                try:
                    req = json.loads(body.decode("utf-8"))
                    act = str(req.get("action", "")).strip()
                    pid = str(req.get("persona_id") or "").strip()
                    slot_id = str(req.get("slot_id", "")).strip()
                    if act == "save_persona":
                        manifest = swooz_persona.create_or_update_persona(dict(req.get("persona") or req))
                    elif act == "delete_persona":
                        manifest = swooz_persona.delete_persona(pid)
                    elif act == "save_line":
                        manifest = swooz_persona.save_slot_line(slot_id, str(req.get("custom_line", "")), pid)
                    elif req.get("delete") or act == "delete_wav":
                        manifest = swooz_persona.delete_slot_wav(slot_id, pid)
                    else:
                        wav_b64 = str(req.get("wav_base64", ""))
                        wav_bytes = base64.b64decode(wav_b64)
                        cline = req.get("custom_line")
                        manifest = swooz_persona.save_slot_wav(
                            slot_id,
                            wav_bytes,
                            persona_id=pid,
                            custom_line=str(cline) if cline is not None else None,
                        )
                    await self._send_http(writer, 200, "application/json; charset=utf-8", json.dumps(manifest).encode("utf-8"))
                except Exception as exc:
                    await self._send_http(writer, 422, "text/plain", str(exc).encode("utf-8"))
                return

        # 5) Primary Local WinRT + Custom Recorded Persona Radio TTS (/api/tts)
        if method == "POST" and path == "/api/tts":
            clen = int(headers.get("content-length", "0") or "0")
            if clen <= 0 or clen > 8192:
                await self._send_http(writer, 503, "text/plain", b"TTS unavailable")
                return
            body = await reader.readexactly(clen)
            try:
                req = json.loads(body.decode("utf-8"))
                text_in = str(req.get("text", "")).strip()[:360]
                voice_id = str(req.get("voice", "en-GB-SoniaNeural"))
                is_cust = swooz_persona.is_custom_persona(voice_id)
                if voice_id not in LOCAL_VOICE_PROFILES and not is_cust:
                    voice_id = "en-GB-SoniaNeural"
                rate_pct = max(-25, min(45, int(req.get("rate_pct", 8))))
                self.active_voice_id = voice_id
                self.active_rate_pct = rate_pct

                persona_line_hdr = ""
                # Direct recorded WAV clip match (<2ms!) + Custom Spin Line override for any custom persona!
                if is_cust:
                    explicit_slot = str(req.get("slot_id", "")).strip()
                    rec_wav: Optional[bytes] = None
                    custom_line: Optional[str] = None
                    if explicit_slot:
                        rec_wav = swooz_persona.read_slot_wav(explicit_slot, voice_id)
                        meta_p = swooz_persona.load_persona_meta(voice_id) or {}
                        custom_line = (meta_p.get("custom_lines") or {}).get(explicit_slot)
                    if rec_wav is None:
                        matched = swooz_persona.match_recorded_wav(text_in, voice_id)
                        if matched is not None:
                            rec_wav = matched[1]
                            custom_line = matched[2]
                    if custom_line:
                        safe_hdr_line = urllib.parse.quote(str(custom_line).strip(), safe=" ")
                        persona_line_hdr = f"X-Persona-Line: {safe_hdr_line}\r\n"
                    if rec_wav is not None:
                        await self._send_http(
                            writer,
                            200,
                            "audio/wav",
                            rec_wav,
                            extra_hdr=f"X-TTS-Cache: SWOOZ-REC\r\n{persona_line_hdr}",
                        )
                        return
                    # Unrecorded slot on a custom persona -> if user wrote a custom spin text, speak THEIR spin text via sculpted WinRT!
                    _, unrec_custom = swooz_persona.get_custom_slot_line(text_in, voice_id)
                    if unrec_custom:
                        text_in = unrec_custom
                        safe_hdr_line = urllib.parse.quote(str(unrec_custom).strip(), safe=" ")
                        persona_line_hdr = f"X-Persona-Line: {safe_hdr_line}\r\n"

                audio_bytes, mime_out, hit = await self.synthesize_tts_cached(voice_id, rate_pct, text_in)
                await self._send_http(
                    writer,
                    200,
                    mime_out,
                    audio_bytes,
                    extra_hdr=f"X-TTS-Cache: {'HIT' if hit else 'LOCAL'}\r\n{persona_line_hdr}",
                )
            except Exception as exc:
                await self._send_http(writer, 500, "text/plain", str(exc).encode("utf-8"))
            return

        # 6) Static files
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not safe_path.startswith(STATIC_DIR) or not os.path.isfile(safe_path):
            await self._send_http(writer, 404, "text/plain", b"Not Found")
            return

        ext = os.path.splitext(safe_path)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        with open(safe_path, "rb") as f:
            content = f.read()
        await self._send_http(writer, 200, mime, content)

    @staticmethod
    async def _send_http(writer: asyncio.StreamWriter, code: int, content_type: str, body: bytes, extra_hdr: str = "") -> None:
        reasons = {200: "OK", 403: "Forbidden", 404: "Not Found", 413: "Payload Too Large", 422: "Unprocessable", 500: "Error", 503: "Unavailable"}
        head = (
            f"HTTP/1.1 {code} {reasons.get(code, 'OK')}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{extra_hdr}"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        try:
            writer.write(head + body)
            await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()


def detect_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def run_server(args: argparse.Namespace) -> None:
    hub = PitWallHub(args.telemetry_ip, args.telemetry_port, args.game_host, args.command_port, args.token)
    loop = asyncio.get_running_loop()

    def quiet_win_connreset(lp: Any, context: Dict[str, Any]) -> None:
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return
        lp.default_exception_handler(context)

    loop.set_exception_handler(quiet_win_connreset)

    # Bind UDP telemetry listener (127.0.0.1:29770)
    tele_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tele_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    disable_windows_udp_connreset(tele_sock)
    try:
        tele_sock.bind((args.telemetry_ip, args.telemetry_port))
        tele_sock.setblocking(False)
        await loop.create_datagram_endpoint(lambda: TelemetryUDPProtocol(hub), sock=tele_sock)
    except OSError as exc:
        hub.udp_bind_error = f"Port {args.telemetry_port} busy ({exc})"
        tele_sock.close()

    # Bind UDP command socket (ephemeral local port -> sends to game_host:command_port)
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    disable_windows_udp_connreset(cmd_sock)
    cmd_sock.bind(("127.0.0.1" if args.game_host in ("127.0.0.1", "localhost") else "0.0.0.0", 0))
    cmd_sock.setblocking(False)
    _, cmd_proto = await loop.create_datagram_endpoint(lambda: CommandUDPProtocol(hub), sock=cmd_sock)
    hub.cmd_proto = cmd_proto  # type: ignore[assignment]

    http_srv = await asyncio.start_server(hub.handle_http_or_ws, args.web_host, args.web_port)
    print(f"============================================================")
    print(f" SWOOZ PITWALL — LIVE RACE ENGINEER & TEAM COMMS")
    print(f" Dashboard URL:       http://{args.web_host}:{args.web_port}")
    print(f" Telemetry UDP In:    {args.telemetry_ip}:{args.telemetry_port}")
    print(f" Game Command Out:    {args.game_host}:{args.command_port}")
    print(f" Race Results Upload: http://{args.web_host}:{args.web_port}/race-results")
    if hub.udp_bind_error:
        print(f" WARNING: {hub.udp_bind_error}")
    print(f"============================================================", flush=True)

    await asyncio.gather(
        http_srv.serve_forever(),
        hub.simulation_and_boost_loop(),
        hub.hello_probe_loop(),
        hub.broadcast_loop(),
        hub.tts_keepwarm_loop(),
        hub.global_hotkey_loop(),
    )


def main() -> None:
    if sys.stdout is None or sys.stderr is None:
        log_fp = open(os.path.join(ROOT_DIR, "pitwall.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_fp
        if sys.stderr is None:
            sys.stderr = log_fp
    parser = argparse.ArgumentParser(description="Backseat Champions F1 Pit Wall Mission Control")
    parser.add_argument("--web-host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=8765)
    parser.add_argument("--telemetry-ip", default="127.0.0.1")
    parser.add_argument("--telemetry-port", type=int, default=29770)
    parser.add_argument("--game-host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=29771)
    parser.add_argument("--token", default="", help="Optional Command Token for remote game control")
    args = parser.parse_args()
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
