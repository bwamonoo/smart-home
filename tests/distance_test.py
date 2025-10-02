#!/usr/bin/env python3
"""
Quick Ultrasonic Sensor Test - Single run
"""

import time
import RPi.GPIO as GPIO

# Sensor pins
SENSORS = [
    {'name': 'US1 (Top)', 'trigger': 23, 'echo': 24},
    {'name': 'US2 (Side)', 'trigger': 25, 'echo': 12}
]

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    for sensor in SENSORS:
        GPIO.setup(sensor['trigger'], GPIO.OUT)
        GPIO.setup(sensor['echo'], GPIO.IN)
        GPIO.output(sensor['trigger'], False)
    time.sleep(0.5)

def quick_measure(trigger, echo):
    try:
        GPIO.output(trigger, True)
        time.sleep(0.00001)
        GPIO.output(trigger, False)
        
        start = time.time()
        timeout = start + 0.1
        
        while GPIO.input(echo) == 0:
            start = time.time()
            if time.time() > timeout:
                return -1
        
        stop = time.time()
        timeout = stop + 0.1
        
        while GPIO.input(echo) == 1:
            stop = time.time()
            if time.time() > timeout:
                return -1
        
        distance = ((stop - start) * 34300) / 2
        return round(distance, 1) if 2 < distance < 400 else -1
        
    except:
        return -1

def main():
    print("🚀 Quick Ultrasonic Test")
    print("=" * 40)
    
    setup_gpio()
    
    print("Taking 3 readings from each sensor...")
    print()
    
    for sensor in SENSORS:
        print(f"📡 {sensor['name']}:")
        readings = []
        
        for i in range(3):
            dist = quick_measure(sensor['trigger'], sensor['echo'])
            if dist > 0:
                readings.append(dist)
                print(f"   Reading {i+1}: {dist} cm ✅")
            else:
                print(f"   Reading {i+1}: Failed ❌")
            time.sleep(0.5)
        
        if readings:
            avg = sum(readings) / len(readings)
            print(f"   Average: {avg:.1f} cm")
        print()
    
    GPIO.cleanup()
    print("✅ Test complete!")

if __name__ == "__main__":
    main()