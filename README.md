# Innovative Approach to Adaptive Network Traffic Monitoring and Congestion Alerting
**Computer Network Lab (BACSE203P)**

A lightweight, host-only Python tool that captures live packets from your network interface, computes traffic parameters every second, learns "normal" traffic from a rolling history, sets its own adaptive thresholds, and raises congestion alerts.

Unlike typical network monitoring solutions, this tool does **not** rely on static thresholds, router access, SNMP, NetFlow, or heavy Machine Learning models. It observes traffic passively, adapts dynamically to your normal usage patterns, and logs data for academic analysis.

## Features

- **Passive Packet Capture**: Uses `scapy` to sniff packets without interfering with traffic.
- **1-Second Windowing**: Traffic is aggregated into 1-second chunks for real-time analysis.
- **Adaptive Thresholds**: Learns the Mean and Standard Deviation of historical windows to set dynamic thresholds (`T = Mean + K * Stdev`).
- **Approximate TCP Retransmission Detection**: Heuristically detects retransmissions by tracking recent TCP segments in a bounded LRU-style cache.
- **Three-Tier Classification**: Traffic is classified as `NORMAL`, `WARNING` (short bursts), or `CONGESTED` (sustained high traffic).
- **Web Dashboard**: An optional Flask/Chart.js dashboard to view live throughput, packet rates, and alerts.
- **Analysis Tools**: Includes scripts to compare adaptive thresholds against fixed thresholds and profile system resource usage.

## Project Structure

- `config.py` - Core configuration values (window size, history length, adaptive multipliers).
- `capture.py` - Scapy sniffing loop and timer-based window flushing.
- `metrics.py` - Calculates packet rate, throughput, protocol shares, and retransmission ratio.
- `thresholds.py` - Maintains rolling history of normal traffic to generate dynamic thresholds.
- `classifier.py` - Decision logic for `WARMUP`, `NORMAL`, `WARNING`, and `CONGESTED` states.
- `logger.py` - Writes per-window metrics and classifications to a CSV file.
- `report.py` - Generates end-of-run matplotlib graphs and text summaries.
- `monitor.py` - **Main CLI entry point.** Wires the pipeline together for terminal output.
- `dashboard/app.py` - **Web UI entry point.** Runs the monitor as a background thread and serves a live dashboard on port 5000.
- `traffic_gen.py` - Generates synthetic test traffic (parallel downloads / UDP floods).
- `fixed_threshold.py` & `compare.py` - Academic tools to compare adaptive vs. fixed threshold methods.
- `profiler.py` - Tracks the CPU and memory footprint of the monitor process.
- `TESTING.md` - Step-by-step guide on how to test the various capabilities of this project.

## Requirements and Installation

1. **Python 3.10+**
2. **Npcap** (Windows only): Required for `scapy` to capture packets. Download and install from [npcap.com](https://npcap.com/).
3. **Python Libraries**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Installs scapy, pandas, matplotlib, flask, and psutil)*

## How to Run

### 1. Terminal Monitor (CLI)
**Must be run in an Administrator/Elevated terminal.**
```powershell
# Default interface
python monitor.py

# Specific interface and log file
python monitor.py --interface "Wi-Fi" --log logs/my_run.csv

# With a BPF filter (e.g., only capture TCP traffic)
python monitor.py --filter "tcp"
```
*Press `Ctrl+C` to stop. It will automatically generate a summary text file and a PNG graph of your session in the `logs/` directory.*

### 2. Web Dashboard
**Must be run in an Administrator/Elevated terminal.**
```powershell
python dashboard/app.py
```
Open a browser and navigate to **http://localhost:5000**. The terminal will continue to log console alerts while the UI updates in real-time.

### 3. Traffic Generator
**Can be run in a normal terminal.** Use this alongside the monitor to trigger alerts.
```powershell
# Simulate heavy TCP traffic (Downloads)
python traffic_gen.py download --threads 6 --duration 60

# Simulate high packet rate (UDP flood to loopback ONLY)
python traffic_gen.py udpflood --target 127.0.0.1 --rate 800 --duration 30
```

## How Objectives are Met

1. **Host-Only Observation**: The tool requires no network infrastructure access. `capture.py` uses `store=False` in `scapy` to efficiently parse headers on the fly without storing packet payloads in memory.
2. **Adaptive Learning**: `thresholds.py` explicitly ignores `WARNING` and `CONGESTED` windows. Only `NORMAL` windows are appended to the `deque(maxlen=60)`. This ensures the baseline doesn't drift upward during a genuine congestion event.
3. **Persistence (Debouncing)**: `classifier.py` requires multiple parameters to cross the threshold for `CONSECUTIVE=3` windows before declaring a state `CONGESTED`. This prevents transient spikes from causing false alarms.
4. **Offline Comparison**: `fixed_threshold.py` proves the utility of the adaptive method by retroactively applying static thresholds to the logged CSV data, showing how rigid thresholds either miss events or generate false positives.

## Configuration Tuning

Open `config.py` to adjust system behaviour:
- `WARMUP_WINDOWS`: (Default: 15). Number of initial windows to learn the baseline before alerting.
- `K`: (Default: 2). The multiplier for standard deviation. Higher values make the tool less sensitive to spikes.
- `FLOORS`: Minimum threshold limits. These prevent division-by-zero or hyper-sensitivity when the network is completely idle.

## Testing
Please refer to `TESTING.md` for a comprehensive guide on running baseline, web browsing, download, and UDP flood scenarios.
