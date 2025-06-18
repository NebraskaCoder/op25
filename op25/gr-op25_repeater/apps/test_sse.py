#!/usr/bin/env python3
"""
Test script for SSE functionality
This script simulates the OP25 message queue to test SSE events
"""

import json
import time
import threading
from http_server import broadcast_sse_event

def test_sse_events():
    """Test function to simulate OP25 events"""
    
    # Test frequency update
    freq_data = {
        "json_type": "rx_update",
        "files": ["plot-0-fft.png", "plot-0-constellation.png"],
        "error": 0,
        "fine_tune": 0
    }
    print("Testing frequency_update event...")
    broadcast_sse_event("frequency_update", freq_data)
    
    time.sleep(2)
    
    # Test call log
    call_data = {
        "json_type": "call_log",
        "log": [
            {
                "time": time.time(),
                "sysid": 0x4a2,
                "tgid": 1234,
                "tgtag": "Test Talkgroup",
                "rid": 5678,
                "rtag": "Test Radio",
                "rcvr": 0,
                "prio": 1,
                "rcvrtag": "Test Receiver",
                "freq": 851000000,
                "slot": 1
            }
        ]
    }
    print("Testing call_log event...")
    broadcast_sse_event("call_log", call_data)
    
    time.sleep(2)
    
    # Test channel status
    channel_data = {
        "json_type": "channel_update",
        "channels": ["0", "1", "2"],
        "0": {
            "freq": 851000000,
            "tag": "Test Channel",
            "stream": "test_stream",
            "ppm": 0.0,
            "capture": False,
            "error": 0
        }
    }
    print("Testing channel_status event...")
    broadcast_sse_event("channel_status", channel_data)
    
    time.sleep(2)
    
    # Test trunk update
    trunk_data = {
        "json_type": "trunk_update",
        "0x4a2": {
            "sysname": "Test System",
            "nac": "0x4a2",
            "frequencies": {
                "773.84375": {
                    "tag": "Control Channel",
                    "status": "active"
                }
            }
        }
    }
    print("Testing trunk_update event...")
    broadcast_sse_event("trunk_update", trunk_data)

if __name__ == "__main__":
    print("Starting SSE test...")
    print("Make sure the OP25 server is running and you have SSE clients connected")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            test_sse_events()
            time.sleep(10)  # Wait 10 seconds between test cycles
    except KeyboardInterrupt:
        print("\nTest stopped by user") 