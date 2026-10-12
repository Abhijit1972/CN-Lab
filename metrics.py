import time
from collections import OrderedDict
from scapy.layers.inet import IP, TCP, UDP, ICMP

class RetransmissionDetector:
    """
    Approximate TCP retransmission detection.
    Maintains a bounded table of recent TCP segments.
    
    Limitations:
    - Does not track full TCP connection state (SYN/FIN).
    - Ignores Selective Acknowledgements (SACK) and window sizes.
    - Simply flags identical (IPs, Ports, Seq, PayloadLen) tuples seen within a short time
      as probable retransmissions.
    """
    def __init__(self, max_size=10000, expiry_sec=2.0):
        self.max_size = max_size
        self.expiry_sec = expiry_sec
        # OrderedDict maintains insertion order, making it easy to evict oldest items
        self.seen_segments = OrderedDict()

    def _evict_old(self, current_time):
        """Removes entries older than expiry_sec or if we exceed max_size."""
        # Evict based on time
        while self.seen_segments:
            # Look at the oldest item (first item in OrderedDict)
            key, timestamp = next(iter(self.seen_segments.items()))
            if current_time - timestamp > self.expiry_sec:
                self.seen_segments.pop(key)
            else:
                # Since it's ordered, if the oldest isn't expired, the rest aren't either
                break
                
        # Evict based on size (fallback to prevent memory explosion)
        while len(self.seen_segments) > self.max_size:
            self.seen_segments.popitem(last=False)

    def check_retransmission(self, pkt, current_time) -> bool:
        """
        Analyzes a packet and returns True if it's a probable TCP retransmission.
        """
        # We only care about TCP over IP
        if not (pkt.haslayer(IP) and pkt.haslayer(TCP)):
            return False
            
        ip_layer = pkt[IP]
        tcp_layer = pkt[TCP]
        
        # Calculate TCP payload length
        payload_len = len(tcp_layer.payload)
        
        # We ignore empty packets (ACKs without data, SYNs, FINs)
        if payload_len == 0:
            return False
            
        # Unique signature for a TCP data segment
        key = (ip_layer.src, tcp_layer.sport, ip_layer.dst, tcp_layer.dport, tcp_layer.seq, payload_len)
        
        is_retx = False
        if key in self.seen_segments:
            # We have seen this exact segment recently!
            is_retx = True
            # Move to end so it's considered "recently used" and doesn't get evicted yet
            self.seen_segments.move_to_end(key)
        
        # Update/set the timestamp for this segment
        self.seen_segments[key] = current_time
            
        self._evict_old(current_time)
        return is_retx

class MetricsCalculator:
    """
    Computes per-window traffic parameters.
    Maintains state across windows (like the retransmission table).
    """
    def __init__(self):
        self.retx_detector = RetransmissionDetector()

    def compute(self, packets, window_size=1.0):
        """
        Takes a list of packets captured in the current window and computes metrics.
        Returns a dictionary of parameters.
        """
        total_bytes = 0
        num_packets = len(packets)
        
        tcp_count = 0
        udp_count = 0
        icmp_count = 0
        other_count = 0
        
        retx_count = 0
        tcp_data_packets = 0
        
        current_time = time.time()
        
        for pkt in packets:
            # length of the packet on the wire
            total_bytes += len(pkt)
            
            if pkt.haslayer(IP):
                if pkt.haslayer(TCP):
                    tcp_count += 1
                    # Track retransmissions if it's a data packet
                    if len(pkt[TCP].payload) > 0:
                        tcp_data_packets += 1
                        if self.retx_detector.check_retransmission(pkt, current_time):
                            retx_count += 1
                elif pkt.haslayer(UDP):
                    udp_count += 1
                elif pkt.haslayer(ICMP):
                    icmp_count += 1
                else:
                    other_count += 1
            else:
                other_count += 1
                
        # Compute rates
        packet_rate = num_packets / window_size
        throughput_kbps = (total_bytes / window_size) / 1024.0
        avg_packet_size = total_bytes / num_packets if num_packets > 0 else 0.0
        
        # Compute ratio of retransmitted TCP data packets over all TCP data packets
        retx_ratio = retx_count / tcp_data_packets if tcp_data_packets > 0 else 0.0
        
        # Compute protocol shares (%)
        tcp_pct = (tcp_count / num_packets * 100) if num_packets > 0 else 0.0
        udp_pct = (udp_count / num_packets * 100) if num_packets > 0 else 0.0
        icmp_pct = (icmp_count / num_packets * 100) if num_packets > 0 else 0.0
        other_pct = (other_count / num_packets * 100) if num_packets > 0 else 0.0
        
        return {
            'packet_rate': packet_rate,
            'throughput_kbps': throughput_kbps,
            'avg_packet_size': avg_packet_size,
            'retx_ratio': retx_ratio,
            'tcp_pct': tcp_pct,
            'udp_pct': udp_pct,
            'icmp_pct': icmp_pct,
            'other_pct': other_pct
        }
