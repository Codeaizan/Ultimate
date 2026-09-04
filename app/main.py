"""
main.py
========
Entry point for TopMost Shield — the always-on-top AI browser
backed by a kernel driver for maximum priority enforcement.

Usage:
    python main.py              # Launch AI browser (default)
    python main.py --classic    # Launch the original panel window
    python main.py --no-driver  # Launch without driver connection

Must be run as Administrator for full functionality.
"""

import sys
import os
import ctypes
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from driver_interface import DriverInterface
from driver_installer import DriverInstaller

import io
# Ensure stdout can handle unicode
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def is_admin() -> bool:
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin():
    """Re-launch the current script with admin privileges via UAC prompt."""
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        sys.exit(0)
    except Exception as e:
        print(f"[TopMost] Failed to elevate: {e}")
        print("[TopMost] Continuing without admin privileges (limited functionality)")


def setup_driver(no_driver: bool = False) -> DriverInterface | None:
    """
    Attempt to connect to the kernel driver.
    Returns a connected DriverInterface or None.
    """
    if no_driver:
        print("[TopMost] Driver disabled by --no-driver flag")
        return None

    print("[TopMost] Checking kernel driver status...")
    installer = DriverInstaller()
    status = installer.status()

    if not status["installed"]:
        print("[TopMost] Driver is not installed.")
        print("[TopMost] To install, run: python app/driver_installer.py install")
        print("[TopMost] Continuing in user-mode fallback...")
        return None

    if not status["running"]:
        print("[TopMost] Driver is installed but not running. Attempting to start...")
        ok, msg = installer.start()
        if ok:
            print(f"[TopMost] {msg}")
        else:
            print(f"[TopMost] {msg}")
            print("[TopMost] Continuing in user-mode fallback...")
            return None

    # Driver is running — connect
    driver = DriverInterface()
    if driver.connect():
        print("[TopMost] Successfully connected to kernel driver!")
        return driver
    else:
        print("[TopMost] Failed to connect to driver. Continuing in fallback mode...")
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TopMost Shield — Always-on-top AI browser with kernel driver enforcement"
    )
    parser.add_argument(
        "--no-driver", action="store_true",
        help="Disable kernel driver connection (use user-mode enforcement only)"
    )
    parser.add_argument(
        "--no-elevate", action="store_true",
        help="Don't attempt to re-launch as administrator"
    )
    parser.add_argument(
        "--classic", action="store_true",
        help="Launch the classic panel window instead of the AI browser"
    )
    args = parser.parse_args()

    # Banner
    print("=" * 56)
    print("   [*] TopMost Shield v1.0")
    print("   Kernel-Enforced Always-On-Top AI Browser")
    print("=" * 56)
    print()

    # Check admin
    if is_admin():
        print("[TopMost] [OK] Running with administrator privileges")
    else:
        print("[TopMost] [!!] Not running as administrator")
        if not args.no_elevate:
            print("[TopMost] Requesting elevation via UAC...")
            relaunch_as_admin()
        else:
            print("[TopMost] Continuing without admin (limited functionality)")

    print()

    # Setup driver connection
    driver = setup_driver(no_driver=args.no_driver)

    print()

    if args.classic:
        # ── Classic panel mode ──
        from topmost_window import TopMostWindow
        print("[TopMost] Launching classic panel window...")
        window = TopMostWindow(driver_interface=driver)
        try:
            window.run()
        except KeyboardInterrupt:
            print("\n[TopMost] Interrupted. Shutting down...")
    else:
        # ── AI Browser mode (default) ──
        from browser_window import launch_browser
        print("[TopMost] Launching AI Browser...")
        print("[TopMost] Access ChatGPT, Gemini, and Claude — always on top!")
        print()
        try:
            launch_browser(driver_interface=driver)
        except KeyboardInterrupt:
            print("\n[TopMost] Interrupted. Shutting down...")

    # Cleanup
    if driver and driver.is_connected:
        driver.reset_priority()
        driver.disconnect()
    print("[TopMost] Goodbye!")


if __name__ == "__main__":
    main()
