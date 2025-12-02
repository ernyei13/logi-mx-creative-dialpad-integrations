import hid
import time
import socket
import sys

# =========================================================================
# CONFIGURATION
# =========================================================================
LOGITECH_VID = 0x046d
UDP_IP = "127.0.0.1"
UDP_PORT = 7777

# Initialize Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def get_signed_int(byte_val):
    """Converts a byte (0-255) to a signed int (-128 to 127)"""
    if byte_val > 127:
        return byte_val - 256
    return byte_val

def send_udp(control_type, delta):
    """Sends the control change over UDP"""
    # Format: "BIG:5" or "SMALL:-1"
    message = f"{control_type}:{delta}"
    try:
        sock.sendto(message.encode(), (UDP_IP, UDP_PORT))
    except Exception as e:
        print(f"UDP Error: {e}")

def process_data(data):
    """Interprets raw bytes, prints status, and sends UDP"""
    if not data: return
    
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    report_id = data[0]

    # =========================================================================
    # REPORT ID 02: Standard Mouse Mode
    # =========================================================================
    if report_id == 0x02:
        if len(data) < 8: return
        
        raw_small = data[6]  # Byte 6 -> SMALL SCROLLER
        raw_big   = data[7]  # Byte 7 -> BIG DIAL
        
        val_small = get_signed_int(raw_small)
        val_big   = get_signed_int(raw_big)

        # --- HANDLE SMALL SCROLLER ---
        if val_small != 0:
            send_udp("SMALL", val_small)
            
            # Console Feedback
            direction = "RIGHT (CW)" if val_small > 0 else "LEFT (CCW)"
            print(f"[{timestamp}] SMALL SCROLLER | {direction:<10} | Speed: {val_small:<3} -> UDP SENT")

        # --- HANDLE BIG DIAL ---
        if val_big != 0:
            send_udp("BIG", val_big)

            # Console Feedback
            direction = "RIGHT (CW)" if val_big > 0 else "LEFT (CCW)"
            print(f"[{timestamp}] BIG DIAL       | {direction:<10} | Speed: {val_big:<3} -> UDP SENT")

    # =========================================================================
    # REPORT ID 11: Vendor Mode (Fallback)
    # =========================================================================
    elif report_id == 0x11:
        if len(data) < 6: return
        control_id = data[4]
        val = get_signed_int(data[5])
        
        # 0x01 is usually the Big Dial in Vendor Mode
        if control_id == 0x01 and val != 0:
            send_udp("BIG", val)
            
            direction = "RIGHT (CW)" if val > 0 else "LEFT (CCW)"
            print(f"[{timestamp}] BIG DIAL (V)   | {direction:<10} | Speed: {val:<3} -> UDP SENT")

def scan_interfaces():
    """Scans for Logitech devices and guesses their usage"""
    print("\nScanning for MX Creative / Dialpad Interfaces...")
    print(f"{'IDX':<5} | {'USAGE PAGE':<12} | {'USAGE':<8} | {'INTERFACE TYPE'}")
    print("-" * 65)

    devices = []
    found_count = 0

    for d in hid.enumerate():
        if d['vendor_id'] == LOGITECH_VID:
            name = d.get('product_string', 'Unknown')
            # Filter for likely Creative/Dial devices
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

def main():
    devices = scan_interfaces()
    if not devices:
        print("No device found.")
        return

    try:
        idx = int(input("\nEnter IDX to sniff (Select the 'Generic' or '0x0001' one): "))
        target = devices[idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return

    print("-" * 60)
    print(f"Connected to {target['product_string']}")
    print(f"Sending UDP to {UDP_IP}:{UDP_PORT}")
    print("Turn the BIG DIAL or the SMALL SCROLLER...")
    print("-" * 60)

    try:
        h = hid.device()
        h.open_path(target['path'])
        h.set_nonblocking(True)

        while True:
            data = h.read(64)
            if data:
                process_data(data)
            time.sleep(0.005)

    except IOError as e:
        print(f"[-] Error: {e}")
    except KeyboardInterrupt:
        print("\n[*] Stopping.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()