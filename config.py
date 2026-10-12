# config.py

# Time window size in seconds
WINDOW_SIZE = 1  

# Number of historical windows to keep for computing adaptive thresholds
HISTORY_LEN = 60

# Multiplier for the standard deviation (Threshold = Mean + K * Stdev)
K = 2  

# Number of initial windows to just learn history without generating alerts
WARMUP_WINDOWS = 15

# Number of consecutive windows a parameter must be above threshold to trigger CONGESTED
CONSECUTIVE = 3

# Adaptive threshold floors.
# To prevent false alerts when traffic is extremely low (e.g. mean=0, stdev=0, threshold=0),
# we set sensible minimum thresholds.
FLOORS = {
    'packet_rate': 100.0,       # Min threshold: 100 packets/sec
    'throughput_kbps': 500.0,   # Min threshold: 500 KB/sec
    'retx_ratio': 0.05          # Min threshold: 5% of TCP packets being retransmissions
}

# Network interface to capture on. 
# Set to None to use Scapy's default (all available).
# On Windows, you can change this to a specific name if needed, e.g., 'Ethernet' or 'Wi-Fi'.
INTERFACE = None
