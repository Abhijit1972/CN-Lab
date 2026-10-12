# test_report.py
#
# Offline test for report.py.
# Generates a synthetic CSV log (no real traffic needed) and calls
# generate_report() to produce a PNG and a summary TXT.
#
# Run: python test_report.py
# Output files land in logs/

import csv
import os
import random
import datetime

# Build a synthetic CSV that mimics real monitor output
HEADERS = [
    "timestamp",
    "packet_rate", "throughput_kbps", "avg_packet_size", "retx_ratio",
    "tcp_pct", "udp_pct", "icmp_pct", "other_pct",
    "T_rate", "T_throughput", "T_retx",
    "level", "params_over"
]

os.makedirs("logs", exist_ok=True)
csv_path = "logs/test_synthetic.csv"

# ── Generate 120 seconds of fake data ────────────────────────────────────────
random.seed(42)
rows = []
base_time = datetime.datetime(2026, 10, 10, 20, 0, 0)

for i in range(120):
    ts = (base_time + datetime.timedelta(seconds=i)).isoformat(timespec='seconds')
    rate   = random.uniform(40, 80)
    bw     = random.uniform(150, 350)
    retx   = random.uniform(0.0, 0.03)
    t_rate = 120.0
    t_bw   = 500.0
    t_retx = 0.05

    # Inject a congestion burst from window 60 to 72
    if 60 <= i <= 72:
        rate  = random.uniform(200, 400)
        bw    = random.uniform(700, 1200)
        retx  = random.uniform(0.07, 0.20)
        level = 'CONGESTED'
        over  = 'packet_rate|throughput_kbps|retx_ratio'
    elif i < 15:
        level = 'WARMUP'
        over  = 'none'
    elif i in (30, 31):
        bw    = random.uniform(550, 650)
        level = 'WARNING'
        over  = 'throughput_kbps'
    else:
        level = 'NORMAL'
        over  = 'none'

    rows.append([
        ts,
        f"{rate:.2f}", f"{bw:.2f}",
        f"{bw * 1024 / rate:.2f}",  # avg_packet_size
        f"{retx:.4f}",
        "65.00", "30.00", "2.00", "3.00",
        f"{t_rate:.2f}", f"{t_bw:.2f}", f"{t_retx:.4f}",
        level, over
    ])

with open(csv_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(HEADERS)
    writer.writerows(rows)

print(f"Synthetic CSV written to {csv_path}  ({len(rows)} rows)")

# ── Call generate_report ─────────────────────────────────────────────────────
from report import generate_report
generate_report(csv_path=csv_path, output_dir="logs")
print("\n[test_report] Done. Check the logs/ folder for the PNG and TXT files.")
