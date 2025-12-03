#!/usr/bin/env python3
"""
host_keypad.py - HID host for MX Creative Keypad

Reads HID input from the keypad and broadcasts button events to the web server.

Usage:
    DYLD_LIBRARY_PATH=/opt/homebrew/lib ./venv/bin/python host_keypad.py
"""

try:
    import hid
except ImportError as e:
    hint = (
        "\nUnable to import the native HID library. This often happens when you're\n"
        "running a different Python interpreter (e.g. Conda) than your project venv.\n"
        "Try running with the project's venv: `./venv/bin/python host_keypad.py`\n"
        "Or install the native lib on macOS: `brew install hidapi` and then\n"
        "reinstall the Python package in the active venv:\n"
        "  ./venv/bin/python -m pip install --force-reinstall hidapi\n"
    )
    raise ImportError(str(e) + hint)

import time
import json
import asyncio
import threading
from aiohttp import ClientSession

# ==============================================================================
# CONFIGURATION
# ==============================================================================
LOGITECH_VID = 0x046d
WEB_PORT = 8080

# Button mapping for MX Creative Keypad (byte 6 values)
# Layout:
#   [1] [2] [3]
#   [4] [5] [6]
#   [7] [8] [9]
KEYPAD_BUTTONS = {
    1: "BTN 1 (Top-Left)",
    2: "BTN 2 (Top-Center)",
    3: "BTN 3 (Top-Right)",
    4: "BTN 4 (Mid-Left)",
    5: "BTN 5 (Mid-Center)",
    6: "BTN 6 (Mid-Right)",
    7: "BTN 7 (Bot-Left)",
    8: "BTN 8 (Bot-Center)",
    9: "BTN 9 (Bot-Right)",
}

# Track last button state
LAST_BUTTON = 0

# Global state for async loop and send queue
LOOP = None
SEND_QUEUE = None

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_signed_int(byte_val):
    """Converts a byte (0-255) to a signed int (-128 to 127)"""
    if byte_val > 127:
        return byte_val - 256
    return byte_val


def format_hex(data):
    """Format data as hex string with spacing."""
    return ' '.join(f'{b:02x}' for b in data)


def format_detailed(data):
    """Format data showing index, hex, and signed value for non-zero bytes."""
    parts = []
    for i, b in enumerate(data):
        if b != 0:
            parts.append(f"[{i}]=0x{b:02x}({get_signed_int(b):+d})")
    return ' '.join(parts) if parts else "(all zeros)"


def broadcast_to_web(ctrl_type, payload_dict):
    """Put a JSON payload onto the async SEND_QUEUE so the bridge task
    can forward it to the receiver. Safe to call from HID thread.
    """
    if LOOP and SEND_QUEUE:
        payload_obj = {"ctrl": ctrl_type}
        payload_obj.update(payload_dict)
        payload = json.dumps(payload_obj)
        asyncio.run_coroutine_threadsafe(SEND_QUEUE.put(payload), LOOP)


async def _send_loop_over_ws(ws):
    """Continuously read from SEND_QUEUE and send over the open websocket."""
    while True:
        payload = await SEND_QUEUE.get()
        try:
            await ws.send_str(payload)
        except Exception:
            raise


async def _bridge_client_loop(receiver_host, receiver_port):
    """Maintain a websocket connection to the remote receiver and forward queue payloads."""
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


def process_data(data):
    """
    Log all received HID data in multiple formats for discovery.
    Parse known button presses for MX Creative Keypad.
    """
    global LAST_BUTTON
    
    if not data:
        return

    # Normalize to list of ints
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
            print(f"[{timestamp}] BUTTON        | {btn_name:<20} | PRESSED")
            LAST_BUTTON = button_byte
            # Broadcast to web
            broadcast_to_web("KEYPAD", {"button": button_byte, "state": "PRESSED"})
        elif LAST_BUTTON != 0:
            # Button released (byte 6 went to 0)
            btn_name = KEYPAD_BUTTONS.get(LAST_BUTTON, f"UNKNOWN ({LAST_BUTTON})")
            print(f"[{timestamp}] BUTTON        | {btn_name:<20} | RELEASED")
            # Broadcast to web
            broadcast_to_web("KEYPAD", {"button": LAST_BUTTON, "state": "RELEASED"})
            LAST_BUTTON = 0
        
        # Also log any other non-zero bytes (for dial/roller discovery)
        handled = {0, 1, 2, 4, 5, 6}  # Skip known static bytes
        raw_items = []
        for i, b in enumerate(seq):
            if i in handled:
                continue
            if b != 0:
                raw_items.append(f"[{i}]=0x{b:02x}({get_signed_int(b):+d})")
        
        if raw_items:
            print(f"[{timestamp}] RAW OTHER     | {' '.join(raw_items)}")
        
        return

    # =========================================================================
    # OTHER REPORT IDs: Log raw for discovery
    # =========================================================================
    hex_str = format_hex(seq)
    detail_str = format_detailed(seq)

    print(f"[{timestamp}] RID=0x{report_id:02x} | HEX: {hex_str}")
    print(f"           | NON-ZERO: {detail_str}")
    print()


def scan_interfaces():
    """Scan for Logitech HID interfaces."""
    print("\nScanning for MX Creative Keypad / Logitech Interfaces...")
    print(f"{'IDX':<5} | {'USAGE PAGE':<12} | {'USAGE':<8} | {'INTERFACE TYPE':<25} | {'PRODUCT'}")
    print("-" * 100)

    devices = []
    found_count = 0

    for d in hid.enumerate():
        if d['vendor_id'] == LOGITECH_VID:
            name = d.get('product_string', 'Unknown') or 'Unknown'
            # Include Creative, Dial, MX, Keypad in search
            if any(x in name for x in ['Creative', 'Dial', 'MX', 'Keypad', 'Keys']):
                up = d.get('usage_page', 0)
                u = d.get('usage', 0)

                if up == 0x01:
                    type_guess = "Generic (Mouse/Keys)"
                elif up == 0x0C:
                    type_guess = "Consumer (Vol/Media)"
                elif up >= 0xFF00:
                    type_guess = "Vendor (RAW DATA)"
                else:
                    type_guess = f"Other (0x{up:04x})"

                print(f"{found_count:<5} | 0x{up:04x}       | 0x{u:04x}   | {type_guess:<25} | {name}")
                devices.append(d)
                found_count += 1

    if not devices:
        print("(No matching devices found)")

    return devices


def hid_listener(device_path):
    """Open the HID device and log all incoming packets."""
    print(f"\n[*] Opening device: {device_path}")
    print("[*] Logging all HID input. Press Ctrl+C to stop.\n")
    print("=" * 80)

    # Detect which API is available (Cython vs ctypes binding)
    if hasattr(hid, 'device'):
        # Cython-style API
        h = hid.device()
        if isinstance(device_path, bytes):
            h.open_path(device_path)
        else:
            h.open_path(device_path.encode() if isinstance(device_path, str) else device_path)

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
                process_data(data)

            time.sleep(0.001)
    else:
        # ctypes-style API (Device class)
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
                process_data(data)

            time.sleep(0.001)


def main():
    global LOOP
    
    # 1. Scan and list devices
    devices = scan_interfaces()
    if not devices:
        print("\nNo Logitech devices found. Make sure the device is connected.")
        return

    # 2. Select device
    print()
    try:
        idx = int(input("Enter IDX to sniff: "))
        if idx < 0 or idx >= len(devices):
            print("Invalid index.")
            return
        target = devices[idx]
    except (ValueError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    print("-" * 80)
    print(f"Target: {target.get('product_string', 'Unknown')}")
    print(f"Path: {target['path']}")
    print("-" * 80)

    # 3. Ask for receiver (web_server.py) host
    receiver_host = input("Enter receiver IP (default: 127.0.0.1): ").strip() or "127.0.0.1"

    # 4. Create asyncio event loop and start HID listener in background thread
    LOOP = asyncio.new_event_loop()
    
    def run_hid():
        try:
            hid_listener(target['path'])
        except IOError as e:
            print(f"\n[-] HID Error: {e}")
        except KeyboardInterrupt:
            pass
    
    hid_thread = threading.Thread(target=run_hid, daemon=True)
    hid_thread.start()
    
    # 5. Run the bridge client loop on the main thread
    try:
        LOOP.run_until_complete(_bridge_client_loop(receiver_host, WEB_PORT))
    except KeyboardInterrupt:
        print("\n[*] Stopped.")


if __name__ == "__main__":
    main()
