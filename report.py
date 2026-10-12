# report.py
#
# Generates a PNG graph and a plain-text summary at the end of a monitoring run.
# Called from monitor.py on exit (Ctrl+C).
#
# Requires: pandas, matplotlib

import os
import datetime
import pandas as pd
import matplotlib
matplotlib.use('Agg')          # Non-interactive backend – no GUI window needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def generate_report(csv_path: str, output_dir: str = "logs") -> None:
    """
    Reads the CSV log produced by CSVLogger and:
      1. Saves a PNG graph of throughput and retx_ratio over time,
         with the adaptive threshold line and congested periods shaded.
      2. Prints a human-readable summary to the console.
      3. Saves that summary as a .txt file alongside the graph.

    Parameters
    ----------
    csv_path   : Path to the CSV log file written by CSVLogger.
    output_dir : Directory where the PNG and TXT will be written.
    """
    # ------------------------------------------------------------------ #
    # 0. Load the CSV
    # ------------------------------------------------------------------ #
    if not os.path.exists(csv_path):
        print(f"[report] No log file found at {csv_path}. Nothing to report.")
        return

    df = pd.read_csv(csv_path)

    if df.empty:
        print("[report] Log file is empty. Nothing to report.")
        return

    # Cast numeric columns (they were written as formatted strings)
    numeric_cols = [
        'packet_rate', 'throughput_kbps', 'avg_packet_size', 'retx_ratio',
        'tcp_pct', 'udp_pct', 'icmp_pct', 'other_pct',
        'T_rate', 'T_throughput', 'T_retx'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Use row index as a simple "elapsed seconds" x-axis
    df['elapsed_s'] = df.index

    # ------------------------------------------------------------------ #
    # 1. Compute summary statistics (skip WARMUP windows)
    # ------------------------------------------------------------------ #
    active_df = df[df['level'] != 'WARMUP']

    total_packets_approx = (active_df['packet_rate'].sum())   # packets / window, each window = 1 s
    avg_throughput = active_df['throughput_kbps'].mean()
    peak_throughput = active_df['throughput_kbps'].max()

    # Identify congestion events: contiguous runs of CONGESTED windows
    congested_mask = (df['level'] == 'CONGESTED')
    # Detect transitions: rising edge starts an event, falling edge ends it
    transitions = congested_mask.astype(int).diff().fillna(0)
    event_starts = df.index[transitions == 1].tolist()
    event_ends   = df.index[transitions == -1].tolist()

    # If congestion extends to the last row, close the last event
    if len(event_starts) > len(event_ends):
        event_ends.append(df.index[-1])

    num_congestion_events = len(event_starts)
    # Each window is 1 second, so duration in seconds = number of windows
    congestion_durations = [
        (e - s + 1) for s, e in zip(event_starts, event_ends)
    ]
    total_congestion_s  = sum(congestion_durations)
    avg_congestion_s    = (total_congestion_s / num_congestion_events
                           if num_congestion_events > 0 else 0)

    run_duration_s = len(df)

    # ------------------------------------------------------------------ #
    # 2. Build the summary text
    # ------------------------------------------------------------------ #
    summary_lines = [
        "=" * 60,
        "  ADAPTIVE NETWORK MONITOR  –  END-OF-RUN SUMMARY",
        "=" * 60,
        f"  Run started  : {df['timestamp'].iloc[0]}",
        f"  Run ended    : {df['timestamp'].iloc[-1]}",
        f"  Duration     : {run_duration_s} seconds",
        "",
        f"  Total packets (approx)   : {int(total_packets_approx):,}",
        f"  Average throughput       : {avg_throughput:.2f} KB/s",
        f"  Peak throughput          : {peak_throughput:.2f} KB/s",
        "",
        f"  Congestion events        : {num_congestion_events}",
        f"  Total congestion time    : {total_congestion_s} s",
        f"  Average congestion dur.  : {avg_congestion_s:.1f} s",
    ]

    if congestion_durations:
        summary_lines.append("")
        summary_lines.append("  Individual events (start row, duration):")
        for i, (s, dur) in enumerate(zip(event_starts, congestion_durations), 1):
            ts = df['timestamp'].iloc[s] if s < len(df) else "?"
            summary_lines.append(f"    Event {i}: row {s} ({ts}), {dur} s")

    summary_lines.append("=" * 60)
    summary_text = "\n".join(summary_lines)

    print("\n" + summary_text + "\n")

    # ------------------------------------------------------------------ #
    # 3. Save the summary text file
    # ------------------------------------------------------------------ #
    os.makedirs(output_dir, exist_ok=True)
    timestamp_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(output_dir, f"summary_{timestamp_tag}.txt")
    with open(txt_path, 'w') as f:
        f.write(summary_text + "\n")
    print(f"[report] Summary saved to {txt_path}")

    # ------------------------------------------------------------------ #
    # 4. Plot
    # ------------------------------------------------------------------ #
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("Adaptive Network Traffic Monitor – Run Report", fontsize=14, fontweight='bold')

    x = df['elapsed_s']

    # --- Top chart: Throughput vs adaptive threshold ---
    ax1.plot(x, df['throughput_kbps'], color='steelblue', linewidth=1.2,
             label='Throughput (KB/s)')
    ax1.plot(x, df['T_throughput'], color='orange', linewidth=1.0,
             linestyle='--', label='Adaptive threshold')
    ax1.set_ylabel("Throughput (KB/s)")
    ax1.set_title("Throughput over time")
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    # Shade congested periods on both charts
    for s, e in zip(event_starts, event_ends):
        ax1.axvspan(s, e, color='red', alpha=0.15)
        ax2.axvspan(s, e, color='red', alpha=0.15)

    # --- Bottom chart: retx_ratio vs adaptive threshold ---
    ax2.plot(x, df['retx_ratio'], color='tomato', linewidth=1.2,
             label='Retx ratio')
    ax2.plot(x, df['T_retx'], color='orange', linewidth=1.0,
             linestyle='--', label='Adaptive threshold')
    ax2.set_ylabel("Retx ratio")
    ax2.set_xlabel("Elapsed time (seconds)")
    ax2.set_title("TCP retransmission ratio over time")
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)

    # Add a shared legend patch for congested shading
    congested_patch = mpatches.Patch(color='red', alpha=0.3, label='Congested period')
    fig.legend(handles=[congested_patch], loc='lower center', ncol=1, fontsize=9)

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    png_path = os.path.join(output_dir, f"report_{timestamp_tag}.png")
    plt.savefig(png_path, dpi=150)
    plt.close()
    print(f"[report] Graph saved to {png_path}")
