# Editor end-to-end verification (Windows console key injection).
# Methodology: hidden console owned by this process; the editor child shares it
# via inheritable CONIN$/CONOUT$ stdio handles; real VK events (keydown+keyup
# pairs with scan codes) are injected with WriteConsoleInput, so the console's
# VT-input translation happens for real. Expected: h,i,VK_LEFT,X,Ctrl+S,Ctrl+Q
# => untitled.txt == "hXi", exit code 0, stderr ends with "Goodbye."
import ctypes, os, sys, time, tempfile, shutil
from ctypes import wintypes

k32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [("bKeyDown", wintypes.BOOL),
                ("wRepeatCount", wintypes.WORD),
                ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD),
                ("UnicodeChar", wintypes.WCHAR),
                ("dwControlKeyState", wintypes.DWORD)]

class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD),
                ("Event", KEY_EVENT_RECORD)]

class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]

class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
OPEN_EXISTING = 3
LEFT_CTRL_PRESSED = 0x0008
KEY_EVENT = 1
STARTF_USESTDHANDLES = 0x100
SW_HIDE = 0

def create_file(name, inherit, disposition=OPEN_EXISTING):
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, inherit)
    h = k32.CreateFileW(name, GENERIC_READ | GENERIC_WRITE, 7,
                        ctypes.byref(sa), disposition, 0, None)
    if not h or h == wintypes.HANDLE(-1):
        raise OSError(f"CreateFileW({name}) failed: {k32.GetLastError()}")
    return h

def key(vk, scan, ch, down, ctrl=False):
    r = INPUT_RECORD()
    r.EventType = KEY_EVENT
    r.Event.bKeyDown = down
    r.Event.wRepeatCount = 1
    r.Event.wVirtualKeyCode = vk
    r.Event.wVirtualScanCode = scan
    r.Event.UnicodeChar = ch
    r.Event.dwControlKeyState = LEFT_CTRL_PRESSED if ctrl else 0
    return r

def seq(vk, scan, ch, ctrl=False):
    return [key(vk, scan, ch, True, ctrl), key(vk, scan, ch, False, ctrl)]

CREATE_NEW_CONSOLE = 0x10

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--stage2":
        return run_in_console(sys.argv[2])
    # stage 1: this process may have no console (mintty/pipe) and AllocConsole
    # can be denied — relaunch ourselves with CREATE_NEW_CONSOLE and relay.
    editor = sys.argv[1]
    # one pipe for stage2 stdout+stderr (its console exists only for CONIN$/CONOUT$)
    r1, w1 = wintypes.HANDLE(), wintypes.HANDLE()
    if not k32.CreatePipe(ctypes.byref(r1), ctypes.byref(w1), None, 0):
        raise OSError("CreatePipe failed")
    k32.SetHandleInformation(w1, 1, 1)  # HANDLE_FLAG_INHERIT
    cmdline = (f'"{sys.executable}" -u "{os.path.abspath(__file__)}" --stage2 "{editor}"'
               + (f' "{sys.argv[2]}"' if len(sys.argv) > 2 else ''))
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.dwFlags = STARTF_USESTDHANDLES
    si.hStdInput = wintypes.HANDLE(k32.GetStdHandle(-10))  # keep stdin whatever it is
    si.hStdOutput = w1
    si.hStdError = w1
    pi = PROCESS_INFORMATION()
    if not k32.CreateProcessW(None, cmdline, None, None, True, CREATE_NEW_CONSOLE,
                              None, None, ctypes.byref(si), ctypes.byref(pi)):
        raise OSError(f"CreateProcessW(stage2) failed: {k32.GetLastError()}")
    k32.CloseHandle(w1)
    out = ctypes.create_string_buffer(65536)
    read = wintypes.DWORD(0)
    while k32.ReadFile(r1, out, 65536, ctypes.byref(read), None) and read.value:
        sys.stdout.buffer.write(out.raw[:read.value])
        sys.stdout.buffer.flush()
    k32.WaitForSingleObject(pi.hProcess, 60000)
    code = wintypes.DWORD(0)
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.CloseHandle(pi.hProcess)
    k32.CloseHandle(pi.hThread)
    k32.CloseHandle(r1)
    sys.exit(code.value)

def run_in_console(editor):
    scenario = sys.argv[3] if len(sys.argv) > 3 else "left"
    for _ in range(10):  # console window may not exist the instant we start
        hwnd = k32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)
            break
        time.sleep(0.1)
    workdir = tempfile.mkdtemp(prefix="frond-editor-e2e-")
    errpath = os.path.join(workdir, "stderr.txt")

    # one CONIN$ handle for the child's stdin (inheritable), one kept here for
    # WriteConsoleInput; both refer to the same console input buffer.
    conin_child = create_file("CONIN$", True)
    conin_mine = create_file("CONIN$", False)
    conout = create_file("CONOUT$", True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE)
    errfile = create_file(errpath, True, 2)  # CREATE_ALWAYS

    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.dwFlags = STARTF_USESTDHANDLES
    si.hStdInput = conin_child
    si.hStdOutput = conout
    si.hStdError = wintypes.HANDLE(errfile)
    pi = PROCESS_INFORMATION()
    frond = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "Frond", "target", "release", "frond.exe")
    cmdline = f'"{os.path.abspath(frond)}" run "{os.path.abspath(editor)}"'
    ok = k32.CreateProcessW(None, cmdline, None, None, True, 0, None, workdir,
                            ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        raise OSError(f"CreateProcessW failed: {k32.GetLastError()}")

    time.sleep(1.5)  # let the editor enter raw mode + render the first frame

    # scenarios: (events, expected untitled.txt content or None)
    VK_DELETE = 0x2E
    ctrl_f = seq(0x46, 0x21, '\x06', True)   # Ctrl+F -> search prompt
    save_quit = seq(0x53, 0x1F, '\x13', True) + seq(0x51, 0x10, '\x11', True)
    scenarios = {
        # h,i,VK_LEFT,X -> cursor moved left, X inserted before i
        "left": (seq(0x48, 0x23, 'h') + seq(0x49, 0x17, 'i') +
                 seq(0x25, 0x4B, '\x00') + seq(0x58, 0x2D, 'X') + save_quit, b"hXi"),
        # h,i,VK_LEFT,VK_DELETE -> forward-delete removes the i (ESC[3~ path)
        "delete": (seq(0x48, 0x23, 'h') + seq(0x49, 0x17, 'i') +
                   seq(0x25, 0x4B, '\x00') + seq(VK_DELETE, 0x53, '\x00') + save_quit, b"h"),
    }
    # esc: standalone ESC must resolve as EscapeKey (no follow-up bytes pending)
    # and cancel the prompt. A VK_ESCAPE key event is swallowed whole by conhost
    # under VT input, so the ESC goes in as a raw byte record (vk=0, ch=0x1b) —
    # exactly what a real terminal (WT/conpty) delivers. Two phases with a gap:
    # if the reader wrongly waits for more bytes, phase 2 never gets processed.
    esc_events_1 = ctrl_f + seq(0x41, 0x1E, 'a') + seq(0, 0, '\x1b')
    esc_events_2 = seq(0x58, 0x2D, 'x') + save_quit
    if scenario == "left" or scenario == "delete":
        events, expected = scenarios[scenario]
        two_phase = None
    else:
        events, expected = esc_events_1, b"x"
        two_phase = esc_events_2
    arr = (INPUT_RECORD * len(events))(*events)
    written = wintypes.DWORD(0)
    k32.WriteConsoleInputW.argtypes = (wintypes.HANDLE, ctypes.POINTER(INPUT_RECORD),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    k32.WriteConsoleInputW.restype = wintypes.BOOL
    if not k32.WriteConsoleInputW(conin_mine, arr, len(events), ctypes.byref(written)):
        raise OSError(f"WriteConsoleInputW failed: {k32.GetLastError()}")
    if two_phase:
        time.sleep(0.8)  # give the editor time to resolve the standalone ESC
        events = two_phase
        arr = (INPUT_RECORD * len(events))(*events)
        if not k32.WriteConsoleInputW(conin_mine, arr, len(events), ctypes.byref(written)):
            raise OSError(f"WriteConsoleInputW(2) failed: {k32.GetLastError()}")

    exited = k32.WaitForSingleObject(pi.hProcess, 15000)
    code = wintypes.DWORD(0)
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.CloseHandle(pi.hProcess)
    k32.CloseHandle(pi.hThread)
    k32.CloseHandle(errfile)
    k32.CloseHandle(conin_child)
    k32.CloseHandle(conin_mine)
    k32.CloseHandle(conout)

    saved = os.path.join(workdir, "untitled.txt")
    content = open(saved, "rb").read() if os.path.exists(saved) else None
    errout = open(errpath, "r", errors="replace").read() if os.path.exists(errpath) else ""

    print(f"exit_code   = {code.value} ({'EXIT' if exited == 0 else 'TIMEOUT'})")
    print(f"untitled    = {content!r}")
    print(f"stderr_tail = {errout[-80:]!r}")
    good = (exited == 0 and code.value == 0 and content == expected
            and "Goodbye." in errout)
    print(f"expected    = {expected!r}")
    print("RESULT:", "ALL PASSED" if good else "FAILED")
    keep = os.environ.get("KEEP_DIR")
    if not keep:
        shutil.rmtree(workdir, ignore_errors=True)
    else:
        print("workdir:", workdir)
    sys.exit(0 if good else 1)

main()
