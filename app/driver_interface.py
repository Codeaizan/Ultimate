r"""
driver_interface.py
====================
Pure-ctypes interface to the TopMost Shield kernel driver.
Communicates with \\.\TopMostDriver via DeviceIoControl.

No external dependencies — uses only the Python standard library.
"""

import ctypes
import ctypes.wintypes as wintypes
import struct
import os
from dataclasses import dataclass
from typing import Optional

# ─── Win32 Constants ──────────────────────────────────────────────────────

GENERIC_READ        = 0x80000000
GENERIC_WRITE       = 0x40000000
OPEN_EXISTING       = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# ─── IOCTL Codes (must match topmost_driver.h) ───────────────────────────

FILE_DEVICE_UNKNOWN = 0x00000022
METHOD_BUFFERED     = 0
FILE_ANY_ACCESS     = 0


def CTL_CODE(device_type, function, method, access):
    """Construct a Windows IOCTL code."""
    return (device_type << 16) | (access << 14) | (function << 2) | method


IOCTL_TOPMOST_BOOST_PRIORITY    = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_TOPMOST_RESET_PRIORITY    = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_TOPMOST_GET_STATUS        = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_TOPMOST_SET_PROTECTED_PID = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)

# ─── Device Path ──────────────────────────────────────────────────────────

DEVICE_PATH = r"\\.\TopMostDriver"

# ─── Status Structure ────────────────────────────────────────────────────

TOPMOST_STATUS_SIZE = 32  # 8 x ULONG = 32 bytes


@dataclass
class TopMostStatus:
    """Mirrors the TOPMOST_STATUS structure from the driver."""
    version: int = 0
    is_active: bool = False
    protected_pid: int = 0
    current_priority: int = 0
    boost_count: int = 0

    @property
    def version_major(self) -> int:
        return (self.version >> 16) & 0xFFFF

    @property
    def version_minor(self) -> int:
        return self.version & 0xFFFF

    @property
    def version_string(self) -> str:
        return f"{self.version_major}.{self.version_minor}"

    @classmethod
    def from_bytes(cls, data: bytes) -> "TopMostStatus":
        """Parse from raw bytes returned by DeviceIoControl."""
        if len(data) < 20:
            return cls()
        values = struct.unpack("<5I", data[:20])
        return cls(
            version=values[0],
            is_active=bool(values[1]),
            protected_pid=values[2],
            current_priority=values[3],
            boost_count=values[4],
        )


# ─── Win32 API Bindings ──────────────────────────────────────────────────

kernel32 = ctypes.windll.kernel32

# CreateFileW
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,   # lpFileName
    wintypes.DWORD,     # dwDesiredAccess
    wintypes.DWORD,     # dwShareMode
    ctypes.c_void_p,    # lpSecurityAttributes
    wintypes.DWORD,     # dwCreationDisposition
    wintypes.DWORD,     # dwFlagsAndAttributes
    wintypes.HANDLE,    # hTemplateFile
]
kernel32.CreateFileW.restype = wintypes.HANDLE

# DeviceIoControl
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,    # hDevice
    wintypes.DWORD,     # dwIoControlCode
    ctypes.c_void_p,    # lpInBuffer
    wintypes.DWORD,     # nInBufferSize
    ctypes.c_void_p,    # lpOutBuffer
    wintypes.DWORD,     # nOutBufferSize
    ctypes.POINTER(wintypes.DWORD),  # lpBytesReturned
    ctypes.c_void_p,    # lpOverlapped
]
kernel32.DeviceIoControl.restype = wintypes.BOOL

# CloseHandle
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

# GetLastError
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD


# ─── Driver Interface Class ──────────────────────────────────────────────

class DriverInterface:
    """
    Communicates with the TopMost Shield kernel driver via IOCTLs.

    Usage:
        driver = DriverInterface()
        if driver.connect():
            status = driver.boost_priority()
            print(f"Boosted! Priority: {status.current_priority}")
            driver.disconnect()
    """

    def __init__(self):
        self._handle: Optional[int] = None
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Check if we have a valid handle to the driver."""
        return self._connected and self._handle is not None

    def connect(self) -> bool:
        """
        Open a handle to the TopMost driver device.
        Returns True if successful, False if driver is not loaded.
        """
        if self._connected:
            return True

        try:
            handle = kernel32.CreateFileW(
                DEVICE_PATH,
                GENERIC_READ | GENERIC_WRITE,
                0,              # No sharing
                None,           # Default security
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None,           # No template
            )

            if handle == INVALID_HANDLE_VALUE or handle == 0:
                error = kernel32.GetLastError()
                print(f"[DriverInterface] Failed to connect: Win32 error {error}")
                if error == 2:
                    print("[DriverInterface] Driver device not found. Is the driver loaded?")
                elif error == 5:
                    print("[DriverInterface] Access denied. Run as Administrator.")
                return False

            self._handle = handle
            self._connected = True
            print(f"[DriverInterface] Connected to {DEVICE_PATH}")
            return True

        except Exception as e:
            print(f"[DriverInterface] Connection error: {e}")
            return False

    def disconnect(self):
        """Close the handle to the driver device."""
        if self._handle is not None:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            self._connected = False
            print("[DriverInterface] Disconnected")

    def _send_ioctl(
        self,
        ioctl_code: int,
        input_data: Optional[bytes] = None,
        output_size: int = TOPMOST_STATUS_SIZE,
    ) -> Optional[bytes]:
        """
        Send an IOCTL to the driver and return the output bytes.
        Returns None on failure.
        """
        if not self.is_connected:
            print("[DriverInterface] Not connected to driver")
            return None

        # Prepare input buffer
        in_buf = None
        in_size = 0
        if input_data:
            in_buf = ctypes.create_string_buffer(input_data)
            in_size = len(input_data)

        # Prepare output buffer
        out_buf = ctypes.create_string_buffer(output_size)
        bytes_returned = wintypes.DWORD(0)

        success = kernel32.DeviceIoControl(
            self._handle,
            ioctl_code,
            in_buf,
            in_size,
            out_buf,
            output_size,
            ctypes.byref(bytes_returned),
            None,
        )

        if not success:
            error = kernel32.GetLastError()
            print(f"[DriverInterface] IOCTL 0x{ioctl_code:08X} failed: Win32 error {error}")
            return None

        return out_buf.raw[:bytes_returned.value]

    def boost_priority(self) -> Optional[TopMostStatus]:
        """
        Request the driver to boost our process/thread to REALTIME priority.
        Returns the driver status or None on failure.
        """
        print("[DriverInterface] Requesting priority boost...")
        data = self._send_ioctl(IOCTL_TOPMOST_BOOST_PRIORITY)
        if data:
            status = TopMostStatus.from_bytes(data)
            print(f"[DriverInterface] Priority boosted (count: {status.boost_count})")
            return status
        return None

    def reset_priority(self) -> Optional[TopMostStatus]:
        """
        Request the driver to reset our priority back to normal.
        Returns the driver status or None on failure.
        """
        print("[DriverInterface] Requesting priority reset...")
        data = self._send_ioctl(IOCTL_TOPMOST_RESET_PRIORITY)
        if data:
            status = TopMostStatus.from_bytes(data)
            print("[DriverInterface] Priority reset")
            return status
        return None

    def get_status(self) -> Optional[TopMostStatus]:
        """
        Query the current driver status.
        Returns the driver status or None on failure.
        """
        data = self._send_ioctl(IOCTL_TOPMOST_GET_STATUS)
        if data:
            return TopMostStatus.from_bytes(data)
        return None

    def set_protected_pid(self, pid: int) -> Optional[TopMostStatus]:
        """
        Register a process ID for protection by the driver.
        Returns the driver status or None on failure.
        """
        print(f"[DriverInterface] Setting protected PID to {pid}...")
        input_data = struct.pack("<I", pid)
        data = self._send_ioctl(IOCTL_TOPMOST_SET_PROTECTED_PID, input_data)
        if data:
            status = TopMostStatus.from_bytes(data)
            print(f"[DriverInterface] Protected PID set to {status.protected_pid}")
            return status
        return None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def __del__(self):
        self.disconnect()
