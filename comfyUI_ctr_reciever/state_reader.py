"""
ComfyUI Node: Controller State Reader

Reads controller values from a shared JSON state file.
This file is continuously updated by the web_server.py script.
Works without WebSocket - just reads a file on each queue.

The web_server.py writes to: /tmp/controller_state.json (or C:/temp/controller_state.json on Windows)

Usage:
1. Run host.py on the machine with the controllers
2. Run web_server.py on the machine with ComfyUI
3. Add these nodes to your ComfyUI workflow
4. Enable "Auto Queue" for continuous updates
"""

import json
import os
import platform
import time

# State file path
if platform.system() == "Windows":
    STATE_FILE = "C:/temp/controller_state.json"
else:
    STATE_FILE = "/tmp/controller_state.json"


def read_state():
    """Read the current controller state from file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Controller Reader] Error reading state: {e}")
    return {}


class ControllerStateReader:
    """
    ComfyUI node that reads dialpad and fader values from a shared state file.
    The web_server.py writes to this file continuously.
    
    Enable Auto Queue in ComfyUI for continuous updates.
    """
    
    CATEGORY = "controller"
    FUNCTION = "read"
    RETURN_TYPES = (
        # Dialpad
        "INT", "INT", "INT", "INT",  # dial_value, dial_delta, scroller_value, scroller_delta
        "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN",  # dialpad buttons
        # LCXL Faders (most commonly used)
        "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT", "FLOAT",
    )
    RETURN_NAMES = (
        "dial_value", "dial_delta", "scroller_value", "scroller_delta",
        "btn_top_left", "btn_top_right", "btn_bottom_left", "btn_bottom_right",
        "fader_1", "fader_2", "fader_3", "fader_4", "fader_5", "fader_6", "fader_7", "fader_8",
    )
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "state_file": ("STRING", {"default": STATE_FILE}),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-read the file on each queue
        return float("nan")
    
    def read(self, state_file=STATE_FILE):
        state = read_state()
        
        # Get dialpad values
        dial_value = state.get("dial_value", 0)
        dial_delta = state.get("dial_delta", 0)
        scroller_value = state.get("scroller_value", 0)
        scroller_delta = state.get("scroller_delta", 0)
        
        # Get dialpad button values
        btn_top_left = state.get("btn_top_left", False)
        btn_top_right = state.get("btn_top_right", False)
        btn_bottom_left = state.get("btn_bottom_left", False)
        btn_bottom_right = state.get("btn_bottom_right", False)
        
        # Get LCXL fader values
        faders = [
            state.get("fader_1", 0.0),
            state.get("fader_2", 0.0),
            state.get("fader_3", 0.0),
            state.get("fader_4", 0.0),
            state.get("fader_5", 0.0),
            state.get("fader_6", 0.0),
            state.get("fader_7", 0.0),
            state.get("fader_8", 0.0),
        ]
        
        return (
            dial_value, dial_delta, scroller_value, scroller_delta,
            btn_top_left, btn_top_right, btn_bottom_left, btn_bottom_right,
            *faders
        )


class LCXLKnobReader:
    """Reads all 24 LCXL knob values from the state file."""
    
    CATEGORY = "controller/midi"
    FUNCTION = "read"
    RETURN_TYPES = tuple(["FLOAT"] * 24)
    RETURN_NAMES = tuple([f"knob_{i+1}{r}" for r in ['a', 'b', 'c'] for i in range(8)])
    
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def read(self):
        state = read_state()
        knobs = []
        for row in ['a', 'b', 'c']:
            for i in range(1, 9):
                knobs.append(state.get(f"knob_{i}{row}", 0.0))
        return tuple(knobs)


class KeypadReader:
    """Reads MX Creative Keypad button states from the state file."""
    
    CATEGORY = "controller"
    FUNCTION = "read"
    RETURN_TYPES = tuple(["BOOLEAN"] * 9 + ["BOOLEAN", "INT"])
    RETURN_NAMES = (
        "btn_1", "btn_2", "btn_3",
        "btn_4", "btn_5", "btn_6",
        "btn_7", "btn_8", "btn_9",
        "any_pressed", "last_pressed"
    )
    
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def read(self):
        state = read_state()
        buttons = []
        last_pressed = 0
        for i in range(1, 10):
            pressed = state.get(f"btn_{i}", False)
            buttons.append(pressed)
            if pressed:
                last_pressed = i
        any_pressed = any(buttons)
        return (*buttons, any_pressed, last_pressed)


# Node registration
NODE_CLASS_MAPPINGS = {
    "ControllerStateReader": ControllerStateReader,
    "LCXLKnobReader": LCXLKnobReader,
    "KeypadReader": KeypadReader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ControllerStateReader": "Controller State (Dial + Faders)",
    "LCXLKnobReader": "LCXL Knobs (24 knobs)",
    "KeypadReader": "Keypad Reader (9 buttons)",
}
