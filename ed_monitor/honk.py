"""Auto-honk: simulate holding PrimaryFire for 7 seconds after an FSD jump.

Linux: evdev UInput — works for both joystick buttons and keyboard keys.
Windows: ctypes SendInput — keyboard keys only (no vJoy dependency).
"""
from __future__ import annotations

import sys
import threading
import time

_active = threading.Event()


def trigger(device_guid: str, key_name: str) -> None:
    """Spawn a daemon thread that holds the binding for 7 seconds.

    Silently no-ops if a honk is already in progress or if the required
    libraries are unavailable.
    """
    if _active.is_set():
        return
    t = threading.Thread(target=_hold, args=(device_guid, key_name), daemon=True)
    t.start()


def _hold(device_guid: str, key_name: str) -> None:
    if _active.is_set():
        return
    _active.set()
    try:
        if sys.platform == "win32":
            _hold_windows(key_name)
        else:
            _hold_linux(device_guid, key_name)
    except Exception:
        pass
    finally:
        _active.clear()


# ── Linux ──────────────────────────────────────────────────────────────────────

def _hold_linux(device_guid: str, key_name: str) -> None:
    try:
        import evdev  # type: ignore
        from evdev import UInput, ecodes  # type: ignore
    except ImportError:
        return

    # Check if this looks like a joystick GUID (8+ hex chars, no "Key_" prefix)
    is_joystick = (
        not key_name.startswith("Key_")
        and len(device_guid) >= 4
        and all(c in "0123456789ABCDEFabcdef" for c in device_guid)
    )

    if is_joystick:
        _hold_linux_joystick(device_guid, key_name, evdev, UInput, ecodes)
    else:
        _hold_linux_keyboard(key_name, UInput, ecodes)


def _hold_linux_joystick(
    device_guid: str, joy_key: str,
    evdev, UInput, ecodes,
) -> None:
    """Hold a joystick button via UInput."""
    # Parse vendor/product from GUID (upper 16 bits = vendor, lower = product)
    try:
        guid_int  = int(device_guid, 16)
        vendor    = (guid_int >> 16) & 0xFFFF
        product   = guid_int & 0xFFFF
    except ValueError:
        return

    # Find the matching evdev device
    target_dev = None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            info = dev.info
            if info.vendor == vendor and info.product == product:
                target_dev = dev
                break
        except Exception:
            continue

    if target_dev is None:
        return

    # Joy_N → sort EV_KEY buttons by code, pick index N-1 (1-based)
    try:
        joy_index = int(joy_key.replace("Joy_", "")) - 1
    except (ValueError, AttributeError):
        return

    caps = target_dev.capabilities()
    buttons = sorted(caps.get(ecodes.EV_KEY, []))
    if joy_index < 0 or joy_index >= len(buttons):
        return

    btn_code = buttons[joy_index]

    try:
        with UInput(
            {ecodes.EV_KEY: [btn_code]},
            name="nova-honk",
            vendor=vendor,
            product=product,
        ) as ui:
            ui.write(ecodes.EV_KEY, btn_code, 1)  # key down
            ui.syn()
            time.sleep(7.0)
            ui.write(ecodes.EV_KEY, btn_code, 0)  # key up
            ui.syn()
    except Exception:
        pass


def _hold_linux_keyboard(key_name: str, UInput, ecodes) -> None:
    """Hold a keyboard key via UInput."""
    # Strip "Key_" prefix and map to evdev key code
    bare = key_name.removeprefix("Key_")
    # Try exact match first (e.g. KEY_SPACE), then constructed name
    ecode = getattr(ecodes, f"KEY_{bare.upper()}", None)
    if ecode is None:
        return

    try:
        with UInput({ecodes.EV_KEY: [ecode]}, name="nova-honk-kb") as ui:
            ui.write(ecodes.EV_KEY, ecode, 1)
            ui.syn()
            time.sleep(7.0)
            ui.write(ecodes.EV_KEY, ecode, 0)
            ui.syn()
    except Exception:
        pass


# ── Windows ────────────────────────────────────────────────────────────────────

def _hold_windows(key_name: str) -> None:
    """Hold a keyboard key on Windows via ctypes SendInput."""
    import ctypes
    import ctypes.wintypes

    bare = key_name.removeprefix("Key_")
    vk = _WIN_VK_MAP.get(bare.upper())
    if vk is None:
        return

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT)]

    def send_key(vk_code: int, flags: int) -> None:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki.wVk = vk_code
        inp.ki.dwFlags = flags
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    send_key(vk, 0)
    time.sleep(7.0)
    send_key(vk, KEYEVENTF_KEYUP)


# Common ED keyboard binding names → Windows VK codes
_WIN_VK_MAP: dict[str, int] = {
    "NUMPAD_0": 0x60, "NUMPAD_1": 0x61, "NUMPAD_2": 0x62, "NUMPAD_3": 0x63,
    "NUMPAD_4": 0x64, "NUMPAD_5": 0x65, "NUMPAD_6": 0x66, "NUMPAD_7": 0x67,
    "NUMPAD_8": 0x68, "NUMPAD_9": 0x69,
    "NUMPAD_MULTIPLY": 0x6A, "NUMPAD_ADD": 0x6B,
    "NUMPAD_SUBTRACT": 0x6D, "NUMPAD_DECIMAL": 0x6E, "NUMPAD_DIVIDE": 0x6F,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
    "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
    "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "RETURN": 0x0D, "ESCAPE": 0x1B, "TAB": 0x09,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCONTROL": 0xA2, "RCONTROL": 0xA3,
    "LMENU": 0xA4, "RMENU": 0xA5,
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
}
