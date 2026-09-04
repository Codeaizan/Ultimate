"""
TopMost Shield - Silent Launcher
Hides its own console window immediately, then runs the browser.
"""
import sys
import os
import ctypes

# ─── HIDE CONSOLE WINDOW IMMEDIATELY ─────────────────────────────────────
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
hwnd_console = kernel32.GetConsoleWindow()
if hwnd_console:
    user32.ShowWindow(hwnd_console, 0)  # 0 = SW_HIDE

# ─── Setup paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(SCRIPT_DIR, "app")
sys.path.insert(0, APP_DIR)
os.chdir(SCRIPT_DIR)

# ─── Fix stdout/stderr for .pyw mode (they can be None) ──────────────────
log_path = os.path.join(SCRIPT_DIR, "topmost_shield.log")
try:
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    if sys.stdout is None or not hasattr(sys.stdout, 'write'):
        sys.stdout = log_file
        sys.stderr = log_file
    elif hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

# ─── Run ──────────────────────────────────────────────────────────────────
try:
    from driver_interface import DriverInterface
    from driver_installer import DriverInstaller
    from browser_window import launch_browser

    # Connect to driver
    driver = None
    try:
        installer = DriverInstaller()
        status = installer.status()
        if status["installed"] and not status["running"]:
            installer.start()
        if status["installed"]:
            driver = DriverInterface()
            if not driver.connect():
                driver = None
    except Exception:
        driver = None

    # Launch
    launch_browser(driver_interface=driver)

    # Cleanup
    if driver and driver.is_connected:
        driver.reset_priority()
        driver.disconnect()

except Exception as e:
    # Write crash info so we can debug
    try:
        import traceback
        with open(os.path.join(SCRIPT_DIR, "crash.log"), "w") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass
