import asyncio
import json
import time
import os
from aiohttp import web

WEB_PORT = 8080
COMMAND_FILE = "C:/temp/logi_command.json"
POSITION_FILE = "C:/temp/logi_position.json"

# Ensure temp directory exists
os.makedirs(os.path.dirname(COMMAND_FILE), exist_ok=True)

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

        /* --- BUTTON GRID --- */
        .button-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            width: 140px;
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
            font-size: 0.6rem;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
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

    </style>
</head>
<body>

    <div class="header">MX Creative Interface</div>

    <div class="stage">
        <div id="group-buttons">
            <div class="button-grid">
                <div class="hw-button" id="btn-tl">Top<br>Left</div>
                <div class="hw-button" id="btn-tr">Top<br>Right</div>
                <div class="hw-button" id="btn-bl">Bot<br>Left</div>
                <div class="hw-button" id="btn-br">Bot<br>Right</div>
            </div>
            <div class="meta">
                <div class="label">Buttons</div>
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
        <div id="group-buttons" style="margin-left:20px;">
            <div class="meta">
                <div class="label">Buttons</div>
                <div class="value" id="btn-log">—</div>
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
        
        // Button elements
        const buttons = {
            'TOP LEFT': document.getElementById('btn-tl'),
            'TOP RIGHT': document.getElementById('btn-tr'),
            'BOTTOM LEFT': document.getElementById('btn-bl'),
            'BOTTOM RIGHT': document.getElementById('btn-br')
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            // Handle button events (ctrl: "BTN", name: "...", state: "PRESSED"/"RELEASED")
            if (data.ctrl === 'BTN') {
                const btn = buttons[data.name];
                if (btn) {
                    if (data.state === 'PRESSED') {
                        btn.classList.add('pressed');
                    } else {
                        btn.classList.remove('pressed');
                    }
                }
                return;
            }
            
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
            else if (data.ctrl === "BTN") {
                // Display latest button event
                const name = data.name || 'BTN';
                const state = data.state || '';
                const el = document.getElementById('btn-log');
                el.innerText = `${name} ${state}`;
                // briefly highlight
                el.style.color = '#3b82f6';
                setTimeout(() => el.style.color = '', 500);
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
                    
                    # Handle button events (ctrl: "BTN", name: "...", state: "PRESSED"/"RELEASED")
                    if data.get('ctrl') == 'BTN':
                        button_name = data.get('name', '')
                        pressed = data.get('state') == 'PRESSED'
                        if button_name in button_states:
                            button_states[button_name] = pressed
                            print(f"[*] Button: {button_name} {'PRESSED' if pressed else 'RELEASED'}")
                    # Handle dial/scroller events
                    elif 'delta' in data:
                        last_slider_state.update(data)
                        ctrl = data.get('ctrl', 'BIG')
                        delta = data.get('delta', 0)
                        write_command_file(delta, ctrl)
                        write_position_file(delta, ctrl)
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
    print(f"[*] Starting web receiver on {bind_host}:{WEB_PORT}")
    web.run_app(app, host=bind_host, port=WEB_PORT)
