import hid
import time
import sys

# Logitech Vendor ID
LOGITECH_VID = 0x046d

def get_signed_int(byte_val):
    """Converts a byte (0-255) to a signed int (-128 to 127)"""
    if byte_val > 127:
        return byte_val - 256
    return byte_val

def process_data(data):
    """Interprets the raw hex bytes and prints human readable text"""
    if not data: return
    
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    report_id = data[0]

    # =========================================================================
    # REPORT ID 02: Standard Mode
    # Structure: 02 00 00 00 00 00 [BYTE 6] [BYTE 7]
    # =========================================================================
    if report_id == 0x02:
        if len(data) < 8: return
        
        # --- SWAPPED MAPPING ---
        raw_small = data[6]  # Byte 6 -> SMALL SCROLLER
        raw_big   = data[7]  # Byte 7 -> BIG DIAL
        
        val_small = get_signed_int(raw_small)
        val_big   = get_signed_int(raw_big)

        # --- DETECT SMALL SCROLLER ---
        if val_small != 0:
            direction = "RIGHT (CW)" if val_small > 0 else "LEFT (CCW)"
            # Use a light shade for the Small Scroller
            bar = "▒" * abs(val_small)
            print(f"[{timestamp}] SMALL SCROLLER | {direction:<10} | Speed: {val_small:<3} | {bar}")

        # --- DETECT BIG DIAL ---
        if val_big != 0:
            direction = "RIGHT (CW)" if val_big > 0 else "LEFT (CCW)"
            # Use a heavy block for the Big Dial
            bar = "▓" * abs(val_big) 
            print(f"[{timestamp}] BIG DIAL       | {direction:<10} | Speed: {val_big:<3} | {bar}")

    # =========================================================================
    # REPORT ID 11: Vendor Mode (Fallback)
    # Structure: 11 FF 0D 00 01 [VAL] ...
    # =========================================================================
    elif report_id == 0x11:
        if len(data) < 6: return
        control_id = data[4]
        val = get_signed_int(data[5])
        
        if control_id == 0x01 and val != 0:
            direction = "RIGHT (CW)" if val > 0 else "LEFT (CCW)"
            bar = "▓" * abs(val)
            print(f"[{timestamp}] BIG DIAL (V)   | {direction:<10} | Speed: {val:<3} | {bar}")

def scan_interfaces():
    print("\nScanning for MX Creative / Dialpad Interfaces...")
    print(f"{'IDX':<5} | {'USAGE PAGE':<12} | {'USAGE':<8} | {'INTERFACE TYPE'}")
    print("-" * 65)

    devices = []
    found_count = 0

    for d in hid.enumerate():
        if d['vendor_id'] == LOGITECH_VID:
            name = d.get('product_string', 'Unknown')
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
        idx = int(input("\nEnter IDX to sniff (Select 0 for Mouse Mode): "))
        target = devices[idx]
    except:
        return

    print("-" * 60)
    print(f"Connected to {target['product_string']}")
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

if __name__ == "__main__":
    main()