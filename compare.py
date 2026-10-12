# compare.py
#
# Adaptive vs. Fixed-threshold comparison tool.
#
# What it measures
# ----------------
# Given the SAME traffic run captured in two CSVs:
#   - The adaptive CSV  : produced by monitor.py
#   - The fixed CSV     : produced by fixed_threshold.py (same rows, extra columns)
#
# We compare the two classifiers on:
#
#  1. Alert counts – total NORMAL / WARNING / CONGESTED windows per method.
#
#  2. False positives (FP) – windows where one method raises WARNING or
#     CONGESTED but the other says NORMAL.  Because we have no external ground
#     truth, FP is computed symmetrically:
#       - Fixed FP   : fixed=WARNING/CONGESTED AND adaptive=NORMAL
#       - Adaptive FP: adaptive=WARNING/CONGESTED AND fixed=NORMAL
#     A lower FP count is better.  The adaptive method is expected to have
#     fewer FP because it learns normal traffic and raises the threshold as
#     average traffic rises.
#
#  3. Congestion event detection – each method's CONGESTED runs are grouped
#     into events (contiguous CONGESTED windows).  For events detected by
#     BOTH methods, the detection delay (in seconds) relative to the earlier
#     detector is reported.
#
#  4. Agreement rate – fraction of windows where both methods agree.
#
# Usage
# -----
#   python compare.py --adaptive logs/traffic_log.csv \
#                     --fixed    logs/traffic_log_fixed.csv
#
# Outputs (in logs/ by default)
# -------
#   comparison_results.csv  – machine-readable results table
#   comparison_results.md   – human-readable Markdown table (for the report)
#   comparison_plot.png     – side-by-side throughput chart with both
#                             threshold lines and congestion shadings

import argparse
import os
import sys
import datetime

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_csv(path: str, label: str) -> pd.DataFrame:
    """Load a CSV, coerce numeric columns, add an elapsed_s index."""
    if not os.path.exists(path):
        print(f"[compare] ERROR: {label} CSV not found: {path}")
        sys.exit(1)

    df = pd.read_csv(path)

    numeric = [
        'packet_rate', 'throughput_kbps', 'avg_packet_size', 'retx_ratio',
        'tcp_pct', 'udp_pct', 'icmp_pct', 'other_pct',
        'T_rate', 'T_throughput', 'T_retx',
    ]
    for col in numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    df['elapsed_s'] = range(len(df))
    return df


def find_events(series: pd.Series) -> list[dict]:
    """
    Given a boolean Series (True = congested), returns a list of dicts:
      { 'start': row_index, 'end': row_index, 'duration': int }
    """
    events: list[dict] = []
    in_event = False
    start = 0
    for i, val in enumerate(series):
        if val and not in_event:
            in_event = True
            start = i
        elif not val and in_event:
            in_event = False
            events.append({'start': start, 'end': i - 1,
                           'duration': i - start})
    if in_event:
        events.append({'start': start, 'end': len(series) - 1,
                       'duration': len(series) - start})
    return events


def events_overlap(e1: dict, e2: dict) -> bool:
    """True if two event dicts share at least one row."""
    return e1['start'] <= e2['end'] and e2['start'] <= e1['end']


# ── Core comparison ───────────────────────────────────────────────────────────

def run_comparison(adaptive_csv: str, fixed_csv: str, output_dir: str) -> None:
    """
    Loads both CSVs and computes the full comparison.
    Writes CSV, Markdown, and PNG to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)

    # ── 1. Load data ─────────────────────────────────────────────────────────
    adp = load_csv(adaptive_csv, 'adaptive')
    fix = load_csv(fixed_csv,    'fixed')

    # The fixed CSV has the original adaptive columns PLUS fixed_* columns.
    # Make sure the fixed_* columns exist.
    required_fixed_cols = ['fixed_level', 'fixed_params_over',
                           'fixed_T_rate', 'fixed_T_throughput', 'fixed_T_retx']
    for col in required_fixed_cols:
        if col not in fix.columns:
            print(f"[compare] ERROR: '{col}' column missing in fixed CSV.\n"
                  f"  Run: python fixed_threshold.py --input {adaptive_csv}")
            sys.exit(1)

    # Align on row index (both files must be same run / same length)
    if len(adp) != len(fix):
        print(f"[compare] WARNING: adaptive has {len(adp)} rows, "
              f"fixed has {len(fix)} rows.  Trimming to shorter length.")
        n = min(len(adp), len(fix))
        adp = adp.iloc[:n].reset_index(drop=True)
        fix = fix.iloc[:n].reset_index(drop=True)

    # ── 2. Exclude WARMUP rows from all statistics ────────────────────────────
    # Both CSVs share the same 'level' column for the adaptive label.
    active_mask = adp['level'] != 'WARMUP'
    adp_a = adp[active_mask].copy()
    fix_a  = fix[active_mask].copy()
    n_active = len(adp_a)

    # ── 3. Alert count table ──────────────────────────────────────────────────
    def count_levels(series: pd.Series) -> dict:
        vc = series.value_counts()
        return {lvl: int(vc.get(lvl, 0))
                for lvl in ['NORMAL', 'WARNING', 'CONGESTED']}

    adp_counts  = count_levels(adp_a['level'])
    fix_counts  = count_levels(fix_a['fixed_level'])

    # ── 4. False-positive analysis ────────────────────────────────────────────
    adp_alert = adp_a['level'].isin(['WARNING', 'CONGESTED'])
    fix_alert = fix_a['fixed_level'].isin(['WARNING', 'CONGESTED'])
    adp_normal = adp_a['level'] == 'NORMAL'
    fix_normal = fix_a['fixed_level'] == 'NORMAL'

    # Fixed FP: fixed raises alert but adaptive says NORMAL
    fixed_fp_mask = fix_alert & adp_normal
    fixed_fp = int(fixed_fp_mask.sum())

    # Adaptive FP: adaptive raises alert but fixed says NORMAL
    adp_fp_mask = adp_alert & fix_normal
    adp_fp = int(adp_fp_mask.sum())

    # Agreement rate
    both_agree = (adp_a['level'].values == fix_a['fixed_level'].values)
    agreement_pct = float(both_agree.sum()) / n_active * 100 if n_active > 0 else 0.0

    # ── 5. Congestion event detection ─────────────────────────────────────────
    adp_congested = (adp['level'] == 'CONGESTED')
    fix_congested = (fix['fixed_level'] == 'CONGESTED')

    adp_events = find_events(adp_congested)
    fix_events = find_events(fix_congested)

    # Match overlapping events and compute detection delay
    event_rows: list[dict] = []
    matched_fix = set()

    for ai, ae in enumerate(adp_events):
        matched = False
        for fi, fe in enumerate(fix_events):
            if fi in matched_fix:
                continue
            if events_overlap(ae, fe):
                delay_s = ae['start'] - fe['start']  # + = adaptive later, - = adaptive earlier
                event_rows.append({
                    'event_id':            ai + 1,
                    'adp_start':           ae['start'],
                    'adp_end':             ae['end'],
                    'adp_duration_s':      ae['duration'],
                    'fix_start':           fe['start'],
                    'fix_end':             fe['end'],
                    'fix_duration_s':      fe['duration'],
                    'detection_delay_s':   delay_s,   # positive = adaptive detected later
                    'matched':             True,
                })
                matched_fix.add(fi)
                matched = True
                break
        if not matched:
            # Adaptive event not caught by fixed at all
            event_rows.append({
                'event_id':          ai + 1,
                'adp_start':         ae['start'],
                'adp_end':           ae['end'],
                'adp_duration_s':    ae['duration'],
                'fix_start':         None,
                'fix_end':           None,
                'fix_duration_s':    None,
                'detection_delay_s': None,
                'matched':           False,
            })

    # Fixed events not matched to any adaptive event (fixed found something adaptive missed)
    for fi, fe in enumerate(fix_events):
        if fi not in matched_fix:
            event_rows.append({
                'event_id':          f'F{fi + 1}',
                'adp_start':         None,
                'adp_end':           None,
                'adp_duration_s':    None,
                'fix_start':         fe['start'],
                'fix_end':           fe['end'],
                'fix_duration_s':    fe['duration'],
                'detection_delay_s': None,
                'matched':           False,
            })

    # ── 6. Summary dict ───────────────────────────────────────────────────────
    matched_delays = [r['detection_delay_s'] for r in event_rows
                      if r['matched'] and r['detection_delay_s'] is not None]

    summary = {
        'total_active_windows':        n_active,
        'adaptive_normal':             adp_counts['NORMAL'],
        'adaptive_warning':            adp_counts['WARNING'],
        'adaptive_congested':          adp_counts['CONGESTED'],
        'fixed_normal':                fix_counts['NORMAL'],
        'fixed_warning':               fix_counts['WARNING'],
        'fixed_congested':             fix_counts['CONGESTED'],
        'adaptive_false_positives':    adp_fp,
        'fixed_false_positives':       fixed_fp,
        'agreement_pct':               f'{agreement_pct:.1f}',
        'adaptive_events_detected':    len(adp_events),
        'fixed_events_detected':       len(fix_events),
        'matched_events':              len([r for r in event_rows if r['matched']]),
        'avg_detection_delay_s':       (
            f'{sum(matched_delays)/len(matched_delays):.1f}'
            if matched_delays else 'N/A'
        ),
    }

    # ── 7. Print to console ───────────────────────────────────────────────────
    _print_summary(summary, event_rows)

    # ── 8. Save CSV results ───────────────────────────────────────────────────
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_out = os.path.join(output_dir, f'comparison_results_{ts}.csv')
    md_out  = os.path.join(output_dir, f'comparison_results_{ts}.md')
    png_out = os.path.join(output_dir, f'comparison_plot_{ts}.png')

    _save_csv(summary, event_rows, csv_out)
    _save_markdown(summary, event_rows, md_out, adaptive_csv, fixed_csv)
    _save_plot(adp, fix, adp_events, fix_events, png_out)

    print(f"\n[compare] Results saved:")
    print(f"  CSV  : {csv_out}")
    print(f"  MD   : {md_out}")
    print(f"  PNG  : {png_out}\n")


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_summary(summary: dict, event_rows: list) -> None:
    print("\n" + "=" * 62)
    print("  ADAPTIVE vs. FIXED THRESHOLD  –  COMPARISON RESULTS")
    print("=" * 62)
    print(f"  Active windows analysed : {summary['total_active_windows']}")
    print()
    print(f"  {'Metric':<36} {'Adaptive':>10} {'Fixed':>10}")
    print(f"  {'-'*36} {'-'*10} {'-'*10}")
    print(f"  {'NORMAL windows':<36} {summary['adaptive_normal']:>10} {summary['fixed_normal']:>10}")
    print(f"  {'WARNING windows':<36} {summary['adaptive_warning']:>10} {summary['fixed_warning']:>10}")
    print(f"  {'CONGESTED windows':<36} {summary['adaptive_congested']:>10} {summary['fixed_congested']:>10}")
    print(f"  {'False positives (vs. other method)':<36} {summary['adaptive_false_positives']:>10} {summary['fixed_false_positives']:>10}")
    print(f"  {'Congestion events detected':<36} {summary['adaptive_events_detected']:>10} {summary['fixed_events_detected']:>10}")
    print()
    print(f"  Agreement rate           : {summary['agreement_pct']} %")
    print(f"  Matched events           : {summary['matched_events']}")
    print(f"  Avg detection delay (s)  : {summary['avg_detection_delay_s']}")
    print("  (positive delay = adaptive detected the event later than fixed)")
    print("=" * 62)

    if event_rows:
        print("\n  Congestion event details:")
        print(f"  {'ID':<4} {'Adp start':>9} {'Adp dur':>7} {'Fix start':>9} "
              f"{'Fix dur':>7} {'Delay':>6} {'Match'}")
        print(f"  {'-'*4} {'-'*9} {'-'*7} {'-'*9} {'-'*7} {'-'*6} {'-'*5}")
        for r in event_rows:
            print(
                f"  {str(r['event_id']):<4} "
                f"{str(r['adp_start'] if r['adp_start'] is not None else '-'):>9} "
                f"{str(r['adp_duration_s'] if r['adp_duration_s'] is not None else '-'):>7} "
                f"{str(r['fix_start'] if r['fix_start'] is not None else '-'):>9} "
                f"{str(r['fix_duration_s'] if r['fix_duration_s'] is not None else '-'):>7} "
                f"{str(r['detection_delay_s'] if r['detection_delay_s'] is not None else '-'):>6} "
                f"{'YES' if r['matched'] else 'NO'}"
            )
    print()


def _save_csv(summary: dict, event_rows: list, path: str) -> None:
    """Saves summary + event table as CSV."""
    import csv
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)

        # Summary block
        w.writerow(['# Summary'])
        for k, v in summary.items():
            w.writerow([k, v])

        w.writerow([])
        # Event detail block
        w.writerow(['# Congestion Event Details'])
        if event_rows:
            w.writerow(list(event_rows[0].keys()))
            for r in event_rows:
                w.writerow(list(r.values()))
        else:
            w.writerow(['No congestion events detected by either method.'])


def _save_markdown(summary: dict, event_rows: list,
                   path: str, adp_csv: str, fix_csv: str) -> None:
    """Saves a formatted Markdown report."""
    lines = [
        "# Adaptive vs. Fixed Threshold – Comparison Results",
        "",
        f"- **Adaptive CSV**: `{adp_csv}`",
        f"- **Fixed CSV**:    `{fix_csv}`",
        "",
        "## Summary",
        "",
        "| Metric | Adaptive | Fixed |",
        "|--------|:--------:|:-----:|",
        f"| Active windows analysed | {summary['total_active_windows']} | {summary['total_active_windows']} |",
        f"| NORMAL windows | {summary['adaptive_normal']} | {summary['fixed_normal']} |",
        f"| WARNING windows | {summary['adaptive_warning']} | {summary['fixed_warning']} |",
        f"| CONGESTED windows | {summary['adaptive_congested']} | {summary['fixed_congested']} |",
        f"| **False positives** (vs. other method) | **{summary['adaptive_false_positives']}** | **{summary['fixed_false_positives']}** |",
        f"| Congestion events detected | {summary['adaptive_events_detected']} | {summary['fixed_events_detected']} |",
        f"| Agreement rate | {summary['agreement_pct']} % | – |",
        f"| Matched congestion events | {summary['matched_events']} | – |",
        f"| Avg detection delay | {summary['avg_detection_delay_s']} s | – |",
        "",
        "> **Detection delay**: positive = adaptive detected the event *later* than fixed;",
        "> negative = adaptive detected it *earlier*.  A near-zero or negative value",
        "> alongside a lower false-positive count proves the adaptive method's advantage.",
        "",
        "## Congestion Event Details",
        "",
    ]

    if event_rows:
        lines += [
            "| Event | Adp start (s) | Adp dur (s) | Fix start (s) | Fix dur (s) | Delay (s) | Matched |",
            "|-------|:-------------:|:-----------:|:-------------:|:-----------:|:---------:|:-------:|",
        ]
        for r in event_rows:
            lines.append(
                f"| {r['event_id']} "
                f"| {r['adp_start'] if r['adp_start'] is not None else '–'} "
                f"| {r['adp_duration_s'] if r['adp_duration_s'] is not None else '–'} "
                f"| {r['fix_start'] if r['fix_start'] is not None else '–'} "
                f"| {r['fix_duration_s'] if r['fix_duration_s'] is not None else '–'} "
                f"| {r['detection_delay_s'] if r['detection_delay_s'] is not None else '–'} "
                f"| {'YES' if r['matched'] else 'NO'} |"
            )
    else:
        lines.append("*No congestion events detected by either method.*")

    lines += [
        "",
        "## Interpretation",
        "",
        "- A **lower false-positive count** means the method raises fewer nuisance alerts.",
        "- The adaptive method's false-positive count should be lower because it raises",
        "  the threshold proportionally to measured normal traffic.",
        "- The fixed method may produce many false positives on high-baseline machines",
        "  (e.g. a 4K stream counts as congestion even on an otherwise healthy connection).",
        "- If the detection delay for the adaptive method is ≤ 0, it detects congestion",
        "  at least as fast as the fixed method.",
    ]

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def _save_plot(
    adp: pd.DataFrame,
    fix: pd.DataFrame,
    adp_events: list,
    fix_events: list,
    path: str,
) -> None:
    """Side-by-side throughput chart showing both threshold lines and shadings."""
    x = adp['elapsed_s']
    fig, axes = plt.subplots(2, 1, figsize=(15, 8), sharex=True)
    fig.suptitle("Adaptive vs. Fixed Threshold – Throughput Comparison", fontweight='bold')

    for ax, (label, t_col, shading_events, color, shade_col) in zip(
        axes,
        [
            ('Adaptive threshold', 'T_throughput', adp_events, 'steelblue', 'red'),
            ('Fixed threshold',    'fixed_T_throughput', fix_events, 'darkorange', 'purple'),
        ]
    ):
        ax.plot(x, adp['throughput_kbps'], color='steelblue', linewidth=1.0,
                alpha=0.8, label='Throughput (KB/s)')
        ax.plot(x, fix[t_col].astype(float), color=color, linewidth=1.2,
                linestyle='--', label=label)
        ax.set_ylabel('Throughput (KB/s)')
        ax.grid(True, alpha=0.25)

        for ev in shading_events:
            ax.axvspan(ev['start'], ev['end'], color=shade_col, alpha=0.15)

        # Legend patches
        cong_patch = mpatches.Patch(color=shade_col, alpha=0.3, label='Congested (this method)')
        handles, labels_ = ax.get_legend_handles_labels()
        ax.legend(handles=handles + [cong_patch], loc='upper right', fontsize=8)

    axes[0].set_title('Adaptive method  (threshold moves with traffic)')
    axes[1].set_title('Fixed method  (threshold is constant)')
    axes[1].set_xlabel('Elapsed time (seconds)')

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare adaptive vs. fixed-threshold classification results.\n"
            "Reads two CSVs (from monitor.py and fixed_threshold.py) and\n"
            "produces a Markdown + CSV results table and a comparison plot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--adaptive', '-a',
        required=True,
        help="Path to the adaptive-threshold CSV (produced by monitor.py).",
    )
    parser.add_argument(
        '--fixed', '-f',
        required=True,
        help="Path to the fixed-threshold CSV (produced by fixed_threshold.py).",
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='logs',
        help="Directory for output files (default: logs/).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_comparison(
        adaptive_csv=args.adaptive,
        fixed_csv=args.fixed,
        output_dir=args.output_dir,
    )


if __name__ == '__main__':
    main()
