#!/usr/bin/env python3
"""
host.py - Unified HID + MIDI host for MX Creative Dialpad, Keypad, and MIDI controllers

Auto-detects and connects to:
- MX Creative Dialpad (dials + 4 buttons)
- MX Creative Keypad (9 buttons)
- MIDI controllers (e.g., Novation Launch Control XL)

Broadcasts all events to the web server.

Usage (fully automatic, no prompts):
    ./start_logi_host.sh
    python host.py
    python host.py --host=10.0.0.5    # Connect to remote web server
    python host.py --no-midi          # Disable MIDI

Manual mode (interactive device selection):
    python host.py --manual
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
import platform
from aiohttp import ClientSession

# ==============================================================================
# CONFIGURATION & STATE
# ==============================================================================
LOGITECH_VID = 0x046d
WEB_PORT = 8080

# Global state to manage the async loop from the separate HID thread
LOOP = None
SEND_QUEUE = None

# MIDI Configuration
MIDI_ENABLED = True
MIDI_PORT_NAME = "Launch Control XL"  # Partial match for port name
MIDI_POLL_INTERVAL = 0.001

# Novation Launch Control XL CC mappings (CC number -> descriptive name)
# Row 1: Send A knobs (CC 13-20)
# Row 2: Send B knobs (CC 29-36)
# Row 3: Pan knobs (CC 49-56)
# Faders (CC 77-84)
MIDI_CC_MAP = {
    # Send A knobs (top row)
    13: "KNOB_1A", 14: "KNOB_2A", 15: "KNOB_3A", 16: "KNOB_4A",
    17: "KNOB_5A", 18: "KNOB_6A", 19: "KNOB_7A", 20: "KNOB_8A",
    # Send B knobs (second row)
    29: "KNOB_1B", 30: "KNOB_2B", 31: "KNOB_3B", 32: "KNOB_4B",
    33: "KNOB_5B", 34: "KNOB_6B", 35: "KNOB_7B", 36: "KNOB_8B",
    # Pan knobs (third row)
    49: "KNOB_1C", 50: "KNOB_2C", 51: "KNOB_3C", 52: "KNOB_4C",
    53: "KNOB_5C", 54: "KNOB_6C", 55: "KNOB_7C", 56: "KNOB_8C",
    # Faders
    77: "FADER_1", 78: "FADER_2", 79: "FADER_3", 80: "FADER_4",
    81: "FADER_5", 82: "FADER_6", 83: "FADER_7", 84: "FADER_8",
}

# Note mappings for buttons (Note number -> descriptive name)
MIDI_NOTE_MAP = {
    # Track Focus buttons (top row)
    41: "BTN_FOCUS_1", 42: "BTN_FOCUS_2", 43: "BTN_FOCUS_3", 44: "BTN_FOCUS_4",
    57: "BTN_FOCUS_5", 58: "BTN_FOCUS_6", 59: "BTN_FOCUS_7", 60: "BTN_FOCUS_8",
    # Track Control buttons (bottom row)
    73: "BTN_CTRL_1", 74: "BTN_CTRL_2", 75: "BTN_CTRL_3", 76: "BTN_CTRL_4",
    89: "BTN_CTRL_5", 90: "BTN_CTRL_6", 91: "BTN_CTRL_7", 92: "BTN_CTRL_8",
}

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
    """Process data from MX Creative Dialpad (dials and 4 buttons)
    
    Data format (Report ID 0x11 via Generic HID interface):
    - Byte 0: Report ID (0x11)
    - Byte 4: Control ID (0x01 = big dial)
    - Byte 5: Dial delta (signed: 0xff=-1, 0x01=+1, 0x02=+2, etc.)
    
    Legacy format (Report ID 0x02 via Vendor interface - may not work with Logi Options+):
    - Byte 0: Report ID (0x02)
    - Byte 1: Button bitmask
    - Byte 6: Small scroller
    - Byte 7: Big dial
    """
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
    # REPORT ID 0x11: Generic HID Mode (works with Logi Options+ killed)
    # Format: [0x11, 0xff, type, 0x00, control_id, delta, ...]
    # - type 0x0d = dial rotation
    # - type 0x0a = button/other
    # =========================================================================
    if report_id == 0x11:
        if len(seq) < 6:
            return
        
        msg_type = seq[2]  # 0x0d = dial, 0x0a = button/other
        control_id = seq[4]
        val = get_signed_int(seq[5])

        # Dial rotation (control_id 0x00 or 0x01, msg_type 0x0d)
        if msg_type == 0x0d and val != 0:
            direction = "RIGHT (CW)" if val > 0 else "LEFT (CCW)"
            bar = "▓" * min(abs(val), 10)
            print(f"[{timestamp}] BIG DIAL       | {direction:<10} | Speed: {val:<3} | {bar}")
            broadcast_to_web("BIG", val)
        
        # Button events (msg_type 0x0a)
        elif msg_type == 0x0a:
            # Byte 5 seems to contain button identifier: 0x53, 0x56, 0x59, 0x5a
            # These may map to the 4 corner buttons
            btn_val = seq[5]
            if btn_val != 0:
                # Map button values to names (discovered values)
                btn_map = {
                    0x53: "TOP LEFT",
                    0x56: "TOP RIGHT",
                    0x59: "BOTTOM LEFT",
                    0x5a: "BOTTOM RIGHT",
                }
                btn_name = btn_map.get(btn_val, f"BTN_0x{btn_val:02x}")
                # Check byte 6 or 7 for press/release state
                state_byte = seq[6] if len(seq) > 6 else 0
                action = "PRESSED" if state_byte else "RELEASED"
                print(f"[{timestamp}] DIALPAD BTN   | {btn_name:<12} | {action}")
                broadcast_to_web("BTN", {"name": btn_name, "state": action})

    # =========================================================================
    # REPORT ID 0x02: Vendor Mode (legacy - may not work with Logi Options+)
    # =========================================================================
    elif report_id == 0x02:
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
    """Scan for Logitech MX Creative devices and auto-identify type.
    Returns the best interface for each device type.
    """
    print("\n[*] Auto-detecting Logitech MX Creative devices...")
    
    dialpad_candidates = []
    keypad_candidates = []
    
    for d in hid.enumerate():
        if d['vendor_id'] != LOGITECH_VID:
            continue
            
        name = d.get('product_string', '') or ''
        up = d.get('usage_page', 0)
        usage = d.get('usage', 0)
        
        name_lower = name.lower()
        
        # MX Creative Keypad - prefer vendor-specific interface 0xff43
        if 'keypad' in name_lower or 'keys' in name_lower:
            keypad_candidates.append((d, up))
        # MX Dialpad - prefer vendor-specific interface 0xff43 with usage 0x0202
        elif 'dialpad' in name_lower:
            dialpad_candidates.append((d, up, usage))
        # Fallback: "MX Creative" without "Keypad" is likely the dialpad
        elif 'dial' in name_lower:
            dialpad_candidates.append((d, up, usage))
    
    # Select best interface for each device
    dialpad_device = None
    keypad_device = None
    
    # For dialpad: prefer Generic interface 0x0001/0x0002 (works even with Logi Options+ running)
    # The vendor interface 0xff43/0x0202 may be locked by Logi Options+
    for d, up, usage in dialpad_candidates:
        if up == 0x0001 and usage == 0x0002:
            dialpad_device = d
            break
    # Fallback to 0x0001/0x0001
    if not dialpad_device:
        for d, up, usage in dialpad_candidates:
            if up == 0x0001 and usage == 0x0001:
                dialpad_device = d
                break
    # Last resort: vendor interface (may not work if Logi Options+ is running)
    if not dialpad_device:
        for d, up, usage in dialpad_candidates:
            if up >= 0xFF00:
                dialpad_device = d
                break
    
    # For keypad: prefer 0xff43/0x1a02 (first vendor interface)
    for d, up in keypad_candidates:
        if up == 0xff43:
            keypad_device = d
            break
    # Fallback to any vendor interface
    if not keypad_device:
        for d, up in keypad_candidates:
            if up >= 0xFF00:
                keypad_device = d
                break
    
    # Report findings
    if dialpad_device:
        print(f"    [DIALPAD] {dialpad_device.get('product_string', 'Unknown')}")
    if keypad_device:
        print(f"    [KEYPAD]  {keypad_device.get('product_string', 'Unknown')}")
    if not dialpad_device and not keypad_device:
        print("    (No MX Creative devices found)")
    
    return dialpad_device, keypad_device


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
# MIDI LISTENER
# ==============================================================================

def find_midi_port():
    """Find a MIDI port matching MIDI_PORT_NAME."""
    try:
        import rtmidi
    except ImportError:
        print("[!] rtmidi not installed. Run: pip install python-rtmidi")
        return None, None
    
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    
    if not ports:
        return None, None
    
    # Find port matching name
    for i, port_name in enumerate(ports):
        if MIDI_PORT_NAME.lower() in port_name.lower():
            return midi_in, i
    
    # Not found - list available ports
    print(f"[!] MIDI port '{MIDI_PORT_NAME}' not found. Available ports:")
    for i, p in enumerate(ports):
        print(f"    [{i}] {p}")
    
    return None, None


def midi_listener_thread():
    """Background thread that listens for MIDI messages."""
    print("[*] MIDI Thread Starting...")
    
    midi_in, port_idx = find_midi_port()
    if midi_in is None:
        print("[-] MIDI disabled: no matching port found")
        return
    
    try:
        ports = midi_in.get_ports()
        midi_in.open_port(port_idx)
        print(f"[*] MIDI Connected: {ports[port_idx]}")
    except Exception as e:
        print(f"[-] MIDI Error: {e}")
        return
    
    # Track button states for toggle behavior
    button_states = {}
    
    while True:
        try:
            msg = midi_in.get_message()
            if msg:
                midi_data, delta_time = msg
                status = midi_data[0]
                data1 = midi_data[1] if len(midi_data) > 1 else 0
                data2 = midi_data[2] if len(midi_data) > 2 else 0
                
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                channel = status & 0x0F
                msg_type = status & 0xF0
                
                # Control Change (CC): 0xB0-0xBF (176-191)
                if msg_type == 0xB0:
                    cc_num = data1
                    cc_val = data2
                    normalized = round((cc_val / 127.0) * 100.0, 1)
                    
                    if cc_num in MIDI_CC_MAP:
                        cc_name = MIDI_CC_MAP[cc_num]
                        print(f"[{timestamp}] MIDI CC       | {cc_name:<12} | Val: {cc_val:3d} ({normalized:5.1f}%)")
                        broadcast_to_web("MIDI_CC", {
                            "cc": cc_num,
                            "name": cc_name,
                            "value": cc_val,
                            "normalized": normalized
                        })
                    else:
                        print(f"[{timestamp}] MIDI CC       | CC_{cc_num:<9} | Val: {cc_val:3d} ({normalized:5.1f}%)")
                        broadcast_to_web("MIDI_CC", {
                            "cc": cc_num,
                            "name": f"CC_{cc_num}",
                            "value": cc_val,
                            "normalized": normalized
                        })
                
                # Note On: 0x90-0x9F (144-159)
                elif msg_type == 0x90:
                    note = data1
                    velocity = data2
                    
                    if velocity > 0:  # Note On
                        if note in MIDI_NOTE_MAP:
                            note_name = MIDI_NOTE_MAP[note]
                            # Toggle button state
                            button_states[note] = not button_states.get(note, False)
                            state = "ON" if button_states[note] else "OFF"
                            print(f"[{timestamp}] MIDI NOTE     | {note_name:<12} | {state} (vel: {velocity})")
                            broadcast_to_web("MIDI_NOTE", {
                                "note": note,
                                "name": note_name,
                                "velocity": velocity,
                                "state": state
                            })
                        else:
                            print(f"[{timestamp}] MIDI NOTE     | Note_{note:<7} | ON (vel: {velocity})")
                            broadcast_to_web("MIDI_NOTE", {
                                "note": note,
                                "name": f"Note_{note}",
                                "velocity": velocity,
                                "state": "ON"
                            })
                    else:  # Note Off (velocity 0)
                        if note in MIDI_NOTE_MAP:
                            note_name = MIDI_NOTE_MAP[note]
                            print(f"[{timestamp}] MIDI NOTE     | {note_name:<12} | RELEASE")
                        
                # Note Off: 0x80-0x8F (128-143)
                elif msg_type == 0x80:
                    note = data1
                    if note in MIDI_NOTE_MAP:
                        note_name = MIDI_NOTE_MAP[note]
                        print(f"[{timestamp}] MIDI NOTE     | {note_name:<12} | RELEASE")
            
            time.sleep(MIDI_POLL_INTERVAL)
            
        except Exception as e:
            print(f"[-] MIDI Error: {e}")
            time.sleep(1)


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
    global LOOP, MIDI_ENABLED
    
    # Check for manual mode flag
    manual_mode = '--manual' in sys.argv or '-m' in sys.argv
    
    # Check for --no-midi flag
    if '--no-midi' in sys.argv:
        MIDI_ENABLED = False
    
    # Check for custom receiver IP
    receiver = "127.0.0.1"
    for arg in sys.argv[1:]:
        if arg.startswith('--host='):
            receiver = arg.split('=', 1)[1]
        elif arg.startswith('-h='):
            receiver = arg.split('=', 1)[1]
    
    # 1. SCAN FOR DEVICES
    if manual_mode:
        # Manual selection mode
        devices = scan_all_interfaces()
        if not devices:
            print("No devices found.")
            return

        print("\nEnter device indices to use (comma-separated, or 'all' for auto-detect):")
        user_input = input("> ").strip()
        
        if user_input.lower() == 'all':
            dialpad_device, keypad_device = scan_devices()
            selected_devices = []
            if dialpad_device:
                selected_devices.append((dialpad_device['path'], DEVICE_TYPE_DIALPAD, dialpad_device.get('product_string', 'Dialpad')))
            if keypad_device:
                selected_devices.append((keypad_device['path'], DEVICE_TYPE_KEYPAD, keypad_device.get('product_string', 'Keypad')))
        else:
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
        
        # Ask for receiver in manual mode
        receiver = input("\nReceiver host/IP [127.0.0.1]: ").strip() or "127.0.0.1"
    else:
        # AUTO MODE (default) - auto-detect devices, but ask for receiver IP
        dialpad_device, keypad_device = scan_devices()
        
        selected_devices = []
        if dialpad_device:
            selected_devices.append((dialpad_device['path'], DEVICE_TYPE_DIALPAD, dialpad_device.get('product_string', 'Dialpad')))
        if keypad_device:
            selected_devices.append((keypad_device['path'], DEVICE_TYPE_KEYPAD, keypad_device.get('product_string', 'Keypad')))
        
        if not selected_devices and not MIDI_ENABLED:
            print("\n[!] No MX Creative devices found!")
            print("    Make sure your Dialpad or Keypad is connected.")
            print("    Use --manual flag for interactive device selection.")
            return
        
        # Ask for receiver IP (unless provided via --host=)
        if receiver == "127.0.0.1":
            receiver = input("\nReceiver host/IP [127.0.0.1]: ").strip() or "127.0.0.1"

    if not selected_devices and not MIDI_ENABLED:
        print("No devices selected.")
        return

    # 3. PRINT CONFIG
    print("\n" + "=" * 60)
    print("STARTING LOGI HOST")
    print("=" * 60)
    for path, dev_type, name in selected_devices:
        print(f"  [{dev_type.upper()}] {name}")
    if MIDI_ENABLED:
        print(f"  [MIDI] {MIDI_PORT_NAME}")
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

    # 5. START MIDI THREAD (if enabled)
    if MIDI_ENABLED:
        midi_thread = threading.Thread(target=midi_listener_thread, daemon=True)
        midi_thread.start()

    # 6. Optionally open the web UI (only in manual mode)
    if manual_mode:
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
