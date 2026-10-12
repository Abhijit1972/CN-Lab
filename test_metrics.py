import time
import sys
import logging
from config import WINDOW_SIZE, INTERFACE
from capture import PacketCapturer
from metrics import MetricsCalculator

# Suppress harmless Scapy warnings (like "DNS decompression loop detected") 
# to keep our debug output clean.
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

def main():
    print("==================================================")
    print("Phase 2: Metrics & Retransmission Debug Mode")
    print("==================================================")
    print(f"Interface: {INTERFACE if INTERFACE else 'Default (All)'}")
    print(f"Window Size: {WINDOW_SIZE} seconds")
    print("Press Ctrl+C to stop.")
    print("==================================================\n")
    
    # Instantiate the calculator which holds the retransmission detector state
    calculator = MetricsCalculator()

    def window_callback(packets):
        # Compute the metrics for the current window of packets
        metrics = calculator.compute(packets, window_size=WINDOW_SIZE)
        
        # Print a formatted debug block
        print("-" * 60)
        print(f"[{time.strftime('%H:%M:%S')}] Window Summary ({len(packets)} packets captured)")
        print(f"  Packet Rate  : {metrics['packet_rate']:.2f} pkts/s")
        print(f"  Throughput   : {metrics['throughput_kbps']:.2f} KB/s")
        print(f"  Avg Pkt Size : {metrics['avg_packet_size']:.0f} bytes")
        print(f"  Retx Ratio   : {metrics['retx_ratio']:.2%} ({metrics['retx_ratio']*100:.2f}%)")
        print(f"  Protocols    : TCP {metrics['tcp_pct']:.1f}% | UDP {metrics['udp_pct']:.1f}% | ICMP {metrics['icmp_pct']:.1f}% | Other {metrics['other_pct']:.1f}%")
    
    capturer = PacketCapturer(
        interface=INTERFACE, 
        window_size=WINDOW_SIZE, 
        callback=window_callback
    )
    
    capturer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping capture...")
        capturer.stop()
        print("Capture stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
