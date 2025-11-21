#twentytw93-KronosTeam
import os
import time
import subprocess
import xbmc
import xbmcaddon
import xbmcgui
import shutil

xbmc.log("[Kronos Signal] Boot detected. Smart 21s delay engaged", xbmc.LOGINFO)

ADDON = xbmcaddon.Addon()
MON   = xbmc.Monitor()
HOME  = xbmcgui.Window(10000)
LOCK_KEY = "kronos.signal.lock"

if HOME.getProperty(LOCK_KEY) == "1":
    xbmc.log("[Kronos Signal] Another instance already running. Exiting.", xbmc.LOGWARNING)
    raise SystemExit
HOME.setProperty(LOCK_KEY, "1")

start_time = time.time()

while not xbmc.getCondVisibility("Window.IsVisible(home)"):
    if MON.waitForAbort(0.1):
        HOME.clearProperty(LOCK_KEY)
        raise SystemExit

while xbmc.getCondVisibility("System.HasActiveModalDialog"):
    if MON.waitForAbort(0.1):
        HOME.clearProperty(LOCK_KEY)
        raise SystemExit

elapsed_ms = int((time.time() - start_time) * 1000)
remaining_ms = max(0, 15000 - elapsed_ms)
if remaining_ms > 0 and MON.waitForAbort(remaining_ms / 1000.0):
    HOME.clearProperty(LOCK_KEY)
    raise SystemExit

REFRESH_INTERVAL = 5   # Delay between updates
VISIBLE_TIME    = 9    # How long each label stays on screen
BOOT_DELAY      = 3    # Delay before first label appears (after the smart boot logic above)

def _ip_cmd():
    candidates = (
        "/usr/sbin/ip",
        "/sbin/ip",
        "/bin/ip",
        "/usr/bin/ip",
    )
    for p in candidates:
        if os.path.exists(p):
            return p
    w = shutil.which("ip")
    return w if w else "/sbin/ip"

def _vpn_ifaces():
    try:
        names = os.listdir("/sys/class/net")
    except Exception:
        return []
    return [n for n in names if n.startswith(("tun", "wg")) or n in ("mullvad", "mullvad0")]

def _iface_has_ipv4(name):
    try:
        res = subprocess.run(
            [_ip_cmd(), "-o", "addr", "show", "dev", name],
            capture_output=True, text=True, timeout=1.0
        )
        return (res.returncode == 0) and (" inet " in res.stdout or res.stdout.startswith("inet "))
    except Exception:
        return False

def _iface_bytes(name):
    try:
        with open(f"/sys/class/net/{name}/statistics/rx_bytes", "r") as f:
            rx = int(f.read().strip())
        with open(f"/sys/class/net/{name}/statistics/tx_bytes", "r") as f:
            tx = int(f.read().strip())
        return rx, tx
    except Exception:
        return 0, 0

def get_vpn_status():
    ifaces = _vpn_ifaces()
    if not ifaces:
        return "VPN: off"
    for iface in ifaces:
        if _iface_has_ipv4(iface):
            try:
                rx1, tx1 = _iface_bytes(iface)
                time.sleep(0.5)
                rx2, tx2 = _iface_bytes(iface)
                if (rx2 - rx1) > 0 or (tx2 - tx1) > 0:
                    return "VPN: on"
            except Exception:
                pass
    return "VPN: idle"

def _read_cpu_times():
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu":
            return None
        vals = list(map(int, parts[1:]))
        idle = vals[3] + vals[4]
        total = sum(vals)
        return idle, total
    except Exception:
        return None

_last_cpu_idle = None
_last_cpu_total = None

def get_cpu_usage():
    global _last_cpu_idle, _last_cpu_total
    now = _read_cpu_times()
    if not now:
        return "CPU: n/a"
    idle, total = now
    if _last_cpu_idle is None or _last_cpu_total is None:
        _last_cpu_idle, _last_cpu_total = idle, total
        return "CPU: ..."
    idle_delta = idle - _last_cpu_idle
    total_delta = total - _last_cpu_total
    _last_cpu_idle, _last_cpu_total = idle, total
    if total_delta <= 0:
        return "CPU: n/a"
    usage = 100.0 * (1.0 - float(idle_delta) / float(total_delta))
    return "CPU: {:>3.0f}%".format(usage)

def _read_meminfo():
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                info[key] = int(val)
    except Exception:
        return {}
    return info

def get_ram_usage():
    info = _read_meminfo()
    if not info:
        return "RAM: n/a"
    mem_total_kb = info.get("MemTotal", 0)
    mem_avail_kb = info.get("MemAvailable", 0)
    if mem_total_kb <= 0:
        return "RAM: n/a"
    used = mem_total_kb - mem_avail_kb
    pct = 100.0 * used / float(mem_total_kb)
    return "RAM: {:>3.0f}%".format(pct)

def get_temp():
    paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
    ]
    for p in paths:
        try:
            with open(p, "r") as f:
                val = int(f.read().strip())
            c = val / 1000.0
            return "Temp: {:>4.1f}°C".format(c)
        except Exception:
            continue
    return "Temp: n/a"

def load_settings():
    return {
        "show_vpn": ADDON.getSettingBool("show_vpn"),
        "show_cpu": ADDON.getSettingBool("show_cpu"),
        "show_ram": ADDON.getSettingBool("show_ram"),
        "show_temp": ADDON.getSettingBool("show_temp"),
        "silent_mode": ADDON.getSettingBool("silent_mode"),
    }

def build_text(settings):
    lines = []
    row1 = []
    if settings["show_vpn"]:
        row1.append(get_vpn_status())
    if settings["show_cpu"]:
        row1.append(get_cpu_usage())
    if row1:
        lines.append(" | ".join(row1))
    row2 = []
    if settings["show_ram"]:
        row2.append(get_ram_usage())
    if settings["show_temp"]:
        row2.append(get_temp())
    if row2:
        lines.append(" | ".join(row2))
    return "\n".join(lines) if lines else ""

def show_overlay(text):
    try:
        window_id = xbmcgui.getCurrentWindowId()
        current_window = xbmcgui.Window(window_id)
        label = xbmcgui.ControlLabel(
            x=20, y=20,
            width=800,
            height=120,
            label=text,
            font="font10",
            textColor="0xFFFFFFFF",
            alignment=0
        )
        current_window.addControl(label)
        xbmc.sleep(VISIBLE_TIME * 1000)
        current_window.removeControl(label)
    except Exception as e:
        xbmc.log(f"[Kronos Signal] Overlay error: {e}", xbmc.LOGERROR)

try:
    xbmc.sleep(BOOT_DELAY * 1000)
    while not MON.abortRequested():
        s = load_settings()
        text = build_text(s)
        if text:
            if s.get("silent_mode") and xbmc.getCondVisibility("Player.HasVideo | Player.HasAudio"):
                xbmc.log("[Kronos Signal] Silent Mode: playback active, overlay suppressed", xbmc.LOGDEBUG)
            else:
                show_overlay(text)
        if MON.waitForAbort(REFRESH_INTERVAL):
            break
finally:
    HOME.clearProperty(LOCK_KEY)
    xbmc.log("[Kronos Signal] Clean shutdown, lock cleared", xbmc.LOGINFO)
