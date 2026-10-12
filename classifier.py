from thresholds import AdaptiveThresholds
from config import WARMUP_WINDOWS, CONSECUTIVE

class TrafficClassifier:
    """
    Evaluates current metrics against adaptive thresholds and decides
    if the network state is NORMAL, WARNING, or CONGESTED.
    """
    def __init__(self):
        self.thresholds = AdaptiveThresholds()
        self.warmup_count = 0
        
        # Tracks how many consecutive windows had >= 2 parameters over threshold
        self.consecutive_over_two = 0
        
    def classify(self, metrics):
        """
        Classifies the current window based on metrics.
        Returns: (level, over_params, current_thresholds)
        """
        current_t = self.thresholds.get_thresholds()
        
        # Check which parameters exceed their current threshold
        over_params = []
        for p in self.thresholds.history.keys():
            if metrics.get(p, 0) > current_t[p]:
                over_params.append(p)
                
        # 1. Handle WARMUP phase
        if self.warmup_count < WARMUP_WINDOWS:
            self.warmup_count += 1
            # We learn from all traffic during warmup to establish a baseline
            self.thresholds.add_normal_window(metrics)
            return 'WARMUP', over_params, current_t
            
        # 2. Handle NORMAL phase
        if len(over_params) == 0:
            level = 'NORMAL'
            self.consecutive_over_two = 0
            # Only normal windows are added to history, preventing the tool 
            # from getting "used to" congestion.
            self.thresholds.add_normal_window(metrics)
            
        # 3. Handle WARNING / CONGESTED phases
        else:
            if len(over_params) >= 2:
                self.consecutive_over_two += 1
            else:
                self.consecutive_over_two = 0
                
            if self.consecutive_over_two >= CONSECUTIVE:
                level = 'CONGESTED'
            else:
                level = 'WARNING'
                
        return level, over_params, current_t
