#!/bin/bash
# Start the dialpad host on macOS
cd "$(dirname "$0")"
DYLD_LIBRARY_PATH=/opt/homebrew/lib ./venv/bin/python host.py
