/*
 * TopMost Shield — C++ Implementation
 * ====================================
 * Kernel-enforced always-on-top AI browser.
 * 
 * Features:
 *   - WebView2 browser (ChatGPT, Gemini, Claude)
 *   - Always-on-top enforcement
 *   - Screen capture protection (WDA_EXCLUDEFROMCAPTURE)
 *   - Hidden from taskbar and Alt+Tab
 *   - Transparency/opacity control
 *   - Global hotkeys (P+L+, toggle, Ctrl+Shift+Up/Down opacity)
 *   - Kernel driver integration (IOCTL)
 *   - No console window
 *
 * Build: build.bat
 */

#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <wrl.h>
#include <string>
#include <shlwapi.h>
#include <aclapi.h>
#include <shellapi.h>
#include "WebView2.h"

using namespace Microsoft::WRL;

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "version.lib")
#pragma comment(lib, "advapi32.lib")

// ─── IOCTL Codes (must match topmost_driver.h) ─────────────────────────

#define FILE_DEVICE_UNKNOWN     0x00000022
#define METHOD_BUFFERED         0
#define FILE_ANY_ACCESS         0
#define CTL_CODE_CUSTOM(func) \
    ((FILE_DEVICE_UNKNOWN << 16) | (FILE_ANY_ACCESS << 14) | ((func) << 2) | METHOD_BUFFERED)

#define IOCTL_TOPMOST_BOOST_PRIORITY    CTL_CODE_CUSTOM(0x800)
#define IOCTL_TOPMOST_RESET_PRIORITY    CTL_CODE_CUSTOM(0x801)
#define IOCTL_TOPMOST_SET_PROTECTED_PID CTL_CODE_CUSTOM(0x803)

// ─── Custom Messages ────────────────────────────────────────────────────

#define WM_TOGGLE_VISIBILITY (WM_USER + 1)
#define WM_OPACITY_UP        (WM_USER + 2)
#define WM_OPACITY_DOWN      (WM_USER + 3)

#define HOTKEY_OPACITY_UP    1
#define HOTKEY_OPACITY_DOWN  2
#define HOTKEY_EXIT          3

// ─── Global State ───────────────────────────────────────────────────────

static HWND                         g_hWnd = NULL;
static HINSTANCE                    g_hInstance = NULL;
static ICoreWebView2Controller*     g_controller = nullptr;
static ICoreWebView2*               g_webview = nullptr;
static HHOOK                        g_keyboardHook = NULL;
static HANDLE                       g_driverHandle = INVALID_HANDLE_VALUE;
static bool                         g_visible = true;
static int                          g_opacity = 255;
static bool                         g_onLandingPage = true;
static bool                         g_captureProtected = false;
static DWORD                        g_guardPid = 0;
static bool                         g_cleanExit = false;

// Key state tracking for P+L+, hotkey
static bool g_keyP = false;
static bool g_keyL = false;
static bool g_keyComma = false;

// ─── Landing Page HTML ──────────────────────────────────────────────────

static const wchar_t* LANDING_HTML = LR"HTML(
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
            <div class="card" onclick="window.chrome.webview.postMessage('navigate:chatgpt')">
                <div class="card-name" style="color:#10a37f">ChatGPT</div>
                <div class="card-desc">OpenAI</div>
            </div>
            <div class="card" onclick="window.chrome.webview.postMessage('navigate:gemini')">
                <div class="card-name" style="color:#4285f4">Gemini</div>
                <div class="card-desc">Google</div>
            </div>
            <div class="card" onclick="window.chrome.webview.postMessage('navigate:claude')">
                <div class="card-name" style="color:#d4956a">Claude</div>
                <div class="card-desc">Anthropic</div>
            </div>
        </div>
        <div class="badge">KERNEL DRIVER ACTIVE - TOPMOST ENFORCED</div>
        <div class="shortcuts">
            <kbd>P+L+,</kbd> Hide / Show &nbsp;&nbsp;
            <kbd>Ctrl+Shift+Up</kbd> Less transparent &nbsp;&nbsp;
            <kbd>Ctrl+Shift+Down</kbd> More transparent &nbsp;&nbsp;
            <kbd>Ctrl+Shift+Q</kbd> Exit
        </div>
    </div>
</body>
</html>
)HTML";

// ─── Controls JS (injected into AI pages) ───────────────────────────────

static const wchar_t* CONTROLS_JS = LR"JS(
(function() {
    if (document.getElementById('topmost-controls')) return;
    var panel = document.createElement('div');
    panel.id = 'topmost-controls';
    panel.style.cssText = 'position:fixed;top:8px;left:8px;z-index:2147483647;' +
        'display:flex;align-items:center;gap:8px;' +
        'background:rgba(13,17,23,0.92);border:1px solid #30363d;border-radius:8px;' +
        'padding:6px 12px;font-family:Segoe UI,sans-serif;box-shadow:0 2px 12px rgba(0,0,0,0.5);';

    var btn = document.createElement('div');
    btn.innerHTML = '&#9664; Home';
    btn.style.cssText = 'color:#7c3aed;font-size:12px;font-weight:600;cursor:pointer;' +
        'padding:2px 8px;border-radius:4px;transition:background 0.2s;';
    btn.onmouseenter = function() { btn.style.background = 'rgba(124,58,237,0.2)'; };
    btn.onmouseleave = function() { btn.style.background = 'none'; };
    btn.onclick = function() { window.chrome.webview.postMessage('go_home'); };
    panel.appendChild(btn);

    var sep = document.createElement('div');
    sep.style.cssText = 'width:1px;height:16px;background:#30363d;';
    panel.appendChild(sep);

    var label = document.createElement('div');
    label.textContent = 'Opacity';
    label.style.cssText = 'color:#8b949e;font-size:11px;';
    panel.appendChild(label);

    var slider = document.createElement('input');
    slider.type = 'range'; slider.min = '30'; slider.max = '255'; slider.value = '255';
    slider.style.cssText = 'width:80px;height:4px;cursor:pointer;accent-color:#7c3aed;';
    slider.oninput = function() {
        window.chrome.webview.postMessage('opacity:' + slider.value);
    };
    panel.appendChild(slider);

    document.body.appendChild(panel);
})();
)JS";

// ─── Driver Communication ───────────────────────────────────────────────

static bool DriverConnect() {
    g_driverHandle = CreateFileW(
        L"\\\\.\\TopMostDriver",
        GENERIC_READ | GENERIC_WRITE,
        0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL
    );
    return g_driverHandle != INVALID_HANDLE_VALUE;
}

static void DriverBoost() {
    if (g_driverHandle == INVALID_HANDLE_VALUE) return;
    BYTE buf[32] = {};
    DWORD ret = 0;
    DeviceIoControl(g_driverHandle, IOCTL_TOPMOST_BOOST_PRIORITY,
        NULL, 0, buf, sizeof(buf), &ret, NULL);
}

static void DriverSetPid(DWORD pid) {
    if (g_driverHandle == INVALID_HANDLE_VALUE) return;
    BYTE buf[32] = {};
    DWORD ret = 0;
    DeviceIoControl(g_driverHandle, IOCTL_TOPMOST_SET_PROTECTED_PID,
        &pid, sizeof(pid), buf, sizeof(buf), &ret, NULL);
}

static void DriverDisconnect() {
    if (g_driverHandle == INVALID_HANDLE_VALUE) return;
    BYTE buf[32] = {};
    DWORD ret = 0;
    DeviceIoControl(g_driverHandle, IOCTL_TOPMOST_RESET_PRIORITY,
        NULL, 0, buf, sizeof(buf), &ret, NULL);
    CloseHandle(g_driverHandle);
    g_driverHandle = INVALID_HANDLE_VALUE;
}

// ─── Process Termination Protection ─────────────────────────────────────

static void ProtectProcess() {
    // Deny PROCESS_TERMINATE to Everyone — other apps can't kill us
    HANDLE hProcess = GetCurrentProcess();

    // Build the "Everyone" SID
    SID_IDENTIFIER_AUTHORITY worldAuth = SECURITY_WORLD_SID_AUTHORITY;
    PSID pEveryoneSid = NULL;
    if (!AllocateAndInitializeSid(&worldAuth, 1, SECURITY_WORLD_RID,
            0, 0, 0, 0, 0, 0, 0, &pEveryoneSid)) return;

    // Create a DENY ACE for PROCESS_TERMINATE
    EXPLICIT_ACCESS ea = {};
    ea.grfAccessPermissions = PROCESS_TERMINATE;
    ea.grfAccessMode = DENY_ACCESS;
    ea.grfInheritance = NO_INHERITANCE;
    ea.Trustee.TrusteeForm = TRUSTEE_IS_SID;
    ea.Trustee.TrusteeType = TRUSTEE_IS_WELL_KNOWN_GROUP;
    ea.Trustee.ptstrName = (LPTSTR)pEveryoneSid;

    // Get current DACL
    PACL pOldDacl = NULL;
    PSECURITY_DESCRIPTOR pSD = NULL;
    GetSecurityInfo(hProcess, SE_KERNEL_OBJECT, DACL_SECURITY_INFORMATION,
        NULL, NULL, &pOldDacl, NULL, &pSD);

    // Merge deny entry into existing DACL
    PACL pNewDacl = NULL;
    SetEntriesInAcl(1, &ea, pOldDacl, &pNewDacl);

    // Apply the new DACL
    SetSecurityInfo(hProcess, SE_KERNEL_OBJECT, DACL_SECURITY_INFORMATION,
        NULL, NULL, pNewDacl, NULL);

    // Cleanup
    if (pEveryoneSid) FreeSid(pEveryoneSid);
    if (pNewDacl) LocalFree(pNewDacl);
    if (pSD) LocalFree(pSD);
}

// ─── Watchdog / Guard System ─────────────────────────────────────────

static void SpawnGuard() {
    WCHAR exePath[MAX_PATH];
    GetModuleFileNameW(NULL, exePath, MAX_PATH);

    WCHAR cmdLine[MAX_PATH + 64];
    swprintf_s(cmdLine, L"\"%s\" --guard %lu", exePath, GetCurrentProcessId());

    STARTUPINFOW si = { sizeof(si) };
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi = {};

    if (CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE,
            CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        g_guardPid = pi.dwProcessId;
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
}

static void KillGuard() {
    if (g_guardPid == 0) return;
    HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, g_guardPid);
    if (h) {
        TerminateProcess(h, 0);
        CloseHandle(h);
    }
    g_guardPid = 0;
}

// Guard mode: watch parent PID, respawn if it dies
static int GuardMode(DWORD parentPid) {
    // Don't apply DACL protection on guard — main process needs to kill us on clean exit

    while (true) {
        // Check if clean exit was signaled (mutex exists = clean exit in progress)
        HANDLE hMutex = OpenMutexW(SYNCHRONIZE, FALSE, L"TopMostShieldCleanExit");
        if (hMutex) {
            CloseHandle(hMutex);
            return 0;  // Clean exit, don't respawn
        }

        // Open handle to parent with SYNCHRONIZE
        HANDLE hParent = OpenProcess(SYNCHRONIZE, FALSE, parentPid);
        if (!hParent) {
            // Can't open = already dead
            Sleep(500);
            // Check again if it was a clean exit
            hMutex = OpenMutexW(SYNCHRONIZE, FALSE, L"TopMostShieldCleanExit");
            if (hMutex) {
                CloseHandle(hMutex);
                return 0;  // Clean exit
            }
            break;  // Not clean — respawn
        }

        // Wait for parent to die (check every 2 seconds)
        DWORD result = WaitForSingleObject(hParent, 2000);
        CloseHandle(hParent);

        if (result == WAIT_OBJECT_0) {
            // Parent died
            Sleep(500);
            // Check if clean exit
            hMutex = OpenMutexW(SYNCHRONIZE, FALSE, L"TopMostShieldCleanExit");
            if (hMutex) {
                CloseHandle(hMutex);
                return 0;
            }
            break;  // Not clean — respawn
        }
        // WAIT_TIMEOUT — parent still alive, loop
    }

    // Respawn the main process
    WCHAR exePath[MAX_PATH];
    GetModuleFileNameW(NULL, exePath, MAX_PATH);

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    CreateProcessW(exePath, NULL, NULL, NULL, FALSE,
        0, NULL, NULL, &si, &pi);
    if (pi.hProcess) CloseHandle(pi.hProcess);
    if (pi.hThread) CloseHandle(pi.hThread);

    return 0;
}

// Thread to watch the guard and respawn it if killed
static DWORD WINAPI GuardWatcherThread(LPVOID) {
    while (!g_cleanExit) {
        if (g_guardPid == 0) {
            SpawnGuard();
            Sleep(1000);
            continue;
        }
        HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, g_guardPid);
        if (!h) {
            // Guard is dead, respawn
            g_guardPid = 0;
            if (!g_cleanExit) SpawnGuard();
            Sleep(1000);
            continue;
        }
        // Wait up to 2 seconds, then check again
        WaitForSingleObject(h, 2000);
        CloseHandle(h);
    }
    return 0;
}

// ─── Window Management ──────────────────────────────────────────────────

static void ApplyWindowProtections(HWND hWnd) {
    if (g_captureProtected) return;

    // Hide from taskbar: remove APPWINDOW, add TOOLWINDOW
    LONG_PTR ex = GetWindowLongPtrW(hWnd, GWL_EXSTYLE);
    ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW;
    ShowWindow(hWnd, SW_HIDE);
    SetWindowLongPtrW(hWnd, GWL_EXSTYLE, ex);
    ShowWindow(hWnd, SW_SHOW);

    // Topmost
    SetWindowPos(hWnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);

    // Capture protection
    if (!SetWindowDisplayAffinity(hWnd, 0x00000011)) { // WDA_EXCLUDEFROMCAPTURE
        SetWindowDisplayAffinity(hWnd, 0x00000001);     // WDA_MONITOR fallback
    }

    g_captureProtected = true;
}

static void SetWindowOpacity(int alpha) {
    g_opacity = max(30, min(255, alpha));
    LONG_PTR ex = GetWindowLongPtrW(g_hWnd, GWL_EXSTYLE);
    if (!(ex & WS_EX_LAYERED)) {
        SetWindowLongPtrW(g_hWnd, GWL_EXSTYLE, ex | WS_EX_LAYERED);
    }
    SetLayeredWindowAttributes(g_hWnd, 0, (BYTE)g_opacity, LWA_ALPHA);
}

static void ToggleVisibility() {
    g_visible = !g_visible;
    ShowWindow(g_hWnd, g_visible ? SW_SHOW : SW_HIDE);
    if (g_visible) {
        SetWindowPos(g_hWnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
    }
}

// ─── Topmost Enforcement Thread ─────────────────────────────────────────

static DWORD WINAPI TopMostThread(LPVOID) {
    Sleep(2000);
    while (true) {
        if (g_visible && g_hWnd) {
            SetWindowPos(g_hWnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
        Sleep(500);
    }
    return 0;
}

// ─── Navigation ─────────────────────────────────────────────────────────

static void NavigateToService(const std::wstring& key) {
    if (!g_webview) return;

    std::wstring url;
    if (key == L"chatgpt") url = L"https://chatgpt.com";
    else if (key == L"gemini") url = L"https://gemini.google.com";
    else if (key == L"claude") url = L"https://claude.ai";
    else return;

    g_onLandingPage = false;
    g_webview->Navigate(url.c_str());
}

static void NavigateHome() {
    if (!g_webview) return;
    g_onLandingPage = true;
    g_webview->NavigateToString(LANDING_HTML);
}

static void InjectControls() {
    if (!g_webview || g_onLandingPage) return;
    g_webview->ExecuteScript(CONTROLS_JS, nullptr);
}

// ─── Low-Level Keyboard Hook (for P+L+, hotkey) ─────────────────────────

static LRESULT CALLBACK LLKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION) {
        KBDLLHOOKSTRUCT* pKb = (KBDLLHOOKSTRUCT*)lParam;
        bool down = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
        bool up = (wParam == WM_KEYUP || wParam == WM_SYSKEYUP);

        if (pKb->vkCode == 'P')            { if (down) g_keyP = true; if (up) g_keyP = false; }
        else if (pKb->vkCode == 'L')       { if (down) g_keyL = true; if (up) g_keyL = false; }
        else if (pKb->vkCode == VK_OEM_COMMA) { if (down) g_keyComma = true; if (up) g_keyComma = false; }

        if (g_keyP && g_keyL && g_keyComma) {
            g_keyP = g_keyL = g_keyComma = false;
            PostMessage(g_hWnd, WM_TOGGLE_VISIBILITY, 0, 0);
        }
    }
    return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
}

// ─── WebView2 Initialization ────────────────────────────────────────────

static void InitWebView(HWND hWnd) {
    CreateCoreWebView2EnvironmentWithOptions(
        nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [hWnd](HRESULT result, ICoreWebView2Environment* env) -> HRESULT {
                if (FAILED(result) || !env) return result;

                env->CreateCoreWebView2Controller(hWnd,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [hWnd](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                            if (FAILED(result) || !controller) return result;

                            g_controller = controller;
                            g_controller->AddRef();
                            g_controller->get_CoreWebView2(&g_webview);

                            // Resize to fill window
                            RECT bounds;
                            GetClientRect(hWnd, &bounds);
                            g_controller->put_Bounds(bounds);

                            // Settings
                            ICoreWebView2Settings* settings;
                            g_webview->get_Settings(&settings);
                            settings->put_IsStatusBarEnabled(FALSE);
                            settings->put_AreDefaultContextMenusEnabled(TRUE);
                            settings->put_AreDevToolsEnabled(FALSE);
                            settings->Release();

                            // Handle messages from JavaScript
                            EventRegistrationToken token;
                            g_webview->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [](ICoreWebView2* sender, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        LPWSTR msgRaw;
                                        args->TryGetWebMessageAsString(&msgRaw);
                                        if (!msgRaw) return S_OK;

                                        std::wstring msg(msgRaw);
                                        CoTaskMemFree(msgRaw);

                                        if (msg.rfind(L"navigate:", 0) == 0) {
                                            NavigateToService(msg.substr(9));
                                        } else if (msg == L"go_home") {
                                            NavigateHome();
                                        } else if (msg.rfind(L"opacity:", 0) == 0) {
                                            int val = _wtoi(msg.substr(8).c_str());
                                            SetWindowOpacity(val);
                                        }
                                        return S_OK;
                                    }
                                ).Get(), &token
                            );

                            // Inject controls after navigation completes
                            g_webview->add_NavigationCompleted(
                                Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                    [](ICoreWebView2* sender, ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                        // Delay injection slightly for page to render
                                        SetTimer(g_hWnd, 100, 2000, [](HWND hWnd, UINT, UINT_PTR id, DWORD) {
                                            KillTimer(hWnd, id);
                                            InjectControls();
                                        });
                                        return S_OK;
                                    }
                                ).Get(), &token
                            );

                            // Load landing page
                            NavigateHome();

                            return S_OK;
                        }
                    ).Get()
                );
                return S_OK;
            }
        ).Get()
    );
}

// ─── Window Procedure ───────────────────────────────────────────────────

static LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_SIZE:
        if (g_controller) {
            RECT bounds;
            GetClientRect(hWnd, &bounds);
            g_controller->put_Bounds(bounds);
        }
        return 0;

    case WM_HOTKEY:
        if (wParam == HOTKEY_OPACITY_UP) {
            SetWindowOpacity(g_opacity + 25);
        } else if (wParam == HOTKEY_OPACITY_DOWN) {
            SetWindowOpacity(g_opacity - 25);
        } else if (wParam == HOTKEY_EXIT) {
            DestroyWindow(hWnd);
        }
        return 0;

    case WM_TOGGLE_VISIBILITY:
        ToggleVisibility();
        return 0;

    case WM_OPACITY_UP:
        SetWindowOpacity(g_opacity + 25);
        return 0;

    case WM_OPACITY_DOWN:
        SetWindowOpacity(g_opacity - 25);
        return 0;

    case WM_DESTROY:
        g_cleanExit = true;
        // Signal clean exit to guard via named mutex
        CreateMutexW(NULL, FALSE, L"TopMostShieldCleanExit");
        Sleep(100);  // Give guard time to see the mutex
        KillGuard();
        PostQuitMessage(0);
        return 0;

    default:
        return DefWindowProcW(hWnd, msg, wParam, lParam);
    }
}

// ─── Entry Point ────────────────────────────────────────────────────────

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE, LPWSTR lpCmdLine, int) {
    g_hInstance = hInstance;

    // ── Check if we are the guard process ──
    int argc;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argc >= 3 && wcscmp(argv[1], L"--guard") == 0) {
        DWORD parentPid = (DWORD)_wtoi(argv[2]);
        LocalFree(argv);
        return GuardMode(parentPid);
    }
    LocalFree(argv);

    // Initialize COM (required for WebView2)
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);

    // Set process priority
    SetPriorityClass(GetCurrentProcess(), REALTIME_PRIORITY_CLASS);

    // Connect to kernel driver
    if (DriverConnect()) {
        DriverBoost();
        DriverSetPid(GetCurrentProcessId());
    }

    // Protect against termination by other apps
    ProtectProcess();

    // Spawn guard process
    SpawnGuard();

    // Start guard watcher
    CreateThread(NULL, 0, GuardWatcherThread, NULL, 0, NULL);

    // Register window class
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"TopMostShield";
    ATOM cls = RegisterClassExW(&wc);

    // Create window
    g_hWnd = CreateWindowExW(
        0,
        L"TopMostShield",
        L"Acer",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT, CW_USEDEFAULT,
        900, 700,
        NULL, NULL, hInstance, NULL
    );

    if (!g_hWnd) {
        wprintf(L"[ERROR] CreateWindowEx failed: error %lu\n", GetLastError());
        CoUninitialize();
        return 1;
    }

    // Show window and apply protections
    ShowWindow(g_hWnd, SW_SHOW);
    UpdateWindow(g_hWnd);
    ApplyWindowProtections(g_hWnd);

    // Register hotkeys (Ctrl+Shift+Up/Down for opacity)
    RegisterHotKey(g_hWnd, HOTKEY_OPACITY_UP, MOD_CONTROL | MOD_SHIFT, VK_UP);
    RegisterHotKey(g_hWnd, HOTKEY_OPACITY_DOWN, MOD_CONTROL | MOD_SHIFT, VK_DOWN);
    RegisterHotKey(g_hWnd, HOTKEY_EXIT, MOD_CONTROL | MOD_SHIFT, 'Q');

    // Install low-level keyboard hook for P+L+, combo
    g_keyboardHook = SetWindowsHookExW(WH_KEYBOARD_LL, LLKeyboardProc, hInstance, 0);

    // Start topmost enforcement thread
    CreateThread(NULL, 0, TopMostThread, NULL, 0, NULL);

    // Initialize WebView2
    InitWebView(g_hWnd);

    // Message loop
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    // Cleanup
    UnregisterHotKey(g_hWnd, HOTKEY_OPACITY_UP);
    UnregisterHotKey(g_hWnd, HOTKEY_OPACITY_DOWN);
    UnregisterHotKey(g_hWnd, HOTKEY_EXIT);
    if (g_keyboardHook) UnhookWindowsHookEx(g_keyboardHook);
    if (g_controller) g_controller->Release();
    if (g_webview) g_webview->Release();
    DriverDisconnect();
    CoUninitialize();

    return 0;
}
