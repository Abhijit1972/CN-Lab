import csv
import os

class CSVLogger:
    """
    Logs every 1-second window's parameters, thresholds, and classification
    into a structured CSV file for post-analysis and reporting.
    """
    def __init__(self, filename="logs/traffic_log.csv"):
        self.filename = filename
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        self.headers = [
            "timestamp", 
            "packet_rate", "throughput_kbps", "avg_packet_size", "retx_ratio", 
            "tcp_pct", "udp_pct", "icmp_pct", "other_pct", 
            "T_rate", "T_throughput", "T_retx", 
            "level", "params_over"
        ]
        
        # Initialize file and write headers
        with open(self.filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers)
            
    def log_window(self, timestamp, metrics, thresholds, level, over_params):
        """Appends a single row for the current window to the CSV."""
        row = [
            timestamp,
            f"{metrics.get('packet_rate', 0):.2f}",
            f"{metrics.get('throughput_kbps', 0):.2f}",
            f"{metrics.get('avg_packet_size', 0):.2f}",
            f"{metrics.get('retx_ratio', 0):.4f}",
            f"{metrics.get('tcp_pct', 0):.2f}",
            f"{metrics.get('udp_pct', 0):.2f}",
            f"{metrics.get('icmp_pct', 0):.2f}",
            f"{metrics.get('other_pct', 0):.2f}",
            f"{thresholds.get('packet_rate', 0):.2f}",
            f"{thresholds.get('throughput_kbps', 0):.2f}",
            f"{thresholds.get('retx_ratio', 0):.4f}",
            level,
            "|".join(over_params) if over_params else "none"
        ]
        
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
