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
    # Correct order: knob_1a through knob_8a, then knob_1b through knob_8b, then knob_1c through knob_8c
    RETURN_NAMES = tuple([f"knob_{i}{r}" for r in ['a', 'b', 'c'] for i in range(1, 9)])
    
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def read(self):
        state = read_state()
        knobs = []
        # Match the RETURN_NAMES order: row a (1-8), row b (1-8), row c (1-8)
        for row in ['a', 'b', 'c']:
            for i in range(1, 9):
                knobs.append(state.get(f"knob_{i}{row}", 0.0))
        return tuple(knobs)


class LCXLFaderReader:
    """Reads all 8 LCXL fader values from the state file."""
    
    CATEGORY = "controller/midi"
    FUNCTION = "read"
    RETURN_TYPES = tuple(["FLOAT"] * 8)
    RETURN_NAMES = ("fader_1", "fader_2", "fader_3", "fader_4", "fader_5", "fader_6", "fader_7", "fader_8")
    
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def read(self):
        state = read_state()
        faders = []
        for i in range(1, 9):
            faders.append(state.get(f"fader_{i}", 0.0))
        return tuple(faders)


class LCXLButtonReader:
    """Reads all 16 LCXL button states from the state file (Focus + Control rows)."""
    
    CATEGORY = "controller/midi"
    FUNCTION = "read"
    RETURN_TYPES = tuple(["BOOLEAN"] * 16)
    RETURN_NAMES = (
        "focus_1", "focus_2", "focus_3", "focus_4", "focus_5", "focus_6", "focus_7", "focus_8",
        "ctrl_1", "ctrl_2", "ctrl_3", "ctrl_4", "ctrl_5", "ctrl_6", "ctrl_7", "ctrl_8"
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
        # Focus row buttons
        for i in range(1, 9):
            buttons.append(state.get(f"focus_{i}", False))
        # Control row buttons
        for i in range(1, 9):
            buttons.append(state.get(f"ctrl_{i}", False))
        return tuple(buttons)


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


class ValueDisplay:
    """
    Simple node to display any value in the node UI.
    Connect any output to see its current value.
    """
    
    CATEGORY = "controller/debug"
    FUNCTION = "display"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("*",),  # Accept any type
            },
            "optional": {
                "label": ("STRING", {"default": "Value"}),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def display(self, value, label="Value"):
        text = f"{label}: {value}"
        print(f"[Display] {text}")
        return {"ui": {"text": [text]}, "result": (text,)}


class FaderDisplay:
    """
    Visual display for 8 faders with bar representation.
    """
    
    CATEGORY = "controller/debug"
    FUNCTION = "display"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("display",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "fader_1": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_2": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_3": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_4": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_5": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_6": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_7": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "fader_8": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def display(self, fader_1, fader_2, fader_3, fader_4, fader_5, fader_6, fader_7, fader_8):
        faders = [fader_1, fader_2, fader_3, fader_4, fader_5, fader_6, fader_7, fader_8]
        lines = []
        for i, val in enumerate(faders, 1):
            bar_len = int(val * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"F{i}: [{bar}] {val:.2f}")
        text = "\n".join(lines)
        return {"ui": {"text": [text]}, "result": (text,)}


class DialDisplay:
    """
    Visual display for dial and scroller values.
    """
    
    CATEGORY = "controller/debug"
    FUNCTION = "display"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("display",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "dial_value": ("INT", {"default": 0}),
                "scroller_value": ("INT", {"default": 0}),
            },
            "optional": {
                "dial_delta": ("INT", {"default": 0}),
                "scroller_delta": ("INT", {"default": 0}),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")
    
    def display(self, dial_value, scroller_value, dial_delta=0, scroller_delta=0):
        text = f"🎛️ Dial: {dial_value} (Δ{dial_delta:+d})\n📜 Scroller: {scroller_value} (Δ{scroller_delta:+d})"
        return {"ui": {"text": [text]}, "result": (text,)}


# Node registration
NODE_CLASS_MAPPINGS = {
    "ControllerStateReader": ControllerStateReader,
    "LCXLKnobReader": LCXLKnobReader,
    "LCXLFaderReader": LCXLFaderReader,
    "LCXLButtonReader": LCXLButtonReader,
    "KeypadReader": KeypadReader,
    "ValueDisplay": ValueDisplay,
    "FaderDisplay": FaderDisplay,
    "DialDisplay": DialDisplay,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ControllerStateReader": "Controller State (Dial + Faders)",
    "LCXLKnobReader": "LCXL Knobs (24)",
    "LCXLFaderReader": "LCXL Faders (8)",
    "LCXLButtonReader": "LCXL Buttons (16)",
    "KeypadReader": "Keypad Reader (9 buttons)",
    "ValueDisplay": "Value Display",
    "FaderDisplay": "Fader Display (8 bars)",
    "DialDisplay": "Dial Display",
}
