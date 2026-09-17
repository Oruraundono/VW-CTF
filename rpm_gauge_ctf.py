#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# rpm_gauge_ctf.py  --  Mini CTF: tachometer-needle covert channel
# Target : VW Passat B8 (MQB) test bench, CAN ID 0x107 on can1 (Motor_04 RPM)
#
# Why the needle (vs the blinker): at -g 10 (100 Hz) the needle holds STEADY,
# no self-blink, and the cluster is "sticky" (keeps the last value). So an
# analog POSITION is a robust, readable symbol.
#
# Payload : 00 00 00 <raw_lo> <raw_hi> 00 00 00
#           raw (16-bit little-endian) sits in byte3(lo)/byte4(hi).
#           Physical RPM = raw * 3   ->   raw = round(RPM / 3)
#           e.g. 3000 RPM -> raw 1000 -> E8 03 -> 000000E803000000   (your note)
#
# ---------------------------------------------------------------------------
# ENCODING  --  this is the PUZZLE. Do NOT show it to solvers.
#   Each letter -> A1Z26 number (A=1 ... Z=26).
#   Write that number in BASE 6 as two digits:  hi = n//6 , lo = n%6
#   The needle POSITION shown = digit + 1   (so a 0-digit is still visible).
#     position p  ->  RPM = p * 1000  ->  needle points at the printed "p"
#   Per letter: needle -> hi_pos, HOLD, drop to 0, needle -> lo_pos, HOLD, drop.
#   Every letter = exactly TWO needle readings -> solver just pairs them up.
#   START / END = one full sweep 0 -> top -> 0.
#
#   Solver: read each needle numeral, subtract 1, take digits in pairs,
#           value = hi*6 + lo -> A1Z26 -> letter.  (Needle never exceeds 6:
#           that's the hint that the base is 6.)
# ---------------------------------------------------------------------------
#
# Run:
#   python3 rpm_gauge_ctf.py --dry-run       # print the RPM plan, no hardware
#   python3 rpm_gauge_ctf.py --selftest      # step 1000..6000 -- see what reads
#   python3 rpm_gauge_ctf.py                 # broadcast "NTTDATA" (SILENT)
#   python3 rpm_gauge_ctf.py --debug         # organizer only: prints the answer
#   python3 rpm_gauge_ctf.py --message POLIMI
# ---------------------------------------------------------------------------

import time
import argparse

CHANNEL = "can1"
CAN_ID  = 0x107

# --- Encoding knobs -- TUNE if your gauge can't reach 6000 RPM ---------------
BASE      = 6        # two base-6 digits cover A1Z26 (36 > 26). Needle tops at 6.
STEP_RPM  = 1000     # position p -> p * STEP_RPM (needle points at numeral p)
#   If your tach maxes low (diesel): keep BASE=6 but you can lower STEP_RPM,
#   or switch to a 3-digit base-4 scheme (needle only 1..4) -- ask me for it.

# --- Timing (seconds) --------------------------------------------------------
READ_HOLD  = 2.6     # needle parked at a position long enough to READ
DROP_GAP   = 1.2     # needle back to 0 between the two digits of a letter
LETTER_GAP = 1.9     # needle back to 0 between letters
TX_STEP    = 0.01    # resend every 10ms (=-g 10) to hold the needle steady


def rpm_to_frame(rpm):
    raw = max(0, round(rpm / 3.0)) & 0xFFFF
    return bytes([0x00, 0x00, 0x00, raw & 0xFF, (raw >> 8) & 0xFF, 0x00, 0x00, 0x00])


class Sender:
    """Sends CAN frames. --dry-run just prints, no hardware needed."""
    def __init__(self, channel, dry):
        self.dry = dry
        self.bus = None
        if not dry:
            import can
            self.bus = can.Bus(interface="socketcan", channel=channel)

    def _one(self, data):
        import can
        self.bus.send(can.Message(arbitration_id=CAN_ID,
                                  data=data, is_extended_id=False))

    def hold_rpm(self, rpm, dur, tag=""):
        data = rpm_to_frame(rpm)
        if self.dry:
            print(f"    {rpm:5d} RPM  {dur:4.2f}s  107#{data.hex().upper()}  {tag}")
            return
        end = time.time() + dur
        while time.time() < end:
            self._one(data)
            time.sleep(TX_STEP)


# --- Encoding ---------------------------------------------------------------
def show_digit(s, digit):
    pos = digit + 1                       # +1 so digit 0 is a visible deflection
    s.hold_rpm(pos * STEP_RPM, READ_HOLD, f"read: needle at {pos}")
    s.hold_rpm(0, DROP_GAP, "drop")


def marker(s, tag):
    """START/END = a double engine-rev (sweep up-down twice). The needle NEVER
    parks at a position here, so a solver won't mistake it for a reading."""
    top = BASE * STEP_RPM
    if s.dry:
        s.hold_rpm(top, 0.30, tag + " (sweep, no park)")
        s.hold_rpm(0, 0.30, "drop")
        return
    for _ in range(2):
        for r in range(0, top + 1, 500):
            s.hold_rpm(r, 0.05)
        for r in range(top, -1, -500):
            s.hold_rpm(r, 0.05)
    s.hold_rpm(0, 0.8, "settle")


def transmit(s, text, debug=False):
    text = "".join(c for c in text.upper() if c.isalpha())
    marker(s, "START")
    for ch in text:
        n = ord(ch) - 64
        hi, lo = n // BASE, n % BASE
        if debug:
            print(f"    {ch} = {n:02d}  base{BASE}=({hi},{lo})  "
                  f"needle -> {hi + 1} , {lo + 1}")
        show_digit(s, hi)
        s.hold_rpm(0, LETTER_GAP - DROP_GAP, "letter gap")   # a touch longer
        show_digit(s, lo)
        s.hold_rpm(0, LETTER_GAP, "letter gap")
    marker(s, "END")


def selftest(s):
    print("[*] selftest: needle steps 1000..6000, 2s each. Note which you can")
    print("    read cleanly. If 6000 is off-dial, tell me and we drop the base.")
    for p in range(1, BASE + 1):
        s.hold_rpm(p * STEP_RPM, 2.0, f"pos {p}")
        s.hold_rpm(0, 0.8, "drop")
    print("[*] selftest done.")


def main():
    ap = argparse.ArgumentParser(description="RPM-needle flash CTF (ID 107)")
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--message", default="NTTDATA")
    ap.add_argument("--dry-run", action="store_true", help="print RPM plan, no CAN")
    ap.add_argument("--selftest", action="store_true", help="step through positions")
    ap.add_argument("--debug", action="store_true",
                    help="organizer only: prints the answer to the terminal")
    args = ap.parse_args()

    s = Sender(args.channel, args.dry_run)
    try:
        if args.selftest:
            selftest(s)
        else:
            print(f"[*] broadcasting on {args.channel}, ID 0x{CAN_ID:03X} "
                  f"-- watch the tachometer")
            transmit(s, args.message, debug=args.debug)
            print("[*] done.")
    finally:
        if not args.dry_run and s.bus is not None:
            s.hold_rpm(0, 0.1, "off")
            s.bus.shutdown()


if __name__ == "__main__":
    main()

# ===========================================================================
# SOLUTION  (organizer eyes only)
#   Read needle numeral, subtract 1, pair the digits, value = hi*6 + lo,
#   A1Z26 -> letter.
#   NTTDATA:
#     N=14 -> (2,2) -> needle 3,3      T=20 -> (3,2) -> needle 4,3
#     T=20 -> needle 4,3               D=4  -> (0,4) -> needle 1,5
#     A=1  -> (0,1) -> needle 1,2      T=20 -> needle 4,3
#     A=1  -> needle 1,2
# ===========================================================================
