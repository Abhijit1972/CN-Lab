# traffic_gen.py
#
# Test-traffic generator for the Adaptive Network Traffic Monitor.
# Generates controlled load on the local machine so the monitor has
# something interesting to classify.
#
# Two modes
# ---------
#  download  : Downloads a large public file in parallel threads to
#              simulate heavy TCP throughput.
#  udpflood  : Sends a burst of UDP datagrams to a target host/port
#              to simulate high packet rate (use only on hosts you own
#              or loopback – never flood a third-party server).
#
# Usage examples
# --------------
#  python traffic_gen.py download --threads 4 --duration 60
#  python traffic_gen.py udpflood --target 127.0.0.1 --port 9999 --rate 500 --duration 30
#  python traffic_gen.py download --url http://speedtest.tele2.net/10MB.zip --threads 6
#
# NOTE: This script does NOT require admin privileges.
#       Run it in a separate NORMAL terminal while monitor.py runs in
#       an elevated one.

import argparse
import socket
import sys
import threading
import time
import urllib.request
from typing import Optional

# ── Shared stop event – set by Ctrl+C or when duration expires ────────────────
_stop_event = threading.Event()


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD MODE
# ─────────────────────────────────────────────────────────────────────────────

# Default public test files (choose a large one for sustained load)
DEFAULT_URLS = [
    "http://speedtest.tele2.net/10MB.zip",
    "http://proof.ovh.net/files/10Mb.dat",
    "http://ipv4.download.thinkbroadband.com/10MB.zip",
]

# How many bytes to read per urllib chunk (tune for CPU vs. memory)
_CHUNK = 65_536   # 64 KB


def _download_worker(url: str, thread_id: int, counters: dict, lock: threading.Lock) -> None:
    """
    Worker that repeatedly downloads `url` until _stop_event is set.
    Accumulates downloaded bytes into `counters[thread_id]`.
    Each download restarts from the beginning once EOF is reached.
    """
    total_bytes = 0
    rounds = 0
    while not _stop_event.is_set():
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                while not _stop_event.is_set():
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break           # EOF – restart the download
                    total_bytes += len(chunk)
        except Exception as exc:
            # Network hiccup – wait briefly and retry
            if not _stop_event.is_set():
                print(f"  [DL-{thread_id}] Warning: {exc}. Retrying in 2 s …")
                time.sleep(2)
            continue
        rounds += 1

    with lock:
        counters[thread_id] = total_bytes


def run_download(url: str, num_threads: int, duration: int) -> None:
    """
    Launches `num_threads` parallel download workers, runs for `duration` seconds,
    then prints a throughput summary.
    """
    print(f"\n[traffic_gen] DOWNLOAD mode")
    print(f"  URL      : {url}")
    print(f"  Threads  : {num_threads}")
    print(f"  Duration : {duration} s")
    print(f"  Press Ctrl+C to stop early.\n")

    counters: dict[int, int] = {}
    lock = threading.Lock()
    threads = []

    for i in range(num_threads):
        t = threading.Thread(
            target=_download_worker,
            args=(url, i, counters, lock),
            daemon=True,
        )
        t.start()
        threads.append(t)
        print(f"  [DL-{i}] started")

    # Progress ticker every 5 seconds
    start = time.time()
    try:
        while not _stop_event.is_set():
            elapsed = time.time() - start
            if elapsed >= duration:
                break
            remaining = duration - elapsed
            # Print a progress line every 5 s
            time.sleep(min(5.0, remaining))
            with lock:
                total_so_far = sum(counters.values())
            elapsed_now = time.time() - start
            rate_kbps = (total_so_far / elapsed_now / 1024) if elapsed_now > 0 else 0
            print(f"  [{elapsed_now:>5.0f}s] downloaded {total_so_far / 1_048_576:.1f} MB  "
                  f"avg {rate_kbps:.0f} KB/s")
    except KeyboardInterrupt:
        pass

    _stop_event.set()
    print("\n[traffic_gen] Stopping download threads …")
    for t in threads:
        t.join(timeout=5)

    total = sum(counters.values())
    elapsed = time.time() - start
    print(f"\n[traffic_gen] Done.  Total: {total / 1_048_576:.2f} MB  "
          f"in {elapsed:.1f} s  ({total / elapsed / 1024:.0f} KB/s avg)\n")


# ─────────────────────────────────────────────────────────────────────────────
# UDP FLOOD MODE
# ─────────────────────────────────────────────────────────────────────────────

# Safety allowlist – only these targets are acceptable for flooding
_SAFE_TARGETS = {
    "127.0.0.1",
    "localhost",
    "::1",
}

_DEFAULT_PAYLOAD = b"X" * 512    # 512-byte UDP datagram payload


def run_udpflood(
    target: str,
    port: int,
    rate_pps: int,
    duration: int,
    payload_size: int,
) -> None:
    """
    Sends UDP datagrams to `target:port` at approximately `rate_pps` packets/s
    for `duration` seconds.

    IMPORTANT: Only use loopback (127.0.0.1) or your own test machine.
    Never flood a third-party host.
    """
    # ── Safety check ────────────────────────────────────────────────────────
    if target not in _SAFE_TARGETS:
        print(
            f"\n[traffic_gen] ERROR: UDP flood target '{target}' is NOT in the safe-list.\n"
            f"  Allowed targets: {_SAFE_TARGETS}\n"
            f"  Only flood loopback or hosts you explicitly own.\n"
        )
        sys.exit(1)

    payload = b"X" * min(payload_size, 1400)   # cap at ~MTU

    print(f"\n[traffic_gen] UDP FLOOD mode")
    print(f"  Target   : {target}:{port}")
    print(f"  Rate     : ~{rate_pps} pkt/s  ({len(payload)} bytes/pkt)")
    print(f"  Duration : {duration} s")
    print(f"  Press Ctrl+C to stop early.\n")
    print(f"  NOTE: Start a UDP listener on the target if you want to see it receive:\n"
          f"        python -c \"import socket; s=socket.socket(socket.AF_INET,"
          f"socket.SOCK_DGRAM); s.bind(('',{port})); "
          f"[print(len(s.recvfrom(4096)[0]),'bytes') for _ in iter(int,1)]\"\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # SO_SNDBUF: increase send buffer so the kernel can batch sends
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)

    interval = 1.0 / rate_pps   # target inter-packet gap
    sent = 0
    start = time.time()
    next_print = start + 5.0

    try:
        while not _stop_event.is_set():
            t_send = time.time()
            elapsed = t_send - start
            if elapsed >= duration:
                break

            sock.sendto(payload, (target, port))
            sent += 1

            # Progress every 5 s
            if t_send >= next_print:
                print(f"  [{elapsed:>5.0f}s] sent {sent:,} packets  "
                      f"({sent / elapsed:.0f} pkt/s avg)")
                next_print += 5.0

            # Pace to target rate
            sleep_for = interval - (time.time() - t_send)
            if sleep_for > 0:
                time.sleep(sleep_for)

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        _stop_event.set()

    elapsed = time.time() - start
    print(f"\n[traffic_gen] Done.  Sent {sent:,} packets in {elapsed:.1f} s  "
          f"({sent / elapsed:.0f} pkt/s avg)\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test-traffic generator for the Adaptive Network Traffic Monitor.\n"
            "Run this in a NORMAL (non-admin) terminal while monitor.py runs elevated."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    # ── download subcommand ──────────────────────────────────────────────────
    dl = sub.add_parser(
        "download",
        help="Parallel HTTP downloads to simulate heavy TCP throughput.",
    )
    dl.add_argument(
        "--url", "-u",
        default=DEFAULT_URLS[0],
        help=f"URL to download repeatedly. Default: {DEFAULT_URLS[0]}",
    )
    dl.add_argument(
        "--threads", "-n",
        type=int,
        default=4,
        help="Number of parallel download threads (default: 4).",
    )
    dl.add_argument(
        "--duration", "-t",
        type=int,
        default=60,
        help="How many seconds to run (default: 60).",
    )

    # ── udpflood subcommand ──────────────────────────────────────────────────
    flood = sub.add_parser(
        "udpflood",
        help=(
            "Send UDP datagrams at high rate. "
            "ONLY use loopback (127.0.0.1) or your own machine."
        ),
    )
    flood.add_argument(
        "--target", "-T",
        default="127.0.0.1",
        help="Destination IP (only 127.0.0.1 / localhost allowed). Default: 127.0.0.1",
    )
    flood.add_argument(
        "--port", "-p",
        type=int,
        default=9999,
        help="Destination UDP port (default: 9999).",
    )
    flood.add_argument(
        "--rate", "-r",
        type=int,
        default=500,
        help="Target send rate in packets/s (default: 500).",
    )
    flood.add_argument(
        "--duration", "-t",
        type=int,
        default=30,
        help="How many seconds to run (default: 30).",
    )
    flood.add_argument(
        "--size", "-s",
        type=int,
        default=512,
        help="UDP payload size in bytes, max 1400 (default: 512).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mode == "download":
        run_download(
            url=args.url,
            num_threads=args.threads,
            duration=args.duration,
        )
    elif args.mode == "udpflood":
        run_udpflood(
            target=args.target,
            port=args.port,
            rate_pps=args.rate,
            duration=args.duration,
            payload_size=args.size,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _stop_event.set()
        print("\n[traffic_gen] Interrupted by user.")
