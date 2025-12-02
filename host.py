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
# 1. CONFIGURATION & STATE
# ==============================================================================
LOGITECH_VID = 0x046d
WEB_PORT = 8080

# Global state to manage the async loop from the separate HID thread
LOOP = None
# Queue used to send outgoing payloads from HID thread -> asyncio loop -> websocket
SEND_QUEUE = None
# Button mapping for byte index 1 (bitmask values)
# top left, top right, bottom left, bottom right
BUTTON_BIT_MAP = {
    0x08: 'TOP LEFT',
    0x10: 'TOP RIGHT',
    0x20: 'BOTTOM LEFT',
    0x40: 'BOTTOM RIGHT',
}
# remember previous state of byte 1 to detect presses/releases
LAST_BTN_BYTE1 = 0

# ==============================================================================
# 2. EMBEDDED WEB INTERFACE (HTML/CSS/JS)
# ==============================================================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MX Creative Console</title>
    <style>
        :root {
            --bg: #0e0e0e;
            --surface: #1a1a1a;
            --primary: #a0a0a0;
            --accent: #3b82f6; /* Logitech-ish Blue */
            --text-main: #ffffff;
            --text-dim: #555555;
        }

        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            overflow: hidden;
        }

        .header {
            position: absolute;
            top: 40px;
            text-transform: uppercase;
            letter-spacing: 4px;
            font-size: 0.8rem;
            color: var(--text-dim);
        }

        .stage {
            display: flex;
            gap: 100px;
            align-items: center;
        }

        /* --- BIG DIAL UI --- */
        .dial-container {
            position: relative;
            width: 240px;
            height: 240px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .dial-ring {
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            background: conic-gradient(from 0deg, #222, #333, #222);
            box-shadow: 
                -10px -10px 20px rgba(255,255,255,0.02),
                10px 10px 20px rgba(0,0,0,0.8);
            transition: transform 0.05s cubic-bezier(0.2, 0, 0, 1);
        }
        
        .dial-cap {
            position: absolute;
            width: 70%;
            height: 70%;
            background: linear-gradient(145deg, #1e1e1e, #161616);
            border-radius: 50%;
            box-shadow: inset 2px 2px 5px rgba(0,0,0,0.5);
            z-index: 2;
        }

        .dial-marker {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            width: 4px;
            height: 20px;
            background: var(--accent);
            border-radius: 2px;
            box-shadow: 0 0 10px var(--accent);
            z-index: 3;
        }

        /* --- SCROLLER UI --- */
        .scroller-container {
            position: relative;
            width: 80px;
            height: 160px;
            background: #111;
            border-radius: 12px;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.9);
            overflow: hidden;
            border: 1px solid #222;
        }

        .scroller-track {
            width: 100%;
            height: 100%;
            background-image: linear-gradient(0deg, transparent 50%, rgba(255,255,255,0.05) 50%);
            background-size: 100% 20px; /* The gap between ridges */
            background-position-y: 0px;
            transition: background-position-y 0.1s linear;
        }

        .scroller-overlay {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(0deg, var(--bg) 0%, transparent 20%, transparent 80%, var(--bg) 100%);
            pointer-events: none;
        }

        /* --- LABELS & DATA --- */
        .meta {
            margin-top: 20px;
            text-align: center;
        }
        .label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-dim);
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        .value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.2rem;
            color: var(--primary);
            transition: color 0.2s;
        }
        .active .value { color: var(--accent); text-shadow: 0 0 15px rgba(59, 130, 246, 0.5); }

    </style>
</head>
<body>

    <div class="header">MX Creative Interface</div>

    <div class="stage">
        <div id="group-big">
            <div class="dial-container">
                <div class="dial-ring" id="dial-visual">
                    <div class="dial-marker"></div>
                </div>
                <div class="dial-cap"></div>
            </div>
            <div class="meta">
                <div class="label">Dial</div>
                <div class="value" id="val-big">0</div>
            </div>
        </div>

        <div id="group-small">
            <div class="scroller-container">
                <div class="scroller-track" id="scroll-visual"></div>
                <div class="scroller-overlay"></div>
            </div>
            <div class="meta">
                <div class="label">Scroll</div>
                <div class="value" id="val-small">0</div>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket("ws://" + window.location.host + "/ws");
        
        let dialRotation = 0;
        let scrollPosition = 0;
        let tBig, tSmall;

        const elDial = document.getElementById('dial-visual');
        const elScroll = document.getElementById('scroll-visual');
        const valBig = document.getElementById('val-big');
        const valSmall = document.getElementById('val-small');
        const groupBig = document.getElementById('group-big');
        const groupSmall = document.getElementById('group-small');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const delta = parseInt(data.delta);
            
            if (data.ctrl === "BIG") {
                dialRotation += delta * 4; // Multiplier for visual feel
                elDial.style.transform = `rotate(${dialRotation}deg)`;
                
                valBig.innerText = delta > 0 ? `+${delta}` : delta;
                
                groupBig.classList.add('active');
                clearTimeout(tBig);
                tBig = setTimeout(() => groupBig.classList.remove('active'), 300);
            } 
            else if (data.ctrl === "SMALL") {
                scrollPosition -= delta * 15; // Move background pixels
                elScroll.style.backgroundPositionY = `${scrollPosition}px`;
                
                valSmall.innerText = delta > 0 ? `+${delta}` : delta;
                
                groupSmall.classList.add('active');
                clearTimeout(tSmall);
                tSmall = setTimeout(() => groupSmall.classList.remove('active'), 300);
            }
        };

        ws.onopen = () => console.log("Connected to Python Bridge");
        ws.onclose = () => console.log("Disconnected");
    </script>
</body>
</html>
"""

# ==============================================================================
# 3. HELPER FUNCTIONS (YOUR LOGIC)
# ==============================================================================

def get_signed_int(byte_val):
    """Converts a byte (0-255) to a signed int (-128 to 127)"""
    if byte_val > 127:
        return byte_val - 256
    return byte_val

def broadcast_to_web(ctrl_type, delta):
    """Put a JSON payload onto the async SEND_QUEUE so the bridge task
    (running in the asyncio loop) can forward it to the receiver.
    This is safe to call from the HID thread.
    """
    if LOOP and SEND_QUEUE:
        payload = json.dumps({"ctrl": ctrl_type, "delta": delta})
        asyncio.run_coroutine_threadsafe(SEND_QUEUE.put(payload), LOOP)


def broadcast_button_to_web(button_name, pressed):
    """Send button state to the web interface.
    button_name: 'TOP LEFT', 'TOP RIGHT', 'BOTTOM LEFT', 'BOTTOM RIGHT'
    pressed: True if pressed, False if released
    """
    if LOOP and SEND_QUEUE:
        payload = json.dumps({
            "type": "button",
            "button": button_name,
            "pressed": pressed
        })
        print(f"[*] Sending button to web: {payload}")
        asyncio.run_coroutine_threadsafe(SEND_QUEUE.put(payload), LOOP)
    else:
        print(f"[!] Cannot send button - LOOP={LOOP is not None}, QUEUE={SEND_QUEUE is not None}")


async def _send_loop_over_ws(ws):
    """Continuously read from SEND_QUEUE and send over the open websocket."""
    while True:
        payload = await SEND_QUEUE.get()
        try:
            await ws.send_str(payload)
        except Exception:
            # On any send failure, raise so outer connection handler can reconnect
            raise

def process_data(data):
    """
    Interprets the raw hex bytes.
    1. Prints human readable text to terminal (Your Logic).
    2. Sends data to Web Visualizer.
    """
    if not data: return

    # normalize to a sequence of ints
    try:
        seq = list(data)
    except Exception:
        # fallback if data is some custom type
        seq = [int(x) for x in data]

    timestamp = time.strftime("%H:%M:%S", time.localtime())
    report_id = seq[0]

    # =========================================================================
    # REPORT ID 02: Standard Mode
    # =========================================================================
    if report_id == 0x02:
        if len(seq) < 8: return

        # --- SWAPPED MAPPING ---
        raw_small = seq[6]  # Byte 6 -> SMALL SCROLLER
        raw_big   = seq[7]  # Byte 7 -> BIG DIAL

        val_small = get_signed_int(raw_small)
        val_big   = get_signed_int(raw_big)

        # --- DETECT SMALL SCROLLER ---
        if val_small != 0:
            # 1. Terminal Log
            direction = "RIGHT (CW)" if val_small > 0 else "LEFT (CCW)"
            bar = "▒" * abs(val_small)
            print(f"[{timestamp}] SMALL SCROLLER | {direction:<10} | Speed: {val_small:<3} | {bar}")
            
            # 2. Web Visualizer
            broadcast_to_web("SMALL", val_small)

        # --- DETECT BIG DIAL ---
        if val_big != 0:
            # 1. Terminal Log
            direction = "RIGHT (CW)" if val_big > 0 else "LEFT (CCW)"
            bar = "▓" * abs(val_big) 
            print(f"[{timestamp}] BIG DIAL       | {direction:<10} | Speed: {val_big:<3} | {bar}")

            # 2. Web Visualizer (send to remote receiver)
            broadcast_to_web("BIG", val_big)

        # Handle index 1 button bits (top/bottom left/right)
        global LAST_BTN_BYTE1
        btn_byte = seq[1] if len(seq) > 1 else 0
        changed = btn_byte ^ LAST_BTN_BYTE1
        if changed:
            for bit, name in BUTTON_BIT_MAP.items():
                if changed & bit:
                    state = bool(btn_byte & bit)
                    action = 'PRESSED' if state else 'RELEASED'
                    print(f"[{timestamp}] BUTTON        | {name:<12} | {action}")
                    # Send to web interface
                    broadcast_button_to_web(name, state)
        LAST_BTN_BYTE1 = btn_byte

        # Log any other non-zero bytes (raw) so we can see button presses
        handled = {0, 1, 6, 7}
        raw_items = []
        for i, b in enumerate(seq):
            if i in handled:
                continue
            if b != 0:
                raw_items.append(f"[{i}]=0x{b:02x} ({get_signed_int(b)})")

        if raw_items:
            print(f"[{timestamp}] RAW OTHER     | {' '.join(raw_items)}")

    # =========================================================================
    # REPORT ID 11: Vendor Mode (Fallback)
    # =========================================================================
    elif report_id == 0x11:
        if len(seq) < 6: return
        control_id = seq[4]
        val = get_signed_int(seq[5])

        if control_id == 0x01 and val != 0:
            # 1. Terminal Log
            direction = "RIGHT (CW)" if val > 0 else "LEFT (CCW)"
            bar = "▓" * abs(val)
            print(f"[{timestamp}] BIG DIAL (V)   | {direction:<10} | Speed: {val:<3} | {bar}")

            # 2. Web Visualizer (send to remote receiver)
            broadcast_to_web("BIG", val)

        # For other control IDs or bytes, print raw data for debugging/visibility
        handled = {0, 4, 5}
        raw_items = []
        for i, b in enumerate(seq):
            if i in handled:
                continue
            if b != 0:
                raw_items.append(f"[{i}]=0x{b:02x} ({get_signed_int(b)})")

        if raw_items:
            print(f"[{timestamp}] RAW VENDOR    | ctrl=0x{control_id:02x} | {' '.join(raw_items)}")

def scan_interfaces():
    print("\nScanning for MX Creative / Dialpad Interfaces...")
    print(f"{'IDX':<5} | {'USAGE PAGE':<12} | {'USAGE':<8} | {'INTERFACE TYPE'}")
    print("-" * 65)

    devices = []
    found_count = 0

    for d in hid.enumerate():
        if d['vendor_id'] == LOGITECH_VID:
            name = d.get('product_string', 'Unknown')
            if 'Creative' in name or 'Dial' in name or 'MX' in name:
                
                up = d.get('usage_page', 0)
                u = d.get('usage', 0)
                
                type_guess = "?"
                if up == 0x01: type_guess = "Generic (Mouse/Keys)"
                elif up == 0x0C: type_guess = "Consumer (Vol/Media)"
                elif up >= 0xFF00: type_guess = "Vendor (RAW DATA)"
                
                print(f"{found_count:<5} | 0x{up:04x}       | 0x{u:04x}   | {type_guess}")
                devices.append(d)
                found_count += 1

    return devices

# ==============================================================================
# 4. THREADS & SERVER SETUP
# ==============================================================================

def hid_listener_thread(device_path):
    """Background thread that runs the HID blocking loop"""
    print(f"[*] HID Thread Started for {device_path}")
    try:
        # The `hid` package has different bindings depending on which
        # implementation was installed. Detect and adapt to either:
        # - Cython binding: exposes `hid.device()` with `open_path()` etc.
        # - ctypes binding: exposes `Device` class and `enumerate()` function.
        if hasattr(hid, 'device'):
            # Cython-style API
            h = hid.device()
            try:
                h.open_path(device_path)
            except Exception:
                # try decoding bytes path if needed
                if isinstance(device_path, bytes):
                    h.open_path(device_path.decode())
                else:
                    raise
            try:
                # Some bindings call this `set_nonblocking`, others may
                # accept numeric values. Try both.
                h.set_nonblocking(False)
            except Exception:
                try:
                    h.set_nonblocking(0)
                except Exception:
                    pass

            while True:
                # Try the common signatures for cython binding read
                data = None
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
            # ctypes-style API (the `Device` class)
            # The ctypes Device expects `path` argument in the constructor.
            # Accept either bytes or str paths; the ctypes layer will handle it.
            if isinstance(device_path, bytes):
                path_arg = device_path
            else:
                path_arg = device_path

            h = hid.Device(path=path_arg)
            # Use property setter to set blocking/non-blocking
            try:
                h.nonblocking = False
            except Exception:
                pass

            while True:
                # ctypes Device.read signature is read(size, timeout=None)
                try:
                    data = h.read(64, timeout=1000)
                except TypeError:
                    # fallback if implementation expects positional timeout
                    try:
                        data = h.read(64, 1000)
                    except Exception:
                        data = h.read(64)

                if data:
                    process_data(data)

                time.sleep(0.001)

    except IOError as e:
        print(f"[-] HID Error: {e}")
    except Exception as e:
        print(f"[-] Thread Error: {e}")

async def _bridge_client_loop(receiver_host, receiver_port):
    """Maintain a websocket connection to the remote receiver at
    ws://{receiver_host}:{receiver_port}/bridge and forward queue payloads.
    Reconnects automatically on failures.
    """
    global SEND_QUEUE
    SEND_QUEUE = asyncio.Queue()
    url = f"ws://{receiver_host}:{receiver_port}/bridge"

    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    print(f"[*] Connected to receiver at {url}")
                    # send loop will raise if send fails, which will trigger reconnect
                    await _send_loop_over_ws(ws)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[-] Bridge connection failed: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)


def main():
    # 1. SCAN AND SELECT
    devices = scan_interfaces()
    if not devices:
        print("No device found.")
        return

    try:
        idx = int(input("\nEnter IDX to sniff (Select 0 for Mouse Mode): "))
        target = devices[idx]
    except Exception:
        return

    # Ask for the receiver host (machine running `web_server.py`)
    receiver = input(f"\nReceiver host/IP (machine running the web server) [10.10.101.133]: ") or "10.10.101.133"

    print("-" * 60)
    print(f"Target: {target.get('product_string','Unknown')}")
    print(f"Sending to receiver at: ws://{receiver}:{WEB_PORT}/bridge")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    # 2. START HID THREAD
    t = threading.Thread(target=hid_listener_thread, args=(target['path'],), daemon=True)
    t.start()

    # 3. Optionally open the receiver UI locally (not required)
    try:
        webbrowser.open(f"http://{receiver}:{WEB_PORT}")
    except Exception:
        pass

    # 4. START BRIDGE CLIENT (Main Thread)
    global LOOP

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