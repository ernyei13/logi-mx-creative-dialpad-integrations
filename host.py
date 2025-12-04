#!/usr/bin/env python3
"""
host.py - Unified HID host for MX Creative Dialpad and Keypad

Auto-detects and connects to both MX Creative Dialpad (dials + 4 buttons)
and MX Creative Keypad (9 buttons), broadcasting all events to the web server.

Usage:
    python host.py
    
For headless mode (auto-select devices and localhost):
    echo "127.0.0.1" | python host.py --auto
"""

try:
    import hid
except Exception as e:
    hint = (
        "\nUnable to import the native HID library. This often happens when you're\n"
        "running a different Python interpreter (e.g. Conda) than your project venv.\n"
        "Try running with the project's venv: `./venv/bin/python host.py`\n"
        "Or install the native lib on macOS: `brew install hidapi` and then\n"
        "reinstall the Python package in the active venv: `./venv/bin/python -m pip install --force-reinstall hid`\n"
    )
    raise ImportError(str(e) + hint)

import time
import sys
import asyncio
import threading
import json
import webbrowser
from aiohttp import ClientSession

# ==============================================================================
# CONFIGURATION & STATE
# ==============================================================================
LOGITECH_VID = 0x046d
WEB_PORT = 8080

# Global state to manage the async loop from the separate HID thread
LOOP = None
SEND_QUEUE = None

# Dialpad button mapping (byte index 1, bitmask values)
DIALPAD_BUTTON_MAP = {
    0x08: 'TOP LEFT',
    0x10: 'TOP RIGHT',
    0x20: 'BOTTOM LEFT',
    0x40: 'BOTTOM RIGHT',
}

# Keypad button mapping (byte 6 values, 1-9)
KEYPAD_BUTTONS = {
    1: "1",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
}

# State tracking
LAST_DIALPAD_BTN_BYTE = 0
LAST_KEYPAD_BUTTON = 0

# Device type identifiers
DEVICE_TYPE_DIALPAD = "dialpad"
DEVICE_TYPE_KEYPAD = "keypad"

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_signed_int(byte_val):
    """Converts a byte (0-255) to a signed int (-128 to 127)"""
    if byte_val > 127:
        return byte_val - 256
    return byte_val


def broadcast_to_web(ctrl_type, payload):
    """Put a JSON payload onto the async SEND_QUEUE so the bridge task
    can forward it to the receiver. Safe to call from HID thread.
    """
    if LOOP and SEND_QUEUE:
        if isinstance(payload, dict):
            payload_obj = {"ctrl": ctrl_type}
            payload_obj.update(payload)
        else:
            payload_obj = {"ctrl": ctrl_type, "delta": payload}

        json_str = json.dumps(payload_obj)
        asyncio.run_coroutine_threadsafe(SEND_QUEUE.put(json_str), LOOP)


# ==============================================================================
# DIALPAD DATA PROCESSING
# ==============================================================================

def process_dialpad_data(data):
    """Process data from MX Creative Dialpad (dials and 4 buttons)"""
    global LAST_DIALPAD_BTN_BYTE
    
    if not data:
        return

    try:
        seq = list(data)
    except Exception:
        seq = [int(x) for x in data]

    timestamp = time.strftime("%H:%M:%S", time.localtime())
    report_id = seq[0] if seq else 0

    # =========================================================================
    # REPORT ID 0x02: Standard Mode (dials + buttons)
    # =========================================================================
    if report_id == 0x02:
        if len(seq) < 8:
            return

        # Dial values
        raw_small = seq[6]  # Small scroller
        raw_big = seq[7]    # Big dial

        val_small = get_signed_int(raw_small)
        val_big = get_signed_int(raw_big)

        # Small scroller
        if val_small != 0:
            direction = "RIGHT (CW)" if val_small > 0 else "LEFT (CCW)"
            bar = "▒" * abs(val_small)
            print(f"[{timestamp}] SMALL SCROLLER | {direction:<10} | Speed: {val_small:<3} | {bar}")
            broadcast_to_web("SMALL", val_small)

        # Big dial
        if val_big != 0:
            direction = "RIGHT (CW)" if val_big > 0 else "LEFT (CCW)"
            bar = "▓" * abs(val_big)
            print(f"[{timestamp}] BIG DIAL       | {direction:<10} | Speed: {val_big:<3} | {bar}")
            broadcast_to_web("BIG", val_big)

        # Dialpad buttons (4 corner buttons)
        btn_byte = seq[1] if len(seq) > 1 else 0
        changed = btn_byte ^ LAST_DIALPAD_BTN_BYTE
        if changed:
            for bit, name in DIALPAD_BUTTON_MAP.items():
                if changed & bit:
                    state = bool(btn_byte & bit)
                    action = 'PRESSED' if state else 'RELEASED'
                    print(f"[{timestamp}] DIALPAD BTN   | {name:<12} | {action}")
                    broadcast_to_web("BTN", {"name": name, "state": action})
        LAST_DIALPAD_BTN_BYTE = btn_byte

    # =========================================================================
    # REPORT ID 0x11: Vendor Mode (Fallback for big dial)
    # =========================================================================
    elif report_id == 0x11:
        if len(seq) < 6:
            return
        control_id = seq[4]
        val = get_signed_int(seq[5])

        if control_id == 0x01 and val != 0:
            direction = "RIGHT (CW)" if val > 0 else "LEFT (CCW)"
            bar = "▓" * abs(val)
            print(f"[{timestamp}] BIG DIAL (V)   | {direction:<10} | Speed: {val:<3} | {bar}")
            broadcast_to_web("BIG", val)


# ==============================================================================
# KEYPAD DATA PROCESSING
# ==============================================================================

def process_keypad_data(data):
    """Process data from MX Creative Keypad (9 buttons)"""
    global LAST_KEYPAD_BUTTON
    
    if not data:
        return

    try:
        seq = list(data)
    except Exception:
        seq = [int(x) for x in data]

    timestamp = time.strftime("%H:%M:%S", time.localtime())
    report_id = seq[0] if seq else 0

    # =========================================================================
    # REPORT ID 0x13: MX Creative Keypad buttons
    # =========================================================================
    if report_id == 0x13 and len(seq) > 6:
        button_byte = seq[6]
        
        if button_byte != 0:
            # Button pressed
            btn_name = KEYPAD_BUTTONS.get(button_byte, f"UNKNOWN ({button_byte})")
            print(f"[{timestamp}] KEYPAD BTN    | {btn_name:<12} | PRESSED")
            LAST_KEYPAD_BUTTON = button_byte
            broadcast_to_web("KEYPAD", {"button": button_byte, "state": "PRESSED"})
        elif LAST_KEYPAD_BUTTON != 0:
            # Button released
            btn_name = KEYPAD_BUTTONS.get(LAST_KEYPAD_BUTTON, f"UNKNOWN ({LAST_KEYPAD_BUTTON})")
            print(f"[{timestamp}] KEYPAD BTN    | {btn_name:<12} | RELEASED")
            broadcast_to_web("KEYPAD", {"button": LAST_KEYPAD_BUTTON, "state": "RELEASED"})
            LAST_KEYPAD_BUTTON = 0


# ==============================================================================
# DEVICE SCANNING
# ==============================================================================

def scan_devices():
    """Scan for Logitech MX Creative devices and auto-identify type."""
    print("\nScanning for Logitech MX Creative devices...")
    print("-" * 80)
    
    dialpad_devices = []
    keypad_devices = []
    
    for d in hid.enumerate():
        if d['vendor_id'] != LOGITECH_VID:
            continue
            
        name = d.get('product_string', '') or ''
        up = d.get('usage_page', 0)
        
        # Only look at vendor-specific interfaces (raw data)
        if up < 0xFF00:
            continue
        
        # Identify device type by name
        name_lower = name.lower()
        
        if 'keypad' in name_lower or 'keys' in name_lower:
            keypad_devices.append(d)
            print(f"[KEYPAD]  {name} (usage_page=0x{up:04x})")
        elif 'dial' in name_lower or 'creative' in name_lower:
            dialpad_devices.append(d)
            print(f"[DIALPAD] {name} (usage_page=0x{up:04x})")
    
    print("-" * 80)
    
    return dialpad_devices, keypad_devices


def scan_all_interfaces():
    """List all Logitech interfaces for manual selection."""
    print("\nScanning ALL Logitech interfaces...")
    print(f"{'IDX':<5} | {'TYPE':<10} | {'USAGE PAGE':<12} | {'USAGE':<8} | {'PRODUCT'}")
    print("-" * 90)

    devices = []
    found_count = 0

    for d in hid.enumerate():
        if d['vendor_id'] == LOGITECH_VID:
            name = d.get('product_string', 'Unknown') or 'Unknown'
            up = d.get('usage_page', 0)
            u = d.get('usage', 0)
            
            # Guess device type
            name_lower = name.lower()
            if 'keypad' in name_lower or 'keys' in name_lower:
                dev_type = "KEYPAD"
            elif 'dial' in name_lower or 'creative' in name_lower:
                dev_type = "DIALPAD"
            else:
                dev_type = "OTHER"

            if up == 0x01:
                iface_type = "Generic"
            elif up == 0x0C:
                iface_type = "Consumer"
            elif up >= 0xFF00:
                iface_type = "Vendor"
            else:
                iface_type = f"0x{up:04x}"

            print(f"{found_count:<5} | {dev_type:<10} | 0x{up:04x}       | 0x{u:04x}   | {name}")
            devices.append({**d, 'device_type': dev_type})
            found_count += 1

    if not devices:
        print("(No matching devices found)")

    return devices


# ==============================================================================
# HID LISTENER THREADS
# ==============================================================================

def hid_listener_thread(device_path, device_type, device_name):
    """Background thread that runs the HID blocking loop for a device."""
    print(f"[*] HID Thread Started: {device_name} ({device_type})")
    
    # Select the appropriate data processor
    if device_type == DEVICE_TYPE_KEYPAD:
        process_fn = process_keypad_data
    else:
        process_fn = process_dialpad_data
    
    try:
        # Detect which HID API is available
        if hasattr(hid, 'device'):
            # Cython-style API
            h = hid.device()
            try:
                h.open_path(device_path)
            except Exception:
                if isinstance(device_path, bytes):
                    h.open_path(device_path.decode())
                else:
                    raise
            try:
                h.set_nonblocking(False)
            except Exception:
                try:
                    h.set_nonblocking(0)
                except Exception:
                    pass

            while True:
                try:
                    data = h.read(64, timeout_ms=1000)
                except TypeError:
                    try:
                        data = h.read(64, 1000)
                    except Exception:
                        data = h.read(64)

                if data:
                    process_fn(data)
                time.sleep(0.001)
        else:
            # ctypes-style API
            h = hid.Device(path=device_path)
            try:
                h.nonblocking = False
            except Exception:
                pass

            while True:
                try:
                    data = h.read(64, timeout=1000)
                except TypeError:
                    try:
                        data = h.read(64, 1000)
                    except Exception:
                        data = h.read(64)

                if data:
                    process_fn(data)
                time.sleep(0.001)

    except IOError as e:
        print(f"[-] HID Error ({device_name}): {e}")
    except Exception as e:
        print(f"[-] Thread Error ({device_name}): {e}")


# ==============================================================================
# WEBSOCKET BRIDGE
# ==============================================================================

async def _send_loop_over_ws(ws):
    """Continuously read from SEND_QUEUE and send over the open websocket."""
    while True:
        payload = await SEND_QUEUE.get()
        try:
            await ws.send_str(payload)
        except Exception:
            raise


async def _bridge_client_loop(receiver_host, receiver_port):
    """Maintain a websocket connection to the remote receiver."""
    global SEND_QUEUE
    SEND_QUEUE = asyncio.Queue()
    url = f"ws://{receiver_host}:{receiver_port}/bridge"

    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    print(f"[*] Connected to receiver at {url}")
                    await _send_loop_over_ws(ws)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[-] Bridge connection failed: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    global LOOP
    
    auto_mode = '--auto' in sys.argv
    
    # 1. SCAN FOR DEVICES
    if auto_mode:
        # Auto-detect mode - find dialpad and keypad automatically
        dialpad_devices, keypad_devices = scan_devices()
        
        if not dialpad_devices and not keypad_devices:
            print("No MX Creative devices found!")
            return
        
        # Use first device of each type
        selected_devices = []
        if dialpad_devices:
            d = dialpad_devices[0]
            selected_devices.append((d['path'], DEVICE_TYPE_DIALPAD, d.get('product_string', 'Dialpad')))
        if keypad_devices:
            d = keypad_devices[0]
            selected_devices.append((d['path'], DEVICE_TYPE_KEYPAD, d.get('product_string', 'Keypad')))
    else:
        # Manual selection mode
        devices = scan_all_interfaces()
        if not devices:
            print("No devices found.")
            return

        print("\nEnter device indices to use (comma-separated, or 'all' for auto-detect):")
        user_input = input("> ").strip()
        
        if user_input.lower() == 'all':
            # Auto-detect
            dialpad_devices, keypad_devices = scan_devices()
            selected_devices = []
            if dialpad_devices:
                d = dialpad_devices[0]
                selected_devices.append((d['path'], DEVICE_TYPE_DIALPAD, d.get('product_string', 'Dialpad')))
            if keypad_devices:
                d = keypad_devices[0]
                selected_devices.append((d['path'], DEVICE_TYPE_KEYPAD, d.get('product_string', 'Keypad')))
        else:
            # Parse indices
            try:
                indices = [int(x.strip()) for x in user_input.split(',')]
            except ValueError:
                print("Invalid input.")
                return
            
            selected_devices = []
            for idx in indices:
                if 0 <= idx < len(devices):
                    d = devices[idx]
                    dev_type = DEVICE_TYPE_KEYPAD if d.get('device_type') == 'KEYPAD' else DEVICE_TYPE_DIALPAD
                    selected_devices.append((d['path'], dev_type, d.get('product_string', 'Unknown')))

    if not selected_devices:
        print("No devices selected.")
        return

    # 2. GET RECEIVER HOST
    if auto_mode:
        receiver = "127.0.0.1"
        # Check if there's piped input
        if not sys.stdin.isatty():
            try:
                receiver = sys.stdin.readline().strip() or "127.0.0.1"
            except:
                pass
    else:
        receiver = input("\nReceiver host/IP [127.0.0.1]: ").strip() or "127.0.0.1"

    # 3. PRINT CONFIG
    print("\n" + "=" * 60)
    print("STARTING LOGI HOST")
    print("=" * 60)
    for path, dev_type, name in selected_devices:
        print(f"  [{dev_type.upper()}] {name}")
    print(f"  Receiver: ws://{receiver}:{WEB_PORT}/bridge")
    print("=" * 60)
    print("Press Ctrl+C to stop.\n")

    # 4. START HID THREADS FOR EACH DEVICE
    for path, dev_type, name in selected_devices:
        t = threading.Thread(
            target=hid_listener_thread,
            args=(path, dev_type, name),
            daemon=True
        )
        t.start()

    # 5. Optionally open the web UI
    if not auto_mode:
        try:
            webbrowser.open(f"http://{receiver}:{WEB_PORT}")
        except Exception:
            pass

    # 6. START BRIDGE CLIENT (Main Thread)
    async def run_bridge_client():
        global LOOP
        LOOP = asyncio.get_running_loop()
        await _bridge_client_loop(receiver, WEB_PORT)

    try:
        asyncio.run(run_bridge_client())
    except KeyboardInterrupt:
        print("\n[*] Stopping.")


if __name__ == "__main__":
    main()
