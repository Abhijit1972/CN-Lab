from collections import deque
import statistics
from config import HISTORY_LEN, K, FLOORS

class AdaptiveThresholds:
    """
    Maintains a rolling history of normal traffic to compute adaptive thresholds.
    Threshold = Mean(history) + K * Stdev(history).
    """
    def __init__(self):
        # We track history for the three key parameters
        self.history = {
            'packet_rate': deque(maxlen=HISTORY_LEN),
            'throughput_kbps': deque(maxlen=HISTORY_LEN),
            'retx_ratio': deque(maxlen=HISTORY_LEN)
        }
    
    def get_thresholds(self):
        """Calculates current thresholds based on history."""
        thresholds = {}
        for param in self.history:
            hist = self.history[param]
            
            if len(hist) < 2:
                # Not enough data for stdev, default to the floor
                thresholds[param] = FLOORS.get(param, 0.0)
            else:
                mean_val = statistics.mean(hist)
                stdev_val = statistics.stdev(hist)
                
                # T = mean + K * stdev
                adaptive_t = mean_val + K * stdev_val
                
                # Ensure the threshold never drops below the sensible floor minimums
                thresholds[param] = max(FLOORS.get(param, 0.0), adaptive_t)
                
        return thresholds
        
    def add_normal_window(self, metrics):
        """
        Adds a window's metrics to the history. 
        We only call this for NORMAL windows or during WARMUP.
        """
        for param in self.history:
            if param in metrics:
                self.history[param].append(metrics[param])
