# profiler.py
#
# CPU and memory profiler for the monitor.py process.
#
# How to use
# ----------
# You need two terminals:
#
#   Terminal A (Admin) – start the monitor:
#       python monitor.py --log logs/profile_run.csv
#
#   Terminal B (Normal) – attach this profiler by PID:
#       python profiler.py --pid <PID>
#
# The PID is printed on the first line of monitor.py's banner,
# OR you can find it with:
#       Get-Process python | Select-Object Id, CPU, WS
#
# Alternatively, let this script LAUNCH monitor.py for you (requires admin):
#       python profiler.py --launch --interface "Wi-Fi" --duration 600
#
# Output (in logs/)
# -----------------
#   profile_<timestamp>.csv   – sampled CPU% and RSS memory over time
#   profile_<timestamp>.png   – dual-axis line chart
#
# Requirements
# ------------
#   pip install psutil
#   (already in requirements.txt)

import argparse
import csv
import datetime
import os
import subprocess
import sys
import time

try:
    import psutil
except ImportError:
    print("[profiler] ERROR: psutil is not installed.")
    print("  Run:  pip install psutil")
    sys.exit(1)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ── Sampling ──────────────────────────────────────────────────────────────────

def sample_process(
    pid: int,
    duration_s: int,
    interval_s: float,
) -> list[dict]:
    """
    Samples the CPU% and RSS memory of process `pid` every `interval_s` seconds
    for `duration_s` seconds total.

    Returns a list of dicts with keys:
        elapsed_s, cpu_pct, rss_mb
    """
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        print(f"[profiler] ERROR: No process with PID {pid}.")
        sys.exit(1)

    print(f"[profiler] Attached to PID {pid}  ({proc.name()})")
    print(f"[profiler] Sampling every {interval_s:.1f} s for {duration_s} s …")
    print(f"[profiler] Press Ctrl+C to stop early.\n")

    samples: list[dict] = []
    start = time.time()

    # First call to cpu_percent always returns 0.0 (it needs a reference point)
    proc.cpu_percent(interval=None)

    try:
        while True:
            elapsed = time.time() - start
            if elapsed >= duration_s:
                break

            try:
                # cpu_percent(interval=None) is non-blocking; returns since last call
                cpu  = proc.cpu_percent(interval=None)
                mem  = proc.memory_info().rss / (1024 * 1024)   # bytes → MB
            except psutil.NoSuchProcess:
                print("[profiler] Process ended early.")
                break

            samples.append({
                'elapsed_s': round(elapsed, 1),
                'cpu_pct':   round(cpu, 2),
                'rss_mb':    round(mem, 2),
            })

            # Print live ticker every 10 samples
            if len(samples) % 10 == 1:
                print(f"  t={elapsed:>6.0f}s  CPU={cpu:>5.1f}%  RAM={mem:>6.1f} MB")

            time.sleep(interval_s)

    except KeyboardInterrupt:
        print("\n[profiler] Stopped by user.")

    return samples


# ── Output ────────────────────────────────────────────────────────────────────

def save_csv(samples: list[dict], path: str) -> None:
    """Save sampled data to CSV."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['elapsed_s', 'cpu_pct', 'rss_mb'])
        writer.writeheader()
        writer.writerows(samples)
    print(f"[profiler] CSV saved to {path}")


def save_plot(samples: list[dict], pid: int, path: str) -> None:
    """Dual-axis line chart: CPU% (left axis) and RAM MB (right axis)."""
    if not samples:
        print("[profiler] No samples to plot.")
        return

    elapsed = [s['elapsed_s'] for s in samples]
    cpu     = [s['cpu_pct']   for s in samples]
    mem     = [s['rss_mb']    for s in samples]

    fig, ax1 = plt.subplots(figsize=(13, 5))
    fig.suptitle(f"monitor.py Resource Usage  (PID {pid})", fontweight='bold')

    color_cpu = 'steelblue'
    color_mem = 'tomato'

    ax1.plot(elapsed, cpu, color=color_cpu, linewidth=1.2, label='CPU %')
    ax1.set_xlabel('Elapsed time (seconds)')
    ax1.set_ylabel('CPU usage (%)', color=color_cpu)
    ax1.tick_params(axis='y', labelcolor=color_cpu)
    ax1.set_ylim(bottom=0)
    ax1.grid(True, alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(elapsed, mem, color=color_mem, linewidth=1.2, label='RSS memory (MB)')
    ax2.set_ylabel('RSS memory (MB)', color=color_mem)
    ax2.tick_params(axis='y', labelcolor=color_mem)
    ax2.set_ylim(bottom=0)

    # Print summary stats on the plot
    avg_cpu = sum(cpu) / len(cpu)
    peak_cpu = max(cpu)
    avg_mem = sum(mem) / len(mem)
    peak_mem = max(mem)

    stats_text = (
        f"CPU: avg {avg_cpu:.1f}%, peak {peak_cpu:.1f}%\n"
        f"RAM: avg {avg_mem:.1f} MB, peak {peak_mem:.1f} MB"
    )
    ax1.text(0.02, 0.95, stats_text, transform=ax1.transAxes,
             fontsize=8, verticalalignment='top',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))

    # Combine legends from both axes
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"[profiler] Plot saved to {path}")


def print_summary(samples: list[dict]) -> None:
    """Print final CPU/RAM summary to console."""
    if not samples:
        return

    cpus = [s['cpu_pct'] for s in samples]
    mems = [s['rss_mb']  for s in samples]

    print("\n" + "=" * 50)
    print("  RESOURCE USAGE SUMMARY")
    print("=" * 50)
    print(f"  Samples collected  : {len(samples)}")
    print(f"  Duration sampled   : {samples[-1]['elapsed_s']:.0f} s")
    print()
    print(f"  CPU  – avg: {sum(cpus)/len(cpus):.2f}%   peak: {max(cpus):.2f}%")
    print(f"  RAM  – avg: {sum(mems)/len(mems):.2f} MB  peak: {max(mems):.2f} MB")
    print("=" * 50 + "\n")


# ── Launch mode ───────────────────────────────────────────────────────────────

def launch_monitor(interface: str | None, log: str, duration: int) -> subprocess.Popen:
    """
    Launches monitor.py as a child process and returns its Popen handle.
    Note: on Windows, packet capture requires an elevated shell. This function
    will work only if the current shell is already elevated.
    """
    cmd = [sys.executable, 'monitor.py', '--log', log]
    if interface:
        cmd += ['--interface', interface]

    print(f"[profiler] Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"[profiler] monitor.py started with PID {proc.pid}")
    return proc


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "CPU / memory profiler for monitor.py.\n\n"
            "Mode 1 – attach to a running monitor.py:\n"
            "  python profiler.py --pid <PID> --duration 600\n\n"
            "Mode 2 – launch monitor.py automatically (needs admin shell):\n"
            "  python profiler.py --launch --duration 600\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--pid', '-p',
        type=int,
        default=None,
        help="PID of the already-running monitor.py process to attach to.",
    )
    parser.add_argument(
        '--launch',
        action='store_true',
        default=False,
        help="Launch monitor.py as a subprocess (requires admin shell).",
    )
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=600,
        help="How many seconds to profile (default: 600 = 10 minutes).",
    )
    parser.add_argument(
        '--interval', '-n',
        type=float,
        default=5.0,
        help="Sampling interval in seconds (default: 5.0).",
    )
    parser.add_argument(
        '--interface', '-i',
        default=None,
        help="Network interface for monitor.py (only used with --launch).",
    )
    parser.add_argument(
        '--log',
        default='logs/profile_traffic.csv',
        help="Traffic log path for monitor.py (only used with --launch).",
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='logs',
        help="Directory for profiler output files (default: logs/).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    monitor_proc: subprocess.Popen | None = None

    # ── Determine PID ─────────────────────────────────────────────────────────
    if args.launch:
        monitor_proc = launch_monitor(args.interface, args.log, args.duration)
        pid = monitor_proc.pid
        # Give monitor.py a moment to initialise before we start sampling
        print("[profiler] Waiting 3 s for monitor.py to initialise …")
        time.sleep(3)

    elif args.pid is not None:
        pid = args.pid

    else:
        # Neither --pid nor --launch: print help and instruct user
        print(
            "\n[profiler] You must supply either --pid or --launch.\n\n"
            "  Option A – Start monitor.py in an admin terminal first:\n"
            "    python monitor.py --log logs/run.csv\n"
            "  Then note its PID from Task Manager or:\n"
            "    Get-Process python | Select-Object Id, CPU, WS\n"
            "  Then run:\n"
            "    python profiler.py --pid <PID>\n\n"
            "  Option B – Let profiler launch monitor.py (admin shell required):\n"
            "    python profiler.py --launch --duration 600\n"
        )
        sys.exit(0)

    # ── Sample ────────────────────────────────────────────────────────────────
    try:
        samples = sample_process(pid, args.duration, args.interval)
    finally:
        # If we launched monitor.py, stop it cleanly
        if monitor_proc is not None:
            monitor_proc.terminate()
            monitor_proc.wait(timeout=5)
            print("[profiler] monitor.py terminated.")

    # ── Save outputs ──────────────────────────────────────────────────────────
    print_summary(samples)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    save_csv(samples, os.path.join(args.output_dir, f'profile_{ts}.csv'))
    save_plot(samples, pid, os.path.join(args.output_dir, f'profile_{ts}.png'))


if __name__ == '__main__':
    main()
