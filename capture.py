import time
import threading
from scapy.all import sniff

class PacketCapturer:
    """
    Captures live network packets using Scapy and groups them into time windows.
    Runs sniffing in a background thread and uses a timer thread to flush packets
    every `window_size` seconds to a provided callback.
    """
    def __init__(self, interface=None, bpf_filter=None, window_size=1, callback=None):
        self.interface = interface
        self.bpf_filter = bpf_filter
        self.window_size = window_size
        self.callback = callback
        
        self.running = False
        self.current_window_packets = []
        # Lock to protect the packet list, since sniff pushes and timer pops concurrently
        self.lock = threading.Lock()
        
        self.sniff_thread = None
        self.timer_thread = None

    def _packet_handler(self, pkt):
        """Called by Scapy for each captured packet. Kept extremely lightweight."""
        with self.lock:
            self.current_window_packets.append(pkt)

    def _timer_loop(self):
        """Flushes the accumulated packets every window_size seconds."""
        # Optional: Align the loop roughly to the next whole second boundary
        time.sleep(self.window_size - (time.time() % self.window_size))
        
        while self.running:
            start_time = time.time()
            
            with self.lock:
                # Extract all packets for the current window and reset the list
                packets = self.current_window_packets
                self.current_window_packets = []
            
            if self.callback:
                # Deliver the window's packets
                self.callback(packets)
                
            # Sleep precisely enough to wake up at the next window boundary
            elapsed = time.time() - start_time
            sleep_time = max(0.0, self.window_size - elapsed)
            time.sleep(sleep_time)

    def _sniff_loop(self):
        """Blocking Scapy sniff loop."""
        try:
            sniff(
                iface=self.interface,
                filter=self.bpf_filter,
                prn=self._packet_handler,
                store=False, # Extremely important: don't store packets in memory
                stop_filter=lambda _: not self.running
            )
        except Exception as e:
            print(f"\n[!] Sniffing error: {e}")
            print("[!] Do you have Npcap installed and are you running as Administrator?")
            self.running = False

    def start(self):
        """Starts the capture and timer threads."""
        self.running = True
        
        self.timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.timer_thread.start()
        
        self.sniff_thread = threading.Thread(target=self._sniff_loop, daemon=True)
        self.sniff_thread.start()

    def stop(self):
        """
        Stops the capture process. 
        Note: Scapy's sniff blocks and only checks stop_filter AFTER receiving a packet.
        Therefore, it might not exit immediately if the network is completely silent.
        """
        self.running = False
        if self.timer_thread:
            self.timer_thread.join(timeout=1.0)
