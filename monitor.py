# monitor.py
#
# Main entry point for the Adaptive Network Traffic Monitor.
# Wires together: PacketCapturer → MetricsCalculator → TrafficClassifier
#                 → CSVLogger → console output.
# On exit (Ctrl+C) it calls generate_report() to produce the PNG graph
# and text summary.
#
# Usage (must be run in an elevated / administrator terminal):
#
#   python monitor.py
#   python monitor.py --interface "Wi-Fi"
#   python monitor.py --interface "Ethernet" --filter "tcp"
#   python monitor.py --log logs/my_run.csv --debug

import argparse
import datetime
import signal
import sys
import time

# ── Project modules ──────────────────────────────────────────────────────────
from config import WINDOW_SIZE, INTERFACE
from capture import PacketCapturer
from metrics import MetricsCalculator
from classifier import TrafficClassifier
from logger import CSVLogger
from report import generate_report


# ── ANSI colour helpers (work on most modern Windows terminals) ───────────────
RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"


def colour_for(level: str) -> str:
    """Return the ANSI colour code for a traffic level string."""
    return {
        'WARMUP':    CYAN,
        'NORMAL':    GREEN,
        'WARNING':   YELLOW,
        'CONGESTED': RED,
    }.get(level, RESET)


# ── Global state shared between the window callback and the signal handler ───
_csv_logger: CSVLogger | None = None
_csv_path:   str              = ""
_capturer:   PacketCapturer | None = None
_shutdown_requested: bool     = False   # set by Ctrl+C handler


def _signal_handler(sig, frame):
    """Gracefully stop on Ctrl+C."""
    global _shutdown_requested
    print("\n\n[monitor] Ctrl+C received – stopping capture …")
    _shutdown_requested = True
    if _capturer:
        _capturer.stop()


# ── Window processing ─────────────────────────────────────────────────────────

def make_window_callback(
    metrics_calc: MetricsCalculator,
    classifier:   TrafficClassifier,
    csv_logger:   CSVLogger,
    debug:        bool,
    window_count: list,        # mutable int wrapped in a list for closure
):
    """
    Returns the function that PacketCapturer calls every second.
    Using a closure keeps all heavy objects out of global scope.
    """

    def on_window(packets: list) -> None:
        """Called by the timer thread with all packets from the last window."""
        window_count[0] += 1
        ts = datetime.datetime.now().isoformat(timespec='seconds')

        # 1. Compute metrics
        metrics = metrics_calc.compute(packets, window_size=WINDOW_SIZE)

        # 2. Classify (handles warmup internally)
        level, over_params, thresholds = classifier.classify(metrics)

        # 3. Log to CSV
        csv_logger.log_window(ts, metrics, thresholds, level, over_params)

        # 4. Console output
        col = colour_for(level)
        status_line = (
            f"{col}{BOLD}[{level:>9}]{RESET}  "
            f"{ts}  "
            f"pkts={int(metrics['packet_rate']):>4}  "
            f"bw={metrics['throughput_kbps']:>8.2f} KB/s  "
            f"retx={metrics['retx_ratio']:.3f}  "
            f"TCP={metrics['tcp_pct']:.0f}% UDP={metrics['udp_pct']:.0f}%"
        )

        # If any params are over threshold, show which ones
        if over_params:
            status_line += f"  {YELLOW}over={','.join(over_params)}{RESET}"

        print(status_line)

        # 5. Special CONGESTED alert – must be clearly visible
        if level == 'CONGESTED':
            print(
                f"\n{RED}{BOLD}"
                f"╔══════════════════════════════════════════════════════╗\n"
                f"║  ⚠  CONGESTION ALERT  –  {ts}           ║\n"
                f"║  Parameters over threshold: {', '.join(over_params):<26}║\n"
                f"║  Values: rate={metrics['packet_rate']:.0f} pkt/s, "
                f"bw={metrics['throughput_kbps']:.1f} KB/s, "
                f"retx={metrics['retx_ratio']:.3f}  ║\n"
                f"╚══════════════════════════════════════════════════════╝"
                f"{RESET}\n"
            )

        # 6. Debug mode: print raw values for comparison with Wireshark
        if debug:
            print(
                f"  [DEBUG] avg_pkt={metrics['avg_packet_size']:.1f}B  "
                f"icmp={metrics['icmp_pct']:.1f}%  "
                f"T_rate={thresholds.get('packet_rate', 0):.1f}  "
                f"T_bw={thresholds.get('throughput_kbps', 0):.1f}  "
                f"T_retx={thresholds.get('retx_ratio', 0):.4f}"
            )

    return on_window


# ── CLI argument parsing ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Adaptive Network Traffic Monitor\n"
            "Captures live packets and detects congestion using adaptive thresholds.\n"
            "MUST be run as Administrator (Windows) or root (Linux)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--interface', '-i',
        default=INTERFACE,
        help=(
            "Network interface to sniff on. "
            "Leave blank for Scapy's default. "
            "Examples: 'Wi-Fi', 'Ethernet', 'eth0'."
        ),
    )
    parser.add_argument(
        '--filter', '-f',
        default=None,
        dest='bpf_filter',
        help=(
            "Optional BPF filter string passed directly to Scapy/libpcap. "
            "Examples: 'tcp', 'udp port 53', 'host 8.8.8.8'."
        ),
    )
    parser.add_argument(
        '--log', '-l',
        default='logs/traffic_log.csv',
        help="Path for the CSV log file (default: logs/traffic_log.csv).",
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        default=False,
        help=(
            "Print extra per-window debug values (useful for "
            "comparison with Wireshark I/O graphs)."
        ),
    )
    return parser.parse_args()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    global _csv_logger, _csv_path, _capturer, _shutdown_requested

    args = parse_args()
    _csv_path = args.log

    # Banner
    print(
        f"\n{BOLD}{CYAN}"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║   Adaptive Network Traffic Monitor  –  CN Lab, BACSE203P    ║\n"
        "╚══════════════════════════════════════════════════════════════╝"
        f"{RESET}"
    )
    print(f"  Interface : {args.interface or '(Scapy default)'}")
    print(f"  BPF filter: {args.bpf_filter or '(none)'}")
    print(f"  Log file  : {_csv_path}")
    print(f"  Debug mode: {args.debug}")
    print(f"\n  Press Ctrl+C to stop and generate the report.\n")

    # Register the Ctrl+C handler
    signal.signal(signal.SIGINT, _signal_handler)

    # Instantiate the pipeline components
    metrics_calc = MetricsCalculator()
    classifier   = TrafficClassifier()
    _csv_logger  = CSVLogger(filename=_csv_path)

    window_count = [0]   # mutable counter (closure trick)
    callback = make_window_callback(
        metrics_calc, classifier, _csv_logger, args.debug, window_count
    )

    # Create and start the capturer
    _capturer = PacketCapturer(
        interface=args.interface,
        bpf_filter=args.bpf_filter,
        window_size=WINDOW_SIZE,
        callback=callback,
    )

    print("[monitor] Starting packet capture …  (this may take 1-2 s to initialise)\n")
    _capturer.start()

    # Keep the main thread alive; the sniff/timer threads do all the work.
    # We check every 0.5 s so that the Ctrl+C handler's flag is noticed quickly.
    try:
        while not _shutdown_requested:
            time.sleep(0.5)
    except KeyboardInterrupt:
        # Fallback if the signal handler didn't fire (e.g. IDE run)
        _signal_handler(None, None)

    # ── Shutdown ───────────────────────────────────────────────────────────
    print(f"\n[monitor] Capture stopped. {window_count[0]} windows processed.")
    print("[monitor] Generating end-of-run report …\n")

    generate_report(csv_path=_csv_path, output_dir="logs")

    print("\n[monitor] Done. Goodbye!\n")


if __name__ == '__main__':
    main()
