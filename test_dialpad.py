#!/usr/bin/env python3
"""Test script to find which dialpad interface works."""
import hid
import time

LOGITECH_VID = 0x046d

# Find ALL dialpad interfaces
dialpad_interfaces = []
for d in hid.enumerate():
    if d['vendor_id'] != LOGITECH_VID:
        continue
    name = d.get('product_string', '') or ''
    if 'dialpad' in name.lower():
        dialpad_interfaces.append(d)

print(f'Found {len(dialpad_interfaces)} dialpad interfaces:')
for i, d in enumerate(dialpad_interfaces):
    up = d.get('usage_page', 0)
    usage = d.get('usage', 0)
    print(f'  [{i}] usage_page=0x{up:04x}, usage=0x{usage:04x}')

print()
print('NOTE: If Logitech Options+ is running, it may have exclusive access.')
print('      Try: killall logioptionsplus_agent LogiPluginService')
print()
print('Testing each interface for 5 seconds... TURN THE DIAL NOW!')
print()

for i, d in enumerate(dialpad_interfaces):
    up = d.get('usage_page', 0)
    usage = d.get('usage', 0)
    print(f'[{i}] Testing 0x{up:04x}/0x{usage:04x}...', end=' ', flush=True)
    
    try:
        h = hid.Device(path=d['path'])
        h.nonblocking = True  # Non-blocking mode
        start = time.time()
        got_data = False
        data_samples = []
        
        while time.time() - start < 5:  # 5 seconds per interface
            try:
                data = h.read(64)  # Non-blocking read
                if data:
                    data_samples.append([hex(x) for x in data[:10]])
                    got_data = True
            except Exception as e:
                print(f'Read error: {e}')
                break
            time.sleep(0.01)
        
        if got_data:
            print(f'GOT DATA! ({len(data_samples)} packets)')
            for sample in data_samples[:3]:  # Show first 3 samples
                print(f'    {sample}')
            if len(data_samples) > 3:
                print(f'    ... and {len(data_samples) - 3} more')
        else:
            print('(no data)')
        h.close()
    except Exception as e:
        print(f'Error: {e}')

print()
print('Done.')
