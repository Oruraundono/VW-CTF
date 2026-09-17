# 🚗 Tachometer Covert Channel — a CAN bus mini-CTF

A tiny Capture-the-Flag challenge that hides a secret keyword **in the movement of a car's RPM needle**. A Raspberry Pi injects CAN frames onto a VW Passat B8 (MQB) test bench; the tachometer needle then "spells" a word by parking at printed positions on the dial. Your job as a solver is to **watch the needle and decode the word** — no debugger, no logs, just the gauge.

Built as a hands-on automotive-security exercise: reverse-engineered CAN IDs → controlled instrument-cluster actuation → a covert data channel.

---

## ⚠️ Disclaimer

For **education and research on your own, isolated test bench only.** Do **not** run this against a vehicle in operation, a car you don't own, or any shared/public network. Injecting frames onto a live CAN bus can affect safety-critical systems. You are responsible for how you use it.

---

## What it does

The car's tachometer is controlled by CAN ID `0x107` (Motor_04, engine RPM). By continuously injecting RPM frames, the script drives the needle to a chosen position, holds it, drops it back to zero, and repeats — turning the analog gauge into a low-bandwidth display. A hidden keyword is encoded as a sequence of needle positions.

Default hidden keyword: `NTTDATA` (change it with `--message`).

---

## Hardware prerequisites

- A CAN test bench exposing the powertrain/instrument bus — this was built on a **VW Passat B8 (MQB)** bench, but any setup where an RPM-gauge ID is reachable will work with small tweaks.
- A SocketCAN-capable interface, e.g. a **Waveshare 2-CH CAN HAT** on a Raspberry Pi (any `socketcan` device is fine).
- The interface wired to the correct bus (here: `can1`).

## Software prerequisites

- Linux with SocketCAN (Raspberry Pi OS / any modern distro)
- Python 3.8+
- [`python-can`](https://python-can.readthedocs.io/) — `pip install -r requirements.txt`
- (optional) `can-utils` (`cansend`, `candump`) for manual poking / verification

---

## Setup

```bash
# 1. install the Python dependency
pip install -r requirements.txt

# 2. bring the CAN interface up (skip if it's already up)
sudo ip link set can1 up type can bitrate 500000
```

> Match the bitrate to your bench. If `can1` is already running, leave it as is.

---

## Run

```bash
# preview the plan on any machine — prints the RPM sequence, no hardware needed
python3 rpm_gauge_ctf.py --dry-run

# on the bench: step the needle through every position (sanity + tuning)
python3 rpm_gauge_ctf.py --selftest

# on the bench: broadcast the hidden keyword (terminal stays silent — no spoilers)
python3 rpm_gauge_ctf.py

# a different keyword
python3 rpm_gauge_ctf.py --message POLIMI
```

If the needle fights you or falls back to zero, the bench's Body/Gateway controller is broadcasting the real RPM (0) and overriding the injection. Either raise the send rate (lower `TX_STEP` in the script) or isolate/disconnect that controller on your bench.

---

## 🧩 The challenge (for solvers)

> **The tachometer is leaking a keyword. Watch the needle. Decode it.**

What you'll see:

1. The run begins and ends with a **double engine-rev** (the needle sweeps up and down twice, without stopping). That's just the START/END marker — **not** data.
2. In between, the needle **parks** at a numbered position and holds for a couple of seconds — that hold is a **reading**. Then it drops to zero and parks at the next.
3. Note down each position the needle parks at, in order.

Can you turn that sequence of numbers back into a word?

<details>
<summary>💡 Hint 1</summary>

The needle never parks above **6**. Two readings seem to belong together. What number base has digits 0–5?
</details>

<details>
<summary>💡 Hint 2</summary>

Each letter is exactly **two** readings. And the lowest position is 1, never 0 — maybe every reading is offset by one.
</details>

<details>
<summary>✅ Full solution</summary>

Encoding:

- Each letter → its position in the alphabet, `A=1 … Z=26` (A1Z26).
- That number is written in **base 6** as two digits: `hi = n // 6`, `lo = n % 6`.
- Each digit is shown as needle position `digit + 1` (the `+1` keeps a 0-digit visible), i.e. RPM = `position × 1000`.

To solve: read each parked position → **subtract 1** → take the digits in **pairs** → `value = hi×6 + lo` → map back through A1Z26.

`NTTDATA` comes out as the needle sequence:

| Letter | A1Z26 | base-6 | needle parks |
|-------|-------|--------|--------------|
| N | 14 | (2,2) | 3 , 3 |
| T | 20 | (3,2) | 4 , 3 |
| T | 20 | (3,2) | 4 , 3 |
| D | 4  | (0,4) | 1 , 5 |
| A | 1  | (0,1) | 1 , 2 |
| T | 20 | (3,2) | 4 , 3 |
| A | 1  | (0,1) | 1 , 2 |

So the parked positions read: `3 3 4 3 4 3 1 5 1 2 4 3 1 2` → **NTTDATA**.
</details>

---

## How it works (technical)

CAN frame for ID `0x107`:

```
00 00 00  <raw_lo> <raw_hi>  00 00 00
```

- The 16-bit engine-RPM raw value sits little-endian in bytes 3 (LSB) and 4 (MSB).
- Physical RPM = `raw × 3`, so `raw = round(RPM / 3)`.
- Example: 3000 RPM → raw 1000 → `E8 03` → `107#000000E803000000`.

Frames are re-sent every ~10 ms so the needle holds steady instead of decaying — the cluster is "sticky" and keeps the last commanded value.

---
