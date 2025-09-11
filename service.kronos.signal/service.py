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
BOOT_DELAY      = 3    # Delay before first label (on startup)

def _ip_cmd():
    for p in ("/sbin/ip", "/usr/sbin/ip", "/bin/ip", "/usr/bin/ip"):
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
            rx = int(f.read())
        with open(f"/sys/class/net/{name}/statistics/tx_bytes", "r") as f:
            tx = int(f.read())
        return rx + tx
    except Exception:
        return 0

def get_vpn_status():
    try:
        candidates = _vpn_ifaces()
        if not candidates:
            return "VPN:OFF"
        for iface in candidates:
            if _iface_has_ipv4(iface):
                return "VPN:ON"
            if _iface_bytes(iface) > 0:
                return "VPN:ON"
        return "VPN:INIT"
    except Exception:
        return "VPN:??"

_last_cpu = None
_last_time = 0

def get_cpu_usage():
    global _last_cpu, _last_time
    now = time.time()
    if _last_cpu and (now - _last_time) < 5:
        return _last_cpu
    try:
        with open("/proc/stat", "r") as f:
            v1 = list(map(int, f.readline().strip().split()[1:]))
        idle1, total1 = v1[3], sum(v1)
        time.sleep(0.05)
        with open("/proc/stat", "r") as f:
            v2 = list(map(int, f.readline().strip().split()[1:]))
        idle2, total2 = v2[3], sum(v2)
        td = total2 - total1
        if td > 0:
            usage = 100 * (1 - (idle2 - idle1) / float(td))
            _last_cpu = f"CPU:{int(usage)}%"
        else:
            _last_cpu = "CPU:0%"
    except Exception:
        _last_cpu = "CPU:??"
    _last_time = now
    return _last_cpu

def get_ram_usage():
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        mem_total = int([x for x in lines if x.startswith('MemTotal:')][0].split()[1])
        mem_avail = int([x for x in lines if x.startswith('MemAvailable:')][0].split()[1])
        used = mem_total - mem_avail
        return f"RAM:{used // 1024}MB/{mem_total // 1024}MB"
    except Exception:
        return "RAM:??"

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            t = int(f.read()) / 1000.0
        return f"Temp:{int(t)}°"
    except Exception:
        return "Temp:??"

def load_settings():
    return {
        "show_vpn": ADDON.getSettingBool("show_vpn"),
        "show_cpu": ADDON.getSettingBool("show_cpu"),
        "show_ram": ADDON.getSettingBool("show_ram"),
        "show_temp": ADDON.getSettingBool("show_temp"),
    }

def build_text(settings):
    lines = []
    row1 = []
    if settings["show_vpn"]:
        row1.append(get_vpn_status())
    if settings["show_cpu"]:
        row1.append(get_cpu_usage())
    if row1:
        lines.append("  ".join(row1))
    if settings["show_ram"]:
        lines.append(get_ram_usage())
    if settings["show_temp"]:
        lines.append(get_cpu_temp())
    return "\n".join(lines)

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
            show_overlay(text)
        if MON.waitForAbort(REFRESH_INTERVAL):
            break
finally:
    HOME.clearProperty(LOCK_KEY)
    xbmc.log("[Kronos Signal] Clean shutdown, lock cleared", xbmc.LOGINFO)