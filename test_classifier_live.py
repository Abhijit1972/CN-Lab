import time
import sys
import logging
from config import WINDOW_SIZE, INTERFACE
from capture import PacketCapturer
from metrics import MetricsCalculator
from classifier import TrafficClassifier

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

def main():
    calculator = MetricsCalculator()
    classifier = TrafficClassifier()

    def window_callback(packets):
        # 1. Compute Metrics
        metrics = calculator.compute(packets, window_size=WINDOW_SIZE)
        
        # 2. Classify based on Adaptive Thresholds
        level, over_params, current_t = classifier.classify(metrics)
        
        # ANSI Colors for Console
        RESET = "\033[0m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        CYAN = "\033[96m"
        
        if level == 'NORMAL':
            color = GREEN
        elif level == 'WARNING':
            color = YELLOW
        elif level == 'CONGESTED':
            color = RED
        else: # WARMUP
            color = CYAN
            
        timestamp = time.strftime('%H:%M:%S')
        
        # 3. Print the Result
        if level == 'CONGESTED':
            print(f"\n{RED}[!] CONGESTION ALERT @ {timestamp} - Level: {level}{RESET}")
            for p in over_params:
                print(f"{RED}    -> {p}: {metrics[p]:.2f} (Threshold limit was: {current_t[p]:.2f}){RESET}")
            print()
        else:
            over_str = f"Over Threshold: {', '.join(over_params)}" if over_params else ""
            print(f"[{timestamp}] {color}{level:<9}{RESET} | Rate: {metrics['packet_rate']:>6.0f} | Tput: {metrics['throughput_kbps']:>7.0f} KB/s | Retx: {metrics['retx_ratio']:>5.1%} | {over_str}")
            
    print("==================================================")
    print("Phase 3: Live Classification Test")
    print("==================================================")
    print("Press Ctrl+C to stop.")
    
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
