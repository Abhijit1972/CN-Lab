import time
import sys
from config import WINDOW_SIZE, INTERFACE
from capture import PacketCapturer

def window_callback(packets):
    """Callback function executed every window_size seconds."""
    current_time = time.strftime('%H:%M:%S')
    print(f"[{current_time}] Received {len(packets):>4} packets in the last {WINDOW_SIZE}s window.")

def main():
    print("==================================================")
    print("Phase 1: Packet Capture Test")
    print("==================================================")
    print(f"Interface: {INTERFACE if INTERFACE else 'Default (All)'}")
    print(f"Window Size: {WINDOW_SIZE} seconds")
    print("Press Ctrl+C to stop.")
    print("==================================================\n")
    
    # We can pass an optional bpf_filter like 'ip' or 'tcp'
    capturer = PacketCapturer(
        interface=INTERFACE, 
        bpf_filter=None, 
        window_size=WINDOW_SIZE, 
        callback=window_callback
    )
    
    capturer.start()
    
    try:
        # Keep the main thread alive while background threads do the work
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping capture...")
        capturer.stop()
        print("Capture stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
