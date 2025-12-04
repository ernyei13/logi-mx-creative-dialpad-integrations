#!/bin/bash
# Start the web server on macOS
cd "$(dirname "$0")"
DYLD_LIBRARY_PATH=/opt/homebrew/lib ./venv/bin/python web_server.py
