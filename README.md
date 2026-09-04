# TopMost Shield

**Kernel-enforced always-on-top AI browser** — a native C++ application with a Windows kernel driver that provides an unkillable, invisible, always-on-top browser for accessing AI models (ChatGPT, Gemini, Claude) without API keys.

![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows)
![C++](https://img.shields.io/badge/C++-17-00599C?logo=cplusplus)
![WebView2](https://img.shields.io/badge/WebView2-Edge-4285F4?logo=microsoftedge)
![Driver](https://img.shields.io/badge/Kernel-WDM%20Driver-FF6F00)

---

## Features

| Feature | Description |
|---------|-------------|
| 🌐 **AI Browser** | Built-in WebView2 browser with ChatGPT, Gemini, and Claude |
| 📌 **Always-On-Top** | Kernel-level REALTIME priority enforcement |
| 🛡️ **Screen Capture Protection** | `WDA_EXCLUDEFROMCAPTURE` — invisible to screenshots and screen recording |
| 👻 **Stealth Mode** | Hidden from taskbar, Alt+Tab, and system tray |
| 🔒 **Process Protection** | Three-layer termination defense (kernel callbacks, DACL, watchdog) |
| 🎚️ **Transparency Control** | Adjustable window opacity via hotkeys or in-page slider |
| ⌨️ **Global Hotkeys** | System-wide keyboard shortcuts for all controls |
| ⚡ **Native C++** | 176 KB single executable — no runtime dependencies |

## Architecture

```
┌─────────────────────────────────────────────┐
│              User Mode (Acer.exe)           │
│                                             │
│  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Win32 Host  │  │  WebView2 Browser   │  │
│  │  - Hotkeys   │  │  - ChatGPT          │  │
│  │  - Opacity   │  │  - Gemini           │  │
│  │  - Stealth   │  │  - Claude           │  │
│  └──────┬───────┘  └─────────────────────┘  │
│         │                                   │
│  ┌──────┴───────┐  ┌─────────────────────┐  │
│  │ DACL Protect │  │  Watchdog Guard     │  │
│  │ (user-mode)  │  │  (auto-respawn)     │  │
│  └──────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────┤
│         Kernel Mode (topmost_driver.sys)    │
│                                             │
│  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Priority     │  │ ObRegisterCallbacks │  │
│  │ Boost (RT26) │  │ (handle stripping)  │  │
│  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `P + L + ,` | Toggle hide/show |
| `Ctrl + Shift + ↑` | Decrease transparency |
| `Ctrl + Shift + ↓` | Increase transparency |
| `Ctrl + Shift + Q` | Clean exit |

## Protection Layers

| Layer | Protects Against | Mechanism |
|-------|-----------------|-----------|
| **Kernel ObCallbacks** | Admin apps, Task Manager | Strips `PROCESS_TERMINATE` from handles at kernel level |
| **DACL** | Non-admin apps | Denies `PROCESS_TERMINATE` access to Everyone |
| **Watchdog** | Forced termination | Guard process auto-respawns the app in 0.5s |

## Project Structure

```
├── cpp/                        # C++ Application
│   ├── src/
│   │   └── main.cpp            # Full application source (~700 lines)
│   └── build.bat               # Auto-downloads WebView2 SDK & compiles
│
├── driver/                     # Windows Kernel Driver (WDM)
│   ├── topmost_driver.c        # Driver source with ObRegisterCallbacks
│   ├── topmost_driver.h        # Shared IOCTL definitions
│   ├── topmost.inf             # Driver installation INF
│   └── build_driver.bat        # Compiles driver with WDK
│
├── app/                        # Legacy Python implementation
│   ├── browser_window.py       # PyWebView browser (deprecated)
│   ├── driver_interface.py     # Python driver communication
│   ├── driver_installer.py     # Service management wrapper
│   └── main.py                 # Python entry point
│
├── install_driver.bat          # Driver certificate & installation
├── Launch.vbs                  # UAC elevation launcher
└── TopMostShield.pyw           # Python launcher (deprecated)
```

## Build Requirements

### Application (C++)
- **Visual Studio 2022** (Build Tools or Community) with C++ workload
- **WebView2 Runtime** (pre-installed on Windows 11)
- WebView2 SDK is auto-downloaded by `build.bat`

### Kernel Driver
- **Windows Driver Kit (WDK)** for Windows 10/11
- **Test Signing** enabled (`bcdedit /set testsigning on`)

## Build Instructions

### 1. Build the Application

```batch
cd cpp
build.bat
```

Output: `cpp/bin/Acer.exe` (176 KB native executable)

### 2. Build the Kernel Driver

```batch
cd driver
build_driver.bat
```

Output: `driver/build/topmost_driver.sys`

### 3. Install the Driver

```batch
:: Create and install a test signing certificate
install_driver.bat

:: Or manually:
:: 1. Create a self-signed certificate
makecert -r -pe -ss PrivateCertStore -n "CN=TopMost Shield Test" TopMostTest.cer
certutil -addstore Root TopMostTest.cer
certutil -addstore TrustedPublisher TopMostTest.cer

:: 2. Sign the driver
signtool sign /v /s PrivateCertStore /n "TopMost Shield Test" /fd sha256 driver/build/topmost_driver.sys

:: 3. Install and start
sc create TopMostDriver type= kernel binPath= "<full_path>\topmost_driver.sys"
sc start TopMostDriver
```

### 4. Run

Double-click `cpp/bin/Acer.exe` or use the Desktop shortcut.

## System Requirements

- Windows 10 (2004+) or Windows 11
- x64 architecture
- WebView2 Runtime (included in Windows 11)
- Administrator privileges (for driver installation)
- Test Signing mode enabled (for unsigned driver)

## Technical Details

### Stealth
- `WS_EX_TOOLWINDOW` — removes from taskbar and Alt+Tab
- `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` — invisible to screen capture
- Window title set to "Acer" — blends with system utilities

### Process Protection
- **ObRegisterCallbacks** intercepts `OpenProcess()` calls targeting our PID and strips `PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME` access rights from the handle before it's returned to the caller
- **DACL modification** adds an explicit DENY ACE for `PROCESS_TERMINATE` on the Everyone SID
- **Mutual watchdog** — main process and guard monitor each other; if either dies, the other respawns it

### Priority
- Kernel driver boosts thread priority to level 26 (REALTIME range)
- Process class set to `REALTIME_PRIORITY_CLASS`

## License

This project is for educational purposes only. Use responsibly and in accordance with applicable laws.

## Disclaimer

This software interacts with the Windows kernel and modifies process security descriptors. Use at your own risk. The authors are not responsible for any damage caused by the use of this software.
