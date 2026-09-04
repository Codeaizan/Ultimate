"""
topmost_window.py
==================
Premium dark-themed floating window that stays on top of all other windows.
Uses tkinter (built-in) + Win32 API via ctypes for aggressive topmost enforcement.

No external dependencies.
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import ctypes
import ctypes.wintypes as wintypes
import os
import time
import threading

# ─── Win32 API Constants ─────────────────────────────────────────────────

HWND_TOPMOST    = -1
HWND_NOTOPMOST  = -2
SWP_NOMOVE      = 0x0002
SWP_NOSIZE      = 0x0001
SWP_NOACTIVATE  = 0x0010
SWP_SHOWWINDOW  = 0x0040

GWL_EXSTYLE     = -20
WS_EX_TOPMOST   = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED   = 0x00080000

LWA_ALPHA       = 0x00000002

# Process priority classes
REALTIME_PRIORITY_CLASS     = 0x00000100
HIGH_PRIORITY_CLASS         = 0x00000080
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000

# ─── Win32 API Bindings ──────────────────────────────────────────────────

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long

user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long

user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

kernel32.GetCurrentProcess.argtypes = []
kernel32.GetCurrentProcess.restype = wintypes.HANDLE

kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetPriorityClass.restype = wintypes.BOOL


# ─── Color Palette ────────────────────────────────────────────────────────

class Colors:
    """Premium dark theme color palette."""
    BG_DEEP         = "#080b12"
    BG_PRIMARY      = "#0d1117"
    BG_SECONDARY    = "#161b22"
    BG_CARD         = "#1c2333"
    BG_CARD_HOVER   = "#242d3d"
    BORDER          = "#30363d"
    BORDER_ACCENT   = "#7c3aed"

    TEXT_PRIMARY     = "#e6edf3"
    TEXT_SECONDARY   = "#8b949e"
    TEXT_MUTED       = "#484f58"

    ACCENT_PURPLE    = "#7c3aed"
    ACCENT_BLUE      = "#58a6ff"
    ACCENT_CYAN      = "#39d4e0"

    SUCCESS          = "#3fb950"
    WARNING          = "#d29922"
    ERROR            = "#f85149"

    GRADIENT_START   = "#7c3aed"
    GRADIENT_END     = "#3b82f6"

    TITLE_BAR        = "#0d1117"
    TITLE_BAR_BTN    = "#8b949e"
    CLOSE_HOVER      = "#da3633"
    MINIMIZE_HOVER   = "#30363d"


# ─── TopMost Window ──────────────────────────────────────────────────────

class TopMostWindow:
    """
    A premium, dark-themed floating window that aggressively stays
    on top of all other windows using Win32 API enforcement.
    """

    REASSERT_INTERVAL_MS = 500  # Re-assert topmost every 500ms
    DEFAULT_WIDTH  = 480
    DEFAULT_HEIGHT = 580
    MIN_WIDTH      = 380
    MIN_HEIGHT     = 400
    TITLE_BAR_HEIGHT = 38

    def __init__(self, driver_interface=None):
        """
        Args:
            driver_interface: Optional DriverInterface instance for
                              kernel-level priority boosting.
        """
        self.driver = driver_interface
        self.driver_connected = False
        self.driver_status = None
        self._hwnd = None
        self._is_dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._opacity = 245  # 0-255, slightly transparent
        self._reassert_active = True
        self._pulse_phase = 0

        self._build_ui()

    def _build_ui(self):
        """Construct the window and all UI elements."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide during construction

        # ── Window Configuration ──
        self.root.title("TopMost Shield")
        self.root.geometry(f"{self.DEFAULT_WIDTH}x{self.DEFAULT_HEIGHT}")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.root.configure(bg=Colors.BG_PRIMARY)
        self.root.overrideredirect(True)  # Remove default title bar

        # ── Custom Title Bar ──
        self._build_title_bar()

        # ── Main Content Area ──
        self._build_content()

        # ── Status Bar ──
        self._build_status_bar()

        # ── Make Resizable (with custom title bar) ──
        self._setup_resize_handles()

        # Show window
        self.root.deiconify()
        self.root.update_idletasks()

        # Center on screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - self.DEFAULT_WIDTH) // 2
        y = (screen_h - self.DEFAULT_HEIGHT) // 2
        self.root.geometry(f"+{x}+{y}")

    def _build_title_bar(self):
        """Create a custom dark title bar with drag support."""
        self.title_bar = tk.Frame(
            self.root,
            bg=Colors.TITLE_BAR,
            height=self.TITLE_BAR_HEIGHT,
            cursor="arrow"
        )
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)

        # Accent line at top
        accent_line = tk.Frame(self.title_bar, bg=Colors.ACCENT_PURPLE, height=2)
        accent_line.pack(fill=tk.X, side=tk.TOP)

        # Title icon & text container
        title_container = tk.Frame(self.title_bar, bg=Colors.TITLE_BAR)
        title_container.pack(side=tk.LEFT, padx=12, fill=tk.Y)

        # Shield icon (Unicode)
        shield_label = tk.Label(
            title_container,
            text="🛡",
            bg=Colors.TITLE_BAR,
            fg=Colors.ACCENT_PURPLE,
            font=("Segoe UI Emoji", 12),
        )
        shield_label.pack(side=tk.LEFT, pady=2)

        title_label = tk.Label(
            title_container,
            text="TopMost Shield",
            bg=Colors.TITLE_BAR,
            fg=Colors.TEXT_PRIMARY,
            font=("Segoe UI Semibold", 10),
        )
        title_label.pack(side=tk.LEFT, padx=(6, 0), pady=2)

        # ── Window Control Buttons ──
        btn_frame = tk.Frame(self.title_bar, bg=Colors.TITLE_BAR)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Minimize button
        self.btn_minimize = tk.Label(
            btn_frame, text="─", bg=Colors.TITLE_BAR,
            fg=Colors.TITLE_BAR_BTN,
            font=("Segoe UI", 11), width=4, cursor="hand2"
        )
        self.btn_minimize.pack(side=tk.LEFT, fill=tk.Y)
        self.btn_minimize.bind("<Enter>",
            lambda e: self.btn_minimize.configure(bg=Colors.MINIMIZE_HOVER))
        self.btn_minimize.bind("<Leave>",
            lambda e: self.btn_minimize.configure(bg=Colors.TITLE_BAR))
        self.btn_minimize.bind("<Button-1>", self._on_minimize)

        # Close button
        self.btn_close = tk.Label(
            btn_frame, text="✕", bg=Colors.TITLE_BAR,
            fg=Colors.TITLE_BAR_BTN,
            font=("Segoe UI", 11), width=4, cursor="hand2"
        )
        self.btn_close.pack(side=tk.LEFT, fill=tk.Y)
        self.btn_close.bind("<Enter>",
            lambda e: self.btn_close.configure(bg=Colors.CLOSE_HOVER, fg="#ffffff"))
        self.btn_close.bind("<Leave>",
            lambda e: self.btn_close.configure(bg=Colors.TITLE_BAR, fg=Colors.TITLE_BAR_BTN))
        self.btn_close.bind("<Button-1>", self._on_close)

        # ── Drag Bindings ──
        for widget in [self.title_bar, title_container, title_label, shield_label]:
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)

    def _build_content(self):
        """Build the main content area with status cards."""
        # Main container with padding
        self.content_frame = tk.Frame(self.root, bg=Colors.BG_PRIMARY)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 8))

        # ── Driver Status Card ──
        self._build_driver_card()

        # ── Spacer ──
        tk.Frame(self.content_frame, bg=Colors.BG_PRIMARY, height=12).pack(fill=tk.X)

        # ── Window Info Card ──
        self._build_window_card()

        # ── Spacer ──
        tk.Frame(self.content_frame, bg=Colors.BG_PRIMARY, height=12).pack(fill=tk.X)

        # ── Blank Content Area (for user customization) ──
        self._build_blank_area()

    def _create_card(self, parent, title) -> tk.Frame:
        """Create a styled card with a header."""
        # Outer frame with border
        outer = tk.Frame(parent, bg=Colors.BORDER, padx=1, pady=1)
        outer.pack(fill=tk.X)

        card = tk.Frame(outer, bg=Colors.BG_CARD, padx=16, pady=12)
        card.pack(fill=tk.X)

        # Card header
        header = tk.Label(
            card, text=title, bg=Colors.BG_CARD,
            fg=Colors.TEXT_SECONDARY,
            font=("Segoe UI Semibold", 9),
            anchor="w"
        )
        header.pack(fill=tk.X)

        # Separator line
        sep = tk.Frame(card, bg=Colors.BORDER, height=1)
        sep.pack(fill=tk.X, pady=(6, 8))

        return card

    def _build_driver_card(self):
        """Build the kernel driver status card."""
        card = self._create_card(self.content_frame, "KERNEL DRIVER")

        # Status row
        status_row = tk.Frame(card, bg=Colors.BG_CARD)
        status_row.pack(fill=tk.X, pady=(0, 4))

        self.driver_status_dot = tk.Label(
            status_row, text="●", bg=Colors.BG_CARD,
            fg=Colors.TEXT_MUTED,
            font=("Segoe UI", 14),
        )
        self.driver_status_dot.pack(side=tk.LEFT)

        self.driver_status_label = tk.Label(
            status_row, text="NOT CONNECTED",
            bg=Colors.BG_CARD, fg=Colors.TEXT_MUTED,
            font=("Segoe UI Semibold", 11),
            anchor="w"
        )
        self.driver_status_label.pack(side=tk.LEFT, padx=(6, 0))

        # Details
        self.driver_details_frame = tk.Frame(card, bg=Colors.BG_CARD)
        self.driver_details_frame.pack(fill=tk.X)

        self._driver_detail_labels = {}
        for key, label_text in [
            ("priority", "Priority"),
            ("pid", "Protected PID"),
            ("boosts", "Boost Count"),
            ("version", "Driver Version"),
        ]:
            row = tk.Frame(self.driver_details_frame, bg=Colors.BG_CARD)
            row.pack(fill=tk.X, pady=1)

            lbl = tk.Label(
                row, text=f"{label_text}:", bg=Colors.BG_CARD,
                fg=Colors.TEXT_MUTED, font=("Segoe UI", 9), anchor="w", width=16
            )
            lbl.pack(side=tk.LEFT)

            val = tk.Label(
                row, text="—", bg=Colors.BG_CARD,
                fg=Colors.TEXT_SECONDARY, font=("Segoe UI", 9), anchor="w"
            )
            val.pack(side=tk.LEFT)
            self._driver_detail_labels[key] = val

    def _build_window_card(self):
        """Build the window enforcement info card."""
        card = self._create_card(self.content_frame, "WINDOW ENFORCEMENT")

        info_items = [
            ("Mode", "ALWAYS ON TOP"),
            ("Z-Order", "HWND_TOPMOST"),
            ("Re-assert", f"Every {self.REASSERT_INTERVAL_MS}ms"),
            ("Priority Class", "REALTIME (kernel)"),
        ]

        for label_text, value_text in info_items:
            row = tk.Frame(card, bg=Colors.BG_CARD)
            row.pack(fill=tk.X, pady=1)

            lbl = tk.Label(
                row, text=f"{label_text}:", bg=Colors.BG_CARD,
                fg=Colors.TEXT_MUTED, font=("Segoe UI", 9), anchor="w", width=16
            )
            lbl.pack(side=tk.LEFT)

            val = tk.Label(
                row, text=value_text, bg=Colors.BG_CARD,
                fg=Colors.ACCENT_CYAN, font=("Segoe UI", 9), anchor="w"
            )
            val.pack(side=tk.LEFT)

    def _build_blank_area(self):
        """Build the blank content area for future customization."""
        outer = tk.Frame(self.content_frame, bg=Colors.BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        self.blank_area = tk.Frame(outer, bg=Colors.BG_SECONDARY)
        self.blank_area.pack(fill=tk.BOTH, expand=True)

        # Subtle placeholder text
        placeholder = tk.Label(
            self.blank_area,
            text="CONTENT AREA",
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT_MUTED,
            font=("Segoe UI", 10),
        )
        placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _build_status_bar(self):
        """Build the bottom status bar."""
        self.status_bar = tk.Frame(
            self.root, bg=Colors.BG_DEEP, height=28
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)

        # Left: topmost status
        self.topmost_indicator = tk.Label(
            self.status_bar, text="● TOPMOST ACTIVE",
            bg=Colors.BG_DEEP, fg=Colors.SUCCESS,
            font=("Segoe UI", 8), padx=12
        )
        self.topmost_indicator.pack(side=tk.LEFT)

        # Right: resize grip
        grip = tk.Label(
            self.status_bar, text="⠿",
            bg=Colors.BG_DEEP, fg=Colors.TEXT_MUTED,
            font=("Segoe UI", 10), padx=8,
            cursor="size_nw_se"
        )
        grip.pack(side=tk.RIGHT)
        grip.bind("<Button-1>", self._on_resize_start)
        grip.bind("<B1-Motion>", self._on_resize_motion)

    def _setup_resize_handles(self):
        """Set up window resize via edge dragging."""
        self._resize_data = {}

        # Bottom-right corner resize via status bar grip is handled separately
        # Here we add border sensitivity for edge resizing

        # Right edge
        right_edge = tk.Frame(self.root, bg=Colors.BG_PRIMARY, width=4, cursor="sb_h_double_arrow")
        right_edge.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        right_edge.bind("<Button-1>", lambda e: self._start_edge_resize(e, "right"))
        right_edge.bind("<B1-Motion>", lambda e: self._do_edge_resize(e, "right"))

        # Bottom edge
        bottom_edge = tk.Frame(self.root, bg=Colors.BG_PRIMARY, height=4, cursor="sb_v_double_arrow")
        bottom_edge.place(relx=0.0, rely=1.0, relwidth=1.0, anchor="sw")
        bottom_edge.bind("<Button-1>", lambda e: self._start_edge_resize(e, "bottom"))
        bottom_edge.bind("<B1-Motion>", lambda e: self._do_edge_resize(e, "bottom"))

    def _start_edge_resize(self, event, edge):
        self._resize_data[edge] = {
            "x": event.x_root,
            "y": event.y_root,
            "w": self.root.winfo_width(),
            "h": self.root.winfo_height(),
        }

    def _do_edge_resize(self, event, edge):
        data = self._resize_data.get(edge)
        if not data:
            return

        if edge == "right":
            new_w = max(self.MIN_WIDTH, data["w"] + (event.x_root - data["x"]))
            self.root.geometry(f"{new_w}x{self.root.winfo_height()}")
        elif edge == "bottom":
            new_h = max(self.MIN_HEIGHT, data["h"] + (event.y_root - data["y"]))
            self.root.geometry(f"{self.root.winfo_width()}x{new_h}")

    # ─── Window Events ────────────────────────────────────────────────────

    def _on_drag_start(self, event):
        self._is_dragging = True
        self._drag_start_x = event.x_root - self.root.winfo_x()
        self._drag_start_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event):
        if self._is_dragging:
            x = event.x_root - self._drag_start_x
            y = event.y_root - self._drag_start_y
            self.root.geometry(f"+{x}+{y}")

    def _on_drag_end(self, event):
        self._is_dragging = False

    def _on_resize_start(self, event):
        self._resize_data["grip"] = {
            "x": event.x_root,
            "y": event.y_root,
            "w": self.root.winfo_width(),
            "h": self.root.winfo_height(),
        }

    def _on_resize_motion(self, event):
        data = self._resize_data.get("grip")
        if not data:
            return
        new_w = max(self.MIN_WIDTH, data["w"] + (event.x_root - data["x"]))
        new_h = max(self.MIN_HEIGHT, data["h"] + (event.y_root - data["y"]))
        self.root.geometry(f"{new_w}x{new_h}")

    def _on_minimize(self, event):
        self.root.iconify()

    def _on_close(self, event):
        self._reassert_active = False
        if self.driver and self.driver.is_connected:
            try:
                self.driver.reset_priority()
                self.driver.disconnect()
            except Exception:
                pass
        self.root.destroy()

    # ─── Win32 Topmost Enforcement ────────────────────────────────────────

    def _get_hwnd(self) -> int:
        """Get the Win32 HWND for this tkinter window."""
        if self._hwnd is None:
            # winfo_id() returns the inner Tk widget HWND.
            # GetParent() gives us the actual top-level window HWND.
            inner_hwnd = self.root.winfo_id()
            parent = user32.GetParent(inner_hwnd)
            # Walk up to the top-level window
            while parent:
                self._hwnd = parent
                parent = user32.GetParent(parent)
            if self._hwnd is None or self._hwnd == 0:
                self._hwnd = inner_hwnd
        return self._hwnd

    def _assert_topmost(self):
        """Force the window to the topmost Z-order position."""
        try:
            hwnd = self._get_hwnd()
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def _set_process_priority(self):
        """Set the process priority to the highest possible via user-mode API."""
        try:
            handle = kernel32.GetCurrentProcess()
            # Try REALTIME first (requires admin), fall back to HIGH
            if not kernel32.SetPriorityClass(handle, REALTIME_PRIORITY_CLASS):
                kernel32.SetPriorityClass(handle, HIGH_PRIORITY_CLASS)
        except Exception:
            pass

    def _set_window_styles(self):
        """Apply extended window styles for topmost behavior."""
        try:
            hwnd = self._get_hwnd()
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            # Note: We skip WS_EX_LAYERED to avoid invisibility issues.
            # Transparency can be re-enabled once the window is confirmed visible.
        except Exception:
            pass

    # ─── Driver Communication ─────────────────────────────────────────────

    def _connect_driver(self):
        """Attempt to connect to the kernel driver."""
        if self.driver is None:
            return

        try:
            if self.driver.connect():
                self.driver_connected = True
                # Request priority boost from kernel
                status = self.driver.boost_priority()
                if status:
                    self.driver_status = status
                # Register our PID for protection
                pid = os.getpid()
                self.driver.set_protected_pid(pid)
                self._update_driver_ui(connected=True, status=status)
            else:
                self._update_driver_ui(connected=False)
        except Exception as e:
            print(f"[TopMostWindow] Driver connection failed: {e}")
            self._update_driver_ui(connected=False)

    def _update_driver_ui(self, connected: bool, status=None):
        """Update the driver status card UI."""
        if connected:
            self.driver_status_dot.configure(fg=Colors.SUCCESS)
            self.driver_status_label.configure(
                text="CONNECTED", fg=Colors.SUCCESS)

            if status:
                self._driver_detail_labels["priority"].configure(
                    text=f"Level {status.current_priority} (REALTIME)",
                    fg=Colors.ACCENT_CYAN)
                self._driver_detail_labels["pid"].configure(
                    text=str(status.protected_pid),
                    fg=Colors.TEXT_PRIMARY)
                self._driver_detail_labels["boosts"].configure(
                    text=str(status.boost_count),
                    fg=Colors.TEXT_PRIMARY)
                self._driver_detail_labels["version"].configure(
                    text=status.version_string,
                    fg=Colors.TEXT_PRIMARY)
        else:
            self.driver_status_dot.configure(fg=Colors.WARNING)
            self.driver_status_label.configure(
                text="FALLBACK MODE", fg=Colors.WARNING)
            self._driver_detail_labels["priority"].configure(
                text="HIGH (user-mode)", fg=Colors.WARNING)
            self._driver_detail_labels["pid"].configure(
                text=str(os.getpid()), fg=Colors.TEXT_SECONDARY)
            self._driver_detail_labels["boosts"].configure(
                text="N/A", fg=Colors.TEXT_MUTED)
            self._driver_detail_labels["version"].configure(
                text="N/A", fg=Colors.TEXT_MUTED)

    # ─── Reassert Timer ──────────────────────────────────────────────────

    def _start_reassert_timer(self):
        """Start the periodic topmost re-assertion timer."""
        def _tick():
            if not self._reassert_active:
                return
            self._assert_topmost()
            self._animate_pulse()
            self.root.after(self.REASSERT_INTERVAL_MS, _tick)

        self.root.after(self.REASSERT_INTERVAL_MS, _tick)

    def _animate_pulse(self):
        """Subtle pulse animation on the status indicator."""
        self._pulse_phase = (self._pulse_phase + 1) % 20
        if self._pulse_phase < 10:
            alpha = 180 + (self._pulse_phase * 8)  # Fade in
        else:
            alpha = 180 + ((20 - self._pulse_phase) * 8)  # Fade out

        # We can't easily animate tkinter label opacity, so we alternate
        # between two shades of green
        if self._pulse_phase < 10:
            self.topmost_indicator.configure(fg=Colors.SUCCESS)
        else:
            self.topmost_indicator.configure(fg="#2d8a3e")

    # ─── Deactivation Handler ────────────────────────────────────────────

    def _on_deactivate(self, event):
        """Immediately re-assert topmost when another window takes focus."""
        if self._reassert_active:
            self.root.after(50, self._assert_topmost)

    # ─── Public API ──────────────────────────────────────────────────────

    def run(self):
        """Start the window and enter the main event loop."""
        # Apply Win32 topmost enforcement
        self.root.update_idletasks()
        self._set_process_priority()
        
        # Set tkinter-level topmost FIRST (most reliable)
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        
        # Then apply Win32 styles and topmost
        self._set_window_styles()
        self._assert_topmost()

        # Force to foreground
        try:
            hwnd = self._get_hwnd()
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        except Exception:
            pass

        # Connect to kernel driver (non-blocking)
        self._connect_driver()

        # Start the reassert timer
        self._start_reassert_timer()

        # Bind deactivation handler
        self.root.bind("<FocusOut>", self._on_deactivate)

        # Enter main loop
        self.root.mainloop()

    def get_blank_area(self) -> tk.Frame:
        """
        Returns the blank content area frame for adding custom widgets.
        Use this to add your own UI elements to the window.
        """
        return self.blank_area
