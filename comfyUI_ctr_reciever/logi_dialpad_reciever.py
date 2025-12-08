"""
ComfyUI Node: Logi MX Dialpad Receiver

Receives real-time dial, scroller, and button data from MX Creative Dialpad.
Connects to the web server via WebSocket to receive controller events.

Outputs:
- dial_value: Accumulated dial position (INT)
- dial_delta: Last dial change delta (INT)
- scroller_value: Accumulated scroller position (INT)
- scroller_delta: Last scroller change delta (INT)
- btn_top_left: Top-left button state (BOOLEAN)
- btn_top_right: Top-right button state (BOOLEAN)
- btn_bottom_left: Bottom-left button state (BOOLEAN)
- btn_bottom_right: Bottom-right button state (BOOLEAN)
"""

import threading
import json
import time

# Global state for dialpad data (shared across node instances)
_dialpad_state = {
    "dial_value": 0,
    "dial_delta": 0,
    "scroller_value": 0,
    "scroller_delta": 0,
    "btn_top_left": False,
    "btn_top_right": False,
    "btn_bottom_left": False,
    "btn_bottom_right": False,
    "connected": False,
    "last_update": 0,
}
_dialpad_lock = threading.Lock()
_dialpad_ws_thread = None


def _start_dialpad_listener(host: str, port: int):
    """Background thread to listen for dialpad WebSocket messages."""
    global _dialpad_ws_thread
    
    if _dialpad_ws_thread is not None and _dialpad_ws_thread.is_alive():
        return  # Already running
    
    def listener():
        import websocket
        
        ws_url = f"ws://{host}:{port}/ws"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                with _dialpad_lock:
                    _dialpad_state["last_update"] = time.time()
                    
                    # Handle dial events
                    if data.get("ctrl") == "BIG":
                        delta = data.get("delta", 0)
                        _dialpad_state["dial_delta"] = delta
                        _dialpad_state["dial_value"] += delta
                    
                    # Handle scroller events
                    elif data.get("ctrl") == "SMALL":
                        delta = data.get("delta", 0)
                        _dialpad_state["scroller_delta"] = delta
                        _dialpad_state["scroller_value"] += delta
                    
                    # Handle button events
                    elif data.get("ctrl") == "BTN":
                        name = data.get("name", "")
                        pressed = data.get("state") == "PRESSED"
                        if name == "TOP LEFT":
                            _dialpad_state["btn_top_left"] = pressed
                        elif name == "TOP RIGHT":
                            _dialpad_state["btn_top_right"] = pressed
                        elif name == "BOTTOM LEFT":
                            _dialpad_state["btn_bottom_left"] = pressed
                        elif name == "BOTTOM RIGHT":
                            _dialpad_state["btn_bottom_right"] = pressed
            except Exception as e:
                print(f"[Dialpad Receiver] Error parsing message: {e}")
        
        def on_open(ws):
            with _dialpad_lock:
                _dialpad_state["connected"] = True
            print(f"[Dialpad Receiver] Connected to {ws_url}")
        
        def on_close(ws, close_status_code, close_msg):
            with _dialpad_lock:
                _dialpad_state["connected"] = False
            print(f"[Dialpad Receiver] Disconnected")
        
        def on_error(ws, error):
            print(f"[Dialpad Receiver] WebSocket error: {error}")
        
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
                print(f"[Dialpad Receiver] Connection failed: {e}")
            
            time.sleep(2)  # Reconnect delay
    
    _dialpad_ws_thread = threading.Thread(target=listener, daemon=True)
    _dialpad_ws_thread.start()


class LogiDialpadReceiver:
    """ComfyUI node that receives MX Creative Dialpad input."""
    
    CATEGORY = "controller/logi"
    FUNCTION = "receive"
    RETURN_TYPES = ("INT", "INT", "INT", "INT", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("dial_value", "dial_delta", "scroller_value", "scroller_delta", 
                    "btn_top_left", "btn_top_right", "btn_bottom_left", "btn_bottom_right")
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "host": ("STRING", {"default": "127.0.0.1"}),
                "port": ("INT", {"default": 8080, "min": 1, "max": 65535}),
                "trigger": ("*",),  # Any input to trigger re-evaluation
            },
            "optional": {
                "reset_dial": ("BOOLEAN", {"default": False}),
                "reset_scroller": ("BOOLEAN", {"default": False}),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-evaluate to get latest state
        return float("nan")
    
    def receive(self, host: str, port: int, trigger, reset_dial: bool = False, reset_scroller: bool = False):
        # Start listener if not running
        _start_dialpad_listener(host, port)
        
        with _dialpad_lock:
            if reset_dial:
                _dialpad_state["dial_value"] = 0
            if reset_scroller:
                _dialpad_state["scroller_value"] = 0
            
            return (
                _dialpad_state["dial_value"],
                _dialpad_state["dial_delta"],
                _dialpad_state["scroller_value"],
                _dialpad_state["scroller_delta"],
                _dialpad_state["btn_top_left"],
                _dialpad_state["btn_top_right"],
                _dialpad_state["btn_bottom_left"],
                _dialpad_state["btn_bottom_right"],
            )
