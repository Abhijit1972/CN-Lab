# fixed_threshold.py
#
# Baseline comparison method: replays an existing CSV log produced by monitor.py
# and reclassifies every window using FIXED (static) thresholds instead of
# adaptive ones.
#
# Purpose
# -------
# Academic comparison: show that a fixed-threshold system either raises too
# many false alerts on low-traffic days, or misses congestion on high-traffic
# days – motivating the adaptive approach.
#
# Usage
# -----
#   python fixed_threshold.py --input logs/traffic_log.csv
#   python fixed_threshold.py --input logs/traffic_log.csv \
#       --t-rate 200 --t-throughput 800 --t-retx 0.05
#
# Output
# ------
#   A new CSV alongside the input file, e.g. logs/traffic_log_fixed.csv
#   with two extra columns: fixed_level, fixed_params_over.

import argparse
import csv
import os
import sys

# ── Default fixed thresholds ─────────────────────────────────────────────────
# These are "textbook" values a student might choose by hand before seeing the
# data.  They are deliberately NOT tuned to the actual traffic, to show the
# weakness of fixed thresholds.
#
#  packet_rate   200 pkt/s  – a common rule-of-thumb for "busy" residential Wi-Fi
#  throughput    1000 KB/s  – 1 MB/s is a reasonable upper bound for light use
#  retx_ratio    0.05       – 5 % retransmissions is a widely cited warning level
#
FIXED_T_RATE:       float = 200.0   # packets / second
FIXED_T_THROUGHPUT: float = 1000.0  # KB/s
FIXED_T_RETX:       float = 0.05    # ratio (0–1)

# Reuse the same persistence logic as the adaptive classifier
CONSECUTIVE: int = 3   # consecutive windows with ≥ 2 params over → CONGESTED


def reclassify_with_fixed(
    input_csv: str,
    output_csv: str,
    t_rate:       float,
    t_throughput: float,
    t_retx:       float,
) -> None:
    """
    Reads `input_csv` (written by CSVLogger) row by row.
    For each row, applies fixed thresholds and writes the result to `output_csv`.

    New columns appended:
        fixed_T_rate        – fixed threshold used for packet_rate
        fixed_T_throughput  – fixed threshold used for throughput_kbps
        fixed_T_retx        – fixed threshold used for retx_ratio
        fixed_level         – WARMUP / NORMAL / WARNING / CONGESTED
        fixed_params_over   – pipe-separated list of params over threshold
    """
    if not os.path.exists(input_csv):
        print(f"[fixed] ERROR: Input file not found: {input_csv}")
        sys.exit(1)

    consecutive_over_two: int = 0   # persistence counter (mirrors classifier.py)

    with open(input_csv, newline='', encoding='utf-8') as fin, \
         open(output_csv, 'w', newline='', encoding='utf-8') as fout:

        reader = csv.DictReader(fin)
        if reader.fieldnames is None:
            print("[fixed] ERROR: CSV has no header row.")
            sys.exit(1)

        # Output columns = all original columns + fixed threshold info
        new_fields = ['fixed_T_rate', 'fixed_T_throughput', 'fixed_T_retx',
                      'fixed_level', 'fixed_params_over']
        writer = csv.DictWriter(fout, fieldnames=list(reader.fieldnames) + new_fields)
        writer.writeheader()

        for row in reader:
            # ── Read measured values ─────────────────────────────────────────
            try:
                rate       = float(row.get('packet_rate',    0) or 0)
                throughput = float(row.get('throughput_kbps', 0) or 0)
                retx       = float(row.get('retx_ratio',      0) or 0)
            except ValueError:
                # Malformed row – keep original, mark as UNKNOWN
                row.update({
                    'fixed_T_rate':       f'{t_rate:.2f}',
                    'fixed_T_throughput': f'{t_throughput:.2f}',
                    'fixed_T_retx':       f'{t_retx:.4f}',
                    'fixed_level':        'UNKNOWN',
                    'fixed_params_over':  'none',
                })
                writer.writerow(row)
                continue

            # ── WARMUP rows pass through unchanged ───────────────────────────
            # The adaptive monitor labels warm-up rows; the fixed method has
            # no warm-up concept (it starts alerting from window 1), but for a
            # fair comparison we respect the same warm-up window count.
            if row.get('level', '') == 'WARMUP':
                row.update({
                    'fixed_T_rate':       f'{t_rate:.2f}',
                    'fixed_T_throughput': f'{t_throughput:.2f}',
                    'fixed_T_retx':       f'{t_retx:.4f}',
                    'fixed_level':        'WARMUP',
                    'fixed_params_over':  'none',
                })
                writer.writerow(row)
                continue

            # ── Apply fixed thresholds ───────────────────────────────────────
            over: list[str] = []
            if rate       > t_rate:       over.append('packet_rate')
            if throughput > t_throughput: over.append('throughput_kbps')
            if retx       > t_retx:       over.append('retx_ratio')

            # ── Classification (identical persistence logic to classifier.py) ─
            if len(over) == 0:
                fixed_level = 'NORMAL'
                consecutive_over_two = 0

            else:
                if len(over) >= 2:
                    consecutive_over_two += 1
                else:
                    # Only 1 parameter over threshold – reset streak
                    consecutive_over_two = 0

                if consecutive_over_two >= CONSECUTIVE:
                    fixed_level = 'CONGESTED'
                else:
                    fixed_level = 'WARNING'

            # ── Write enriched row ───────────────────────────────────────────
            row.update({
                'fixed_T_rate':       f'{t_rate:.2f}',
                'fixed_T_throughput': f'{t_throughput:.2f}',
                'fixed_T_retx':       f'{t_retx:.4f}',
                'fixed_level':        fixed_level,
                'fixed_params_over':  '|'.join(over) if over else 'none',
            })
            writer.writerow(row)

    print(f"[fixed] Done. Output: {output_csv}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _default_output(input_path: str) -> str:
    """Derive output filename from input: logs/foo.csv → logs/foo_fixed.csv"""
    base, ext = os.path.splitext(input_path)
    return f"{base}_fixed{ext}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a monitor.py CSV log with fixed (static) thresholds.\n"
            "Output CSV is used by compare.py for adaptive vs. fixed analysis."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help="Path to the CSV log produced by monitor.py.",
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help="Output CSV path (default: <input>_fixed.csv).",
    )
    parser.add_argument(
        '--t-rate',
        type=float,
        default=FIXED_T_RATE,
        help=f"Fixed threshold for packet_rate (pkt/s). Default: {FIXED_T_RATE}",
    )
    parser.add_argument(
        '--t-throughput',
        type=float,
        default=FIXED_T_THROUGHPUT,
        help=f"Fixed threshold for throughput_kbps. Default: {FIXED_T_THROUGHPUT}",
    )
    parser.add_argument(
        '--t-retx',
        type=float,
        default=FIXED_T_RETX,
        help=f"Fixed threshold for retx_ratio. Default: {FIXED_T_RETX}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output or _default_output(args.input)

    print(f"[fixed] Input  : {args.input}")
    print(f"[fixed] Output : {output}")
    print(f"[fixed] Thresholds: rate={args.t_rate} pkt/s, "
          f"throughput={args.t_throughput} KB/s, retx={args.t_retx}")
    print()

    reclassify_with_fixed(
        input_csv=args.input,
        output_csv=output,
        t_rate=args.t_rate,
        t_throughput=args.t_throughput,
        t_retx=args.t_retx,
    )


if __name__ == '__main__':
    main()
