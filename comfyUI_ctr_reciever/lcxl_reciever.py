"""
ComfyUI Node: Launch Control XL Receiver

Receives real-time MIDI data from Novation Launch Control XL.
Connects to the web server via WebSocket to receive controller events.

Outputs:
- Knobs (24 total): 3 rows of 8 knobs, normalized 0-100
- Faders (8 total): 8 faders, normalized 0-100
- Buttons (16 total): Focus and Control button states
"""

import threading
import json
import time

# Global state for LCXL data (shared across node instances)
_lcxl_state = {
    # Knobs Row A (Send A): CC 13-20
    "knob_1a": 0.0, "knob_2a": 0.0, "knob_3a": 0.0, "knob_4a": 0.0,
    "knob_5a": 0.0, "knob_6a": 0.0, "knob_7a": 0.0, "knob_8a": 0.0,
    # Knobs Row B (Send B): CC 29-36
    "knob_1b": 0.0, "knob_2b": 0.0, "knob_3b": 0.0, "knob_4b": 0.0,
    "knob_5b": 0.0, "knob_6b": 0.0, "knob_7b": 0.0, "knob_8b": 0.0,
    # Knobs Row C (Pan): CC 49-56
    "knob_1c": 0.0, "knob_2c": 0.0, "knob_3c": 0.0, "knob_4c": 0.0,
    "knob_5c": 0.0, "knob_6c": 0.0, "knob_7c": 0.0, "knob_8c": 0.0,
    # Faders: CC 77-84
    "fader_1": 0.0, "fader_2": 0.0, "fader_3": 0.0, "fader_4": 0.0,
    "fader_5": 0.0, "fader_6": 0.0, "fader_7": 0.0, "fader_8": 0.0,
    # Focus buttons: Notes 41-44, 57-60
    "btn_focus_1": False, "btn_focus_2": False, "btn_focus_3": False, "btn_focus_4": False,
    "btn_focus_5": False, "btn_focus_6": False, "btn_focus_7": False, "btn_focus_8": False,
    # Control buttons: Notes 73-76, 89-92
    "btn_ctrl_1": False, "btn_ctrl_2": False, "btn_ctrl_3": False, "btn_ctrl_4": False,
    "btn_ctrl_5": False, "btn_ctrl_6": False, "btn_ctrl_7": False, "btn_ctrl_8": False,
    "connected": False,
    "last_update": 0,
}

# CC number to state key mapping
_cc_map = {
    # Row A
    13: "knob_1a", 14: "knob_2a", 15: "knob_3a", 16: "knob_4a",
    17: "knob_5a", 18: "knob_6a", 19: "knob_7a", 20: "knob_8a",
    # Row B
    29: "knob_1b", 30: "knob_2b", 31: "knob_3b", 32: "knob_4b",
    33: "knob_5b", 34: "knob_6b", 35: "knob_7b", 36: "knob_8b",
    # Row C
    49: "knob_1c", 50: "knob_2c", 51: "knob_3c", 52: "knob_4c",
    53: "knob_5c", 54: "knob_6c", 55: "knob_7c", 56: "knob_8c",
    # Faders
    77: "fader_1", 78: "fader_2", 79: "fader_3", 80: "fader_4",
    81: "fader_5", 82: "fader_6", 83: "fader_7", 84: "fader_8",
}

# Note number to state key mapping
_note_map = {
    # Focus buttons row 1
    41: "btn_focus_1", 42: "btn_focus_2", 43: "btn_focus_3", 44: "btn_focus_4",
    # Focus buttons row 2
    57: "btn_focus_5", 58: "btn_focus_6", 59: "btn_focus_7", 60: "btn_focus_8",
    # Control buttons row 1
    73: "btn_ctrl_1", 74: "btn_ctrl_2", 75: "btn_ctrl_3", 76: "btn_ctrl_4",
    # Control buttons row 2
    89: "btn_ctrl_5", 90: "btn_ctrl_6", 91: "btn_ctrl_7", 92: "btn_ctrl_8",
}

_lcxl_lock = threading.Lock()
_lcxl_ws_thread = None


def _start_lcxl_listener(host: str, port: int):
    """Background thread to listen for LCXL WebSocket messages."""
    global _lcxl_ws_thread
    
    if _lcxl_ws_thread is not None and _lcxl_ws_thread.is_alive():
        return  # Already running
    
    def listener():
        import websocket
        
        ws_url = f"ws://{host}:{port}/ws"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                with _lcxl_lock:
                    _lcxl_state["last_update"] = time.time()
                    
                    # Handle MIDI CC events (knobs and faders)
                    if data.get("ctrl") == "MIDI_CC":
                        cc = data.get("cc", 0)
                        normalized = data.get("normalized", 0.0)
                        
                        if cc in _cc_map:
                            _lcxl_state[_cc_map[cc]] = normalized
                    
                    # Handle MIDI Note events (buttons)
                    elif data.get("ctrl") == "MIDI_NOTE":
                        note = data.get("note", 0)
                        state = data.get("state", "OFF")
                        
                        if note in _note_map:
                            _lcxl_state[_note_map[note]] = (state == "ON")
            except Exception as e:
                print(f"[LCXL Receiver] Error parsing message: {e}")
        
        def on_open(ws):
            with _lcxl_lock:
                _lcxl_state["connected"] = True
            print(f"[LCXL Receiver] Connected to {ws_url}")
        
        def on_close(ws, close_status_code, close_msg):
            with _lcxl_lock:
                _lcxl_state["connected"] = False
            print(f"[LCXL Receiver] Disconnected")
        
        def on_error(ws, error):
            print(f"[LCXL Receiver] WebSocket error: {error}")
        
        while True:
            try:
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_open=on_open,
                    on_close=on_close,
                    on_error=on_error
                )
                ws.run_forever()
            except Exception as e:
                print(f"[LCXL Receiver] Connection failed: {e}")
            
            time.sleep(2)  # Reconnect delay
    
    _lcxl_ws_thread = threading.Thread(target=listener, daemon=True)
    _lcxl_ws_thread.start()


class LCXLReceiver:
    """ComfyUI node that receives Novation Launch Control XL input."""
    
    CATEGORY = "controller/midi"
    FUNCTION = "receive"
    RETURN_TYPES = (
        # Row A knobs (8)
        "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT",
        # Row B knobs (8)
        "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT",
        # Row C knobs (8)
        "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT",
        # Faders (8)
        "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT",
        # Focus buttons (8)
        "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN",
        # Control buttons (8)
        "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN",
    )
    RETURN_NAMES = (
        # Row A knobs
        "knob_1a", "knob_2a", "knob_3a", "knob_4a", "knob_5a", "knob_6a", "knob_7a", "knob_8a",
        # Row B knobs
        "knob_1b", "knob_2b", "knob_3b", "knob_4b", "knob_5b", "knob_6b", "knob_7b", "knob_8b",
        # Row C knobs
        "knob_1c", "knob_2c", "knob_3c", "knob_4c", "knob_5c", "knob_6c", "knob_7c", "knob_8c",
        # Faders
        "fader_1", "fader_2", "fader_3", "fader_4", "fader_5", "fader_6", "fader_7", "fader_8",
        # Focus buttons
        "focus_1", "focus_2", "focus_3", "focus_4", "focus_5", "focus_6", "focus_7", "focus_8",
        # Control buttons
        "ctrl_1", "ctrl_2", "ctrl_3", "ctrl_4", "ctrl_5", "ctrl_6", "ctrl_7", "ctrl_8",
    )
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "host": ("STRING", {"default": "127.0.0.1"}),
                "port": ("INT", {"default": 8080, "min": 1, "max": 65535}),
                "trigger": ("*",),  # Any input to trigger re-evaluation
            },
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-evaluate to get latest state
        return float("nan")
    
    def receive(self, host: str, port: int, trigger):
        # Start listener if not running
        _start_lcxl_listener(host, port)
        
        with _lcxl_lock:
            return (
                # Row A knobs
                _lcxl_state["knob_1a"], _lcxl_state["knob_2a"], _lcxl_state["knob_3a"], _lcxl_state["knob_4a"],
                _lcxl_state["knob_5a"], _lcxl_state["knob_6a"], _lcxl_state["knob_7a"], _lcxl_state["knob_8a"],
                # Row B knobs
                _lcxl_state["knob_1b"], _lcxl_state["knob_2b"], _lcxl_state["knob_3b"], _lcxl_state["knob_4b"],
                _lcxl_state["knob_5b"], _lcxl_state["knob_6b"], _lcxl_state["knob_7b"], _lcxl_state["knob_8b"],
                # Row C knobs
                _lcxl_state["knob_1c"], _lcxl_state["knob_2c"], _lcxl_state["knob_3c"], _lcxl_state["knob_4c"],
                _lcxl_state["knob_5c"], _lcxl_state["knob_6c"], _lcxl_state["knob_7c"], _lcxl_state["knob_8c"],
                # Faders
                _lcxl_state["fader_1"], _lcxl_state["fader_2"], _lcxl_state["fader_3"], _lcxl_state["fader_4"],
                _lcxl_state["fader_5"], _lcxl_state["fader_6"], _lcxl_state["fader_7"], _lcxl_state["fader_8"],
                # Focus buttons
                _lcxl_state["btn_focus_1"], _lcxl_state["btn_focus_2"], _lcxl_state["btn_focus_3"], _lcxl_state["btn_focus_4"],
                _lcxl_state["btn_focus_5"], _lcxl_state["btn_focus_6"], _lcxl_state["btn_focus_7"], _lcxl_state["btn_focus_8"],
                # Control buttons
                _lcxl_state["btn_ctrl_1"], _lcxl_state["btn_ctrl_2"], _lcxl_state["btn_ctrl_3"], _lcxl_state["btn_ctrl_4"],
                _lcxl_state["btn_ctrl_5"], _lcxl_state["btn_ctrl_6"], _lcxl_state["btn_ctrl_7"], _lcxl_state["btn_ctrl_8"],
            )
