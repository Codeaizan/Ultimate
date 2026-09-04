"""
browser_window.py
==================
AI browser with transparency control, hotkeys, and capture protection.
"""

import webview
import threading
import ctypes
import ctypes.wintypes as wintypes
import os
import time
import json
import keyboard

# ─── Win32 API ────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
LWA_ALPHA = 0x00000002
WDA_EXCLUDEFROMCAPTURE = 0x00000011
WDA_MONITOR = 0x00000001
SW_HIDE = 0
SW_SHOW = 5

user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long

user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long

user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_byte, wintypes.DWORD
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.IsWindowVisible = ctypes.windll.user32.IsWindowVisible
user32.EnumWindows = ctypes.windll.user32.EnumWindows
user32.GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

REALTIME_PRIORITY_CLASS = 0x00000100
HIGH_PRIORITY_CLASS = 0x00000080


# ─── AI Services ─────────────────────────────────────────────────────────

AI_SERVICES = {
    "chatgpt": {"name": "ChatGPT", "url": "https://chatgpt.com", "color": "#10a37f"},
    "gemini": {"name": "Gemini", "url": "https://gemini.google.com", "color": "#4285f4"},
    "claude": {"name": "Claude", "url": "https://claude.ai", "color": "#d4956a"},
}


# ─── Landing Page ─────────────────────────────────────────────────────────

LANDING_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        background: #0d1117; color: #e6edf3;
        font-family: 'Segoe UI', system-ui, sans-serif;
        height: 100vh; display: flex;
        align-items: center; justify-content: center;
    }
    .container { text-align: center; max-width: 600px; padding: 40px; }
    h1 { font-size: 28px; margin-bottom: 8px; color: #7c3aed; }
    .subtitle { color: #8b949e; font-size: 14px; margin-bottom: 40px; }
    .cards { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
    .card {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px;
        padding: 24px 32px; cursor: pointer; transition: all 0.3s ease; min-width: 150px;
    }
    .card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
    .card-name { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
    .card-desc { font-size: 11px; color: #8b949e; }
    .badge {
        margin-top: 40px; display: inline-flex; align-items: center; gap: 8px;
        padding: 8px 16px; border-radius: 20px;
        background: rgba(63,185,80,0.1); border: 1px solid rgba(63,185,80,0.3);
        color: #3fb950; font-size: 11px; font-weight: 600;
    }
    .shortcuts {
        margin-top: 20px; color: #484f58; font-size: 11px; line-height: 1.8;
    }
    .shortcuts kbd {
        background: #21262d; border: 1px solid #30363d; border-radius: 4px;
        padding: 2px 6px; font-family: 'Segoe UI', monospace; color: #8b949e;
    }
</style>
</head>
<body>
    <div class="container">
        <h1>TopMost Shield</h1>
        <p class="subtitle">Kernel-enforced always-on-top AI browser</p>
        <div class="cards">
            <div class="card" id="btn-chatgpt">
                <div class="card-name" style="color:#10a37f">ChatGPT</div>
                <div class="card-desc">OpenAI</div>
            </div>
            <div class="card" id="btn-gemini">
                <div class="card-name" style="color:#4285f4">Gemini</div>
                <div class="card-desc">Google</div>
            </div>
            <div class="card" id="btn-claude">
                <div class="card-name" style="color:#d4956a">Claude</div>
                <div class="card-desc">Anthropic</div>
            </div>
        </div>
        <div class="badge">KERNEL DRIVER ACTIVE - TOPMOST ENFORCED</div>
        <div class="shortcuts">
            <kbd>P+L+,</kbd> Hide / Show &nbsp;&nbsp;
            <kbd>Ctrl+Shift+Up</kbd> Less transparent &nbsp;&nbsp;
            <kbd>Ctrl+Shift+Down</kbd> More transparent
        </div>
    </div>
    <script>
        window.addEventListener('pywebviewready', function() {
            document.getElementById('btn-chatgpt').onclick = function() {
                pywebview.api.navigate('chatgpt');
            };
            document.getElementById('btn-gemini').onclick = function() {
                pywebview.api.navigate('gemini');
            };
            document.getElementById('btn-claude').onclick = function() {
                pywebview.api.navigate('claude');
            };
        });
    </script>
</body>
</html>
"""


# ─── Back + Opacity Slider (injected into AI pages) ──────────────────────

CONTROLS_JS = """
(function() {
    if (document.getElementById('topmost-controls')) return;

    var panel = document.createElement('div');
    panel.id = 'topmost-controls';
    panel.style.cssText = 'position:fixed;top:8px;left:8px;z-index:2147483647;' +
        'display:flex;align-items:center;gap:8px;' +
        'background:rgba(13,17,23,0.9);border:1px solid #30363d;border-radius:8px;' +
        'padding:6px 12px;font-family:Segoe UI,sans-serif;box-shadow:0 2px 12px rgba(0,0,0,0.5);';

    // Back button
    var btn = document.createElement('div');
    btn.innerHTML = '&#9664; Home';
    btn.style.cssText = 'color:#7c3aed;font-size:12px;font-weight:600;cursor:pointer;' +
        'padding:2px 8px;border-radius:4px;transition:background 0.2s;';
    btn.onmouseenter = function() { btn.style.background = 'rgba(124,58,237,0.2)'; };
    btn.onmouseleave = function() { btn.style.background = 'none'; };
    btn.onclick = function() { pywebview.api.go_home(); };
    panel.appendChild(btn);

    // Separator
    var sep = document.createElement('div');
    sep.style.cssText = 'width:1px;height:16px;background:#30363d;';
    panel.appendChild(sep);

    // Opacity label
    var label = document.createElement('div');
    label.textContent = 'Opacity';
    label.style.cssText = 'color:#8b949e;font-size:11px;';
    panel.appendChild(label);

    // Opacity slider
    var slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '30';
    slider.max = '255';
    slider.value = '255';
    slider.style.cssText = 'width:80px;height:4px;cursor:pointer;accent-color:#7c3aed;';
    slider.oninput = function() {
        pywebview.api.set_opacity(parseInt(slider.value));
    };
    panel.appendChild(slider);

    document.body.appendChild(panel);
})();
"""


# ─── Global State ─────────────────────────────────────────────────────────

_window_hwnds = set()
_is_visible = True
_current_opacity = 255


# ─── API ──────────────────────────────────────────────────────────────────

class BrowserAPI:
    def __init__(self, window_ref):
        self._window_ref = window_ref
        self._pending_nav = None

    def navigate(self, service_key):
        if service_key in AI_SERVICES:
            self._pending_nav = service_key
            threading.Timer(0.1, self._do_navigate).start()

    def go_home(self):
        threading.Timer(0.1, self._do_go_home).start()

    def set_opacity(self, value):
        global _current_opacity
        _current_opacity = max(30, min(255, int(value)))
        _apply_opacity_to_all(_current_opacity)

    def _do_navigate(self):
        window = self._window_ref()
        if window and self._pending_nav:
            url = AI_SERVICES[self._pending_nav]["url"]
            print(f"[Browser] Navigating to {self._pending_nav}: {url}")
            window.load_url(url)
            time.sleep(3)
            try:
                window.evaluate_js(CONTROLS_JS)
            except Exception as e:
                print(f"[Browser] Controls injection failed: {e}")

    def _do_go_home(self):
        window = self._window_ref()
        if window:
            print("[Browser] Navigating home")
            window.load_html(LANDING_HTML)


# ─── Window Opacity ──────────────────────────────────────────────────────

def _make_layered(hwnd):
    """Enable WS_EX_LAYERED on a window so we can set opacity."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if not (ex & WS_EX_LAYERED):
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)


def _apply_opacity_to_all(alpha):
    """Set opacity on all tracked windows."""
    for hwnd in list(_window_hwnds):
        try:
            _make_layered(hwnd)
            user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
        except Exception:
            pass


# ─── Toggle Visibility ───────────────────────────────────────────────────

def _toggle_visibility():
    """Hide or show all app windows."""
    global _is_visible
    _is_visible = not _is_visible
    mode = SW_SHOW if _is_visible else SW_HIDE
    for hwnd in list(_window_hwnds):
        try:
            user32.ShowWindow(hwnd, mode)
            if _is_visible:
                # Re-assert topmost after showing
                user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                )
        except Exception:
            pass
    state = "visible" if _is_visible else "hidden"
    print(f"[Browser] Window {state}")


def _opacity_up():
    """Increase opacity by 25."""
    global _current_opacity
    _current_opacity = min(255, _current_opacity + 25)
    _apply_opacity_to_all(_current_opacity)
    print(f"[Browser] Opacity: {_current_opacity}/255")


def _opacity_down():
    """Decrease opacity by 25."""
    global _current_opacity
    _current_opacity = max(30, _current_opacity - 25)
    _apply_opacity_to_all(_current_opacity)
    print(f"[Browser] Opacity: {_current_opacity}/255")


# ─── Hotkeys ──────────────────────────────────────────────────────────────

def _register_hotkeys():
    """Register global keyboard shortcuts."""
    try:
        keyboard.add_hotkey('p+l+comma', _toggle_visibility)
        keyboard.add_hotkey('ctrl+shift+up', _opacity_up)
        keyboard.add_hotkey('ctrl+shift+down', _opacity_down)
        print("[Browser] Hotkeys registered:")
        print("[Browser]   P+L+,            = Toggle hide/show")
        print("[Browser]   Ctrl+Shift+Up    = Less transparent")
        print("[Browser]   Ctrl+Shift+Down  = More transparent")
    except Exception as e:
        print(f"[Browser] Hotkey registration failed: {e}")


# ─── Win32 Helpers ────────────────────────────────────────────────────────

def _find_window_by_pid(pid):
    result = []
    def callback(hwnd, _):
        tid_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid_pid))
        if tid_pid.value == pid and user32.IsWindowVisible(hwnd):
            result.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return result


def _enforce_topmost_loop():
    pid = os.getpid()
    time.sleep(2)
    protected = set()

    while True:
        try:
            for hwnd in _find_window_by_pid(pid):
                _window_hwnds.add(hwnd)

                if hwnd not in protected:
                    # First time seeing this HWND — apply all protections
                    # Hide from taskbar and Alt+Tab
                    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
                    user32.ShowWindow(hwnd, SW_HIDE)
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex)
                    user32.ShowWindow(hwnd, SW_SHOW)
                    user32.SetWindowPos(
                        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    )
                    # Capture protection
                    res = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
                    if not res:
                        user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
                    print(f"[Browser] Protected HWND 0x{hwnd:X} (hidden from taskbar)")
                    protected.add(hwnd)

            # Continuous topmost enforcement — only when visible
            if _is_visible:
                for hwnd in list(_window_hwnds):
                    try:
                        user32.SetWindowPos(
                            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(0.5)


def _set_process_priority():
    try:
        h = kernel32.GetCurrentProcess()
        if not kernel32.SetPriorityClass(h, REALTIME_PRIORITY_CLASS):
            kernel32.SetPriorityClass(h, HIGH_PRIORITY_CLASS)
    except Exception:
        pass


# ─── Launch ──────────────────────────────────────────────────────────────

def launch_browser(driver_interface=None):
    print("[Browser] Starting TopMost AI Browser...")

    _set_process_priority()
    _register_hotkeys()

    if driver_interface:
        try:
            driver_interface.boost_priority()
            driver_interface.set_protected_pid(os.getpid())
            print("[Browser] Kernel driver connected - REALTIME priority")
        except Exception as e:
            print(f"[Browser] Driver error: {e}")

    window = webview.create_window(
        title="TopMost Shield",
        html=LANDING_HTML,
        width=900,
        height=700,
        min_size=(600, 400),
        on_top=True,
        text_select=True,
    )

    api = BrowserAPI(lambda: window)
    window.expose(api.navigate)
    window.expose(api.go_home)
    window.expose(api.set_opacity)

    window.events.shown += lambda: threading.Thread(
        target=_enforce_topmost_loop, daemon=True
    ).start()

    print("[Browser] Launching window...")
    webview.start(debug=False)

    # Cleanup hotkeys
    try:
        keyboard.unhook_all()
    except Exception:
        pass

    print("[Browser] Closed.")


if __name__ == "__main__":
    launch_browser()
