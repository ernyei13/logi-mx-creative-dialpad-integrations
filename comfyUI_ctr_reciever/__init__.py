"""
ComfyUI Custom Nodes for MX Creative Controllers + Launch Control XL

These nodes receive real-time controller data via a shared state file.
The web_server.py writes to the state file as it receives events from host.py.

File-based nodes (recommended - simpler, more reliable):
- ControllerStateReader: Reads dial, scroller, dialpad buttons, and faders
- LCXLKnobReader: Reads all 24 LCXL knobs  
- KeypadReader: Reads 9 MX Creative Keypad buttons

WebSocket-based nodes (legacy):
- LogiDialpadReceiver: Real-time dial/scroller via WebSocket
- LogiKeypadReceiver: Real-time keypad via WebSocket
- LCXLReceiver: Real-time LCXL via WebSocket

For continuous updates in ComfyUI:
1. Run host.py on the machine with the controllers
2. Run web_server.py on the machine with ComfyUI
3. Enable "Auto Queue" in ComfyUI settings
4. Use the file-based readers (ControllerStateReader, etc.)
"""

from .logi_dialpad_reciever import LogiDialpadReceiver
from .logi_keypad_reciever import LogiKeypadReceiver
from .lcxl_reciever import LCXLReceiver
from .state_reader import (
    ControllerStateReader, LCXLKnobReader, LCXLFaderReader, LCXLButtonReader, KeypadReader,
    ValueDisplay, FaderDisplay, DialDisplay
)

NODE_CLASS_MAPPINGS = {
    "LogiDialpadReceiver": LogiDialpadReceiver,
    "LogiKeypadReceiver": LogiKeypadReceiver,
    "LCXLReceiver": LCXLReceiver,
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
    "LogiDialpadReceiver": "Logi MX Dialpad (WebSocket)",
    "LogiKeypadReceiver": "Logi MX Keypad (WebSocket)",
    "LCXLReceiver": "Launch Control XL (WebSocket)",
    "ControllerStateReader": "Controller State (Dial + Faders)",
    "LCXLKnobReader": "LCXL Knobs (24)",
    "LCXLFaderReader": "LCXL Faders (8)",
    "LCXLButtonReader": "LCXL Buttons (16)",
    "KeypadReader": "Keypad Reader (9 buttons)",
    "ValueDisplay": "Value Display",
    "FaderDisplay": "Fader Display (8 bars)",
    "DialDisplay": "Dial Display",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
