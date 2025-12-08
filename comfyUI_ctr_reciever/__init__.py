"""
ComfyUI Custom Nodes for MX Creative Controllers + Launch Control XL

These nodes receive real-time controller data from the web server bridge.
The host.py script must be running and connected to the web server.

Nodes:
- LogiDialpadReceiver: Receives dial/scroller values and 4 button states
- LogiKeypadReceiver: Receives 9 button states from MX Creative Keypad
- LCXLReceiver: Receives 24 knobs, 8 faders, and 16 buttons from Launch Control XL
"""

from .logi_dialpad_reciever import LogiDialpadReceiver
from .logi_keypad_reciever import LogiKeypadReceiver
from .lcxl_reciever import LCXLReceiver

NODE_CLASS_MAPPINGS = {
    "LogiDialpadReceiver": LogiDialpadReceiver,
    "LogiKeypadReceiver": LogiKeypadReceiver,
    "LCXLReceiver": LCXLReceiver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LogiDialpadReceiver": "Logi MX Dialpad Receiver",
    "LogiKeypadReceiver": "Logi MX Keypad Receiver",
    "LCXLReceiver": "Launch Control XL Receiver",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
