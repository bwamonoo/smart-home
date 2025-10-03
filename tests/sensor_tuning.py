#!/usr/bin/env python3
"""
Sensor Tuner / Calibrator (RC LDR boolean + Ultrasonics)
- Uses RC timing for LDR (no ADC needed)
- Ultrasonic code unchanged
Run with: sudo python3 sensor_tuner_rc.py
"""

import csv
import time
import os
import statistics
from datetime import datetime

# Try hardware imports
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("⚠️ RPi.GPIO not available — running in SIMULATION MODE")

# --- CONFIG (change if needed) ---
BEDROOM_SENSORS = {
    'us1_trigger': 23,
    'us1_echo': 24,
    'us2_trigger': 25,
    'us2_echo': 12,
    # LDR RC timing node is read on this GPIO pin (BCM)
    'ldr_gpio': 4,
}

# Tunable collection parameters
DEFAULT_SAMPLES = 120
DEFAULT_DELAY = 0.08  # seconds between samples
TIMEOUT_SEC = 0.12    # ultrasonic echo timeout

# RC timing parameters (tune if needed)
RC_TIMEOUT = 2.0      # seconds: maximum wait for cap to charge (s)
RC_DISCHARGE_MS = 10  # ms to hold pin low to discharge cap

# ----- GPIO helpers -----
def setup_gpio():
    if not GPIO_AVAILABLE:
        return
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    # Ultrasonic pins
    GPIO.setup(BEDROOM_SENSORS['us1_trigger'], GPIO.OUT)
    GPIO.setup(BEDROOM_SENSORS['us1_echo'], GPIO.IN)
    GPIO.setup(BEDROOM_SENSORS['us2_trigger'], GPIO.OUT)
    GPIO.setup(BEDROOM_SENSORS['us2_echo'], GPIO.IN)
    GPIO.output(BEDROOM_SENSORS['us1_trigger'], False)
    GPIO.output(BEDROOM_SENSORS['us2_trigger'], False)
    # don't set up ldr_gpio permanently; we will switch it between OUT/IN during timing
    time.sleep(0.1)

def cleanup_gpio():
    if GPIO_AVAILABLE:
        GPIO.cleanup()

# ----- Ultrasonic reading (unchanged) -----
def read_ultrasonic(trigger_pin, echo_pin):
    if not GPIO_AVAILABLE:
        # simulation
        t = time.monotonic()
        if trigger_pin == BEDROOM_SENSORS['us1_trigger']:
            return 40.0 if (int(t) % 15) in (2,3,4,5) else 250.0
        else:
            return 40.0 if (int(t) % 7) == 1 else 300.0

    try:
        GPIO.output(trigger_pin, True)
        time.sleep(0.00001)
        GPIO.output(trigger_pin, False)

        t_start = time.monotonic()
        timeout = t_start + TIMEOUT_SEC
        while GPIO.input(echo_pin) == 0:
            t_start = time.monotonic()
            if t_start > timeout:
                return None
        t_stop = time.monotonic()
        timeout = t_stop + TIMEOUT_SEC
        while GPIO.input(echo_pin) == 1:
            t_stop = time.monotonic()
            if t_stop > timeout:
                return None
        elapsed = t_stop - t_start
        distance = (elapsed * 34300) / 2.0
        return float(distance)
    except Exception as e:
        print("Ultrasonic read error:", e)
        return None

# ----- RC LDR timing functions (no ADC) -----
def _discharge_cap():
    """Drive the LDR node low to discharge the capacitor."""
    if not GPIO_AVAILABLE:
        return
    gpio = BEDROOM_SENSORS['ldr_gpio']
    GPIO.setup(gpio, GPIO.OUT)
    GPIO.output(gpio, GPIO.LOW)
    time.sleep(RC_DISCHARGE_MS / 1000.0)

def measure_ldr_charge_time(timeout=RC_TIMEOUT):
    """
    Measure time (seconds) it takes capacitor to charge enough that GPIO reads HIGH.
    Returns float seconds or None on timeout/error.
    """
    # Simulation path
    if not GPIO_AVAILABLE:
        t = time.monotonic()
        # simulate alternating bright/dark pattern
        return 0.04 if (int(t) % 10) < 5 else 0.7

    gpio = BEDROOM_SENSORS['ldr_gpio']
    try:
        _discharge_cap()
        # set to input and measure
        GPIO.setup(gpio, GPIO.IN)
        start = time.monotonic()
        deadline = start + timeout
        while time.monotonic() < deadline:
            if GPIO.input(gpio) == GPIO.HIGH:
                return time.monotonic() - start
        return None
    except Exception as e:
        print("LDR measure error:", e)
        return None

def measure_ldr_median(samples=7, delay=0.05):
    vals = []
    for _ in range(samples):
        v = measure_ldr_charge_time()
        if v is not None:
            vals.append(v)
        time.sleep(delay)
    if not vals:
        return None
    return statistics.median(vals)

# Boolean wrapper: True == dark, False == bright
# threshold_seconds should be tuned with calibration helper below
DEFAULT_LDR_THRESHOLD = 0.12  # seconds (example start; calibrate this)
def read_ldr_bool(threshold_seconds=DEFAULT_LDR_THRESHOLD):
    m = measure_ldr_median()
    if m is None:
        # treat timeout as dark (safe default) or False depending on preference — choose dark
        return True, None
    return (m > threshold_seconds), m

# ----- CSV helpers (unchanged) -----
def filename_for(sensor_key, mode):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"samples_{sensor_key}_{mode}_{ts}.csv"

def save_csv(samples, sensor_key, mode):
    fn = filename_for(sensor_key, mode)
    with open(fn, 'w', newline='') as f:
        w = csv.writer(f)
        # for LDR we store raw time (seconds) as value
        w.writerow(['timestamp_iso', 'unix_time', 'value'])
        for t, v in samples:
            w.writerow([datetime.fromtimestamp(t).isoformat(), f"{t:.6f}", "" if v is None else f"{v}"])
    return fn

def load_csv(fn):
    vals = []
    with open(fn, newline='') as f:
        r = csv.reader(f)
        header = next(r, None)
        for row in r:
            if len(row) < 3:
                continue
            v = row[2].strip()
            if v == "":
                vals.append(None)
            else:
                try:
                    vals.append(float(v))
                except:
                    vals.append(None)
    return vals

# ----- Stats & threshold recommendation (works with RC times) -----
def stats_from_list(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    s = {}
    s['count'] = len(clean)
    s['min'] = min(clean)
    s['max'] = max(clean)
    s['mean'] = statistics.mean(clean)
    s['median'] = statistics.median(clean)
    s['stdev'] = statistics.stdev(clean) if len(clean) > 1 else 0.0
    clean_sorted = sorted(clean)
    def percentile(p):
        if not clean_sorted:
            return None
        k = (len(clean_sorted)-1) * (p/100.0)
        f = int(k)
        c = min(f+1, len(clean_sorted)-1)
        if f == c:
            return clean_sorted[int(k)]
        d0 = clean_sorted[f] * (c - k)
        d1 = clean_sorted[c] * (k - f)
        return d0 + d1
    s['p10'] = percentile(10)
    s['p25'] = percentile(25)
    s['p75'] = percentile(75)
    s['p90'] = percentile(90)
    return s

def recommend_threshold(sensor_key, baseline_vals, occupied_vals, kind='ultrasonic'):
    """
    For LDR via RC timing: baseline = bright (small time), occupied = dark (large time)
    Recommendation: midpoint between medians unless overlap -> occupied_p90 + margin
    """
    b = stats_from_list(baseline_vals)
    o = stats_from_list(occupied_vals)
    if not b or not o:
        return None, "Insufficient data"

    if kind == 'ldr':
        b_med = b['median']; o_med = o['median']
        b_p10 = b['p10']; o_p90 = o['p90']
        if b_p10 is not None and o_p90 is not None and o_p90 > b_p10:
            # no overlap (bright median < dark median) -> midpoint
            thresh = (b_med + o_med) / 2.0
            rationale = "Midpoint between medians (no overlap)"
        else:
            margin = max(0.01, o['stdev'] if o['stdev'] else 0.01)
            thresh = o_p90 + margin
            rationale = "Overlap: chosen occupied p90 + margin"
        return round(thresh, 4), rationale

    # fallback to original ultrasonic behavior
    if kind == 'ultrasonic':
        b_med = b['median']; o_med = o['median']
        b_p10 = b['p10']; o_p90 = o['p90']
        if b_p10 is not None and o_p90 is not None and o_p90 < b_p10:
            thresh = (b_med + o_med)/2.0
            rationale = "Midpoint between medians (no overlap)"
        else:
            margin = max(1.0, o['stdev'] if o['stdev'] else 1.0)
            thresh = o_p90 + margin
            rationale = "Overlap: chosen occupied p90 + margin"
        return round(thresh, 2), rationale

    return None, "Unknown kind"

# ----- data collection (uses read_ldr_bool for LDR) -----
def collect_samples(sensor_key, mode, samples=DEFAULT_SAMPLES, delay=DEFAULT_DELAY):
    setup_gpio()
    print(f"\nCollecting {samples} samples for {sensor_key} ({mode}) - delay {delay}s")
    print("Make sure room is in the desired state (empty / person standing in place) before starting.")
    input("Press Enter to begin...")

    recorded = []
    for i in range(samples):
        t = time.time()
        if sensor_key == 'us1':
            val = read_ultrasonic(BEDROOM_SENSORS['us1_trigger'], BEDROOM_SENSORS['us1_echo'])
        elif sensor_key == 'us2':
            val = read_ultrasonic(BEDROOM_SENSORS['us2_trigger'], BEDROOM_SENSORS['us2_echo'])
        elif sensor_key == 'ldr':
            # store raw times (seconds) so we can analyze / compute thresholds
            val = measure_ldr_charge_time()
        else:
            raise ValueError("Unknown sensor_key")
        recorded.append((t, val))
        if (i+1) % 10 == 0 or i == samples-1:
            print(f"  {i+1}/{samples}  latest={val}")
        time.sleep(delay)
    fn = save_csv(recorded, sensor_key, mode)
    print(f"Saved {len(recorded)} samples to {fn}")
    return fn, recorded

# Quick single-shot logger (records LDR raw time as value)
def quick_logger():
    setup_gpio()
    print("\nQuick logger: press Enter to capture a single reading labeled with your note.")
    print("Type 'q' + Enter to quit.")
    while True:
        note = input("Label (or 'q' to quit): ").strip()
        if note.lower() == 'q':
            break
        t = time.time()
        us1 = read_ultrasonic(BEDROOM_SENSORS['us1_trigger'], BEDROOM_SENSORS['us1_echo'])
        us2 = read_ultrasonic(BEDROOM_SENSORS['us2_trigger'], BEDROOM_SENSORS['us2_echo'])
        ldr_time = measure_ldr_charge_time()
        fn = f"quick_log_{datetime.now().strftime('%Y%m%d')}.csv"
        header_needed = not os.path.exists(fn)
        with open(fn, 'a', newline='') as f:
            w = csv.writer(f)
            if header_needed:
                w.writerow(['iso', 'unix', 'label', 'us1_cm', 'us2_cm', 'ldr_time_s'])
            w.writerow([datetime.fromtimestamp(t).isoformat(), f"{t:.6f}", note,
                        "" if us1 is None else f"{us1:.2f}",
                        "" if us2 is None else f"{us2:.2f}",
                        "" if ldr_time is None else f"{ldr_time:.4f}"])
        print(f"Logged: us1={us1}, us2={us2}, ldr_time={ldr_time} -> {fn}")

# Simple analyze helper for two CSVs (or lists)
def analyze_pair(baseline_fn_or_list, occupied_fn_or_list, sensor_key):
    def to_values(arg):
        if isinstance(arg, str) and arg:
            vals = load_csv(arg)
            return vals
        elif isinstance(arg, list):
            if not arg:
                return []
            if isinstance(arg[0], tuple) and len(arg[0]) >= 2:
                return [v for (_, v) in arg]
            else:
                return arg
        else:
            return []

    base_vals = to_values(baseline_fn_or_list)
    occ_vals = to_values(occupied_fn_or_list)
    b_stats = stats_from_list(base_vals)
    o_stats = stats_from_list(occ_vals)

    print("\n--- Analysis ---")
    print("Baseline (empty/bright) stats:")
    print(b_stats or "No valid baseline samples")
    print("\nOccupied (dark) stats:")
    print(o_stats or "No valid occupied samples")

    kind = 'ldr' if sensor_key == 'ldr' else 'ultrasonic'
    thresh, rationale = recommend_threshold(sensor_key, base_vals, occ_vals, kind=kind)
    print("\nRecommendation:")
    if thresh is not None:
        if kind == 'ldr':
            print(f"  Recommended LDR threshold (seconds): {thresh}   ({rationale})")
            print("  -> interpretation: measured time > threshold => DARK (True)")
        else:
            print(f"  Recommended threshold for {sensor_key}: {thresh}   ({rationale})")
    else:
        print("  Could not compute recommendation:", rationale)
    return thresh

# ----- CLI -----
def menu():
    setup_gpio()
    while True:
        print("\n=== Sensor Tuner Menu ===")
        print("1) Collect baseline (empty) samples for US1")
        print("2) Collect occupied samples for US1 (person present)")
        print("3) Collect baseline (empty) samples for US2")
        print("4) Collect occupied samples for US2 (person crossing doorway)")
        print("5) Collect baseline (bright) samples for LDR (cover/uncover accordingly)")
        print("6) Collect occupied (dark) samples for LDR (cover LDR for dark)")
        print("7) Quick logger (single-shot labeled logs)")
        print("8) Analyze two CSV files (baseline & occupied) and recommend threshold")
        print("9) Exit")
        choice = input("Choice: ").strip()
        if choice == '1':
            fn, rec = collect_samples('us1', 'baseline')
        elif choice == '2':
            fn, rec = collect_samples('us1', 'occupied')
        elif choice == '3':
            fn, rec = collect_samples('us2', 'baseline')
        elif choice == '4':
            fn, rec = collect_samples('us2', 'occupied')
        elif choice == '5':
            fn, rec = collect_samples('ldr', 'baseline')
        elif choice == '6':
            fn, rec = collect_samples('ldr', 'occupied')
        elif choice == '7':
            quick_logger()
        elif choice == '8':
            b = input("Enter baseline CSV filename (or press Enter to skip): ").strip()
            o = input("Enter occupied CSV filename: ").strip()
            sensor_key = input("Sensor key (us1/us2/ldr): ").strip()
            if not o or not sensor_key:
                print("Missing inputs.")
            else:
                analyze_pair(b if b else [], o, sensor_key)
        elif choice == '9':
            break
        else:
            print("Invalid choice.")
    cleanup_gpio()
    print("Goodbye.")

if __name__ == "__main__":
    menu()
