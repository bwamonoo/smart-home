#!/usr/bin/env python3
"""
Ultrasonic debug tool - prints raw timing info and distance
Run with: sudo python3 ultrasonic_debug.py
"""

import time
import sys

# --- Config: change pins to your setup ---
US1_TRIG = 23
US1_ECHO = 24
US2_TRIG = 25
US2_ECHO = 12

# TIMEOUT must be longer than your longest expected reflection (seconds)
TIMEOUT = 0.12

# If you have no RPi.GPIO available, the script will simulate so you can test it.
SIMULATE = False
try:
    import RPi.GPIO as GPIO
    SIMULATE = False
except Exception:
    print("RPi.GPIO not available -> running in SIMULATION MODE")
    SIMULATE = True

def setup():
    if SIMULATE:
        return
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in (US1_TRIG, US2_TRIG):
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, False)
    for pin in (US1_ECHO, US2_ECHO):
        GPIO.setup(pin, GPIO.IN)
    time.sleep(0.1)

def cleanup():
    if not SIMULATE:
        GPIO.cleanup()

def read_distance_raw(trigger_pin, echo_pin, debug=False):
    """Return (distance_cm or None, details dict). details includes start, stop, elapsed, timed_out boolean."""
    if SIMULATE:
        # simple simulation: returns small value based on time, or large when simulating no echo
        t = time.monotonic()
        if trigger_pin == US2_TRIG:
            # simulate the weird behaviour: baseline ~42, sometimes return large
            if int(t) % 10 in (2,3):
                return 42.0, {'sim': True}
            else:
                return 1002.0, {'sim': True}
        else:
            return 50.0, {'sim': True}

    try:
        # trigger pulse
        GPIO.output(trigger_pin, True)
        time.sleep(0.00001)
        GPIO.output(trigger_pin, False)

        start = time.monotonic()
        timeout = start + TIMEOUT

        # wait for echo HIGH
        while GPIO.input(echo_pin) == 0:
            start = time.monotonic()
            if start > timeout:
                return None, {'timed_out_wait_high': True}

        stop = time.monotonic()
        timeout2 = stop + TIMEOUT

        # wait for echo LOW
        while GPIO.input(echo_pin) == 1:
            stop = time.monotonic()
            if stop > timeout2:
                return None, {'timed_out_wait_low': True}

        elapsed = stop - start
        distance = (elapsed * 34300) / 2.0  # cm
        details = {'start': start, 'stop': stop, 'elapsed': elapsed}
        if debug:
            print(f"DEBUG: start={start:.6f}, stop={stop:.6f}, elapsed={elapsed:.6f}s")
        return distance, details

    except Exception as e:
        return None, {'error': str(e)}

def single_shot(sensor_name):
    if sensor_name == 'us1':
        trig, echo = US1_TRIG, US1_ECHO
    else:
        trig, echo = US2_TRIG, US2_ECHO
    dist, details = read_distance_raw(trig, echo, debug=True)
    if dist is None:
        print(f"[{sensor_name}] READ FAILED -> details: {details}")
    else:
        print(f"[{sensor_name}] distance = {dist:.2f} cm -> details: {details}")

def continuous(sensor_name='us2', interval=0.5):
    print("Press Ctrl+C to stop. Collecting samples...")
    try:
        while True:
            single_shot(sensor_name)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopping.")

if __name__ == "__main__":
    setup()
    try:
        print("Choose sensor to test: us1 or us2 (side). Default: us2")
        name = input("Sensor (us1/us2) > ").strip() or "us2"
        print("Run single-shot or continuous? (s/c) Default c")
        mode = input("s/c > ").strip().lower() or "c"
        if mode == 's':
            single_shot(name)
        else:
            continuous(name, interval=0.5)
    finally:
        cleanup()
