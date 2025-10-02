#!/usr/bin/env python3
"""
Dual Ultrasonic Sensor - Optimized for Responsiveness
"""

import RPi.GPIO as GPIO
import time

# Sensor 1 (Top)
TRIG1 = 23
ECHO1 = 24

# Sensor 2 (Side)
TRIG2 = 25
ECHO2 = 12

def setup_sensors():
    GPIO.setmode(GPIO.BCM)
    
    for trig, echo in [(TRIG1, ECHO1), (TRIG2, ECHO2)]:
        GPIO.setup(trig, GPIO.OUT)
        GPIO.setup(echo, GPIO.IN)
        GPIO.output(trig, False)

    time.sleep(0.05)  # shorter init wait

def measure_sensor(trig, echo, timeout=0.02):
    """Measure distance from an ultrasonic sensor"""
    # Send 10us pulse
    GPIO.output(trig, True)
    time.sleep(0.00001)
    GPIO.output(trig, False)
    
    start_time = time.perf_counter()
    timeout_time = start_time + timeout

    # Wait for echo start
    while GPIO.input(echo) == 0:
        start_time = time.perf_counter()
        if start_time > timeout_time:
            return None
    
    # Wait for echo end
    stop_time = time.perf_counter()
    while GPIO.input(echo) == 1:
        stop_time = time.perf_counter()
        if stop_time > timeout_time:
            return None

    # Distance calculation (speed of sound = 34300 cm/s)
    time_elapsed = stop_time - start_time
    return (time_elapsed * 34300) / 2

def main():
    setup_sensors()
    try:
        while True:
            dist1 = measure_sensor(TRIG1, ECHO1)
            dist2 = measure_sensor(TRIG2, ECHO2)

            if dist1 is not None and dist2 is not None:
                print(f"US1 (Top): {dist1:.1f} cm | US2 (Side): {dist2:.1f} cm")
            else:
                print("Missed reading...")

            # Faster loop refresh
            time.sleep(0.05)  # 20 Hz update rate (~50ms)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
