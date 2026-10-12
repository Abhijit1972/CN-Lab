# TESTING.md
# Step-by-step testing guide for the Adaptive Network Traffic Monitor
# CN Lab – BACSE203P

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| Python | 3.10 or newer |
| Npcap | Installed (Windows) – download from https://npcap.com |
| Admin shell | `monitor.py` **must** be run as Administrator |
| Internet | Required for download test cases |
| Dependencies | `pip install scapy pandas matplotlib flask` |

Verify your install once:
```powershell
# In a normal terminal
python -c "import scapy, pandas, matplotlib; print('OK')"
```

---

## Terminal layout

You need **two** terminal windows open side-by-side:

| Terminal A (Elevated / Admin) | Terminal B (Normal) |
|-------------------------------|---------------------|
| Runs `monitor.py`             | Runs `traffic_gen.py` or browser |

**Opening an elevated terminal on Windows:**  
Start Menu → type "PowerShell" → right-click → **Run as Administrator** → `cd "D:\CN lab"`

---

## Test Case 1 – Idle baseline (Warm-up observation)

**Goal:** Confirm the monitor starts, completes the 15-window warm-up, and reports
Normal on an almost-idle machine.

**Steps:**

**Terminal A (Admin):**
```powershell
cd "D:\CN lab"
python monitor.py --log logs/test_idle.csv
```

**Terminal B:** Close all browsers, pause any cloud sync (OneDrive, Dropbox).
Do nothing for 30 seconds.

**Expected output in Terminal A:**
```
[  WARMUP]  ... pkts=...  bw=... KB/s
...  (15 WARMUP lines)
[  NORMAL]  ...
```

**Pass criteria:**
- Lines 1–15 say `WARMUP`
- Lines 16+ say `NORMAL`
- `packet_rate` and `throughput_kbps` are low (tens of pkt/s, < 100 KB/s)
- No `WARNING` or `CONGESTED` alerts

Press **Ctrl+C** after ~60 s. Check `logs/test_idle.csv` – 60 rows, mostly WARMUP + NORMAL.

---

## Test Case 2 – Normal browsing

**Goal:** Confirm the monitor sees moderate traffic, stays mostly Normal,
possibly raises brief Warnings on page loads, but NOT Congested.

**Steps:**

**Terminal A (Admin):**
```powershell
python monitor.py --log logs/test_browse.csv
```

Wait for warm-up to finish (15 s), then:

**Terminal B / Browser:**
Open 5–10 different websites one after another (e.g. news sites, YouTube home page).
Do this for about 2 minutes.

**Expected output:**
```
[  WARMUP]  ...   (first 15 s)
[  NORMAL]  ...   (idle between page loads)
[ WARNING]  ...   (during a heavy page load – OK, expected)
[  NORMAL]  ...   (after page load completes)
```

**Pass criteria:**
- No sustained `CONGESTED` (3 consecutive windows with ≥ 2 params over threshold)
- `WARNING` is acceptable during large page loads
- `throughput_kbps` typically 50–500 KB/s during loads

Press **Ctrl+C** after ~2 minutes. Open the PNG in `logs/` – you should see
spikes in throughput that stay mostly below the adaptive threshold line.

---

## Test Case 3 – Heavy download (trigger Warning / Congested)

**Goal:** Push throughput high enough to cross the adaptive threshold and
see the monitor escalate to `WARNING` and then `CONGESTED`.

### Step 1 – Start the monitor

**Terminal A (Admin):**
```powershell
python monitor.py --log logs/test_download.csv --debug
```

Let warm-up complete (15 s).

### Step 2 – Start parallel downloads

**Terminal B (Normal):**
```powershell
cd "D:\CN lab"
python traffic_gen.py download --threads 6 --duration 90
```

This opens 6 simultaneous download streams to a public speed-test file.

**Expected escalation sequence:**
```
[  WARMUP]  ...  (windows 1–15)
[  NORMAL]  ...  (downloads not started yet)
[ WARNING]  ...  bw=800.00 KB/s  over=throughput_kbps
[CONGESTED] ...  bw=1200.00 KB/s  over=packet_rate,throughput_kbps
```

**Congestion alert box should appear** (red, within 2 s of the 3rd consecutive high window):
```
╔══════════════════════════════════════════════════════╗
║  ⚠  CONGESTION ALERT  –  2026-10-10T21:xx:xx        ║
║  Parameters over threshold: throughput_kbps, ...    ║
╚══════════════════════════════════════════════════════╝
```

### Step 3 – Stop and report

Press **Ctrl+C** in Terminal A. The PNG and summary TXT are saved to `logs/`.

**Pass criteria:**
- At least one `CONGESTED` event visible in the log
- PNG shows the throughput line exceeding the orange dashed threshold
- Red shading visible on the congestion period

---

## Test Case 4 – UDP packet-rate flood (loopback only)

**Goal:** Drive `packet_rate` high via loopback UDP without using internet,
and confirm the monitor detects the elevated rate.

### Step 1 – Start the monitor with a UDP-accepting filter

**Terminal A (Admin):**
```powershell
python monitor.py --log logs/test_udp.csv --filter "udp"
```

### Step 2 – Start the UDP flood (loopback only – safe)

**Terminal B (Normal):**
```powershell
cd "D:\CN lab"
python traffic_gen.py udpflood --target 127.0.0.1 --port 9999 --rate 800 --duration 40
```

**Note:** Scapy on Windows captures loopback traffic on the `\Device\NPF_Loopback`
interface. If `packet_rate` stays at 0, try running monitor.py without `--filter`
or change the interface:
```powershell
python monitor.py --interface "\Device\NPF_Loopback" --log logs/test_udp.csv
```

**Pass criteria:**
- `packet_rate` rises above the adaptive threshold
- Monitor escalates to `WARNING` or `CONGESTED`
- `udp_pct` shows close to 100% UDP

---

## Test Case 5 – Artificial packet loss / delay (optional)

Introducing artificial loss forces TCP retransmissions, driving `retx_ratio` up.

### Windows – Clumsy

1. Download **Clumsy** from https://jagt.github.io/clumsy/
2. Run as Administrator
3. Set filter: `udp` or `outbound`
4. Enable **Drop** at 5–10%, **Lag** at 200 ms
5. Click **Start**

Run the download test (Test Case 3) simultaneously with Clumsy active.

**Expected additional effect:** `retx_ratio` rises and may cross the `T_retx` threshold.

### Linux – tc-netem (if you boot Linux)

```bash
# Add 200 ms delay + 5% random packet loss on the outgoing interface
sudo tc qdisc add dev eth0 root netem delay 200ms loss 5%

# Run the download test (in a separate terminal)
python3 traffic_gen.py download --threads 4 --duration 90

# Remove the rule when done
sudo tc qdisc del dev eth0 root
```

---

## Checking the CSV log manually

```powershell
# Show last 10 rows
Import-Csv "D:\CN lab\logs\test_download.csv" | Select-Object -Last 10 | Format-Table
```

Or open in Excel / any spreadsheet for pivot analysis.

---

## Comparing with Wireshark (debug mode verification)

1. Open Wireshark → choose the same interface as monitor.py
2. Start capture, then run a download test
3. In Wireshark: **Statistics → I/O Graph** → set Y-axis to "Bytes/s", interval 1 s
4. Compare Wireshark's KB/s with `throughput_kbps` in the `--debug` output

**Target:** values within ≈ 5% of each other (small differences are expected
because Wireshark includes Ethernet framing and monitor.py counts at the IP layer).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `[!] Sniffing error` on start | Not running as admin | Open PowerShell as Administrator |
| `packet_rate` always 0 | Wrong interface | Run `python -c "from scapy.all import show_interfaces; show_interfaces()"` and pick the correct one, then use `--interface` |
| Loopback UDP not captured | NPF_Loopback not default | Add `--interface "\Device\NPF_Loopback"` |
| Download test connects but slow | ISP throttling | Use `--threads 8` or try a different `--url` |
| Graph PNG blank / error | pandas/matplotlib not installed | `pip install pandas matplotlib` |
| Colors not showing in terminal | Old Windows terminal | Use Windows Terminal (modern) instead of classic cmd.exe |
