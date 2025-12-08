import asyncio
import json
import time
import os
import platform
import threading
from aiohttp import web

WEB_PORT = 8080
COMMAND_FILE = "C:/temp/logi_command.json"
POSITION_FILE = "C:/temp/logi_position.json"
BUTTON_FILE = "C:/temp/logi_button.json"

# State file for ComfyUI integration (continuous reads)
if platform.system() == "Windows":
    STATE_FILE = "C:/temp/controller_state.json"
else:
    STATE_FILE = "/tmp/controller_state.json"

# Ensure temp directory exists
os.makedirs(os.path.dirname(COMMAND_FILE), exist_ok=True)
if platform.system() != "Windows":
    os.makedirs("/tmp", exist_ok=True)

# Global controller state for ComfyUI (written to file continuously)
controller_state = {
    "dial_value": 0,
    "dial_delta": 0,
    "scroller_value": 0,
    "scroller_delta": 0,
    "btn_top_left": False,
    "btn_top_right": False,
    "btn_bottom_left": False,
    "btn_bottom_right": False,
    # Keypad buttons
    "btn_1": False, "btn_2": False, "btn_3": False,
    "btn_4": False, "btn_5": False, "btn_6": False,
    "btn_7": False, "btn_8": False, "btn_9": False,
    # LCXL Faders
    "fader_1": 0.0, "fader_2": 0.0, "fader_3": 0.0, "fader_4": 0.0,
    "fader_5": 0.0, "fader_6": 0.0, "fader_7": 0.0, "fader_8": 0.0,
    # LCXL Knobs Row A
    "knob_1a": 0.0, "knob_2a": 0.0, "knob_3a": 0.0, "knob_4a": 0.0,
    "knob_5a": 0.0, "knob_6a": 0.0, "knob_7a": 0.0, "knob_8a": 0.0,
    # LCXL Knobs Row B
    "knob_1b": 0.0, "knob_2b": 0.0, "knob_3b": 0.0, "knob_4b": 0.0,
    "knob_5b": 0.0, "knob_6b": 0.0, "knob_7b": 0.0, "knob_8b": 0.0,
    # LCXL Knobs Row C
    "knob_1c": 0.0, "knob_2c": 0.0, "knob_3c": 0.0, "knob_4c": 0.0,
    "knob_5c": 0.0, "knob_6c": 0.0, "knob_7c": 0.0, "knob_8c": 0.0,
    # LCXL Focus buttons (top row)
    "focus_1": False, "focus_2": False, "focus_3": False, "focus_4": False,
    "focus_5": False, "focus_6": False, "focus_7": False, "focus_8": False,
    # LCXL Control buttons (bottom row)
    "ctrl_1": False, "ctrl_2": False, "ctrl_3": False, "ctrl_4": False,
    "ctrl_5": False, "ctrl_6": False, "ctrl_7": False, "ctrl_8": False,
    # Timestamp
    "last_update": 0,
}
state_lock = threading.Lock()


def write_state_file():
    """Write the current controller state to file for ComfyUI."""
    try:
        with state_lock:
            controller_state["last_update"] = time.time()
            with open(STATE_FILE, 'w') as f:
                json.dump(controller_state, f)
    except Exception as e:
        pass  # Silently ignore file write errors


def update_controller_state(key, value):
    """Update a controller state value and write to file."""
    with state_lock:
        controller_state[key] = value
    write_state_file()


# Global state for tracking slider and accumulated position
last_slider_state = {
    "delta": 0,
    "ctrl": "unknown"
}

# Accumulated position offsets
accumulated_position = {
    "x": 0,
    "y": 0
}

# Button states
button_states = {
    "TOP LEFT": False,
    "TOP RIGHT": False,
    "BOTTOM LEFT": False,
    "BOTTOM RIGHT": False
}


def write_command_file(delta, ctrl="BIG"):
    """Write command to file for ExtendScript to read"""
    try:
        cmd = {
            "delta": delta,
            "ctrl": ctrl,
            "timestamp": time.time()
        }
        with open(COMMAND_FILE, 'w') as f:
            json.dump(cmd, f)
        print(f"[*] Wrote command: delta={delta}")
    except Exception as e:
        print(f"[!] Error writing command file: {e}")


def write_position_file(delta, ctrl="BIG"):
    """Write accumulated position to file for AE expression to read"""
    global accumulated_position
    try:
        # Accumulate based on control type
        if ctrl == "BIG":
            accumulated_position["x"] += delta
        else:
            accumulated_position["y"] += delta
        
        with open(POSITION_FILE, 'w') as f:
            json.dump(accumulated_position, f)
        print(f"[*] Position: x={accumulated_position['x']}, y={accumulated_position['y']}")
    except Exception as e:
        print(f"[!] Error writing position file: {e}")


def write_button_file(button_name, pressed):
    """Write button state to file for ExtendScript to read"""
    try:
        btn_data = {
            "button": button_name,
            "pressed": pressed,
            "timestamp": time.time()
        }
        with open(BUTTON_FILE, 'w') as f:
            json.dump(btn_data, f)
    except Exception as e:
        print(f"[!] Error writing button file: {e}")


# Keep small and self-contained: copy of the HTML UI used previously
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

        /* --- BUTTON GRID (Keypad 3x3) --- */
        .button-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            width: 200px;
        }

        /* --- BUTTON GRID (Dialpad 2x2) --- */
        .button-grid-2x2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            width: 130px;
        }
        
        .hw-button {
            width: 60px;
            height: 60px;
            background: linear-gradient(145deg, #1a1a1a, #0f0f0f);
            border: 2px solid #333;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: bold;
            color: var(--text-dim);
            transition: all 0.1s ease;
            box-shadow: 
                0 4px 6px rgba(0,0,0,0.4),
                inset 0 1px 0 rgba(255,255,255,0.05);
        }
        
        .hw-button.pressed {
            background: linear-gradient(145deg, #0a0a0a, #151515);
            border-color: var(--accent);
            color: var(--accent);
            box-shadow: 
                0 0 20px rgba(59, 130, 246, 0.3),
                inset 0 2px 4px rgba(0,0,0,0.5);
            transform: translateY(2px);
        }

        /* --- MIDI CONTROLLER UI --- */
        .midi-section {
            margin-top: 40px;
            padding: 20px;
            background: var(--surface);
            border-radius: 12px;
            border: 1px solid #333;
        }

        .midi-section .label {
            text-align: center;
            margin-bottom: 15px;
            font-size: 0.85rem;
            color: var(--accent);
        }

        .midi-row {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-bottom: 10px;
        }

        .midi-knob {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: conic-gradient(from 220deg, var(--accent) 0%, var(--accent) var(--pct, 0%), #333 var(--pct, 0%), #333 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.55rem;
            color: var(--text-dim);
            position: relative;
            box-shadow: inset 0 0 8px rgba(0,0,0,0.5);
        }

        .midi-knob::after {
            content: '';
            position: absolute;
            width: 28px;
            height: 28px;
            background: #1a1a1a;
            border-radius: 50%;
        }

        .midi-knob span {
            position: absolute;
            z-index: 2;
            font-size: 0.5rem;
        }

        .midi-fader-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 40px;
        }

        .midi-fader {
            width: 12px;
            height: 80px;
            background: #222;
            border-radius: 4px;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 0 6px rgba(0,0,0,0.8);
        }

        .midi-fader-fill {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(to top, var(--accent), #6bb3ff);
            height: var(--pct, 0%);
            transition: height 0.05s ease-out;
            border-radius: 4px;
        }

        .midi-fader-label {
            font-size: 0.5rem;
            color: var(--text-dim);
            margin-top: 4px;
        }

        .midi-btn {
            width: 36px;
            height: 24px;
            background: linear-gradient(145deg, #1a1a1a, #0f0f0f);
            border: 1px solid #333;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.45rem;
            color: var(--text-dim);
            transition: all 0.1s ease;
        }

        .midi-btn.on {
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
        }

    </style>
</head>
<body>

    <div class="header">MX Creative Interface</div>

    <div class="stage">
        <div id="group-keypad">
            <div class="button-grid">
                <div class="hw-button" id="btn-1">1</div>
                <div class="hw-button" id="btn-2">2</div>
                <div class="hw-button" id="btn-3">3</div>
                <div class="hw-button" id="btn-4">4</div>
                <div class="hw-button" id="btn-5">5</div>
                <div class="hw-button" id="btn-6">6</div>
                <div class="hw-button" id="btn-7">7</div>
                <div class="hw-button" id="btn-8">8</div>
                <div class="hw-button" id="btn-9">9</div>
            </div>
            <div class="meta">
                <div class="label">Keypad</div>
            </div>
        </div>

        <div id="group-dialpad-btns">
            <div class="button-grid-2x2">
                <div class="hw-button" id="btn-tl">TL</div>
                <div class="hw-button" id="btn-tr">TR</div>
                <div class="hw-button" id="btn-bl">BL</div>
                <div class="hw-button" id="btn-br">BR</div>
            </div>
            <div class="meta">
                <div class="label">Dialpad</div>
            </div>
        </div>

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

    <!-- MIDI Controller Section -->
    <div class="midi-section" id="midi-section">
        <div class="label">Launch Control XL</div>
        
        <!-- Row A: Send A Knobs (CC 13-20) -->
        <div class="midi-row" id="midi-row-a">
            <div class="midi-knob" id="midi-cc-13" data-cc="13"><span>1A</span></div>
            <div class="midi-knob" id="midi-cc-14" data-cc="14"><span>2A</span></div>
            <div class="midi-knob" id="midi-cc-15" data-cc="15"><span>3A</span></div>
            <div class="midi-knob" id="midi-cc-16" data-cc="16"><span>4A</span></div>
            <div class="midi-knob" id="midi-cc-17" data-cc="17"><span>5A</span></div>
            <div class="midi-knob" id="midi-cc-18" data-cc="18"><span>6A</span></div>
            <div class="midi-knob" id="midi-cc-19" data-cc="19"><span>7A</span></div>
            <div class="midi-knob" id="midi-cc-20" data-cc="20"><span>8A</span></div>
        </div>
        
        <!-- Row B: Send B Knobs (CC 29-36) -->
        <div class="midi-row" id="midi-row-b">
            <div class="midi-knob" id="midi-cc-29" data-cc="29"><span>1B</span></div>
            <div class="midi-knob" id="midi-cc-30" data-cc="30"><span>2B</span></div>
            <div class="midi-knob" id="midi-cc-31" data-cc="31"><span>3B</span></div>
            <div class="midi-knob" id="midi-cc-32" data-cc="32"><span>4B</span></div>
            <div class="midi-knob" id="midi-cc-33" data-cc="33"><span>5B</span></div>
            <div class="midi-knob" id="midi-cc-34" data-cc="34"><span>6B</span></div>
            <div class="midi-knob" id="midi-cc-35" data-cc="35"><span>7B</span></div>
            <div class="midi-knob" id="midi-cc-36" data-cc="36"><span>8B</span></div>
        </div>
        
        <!-- Row C: Pan Knobs (CC 49-56) -->
        <div class="midi-row" id="midi-row-c">
            <div class="midi-knob" id="midi-cc-49" data-cc="49"><span>1C</span></div>
            <div class="midi-knob" id="midi-cc-50" data-cc="50"><span>2C</span></div>
            <div class="midi-knob" id="midi-cc-51" data-cc="51"><span>3C</span></div>
            <div class="midi-knob" id="midi-cc-52" data-cc="52"><span>4C</span></div>
            <div class="midi-knob" id="midi-cc-53" data-cc="53"><span>5C</span></div>
            <div class="midi-knob" id="midi-cc-54" data-cc="54"><span>6C</span></div>
            <div class="midi-knob" id="midi-cc-55" data-cc="55"><span>7C</span></div>
            <div class="midi-knob" id="midi-cc-56" data-cc="56"><span>8C</span></div>
        </div>
        
        <!-- Track Focus Buttons (Notes 41-44, 57-60) -->
        <div class="midi-row">
            <div class="midi-btn" id="midi-note-41">F1</div>
            <div class="midi-btn" id="midi-note-42">F2</div>
            <div class="midi-btn" id="midi-note-43">F3</div>
            <div class="midi-btn" id="midi-note-44">F4</div>
            <div class="midi-btn" id="midi-note-57">F5</div>
            <div class="midi-btn" id="midi-note-58">F6</div>
            <div class="midi-btn" id="midi-note-59">F7</div>
            <div class="midi-btn" id="midi-note-60">F8</div>
        </div>
        
        <!-- Track Control Buttons (Notes 73-76, 89-92) -->
        <div class="midi-row">
            <div class="midi-btn" id="midi-note-73">C1</div>
            <div class="midi-btn" id="midi-note-74">C2</div>
            <div class="midi-btn" id="midi-note-75">C3</div>
            <div class="midi-btn" id="midi-note-76">C4</div>
            <div class="midi-btn" id="midi-note-89">C5</div>
            <div class="midi-btn" id="midi-note-90">C6</div>
            <div class="midi-btn" id="midi-note-91">C7</div>
            <div class="midi-btn" id="midi-note-92">C8</div>
        </div>
        
        <!-- Faders (CC 77-84) -->
        <div class="midi-row" style="margin-top: 15px;">
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-77"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">1</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-78"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">2</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-79"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">3</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-80"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">4</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-81"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">5</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-82"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">6</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-83"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">7</div>
            </div>
            <div class="midi-fader-container">
                <div class="midi-fader" id="midi-cc-84"><div class="midi-fader-fill"></div></div>
                <div class="midi-fader-label">8</div>
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
        
        // Keypad button elements (1-9)
        const keypadButtons = {};
        for (let i = 1; i <= 9; i++) {
            keypadButtons[i] = document.getElementById('btn-' + i);
        }

        // Dialpad button elements (4 corner buttons)
        const dialpadButtons = {
            "TOP LEFT": document.getElementById('btn-tl'),
            "TOP RIGHT": document.getElementById('btn-tr'),
            "BOTTOM LEFT": document.getElementById('btn-bl'),
            "BOTTOM RIGHT": document.getElementById('btn-br')
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const delta = data.delta || 0;
            
            // Handle keypad button events (BTN ctrl with numeric name like "1", "2", etc.)
            if (data.ctrl === "KEYPAD") {
                const btnNum = parseInt(data.button);
                const btn = keypadButtons[btnNum];
                if (btn) {
                    if (data.state === "PRESSED") {
                        btn.classList.add('pressed');
                    } else {
                        btn.classList.remove('pressed');
                    }
                }
                return;
            }

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
            else if (data.ctrl === "BTN") {
                // Handle dialpad button events
                const btn = dialpadButtons[data.name];
                if (btn) {
                    if (data.state === "PRESSED") {
                        btn.classList.add('pressed');
                    } else {
                        btn.classList.remove('pressed');
                    }
                }
            }
            // Handle MIDI CC events (knobs and faders)
            else if (data.ctrl === "MIDI_CC") {
                const cc = data.cc;
                const pct = data.normalized;
                const el = document.getElementById('midi-cc-' + cc);
                if (el) {
                    if (el.classList.contains('midi-fader')) {
                        // Fader: set fill height
                        const fill = el.querySelector('.midi-fader-fill');
                        if (fill) fill.style.setProperty('--pct', pct + '%');
                    } else {
                        // Knob: set conic gradient percentage
                        el.style.setProperty('--pct', (pct * 2.8) + 'deg'); // 280deg sweep
                    }
                }
            }
            // Handle MIDI Note events (buttons)
            else if (data.ctrl === "MIDI_NOTE") {
                const note = data.note;
                const el = document.getElementById('midi-note-' + note);
                if (el) {
                    if (data.state === "ON") {
                        el.classList.add('on');
                    } else {
                        el.classList.remove('on');
                    }
                }
            }
        };

        ws.onopen = () => console.log("Connected to Python Bridge");
        ws.onclose = () => console.log("Disconnected");
    </script>
</body>
</html>
"""

CONNECTED_CLIENTS = set()

async def broadcast_to_browsers(payload):
    # payload is a JSON string
    for ws in list(CONNECTED_CLIENTS):
        try:
            await ws.send_str(payload)
        except Exception:
            try:
                CONNECTED_CLIENTS.remove(ws)
            except Exception:
                pass


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CONNECTED_CLIENTS.add(ws)
    try:
        async for msg in ws:  # Keep socket open; we do not expect incoming messages from browser
            pass
    finally:
        try:
            CONNECTED_CLIENTS.remove(ws)
        except Exception:
            pass
    return ws


async def bridge_handler(request):
    # Sender (visualizer.py) connects here and sends JSON messages to be relayed to browsers
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    peer = request.remote
    print(f"[*] Bridge connected from {peer}")
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                payload = msg.data
                # Update global state and write to files
                try:
                    data = json.loads(payload)
                    
                    # Handle dialpad button events (ctrl: "BTN", name: "...", state: "PRESSED"/"RELEASED")
                    if data.get('ctrl') == 'BTN':
                        button_name = data.get('name', '')
                        pressed = data.get('state') == 'PRESSED'
                        if button_name in button_states:
                            button_states[button_name] = pressed
                            print(f"[*] Button: {button_name} {'PRESSED' if pressed else 'RELEASED'}")
                            # Write to file for ExtendScript
                            write_button_file(button_name, pressed)
                            # Update controller state for ComfyUI
                            state_key_map = {
                                "TOP LEFT": "btn_top_left",
                                "TOP RIGHT": "btn_top_right",
                                "BOTTOM LEFT": "btn_bottom_left",
                                "BOTTOM RIGHT": "btn_bottom_right"
                            }
                            if button_name in state_key_map:
                                update_controller_state(state_key_map[button_name], pressed)
                    
                    # Handle keypad button events (ctrl: "KEYPAD", button: 1-9, state: "PRESSED"/"RELEASED")
                    elif data.get('ctrl') == 'KEYPAD':
                        button_num = data.get('button', 0)
                        button_name = str(button_num)  # "1", "2", etc.
                        pressed = data.get('state') == 'PRESSED'
                        print(f"[*] Keypad: {button_name} {'PRESSED' if pressed else 'RELEASED'}")
                        # Write to file for ExtendScript
                        write_button_file(button_name, pressed)
                        # Update controller state for ComfyUI
                        if 1 <= button_num <= 9:
                            update_controller_state(f"btn_{button_num}", pressed)
                    
                    # Handle dial/scroller events
                    elif 'delta' in data:
                        last_slider_state.update(data)
                        ctrl = data.get('ctrl', 'BIG')
                        delta = data.get('delta', 0)
                        write_command_file(delta, ctrl)
                        write_position_file(delta, ctrl)
                        # Update controller state for ComfyUI
                        if ctrl == 'BIG':
                            with state_lock:
                                controller_state["dial_value"] += delta
                                controller_state["dial_delta"] = delta
                            write_state_file()
                        elif ctrl == 'SMALL':
                            with state_lock:
                                controller_state["scroller_value"] += delta
                                controller_state["scroller_delta"] = delta
                            write_state_file()
                    
                    # Handle MIDI CC events
                    elif data.get('ctrl') == 'MIDI_CC':
                        cc = data.get('cc', 0)
                        val = data.get('value', 0)
                        name = data.get('name', f'CC_{cc}')
                        print(f"[*] MIDI CC: {name} = {val}")
                        # Update controller state for ComfyUI
                        # Convert 0-127 to 0.0-1.0
                        normalized = val / 127.0
                        # Map CC to state key based on name pattern
                        if name.startswith("FADER_"):
                            fader_num = name.split("_")[1]
                            update_controller_state(f"fader_{fader_num}", normalized)
                        elif name.startswith("KNOB_"):
                            parts = name.split("_")  # e.g., "KNOB_1_A"
                            if len(parts) == 3:
                                knob_num = parts[1]
                                row = parts[2].lower()
                                update_controller_state(f"knob_{knob_num}{row}", normalized)
                    
                    # Handle MIDI Note events (LCXL buttons)
                    elif data.get('ctrl') == 'MIDI_NOTE':
                        note = data.get('note', 0)
                        state = data.get('state', 'OFF')
                        name = data.get('name', f'Note_{note}')
                        pressed = (state == 'ON')
                        print(f"[*] MIDI Note: {name} = {state}")
                        # Update controller state for ComfyUI
                        # BTN_FOCUS_1 through BTN_FOCUS_8, BTN_CTRL_1 through BTN_CTRL_8
                        if name.startswith("BTN_FOCUS_"):
                            btn_num = name.split("_")[2]
                            update_controller_state(f"focus_{btn_num}", pressed)
                        elif name.startswith("BTN_CTRL_"):
                            btn_num = name.split("_")[2]
                            update_controller_state(f"ctrl_{btn_num}", pressed)
                except:
                    pass
                # Relay to any connected browser clients
                await broadcast_to_browsers(payload)
            elif msg.type == web.WSMsgType.ERROR:
                print('ws connection closed with exception %s' % ws.exception())
    finally:
        print(f"[*] Bridge disconnected from {peer}")
    return ws


async def status_handler(request):
    """HTTP endpoint for scripts to poll current slider state"""
    return web.json_response(last_slider_state)


async def reset_position_handler(request):
    """Reset accumulated position to zero"""
    global accumulated_position
    accumulated_position = {"x": 0, "y": 0}
    write_position_file(0, "RESET")
    return web.json_response({"status": "ok", "position": accumulated_position})


async def index_handler(request):
    return web.Response(text=HTML_CONTENT, content_type='text/html')


def start_app():
    app = web.Application()
    app.add_routes([
        web.get('/', index_handler),
        web.get('/ws', websocket_handler),
        web.get('/bridge', bridge_handler),
        web.get('/status', status_handler),
        web.get('/reset', reset_position_handler),
    ])
    return app


if __name__ == '__main__':
    app = start_app()
    bind_host = '10.10.101.133'
    bind_host_local = '127.0.0.1'
    choice = input(f"press 1 to bind to local host ({bind_host_local}), any other key to bind to {bind_host}: ")

    if choice == '1':
        bind_host = bind_host_local

    print(f"[*] Starting web receiver on {bind_host}:{WEB_PORT}")
    web.run_app(app, host=bind_host, port=WEB_PORT)
