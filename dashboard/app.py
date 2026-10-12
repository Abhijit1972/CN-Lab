# dashboard/app.py
#
# Flask dashboard for the Adaptive Network Traffic Monitor.
# Runs the full monitor pipeline (capture → metrics → classify → log) in a
# background daemon thread and exposes:
#
#   GET /                → HTML dashboard page
#   GET /api/status      → latest window snapshot (JSON)
#   GET /api/history     → last N windows for charts (JSON)
#   GET /api/alerts      → recent congestion/warning alerts (JSON)
#   GET /api/summary     → aggregate stats (JSON)
#
# Usage (must run as Administrator for packet capture):
#   cd "D:\CN lab"
#   python dashboard/app.py
#   python dashboard/app.py --interface "Wi-Fi" --port 5000
#
# Then open http://localhost:5000 in your browser.
# Console alerts and CSV logging continue to work alongside the dashboard.

import argparse
import datetime
import os
import sys
import threading
import time
from collections import deque

# ── Make sure the parent directory (project root) is on the path ─────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template

from config import WINDOW_SIZE, INTERFACE
from capture import PacketCapturer
from metrics import MetricsCalculator
from classifier import TrafficClassifier
from logger import CSVLogger

# ── ANSI colours (for the console output that runs alongside the dashboard) ───
RESET  = "\033[0m";  GREEN  = "\033[92m"
YELLOW = "\033[93m"; RED    = "\033[91m"
CYAN   = "\033[96m"; BOLD   = "\033[1m"
_COLOUR = {'WARMUP': CYAN, 'NORMAL': GREEN, 'WARNING': YELLOW, 'CONGESTED': RED}


# ─────────────────────────────────────────────────────────────────────────────
# Thread-safe Data Store
# ─────────────────────────────────────────────────────────────────────────────

class DataStore:
    """
    Shared state between the monitor thread and Flask request threads.
    All mutations go through a Lock to prevent race conditions.
    """

    HISTORY_LEN = 120   # keep 2 minutes of per-second windows for charts
    ALERT_LEN   = 50    # keep the last 50 alerts in the table

    def __init__(self):
        self._lock = threading.Lock()

        # Latest single window (dict or None before first window)
        self.latest: dict | None = None

        # Rolling history for chart data
        self.history: deque = deque(maxlen=self.HISTORY_LEN)

        # Recent alerts (WARNING + CONGESTED)
        self.alerts: deque = deque(maxlen=self.ALERT_LEN)

        # Aggregate stats
        self.total_windows: int         = 0
        self.congestion_events: int     = 0
        self.total_congestion_s: int    = 0
        self._was_congested: bool       = False
        self.peak_throughput: float     = 0.0
        self.sum_throughput: float      = 0.0
        self.active_windows: int        = 0   # excludes WARMUP

    def push(self, window: dict) -> None:
        """Called by the monitor thread after each 1-second window."""
        with self._lock:
            self.latest = window
            self.history.append(window)
            self.total_windows += 1

            level = window.get('level', 'WARMUP')

            # Track congestion events
            if level != 'WARMUP':
                self.active_windows += 1
                bw = window.get('throughput_kbps', 0.0)
                self.sum_throughput += bw
                self.peak_throughput = max(self.peak_throughput, bw)

            if level == 'CONGESTED':
                self.total_congestion_s += 1
                if not self._was_congested:
                    self.congestion_events += 1
                self._was_congested = True
            else:
                self._was_congested = False

            # Record alerts
            if level in ('WARNING', 'CONGESTED'):
                self.alerts.appendleft({
                    'time':        window.get('timestamp', ''),
                    'level':       level,
                    'params_over': window.get('params_over', []),
                    'throughput':  round(window.get('throughput_kbps', 0.0), 2),
                    'packet_rate': round(window.get('packet_rate', 0.0), 1),
                    'retx_ratio':  round(window.get('retx_ratio', 0.0), 4),
                })

    # ── Thread-safe snapshots for Flask ──────────────────────────────────────

    def snapshot_latest(self) -> dict:
        with self._lock:
            return dict(self.latest) if self.latest else {}

    def snapshot_history(self, n: int = 60) -> list:
        with self._lock:
            # Return newest-last so Chart.js can plot left→right
            items = list(self.history)
            return items[-n:]

    def snapshot_alerts(self, n: int = 20) -> list:
        with self._lock:
            return list(self.alerts)[:n]

    def snapshot_summary(self) -> dict:
        with self._lock:
            avg_bw = (self.sum_throughput / self.active_windows
                      if self.active_windows > 0 else 0.0)
            return {
                'total_windows':     self.total_windows,
                'active_windows':    self.active_windows,
                'congestion_events': self.congestion_events,
                'total_congestion_s': self.total_congestion_s,
                'avg_throughput_kbps': round(avg_bw, 2),
                'peak_throughput_kbps': round(self.peak_throughput, 2),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Monitor background thread
# ─────────────────────────────────────────────────────────────────────────────

def build_window_callback(
    store:        DataStore,
    metrics_calc: MetricsCalculator,
    classifier:   TrafficClassifier,
    csv_logger:   CSVLogger,
):
    """Returns the per-window callback (same logic as monitor.py)."""

    def on_window(packets: list) -> None:
        ts      = datetime.datetime.now().isoformat(timespec='seconds')
        metrics = metrics_calc.compute(packets, window_size=WINDOW_SIZE)
        level, over_params, thresholds = classifier.classify(metrics)

        # ── CSV log ──────────────────────────────────────────────────────────
        csv_logger.log_window(ts, metrics, thresholds, level, over_params)

        # ── Build the window dict pushed to DataStore ─────────────────────
        window = {
            'timestamp':        ts,
            'level':            level,
            'params_over':      over_params,
            **metrics,
            'T_rate':       thresholds.get('packet_rate',       0),
            'T_throughput': thresholds.get('throughput_kbps',   0),
            'T_retx':       thresholds.get('retx_ratio',        0),
        }
        store.push(window)

        # ── Console output (kept working alongside dashboard) ─────────────
        col = _COLOUR.get(level, RESET)
        print(
            f"{col}{BOLD}[{level:>9}]{RESET}  {ts}  "
            f"pkts={int(metrics['packet_rate']):>4}  "
            f"bw={metrics['throughput_kbps']:>8.2f} KB/s  "
            f"retx={metrics['retx_ratio']:.3f}"
            + (f"  {YELLOW}over={','.join(over_params)}{RESET}" if over_params else "")
        )

        if level == 'CONGESTED':
            print(
                f"\n{RED}{BOLD}"
                f"*** CONGESTION ALERT  {ts}  "
                f"params: {', '.join(over_params)}  "
                f"bw={metrics['throughput_kbps']:.1f} KB/s"
                f" ***{RESET}\n"
            )

    return on_window


def start_monitor_thread(
    store:     DataStore,
    interface: str | None,
    bpf:       str | None,
    log_path:  str,
) -> PacketCapturer:
    """Starts the capture pipeline in a daemon thread and returns the capturer."""
    metrics_calc = MetricsCalculator()
    classifier   = TrafficClassifier()
    csv_logger   = CSVLogger(filename=log_path)

    callback  = build_window_callback(store, metrics_calc, classifier, csv_logger)
    capturer  = PacketCapturer(
        interface=interface,
        bpf_filter=bpf,
        window_size=WINDOW_SIZE,
        callback=callback,
    )
    capturer.start()
    return capturer


# ─────────────────────────────────────────────────────────────────────────────
# Flask application factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app(store: DataStore) -> Flask:
    """Creates and configures the Flask app with the shared DataStore."""

    # template_folder / static_folder are relative to THIS file's directory
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/status')
    def api_status():
        """Latest single window – polled every second by the dashboard."""
        return jsonify(store.snapshot_latest())

    @app.route('/api/history')
    def api_history():
        """Last 60 windows for chart rendering."""
        return jsonify(store.snapshot_history(n=60))

    @app.route('/api/alerts')
    def api_alerts():
        """Recent Warning/Congested alerts for the alert table."""
        return jsonify(store.snapshot_alerts(n=20))

    @app.route('/api/summary')
    def api_summary():
        """Aggregate run statistics for the summary cards."""
        return jsonify(store.snapshot_summary())

    return app


# ─────────────────────────────────────────────────────────────────────────────
# CLI and entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Adaptive Network Traffic Monitor – Web Dashboard\n"
            "Must be run as Administrator (Windows) / root (Linux).\n"
            "Open http://localhost:<port>/ in any browser."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--interface', '-i', default=INTERFACE,
                   help="Network interface (default: Scapy default).")
    p.add_argument('--filter', '-f', default=None, dest='bpf',
                   help="BPF filter string (e.g. 'tcp', 'port 80').")
    p.add_argument('--log', '-l', default='logs/dashboard_traffic.csv',
                   help="CSV log path (default: logs/dashboard_traffic.csv).")
    p.add_argument('--port', '-p', type=int, default=5000,
                   help="Flask port (default: 5000).")
    p.add_argument('--host', default='0.0.0.0',
                   help="Flask host (default: 0.0.0.0 = all interfaces).")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"\n{BOLD}{CYAN}"
          "=============================================================\n"
          "  Adaptive Monitor Dashboard  -  CN Lab BACSE203P\n"
          "=============================================================\n"
          f"{RESET}"
          f"  Interface : {args.interface or '(Scapy default)'}\n"
          f"  BPF filter: {args.bpf or '(none)'}\n"
          f"  CSV log   : {args.log}\n"
          f"  Dashboard : http://localhost:{args.port}/\n"
          f"\n  Starting packet capture ... (1-2 s to initialise)\n")

    store    = DataStore()
    capturer = start_monitor_thread(store, args.interface, args.bpf, args.log)

    app = create_app(store)

    try:
        # use_reloader=False is critical – reloader forks a second process
        # which would also try to start packet capture.
        app.run(host=args.host, port=args.port,
                debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[dashboard] Stopping capture ...")
        capturer.stop()
        print("[dashboard] Goodbye!\n")


if __name__ == '__main__':
    main()
