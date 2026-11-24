"""Silent Desktop Companion & Game-Launch Watcher for Backseat Champions F1 Pit Wall.

Modes:
  pythonw pitwall_companion.pyw --watch        # Zero-CPU background watcher (opens Pit Wall when game starts)
  pythonw pitwall_companion.pyw --launch       # Immediately open standalone Pit Wall Desktop App window
  pythonw pitwall_companion.pyw --launch-both  # Launch Backseat Champions via Steam + open Pit Wall App
  pythonw pitwall_companion.pyw --stop         # Stop background watcher
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(ROOT_DIR, "server.py")
APP_PROFILE_DIR = os.path.join(ROOT_DIR, ".app-profile")
WATCHER_PID_FILE = os.path.join(ROOT_DIR, ".watcher.pid")
COMPANION_LOG = os.path.join(ROOT_DIR, "companion.log")

APP_URL = "http://127.0.0.1:8765"
HEALTH_URL = "http://127.0.0.1:8765/api/lan-info"
REQUIRED_BUILD = "2.3.1-clean-crew-studio"
STEAM_RUN_URL = "steam://rungameid/2174510"
WINDOW_TITLE_FRAGMENT = "SWOOZ PitWall"
GAME_EXE_NAMES = {"backseatchampions.exe", "backseat champions.exe"}

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
TH32CS_SNAPPROCESS = 0x00000002
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


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


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def log_msg(text: str) -> None:
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(COMPANION_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {text}\n")
    except OSError:
        pass


def get_pythonw() -> str:
    py_dir = os.path.dirname(sys.executable)
    pw = os.path.join(py_dir, "pythonw.exe")
    return pw if os.path.isfile(pw) else sys.executable


def is_game_running() -> bool:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value or snap is None:
        return False
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return False
        while True:
            exe_name = entry.szExeFile.lower()
            if exe_name in GAME_EXE_NAMES:
                return True
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
        return False
    finally:
        kernel32.CloseHandle(snap)


def _check_server_health(timeout: float = 0.35) -> tuple[bool, bool, str]:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as resp:
            if resp.status != 200:
                return (False, False, "")
            data = json.loads(resp.read().decode("utf-8"))
            return (
                True,
                bool(data.get("interactive_desktop", False)),
                str(data.get("pitwall_build", "")),
            )
    except Exception:
        return (False, False, "")


def is_server_up(timeout: float = 0.35) -> bool:
    up, _, _ = _check_server_health(timeout)
    return up


def _kill_port_8765() -> None:
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, creationflags=CREATE_NO_WINDOW)
        for line in out.splitlines():
            if ":8765 " in line and "LISTENING" in line:
                subprocess.run(
                    ["taskkill", "/F", "/PID", line.split()[-1]],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        time.sleep(0.35)
    except Exception:
        pass


def ensure_server_running() -> bool:
    up, srv_interactive, srv_build = _check_server_health()
    caller_interactive = bool(user32.GetForegroundWindow())
    if up:
        if srv_build != REQUIRED_BUILD:
            log_msg(f"Upgrading PitWall server from '{srv_build or 'legacy'}' -> '{REQUIRED_BUILD}' ...")
            _kill_port_8765()
        elif caller_interactive and not srv_interactive:
            log_msg("Upgrading PitWall server onto interactive desktop for game Spacebar control ...")
            _kill_port_8765()
        else:
            return True
    log_msg("Starting silent Pit Wall telemetry server on 127.0.0.1:8765 ...")
    subprocess.Popen(
        [get_pythonw(), SERVER_SCRIPT],
        cwd=ROOT_DIR,
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        if is_server_up(timeout=0.35):
            log_msg("Pit Wall server is online.")
            return True
        time.sleep(0.12)
    log_msg("WARNING: Pit Wall server did not respond within 6s.")
    return False


def focus_existing_app_window() -> bool:
    found_hwnd = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if WINDOW_TITLE_FRAGMENT.lower() in buf.value.lower():
            found_hwnd.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_cb, 0)
    if not found_hwnd:
        return False
    hwnd = found_hwnd[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def find_app_browser() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def launch_desktop_app_window() -> None:
    ensure_server_running()
    if focus_existing_app_window():
        log_msg("Focused existing Pit Wall Desktop App window.")
        return

    browser_exe = find_app_browser()
    if browser_exe:
        os.makedirs(APP_PROFILE_DIR, exist_ok=True)
        cmd = [
            browser_exe,
            f"--user-data-dir={APP_PROFILE_DIR}",
            f"--app={APP_URL}",
            "--start-maximized",
            "--window-size=1920,1040",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-ipc-flooding-protection",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
        ]
        subprocess.Popen(
            cmd,
            cwd=ROOT_DIR,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        log_msg(f"Opened standalone Pit Wall Desktop App via {os.path.basename(browser_exe)}.")
    else:
        webbrowser.open(APP_URL)
        log_msg("Opened Pit Wall in default browser.")


def ensure_watcher_running() -> None:
    subprocess.Popen(
        [get_pythonw(), os.path.abspath(__file__), "--watch"],
        cwd=ROOT_DIR,
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def stop_watcher() -> None:
    if os.path.isfile(WATCHER_PID_FILE):
        try:
            pid = int(open(WATCHER_PID_FILE, encoding="utf-8").read().strip())
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except Exception:
            pass
        try:
            os.remove(WATCHER_PID_FILE)
        except OSError:
            pass


def run_watch_loop() -> None:
    mutex = kernel32.CreateMutexW(None, False, "Local\\BackseatPitWallWatcher_v1")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return

    try:
        with open(WATCHER_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    log_msg(f"Watcher active (PID {os.getpid()}) — monitoring for BackseatChampions.exe ...")
    was_running = False
    last_launch_ts = 0.0

    try:
        while True:
            running = is_game_running()
            if running and not was_running:
                now = time.monotonic()
                if now - last_launch_ts > 6.0:
                    last_launch_ts = now
                    log_msg("Detected BackseatChampions.exe launch! Popping up Pit Wall Desktop App ...")
                    launch_desktop_app_window()
            was_running = running
            time.sleep(1.0)
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backseat Pit Wall Desktop Companion")
    parser.add_argument("--watch", action="store_true", help="Run silent game-launch watcher daemon")
    parser.add_argument("--launch", action="store_true", help="Open Pit Wall Desktop App window now")
    parser.add_argument("--launch-both", action="store_true", help="Start Backseat Champions + Pit Wall App")
    parser.add_argument("--stop", action="store_true", help="Stop background watcher")
    args = parser.parse_args()

    if args.stop:
        stop_watcher()
        return

    if args.watch:
        run_watch_loop()
        return

    if args.launch_both:
        os.startfile(STEAM_RUN_URL)
        launch_desktop_app_window()
        ensure_watcher_running()
        return

    # Default or --launch: open Pit Wall Desktop App & make sure watcher is armed
    launch_desktop_app_window()
    ensure_watcher_running()


if __name__ == "__main__":
    main()
