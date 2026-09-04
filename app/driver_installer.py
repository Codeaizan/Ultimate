"""
driver_installer.py
====================
Manages installation, loading, and unloading of the TopMost Shield kernel driver
using sc.exe (Windows Service Control Manager).

Must be run with Administrator privileges.
"""

import subprocess
import os
import sys
import time
from typing import Optional, Tuple
from pathlib import Path


# ─── Constants ────────────────────────────────────────────────────────────

SERVICE_NAME    = "TopMostDriver"
DISPLAY_NAME    = "TopMost Shield Kernel Driver"
DRIVER_FILENAME = "topmost_driver.sys"


class DriverInstaller:
    """
    Manages the lifecycle of the TopMost Shield kernel driver.

    Operations:
        - install()   : Create the service entry + copy driver
        - start()     : Load the driver into kernel
        - stop()      : Unload the driver
        - uninstall() : Remove the service entry
        - status()    : Check if driver is installed/running
    """

    def __init__(self, driver_path: Optional[str] = None):
        """
        Args:
            driver_path: Absolute path to the .sys driver file.
                         If None, searches in the 'driver' subdirectory.
        """
        if driver_path:
            self.driver_path = Path(driver_path)
        else:
            # Default: look in driver/ relative to project root
            project_root = Path(__file__).parent.parent
            self.driver_path = project_root / "driver" / DRIVER_FILENAME

    @staticmethod
    def is_admin() -> bool:
        """Check if the current process has administrator privileges."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _run_sc(self, *args) -> Tuple[int, str, str]:
        """
        Run an sc.exe command and return (returncode, stdout, stderr).
        """
        cmd = ["sc.exe"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", "sc.exe not found"

    def status(self) -> dict:
        """
        Query the current status of the driver service.

        Returns:
            dict with keys: installed, running, state, details
        """
        ret, stdout, stderr = self._run_sc("query", SERVICE_NAME)

        result = {
            "installed": False,
            "running": False,
            "state": "NOT_INSTALLED",
            "details": stdout or stderr,
        }

        if ret != 0:
            # Service doesn't exist
            return result

        result["installed"] = True

        # Parse the state from sc query output
        for line in stdout.splitlines():
            line = line.strip()
            if "STATE" in line:
                if "RUNNING" in line:
                    result["running"] = True
                    result["state"] = "RUNNING"
                elif "STOPPED" in line:
                    result["state"] = "STOPPED"
                elif "START_PENDING" in line:
                    result["state"] = "START_PENDING"
                elif "STOP_PENDING" in line:
                    result["state"] = "STOP_PENDING"
                break

        return result

    def install(self) -> Tuple[bool, str]:
        """
        Install the driver as a kernel service.

        Returns:
            (success, message)
        """
        if not self.is_admin():
            return False, "Administrator privileges required. Run as Admin."

        if not self.driver_path.exists():
            return False, f"Driver file not found: {self.driver_path}"

        # Check if already installed
        current = self.status()
        if current["installed"]:
            return True, f"Driver already installed (state: {current['state']})"

        # Create the service
        # type= kernel  : This is a kernel-mode driver
        # start= demand : Start manually (not at boot)
        # binPath=       : Path to the .sys file
        driver_abs = str(self.driver_path.resolve())

        ret, stdout, stderr = self._run_sc(
            "create", SERVICE_NAME,
            f"type=", "kernel",
            f"start=", "demand",
            f"binPath=", driver_abs,
            f"DisplayName=", DISPLAY_NAME,
        )

        if ret == 0:
            return True, f"Driver installed successfully from {driver_abs}"
        else:
            return False, f"Failed to install driver: {stdout} {stderr}"

    def start(self) -> Tuple[bool, str]:
        """
        Start (load) the driver into the kernel.

        Returns:
            (success, message)
        """
        if not self.is_admin():
            return False, "Administrator privileges required. Run as Admin."

        current = self.status()
        if not current["installed"]:
            return False, "Driver is not installed. Call install() first."

        if current["running"]:
            return True, "Driver is already running."

        ret, stdout, stderr = self._run_sc("start", SERVICE_NAME)

        if ret == 0:
            # Wait a moment for the driver to initialize
            time.sleep(0.5)
            return True, "Driver started successfully"
        else:
            msg = stdout or stderr
            if "1275" in msg:
                return False, (
                    "Driver blocked by Windows. Enable test signing:\n"
                    "  bcdedit /set testsigning on\n"
                    "Then reboot and try again."
                )
            return False, f"Failed to start driver: {msg}"

    def stop(self) -> Tuple[bool, str]:
        """
        Stop (unload) the driver from the kernel.

        Returns:
            (success, message)
        """
        if not self.is_admin():
            return False, "Administrator privileges required. Run as Admin."

        current = self.status()
        if not current["running"]:
            return True, "Driver is not running."

        ret, stdout, stderr = self._run_sc("stop", SERVICE_NAME)

        if ret == 0:
            time.sleep(0.5)
            return True, "Driver stopped successfully"
        else:
            return False, f"Failed to stop driver: {stdout} {stderr}"

    def uninstall(self) -> Tuple[bool, str]:
        """
        Stop and remove the driver service entirely.

        Returns:
            (success, message)
        """
        if not self.is_admin():
            return False, "Administrator privileges required. Run as Admin."

        # Stop first if running
        current = self.status()
        if current["running"]:
            self.stop()
            time.sleep(1)

        if not current["installed"]:
            return True, "Driver is not installed."

        ret, stdout, stderr = self._run_sc("delete", SERVICE_NAME)

        if ret == 0:
            return True, "Driver uninstalled successfully"
        else:
            return False, f"Failed to uninstall driver: {stdout} {stderr}"

    def install_and_start(self) -> Tuple[bool, str]:
        """
        Convenience: install (if needed) then start the driver.

        Returns:
            (success, message)
        """
        success, msg = self.install()
        if not success:
            return False, msg

        success, msg = self.start()
        return success, msg

    @staticmethod
    def check_test_signing() -> bool:
        """Check if test signing mode is enabled."""
        try:
            result = subprocess.run(
                ["bcdedit", "/enum", "{current}"],
                capture_output=True, text=True, timeout=10
            )
            return "testsigning" in result.stdout.lower() and "yes" in result.stdout.lower()
        except Exception:
            return False

    @staticmethod
    def enable_test_signing() -> Tuple[bool, str]:
        """Enable test signing mode (requires reboot)."""
        try:
            result = subprocess.run(
                ["bcdedit", "/set", "testsigning", "on"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "Test signing enabled. Please reboot."
            return False, f"Failed: {result.stdout} {result.stderr}"
        except Exception as e:
            return False, f"Error: {e}"


# ─── CLI Interface ────────────────────────────────────────────────────────

def main():
    """CLI for managing the TopMost driver."""
    installer = DriverInstaller()

    if len(sys.argv) < 2:
        print("Usage: driver_installer.py <command>")
        print("Commands: install, start, stop, uninstall, status, enable-testsign")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "install":
        ok, msg = installer.install()
    elif command == "start":
        ok, msg = installer.start()
    elif command == "stop":
        ok, msg = installer.stop()
    elif command == "uninstall":
        ok, msg = installer.uninstall()
    elif command == "status":
        status = installer.status()
        print(f"  Installed: {status['installed']}")
        print(f"  Running:   {status['running']}")
        print(f"  State:     {status['state']}")
        print(f"  Details:   {status['details']}")
        sys.exit(0)
    elif command == "enable-testsign":
        ok, msg = installer.enable_test_signing()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    print(f"{'✓' if ok else '✗'} {msg}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
