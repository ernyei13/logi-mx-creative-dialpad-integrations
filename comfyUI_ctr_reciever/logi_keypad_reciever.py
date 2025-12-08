"""
ComfyUI Node: Logi MX Keypad Receiver

Receives real-time button data from MX Creative Keypad (9 buttons).
Connects to the web server via WebSocket to receive controller events.

Outputs:
- btn_1 through btn_9: Button states (BOOLEAN)
- any_pressed: True if any button is currently pressed (BOOLEAN)
- last_pressed: Number of last pressed button (INT, 0 if none)
"""

import threading
import json
import time

# Global state for keypad data (shared across node instances)
_keypad_state = {
    "btn_1": False, "btn_2": False, "btn_3": False,
    "btn_4": False, "btn_5": False, "btn_6": False,
    "btn_7": False, "btn_8": False, "btn_9": False,
    "last_pressed": 0,
    "connected": False,
    "last_update": 0,
}
_keypad_lock = threading.Lock()
_keypad_ws_thread = None


def _start_keypad_listener(host: str, port: int):
    """Background thread to listen for keypad WebSocket messages."""
    global _keypad_ws_thread
    
    if _keypad_ws_thread is not None and _keypad_ws_thread.is_alive():
        return  # Already running
    
    def listener():
        import websocket
        
        ws_url = f"ws://{host}:{port}/ws"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                with _keypad_lock:
                    _keypad_state["last_update"] = time.time()
                    
                    # Handle keypad button events
                    if data.get("ctrl") == "KEYPAD":
                        btn_num = data.get("button", 0)
                        pressed = data.get("state") == "PRESSED"
                        
                        if 1 <= btn_num <= 9:
                            _keypad_state[f"btn_{btn_num}"] = pressed
                            if pressed:
                                _keypad_state["last_pressed"] = btn_num
            except Exception as e:
                print(f"[Keypad Receiver] Error parsing message: {e}")
        
        def on_open(ws):
            with _keypad_lock:
                _keypad_state["connected"] = True
            print(f"[Keypad Receiver] Connected to {ws_url}")
        
        def on_close(ws, close_status_code, close_msg):
            with _keypad_lock:
                _keypad_state["connected"] = False
            print(f"[Keypad Receiver] Disconnected")
        
        def on_error(ws, error):
            print(f"[Keypad Receiver] WebSocket error: {error}")
        
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
                print(f"[Keypad Receiver] Connection failed: {e}")
            
            time.sleep(2)  # Reconnect delay
    
    _keypad_ws_thread = threading.Thread(target=listener, daemon=True)
    _keypad_ws_thread.start()


class LogiKeypadReceiver:
    """ComfyUI node that receives MX Creative Keypad input."""
    
    CATEGORY = "controller/logi"
    FUNCTION = "receive"
    RETURN_TYPES = ("BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", 
                    "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "INT")
    RETURN_NAMES = ("btn_1", "btn_2", "btn_3", "btn_4", "btn_5", "btn_6", 
                    "btn_7", "btn_8", "btn_9", "any_pressed", "last_pressed")
    
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
        _start_keypad_listener(host, port)
        
        with _keypad_lock:
            any_pressed = any([
                _keypad_state["btn_1"], _keypad_state["btn_2"], _keypad_state["btn_3"],
                _keypad_state["btn_4"], _keypad_state["btn_5"], _keypad_state["btn_6"],
                _keypad_state["btn_7"], _keypad_state["btn_8"], _keypad_state["btn_9"],
            ])
            
            return (
                _keypad_state["btn_1"],
                _keypad_state["btn_2"],
                _keypad_state["btn_3"],
                _keypad_state["btn_4"],
                _keypad_state["btn_5"],
                _keypad_state["btn_6"],
                _keypad_state["btn_7"],
                _keypad_state["btn_8"],
                _keypad_state["btn_9"],
                any_pressed,
                _keypad_state["last_pressed"],
            )
