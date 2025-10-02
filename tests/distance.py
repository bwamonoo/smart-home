#!/usr/bin/env python3
"""
Ultrasonic Sensor Distance Measurement Test
Tests both ultrasonic sensors separately to verify wiring and functionality
"""

import time
import RPi.GPIO as GPIO

# Sensor configuration - using your actual pins
SENSOR_CONFIG = {
    # Ultrasonic Sensor 1 (Top - inside room detection)
    'us1_trigger': 23,
    'us1_echo': 24,
    
    # Ultrasonic Sensor 2 (Side - doorway crossing detection)  
    'us2_trigger': 25,
    'us2_echo': 12,
}

def setup_gpio():
    """Initialize GPIO pins for both sensors"""
    GPIO.setmode(GPIO.BCM)
    
    # Setup Sensor 1
    GPIO.setup(SENSOR_CONFIG['us1_trigger'], GPIO.OUT)
    GPIO.setup(SENSOR_CONFIG['us1_echo'], GPIO.IN)
    
    # Setup Sensor 2  
    GPIO.setup(SENSOR_CONFIG['us2_trigger'], GPIO.OUT)
    GPIO.setup(SENSOR_CONFIG['us2_echo'], GPIO.IN)
    
    # Initialize triggers to low
    GPIO.output(SENSOR_CONFIG['us1_trigger'], False)
    GPIO.output(SENSOR_CONFIG['us2_trigger'], False)
    
    time.sleep(0.5)
    print("✅ GPIO setup complete")

def measure_distance(trigger_pin, echo_pin, sensor_name):
    """
    Measure distance from a single ultrasonic sensor
    Returns distance in cm, or -1 if error
    """
    try:
        # Send 10us trigger pulse
        GPIO.output(trigger_pin, True)
        time.sleep(0.00001)  # 10 microseconds
        GPIO.output(trigger_pin, False)
        
        start_time = time.time()
        stop_time = time.time()
        
        # Wait for echo to go HIGH (with timeout)
        timeout_start = time.time()
        while GPIO.input(echo_pin) == 0:
            start_time = time.time()
            if time.time() - timeout_start > 0.1:  # 100ms timeout
                return -1, "Timeout waiting for echo HIGH"
        
        # Wait for echo to go LOW (with timeout)  
        timeout_start = time.time()
        while GPIO.input(echo_pin) == 1:
            stop_time = time.time()
            if time.time() - timeout_start > 0.1:  # 100ms timeout
                return -1, "Timeout waiting for echo LOW"
        
        # Calculate distance (speed of sound = 34300 cm/s)
        time_elapsed = stop_time - start_time
        distance = (time_elapsed * 34300) / 2
        
        # Filter out obviously wrong readings
        if distance > 400:  # Max reasonable distance
            return -1, "Distance too large (>400cm)"
        if distance < 2:    # Min reasonable distance
            return -1, "Distance too small (<2cm)"
            
        return round(distance, 1), "Success"
        
    except Exception as e:
        return -1, f"Error: {str(e)}"

def test_single_sensor(trigger_pin, echo_pin, sensor_name, num_readings=10):
    """Test a single ultrasonic sensor with multiple readings"""
    print(f"\n{'='*50}")
    print(f"🔧 Testing {sensor_name}")
    print(f"   Trigger: GPIO{trigger_pin}, Echo: GPIO{echo_pin}")
    print(f"{'='*50}")
    
    readings = []
    successful_readings = 0
    
    for i in range(num_readings):
        distance, status = measure_distance(trigger_pin, echo_pin, sensor_name)
        
        if distance > 0:
            readings.append(distance)
            successful_readings += 1
            print(f"  Reading {i+1:2d}: {distance:5.1f} cm ✅")
        else:
            print(f"  Reading {i+1:2d}: Failed - {status} ❌")
        
        time.sleep(0.5)  # Wait between readings
    
    # Print statistics
    if successful_readings > 0:
        avg_distance = sum(readings) / len(readings)
        min_distance = min(readings)
        max_distance = max(readings)
        
        print(f"\n📊 {sensor_name} Results:")
        print(f"   Successful readings: {successful_readings}/{num_readings}")
        print(f"   Average distance: {avg_distance:.1f} cm")
        print(f"   Range: {min_distance:.1f} - {max_distance:.1f} cm")
        print(f"   Stability: ±{max_distance - avg_distance:.1f} cm")
    else:
        print(f"\n❌ {sensor_name} - All readings failed!")
    
    return successful_readings

def continuous_monitoring():
    """Continuously monitor both sensors"""
    print(f"\n{'='*60}")
    print("📡 Continuous Monitoring Mode")
    print("Press Ctrl+C to stop monitoring")
    print(f"{'='*60}")
    
    try:
        while True:
            # Test Sensor 1
            dist1, status1 = measure_distance(
                SENSOR_CONFIG['us1_trigger'], 
                SENSOR_CONFIG['us1_echo'], 
                "US1"
            )
            
            # Test Sensor 2
            dist2, status2 = measure_distance(
                SENSOR_CONFIG['us2_trigger'], 
                SENSOR_CONFIG['us2_echo'], 
                "US2"
            )
            
            # Display results
            us1_status = f"{dist1:5.1f} cm" if dist1 > 0 else "FAILED"
            us2_status = f"{dist2:5.1f} cm" if dist2 > 0 else "FAILED"
            
            print(f"US1 (Top): {us1_status} | US2 (Side): {us2_status}")
            
            time.sleep(1)  # Update every second
            
    except KeyboardInterrupt:
        print("\n🛑 Continuous monitoring stopped")

def wiring_check():
    """Check if sensors are properly wired"""
    print(f"\n{'='*50}")
    print("🔌 Wiring Check")
    print(f"{'='*50}")
    
    print("Please verify your wiring:")
    print("\n📡 Ultrasonic Sensor 1 (Top - US1):")
    print("   VCC  → 5V (Physical pin 2 or 4)")
    print("   GND  → GND")
    print(f"   Trig → GPIO{SENSOR_CONFIG['us1_trigger']} (Physical pin {GPIO_TO_PHYSICAL[SENSOR_CONFIG['us1_trigger']]})")
    print(f"   Echo → GPIO{SENSOR_CONFIG['us1_echo']} (Physical pin {GPIO_TO_PHYSICAL[SENSOR_CONFIG['us1_echo']]})")
    
    print("\n📡 Ultrasonic Sensor 2 (Side - US2):")
    print("   VCC  → 5V (Physical pin 2 or 4)")
    print("   GND  → GND")
    print(f"   Trig → GPIO{SENSOR_CONFIG['us2_trigger']} (Physical pin {GPIO_TO_PHYSICAL[SENSOR_CONFIG['us2_trigger']]})")
    print(f"   Echo → GPIO{SENSOR_CONFIG['us2_echo']} (Physical pin {GPIO_TO_PHYSICAL[SENSOR_CONFIG['us2_echo']]})")
    
    print("\n💡 Tips:")
    print("   - Use separate 5V and GND pins for each sensor if possible")
    print("   - Ensure good connections - loose wires cause failures")
    print("   - Keep sensors away from electrical noise sources")
    print("   - Test with objects at known distances (20cm, 50cm, 100cm)")

# GPIO to Physical pin mapping for Raspberry Pi
GPIO_TO_PHYSICAL = {
    23: 16,  # GPIO23 → Physical pin 16
    24: 18,  # GPIO24 → Physical pin 18
    25: 22,  # GPIO25 → Physical pin 22
    12: 32,  # GPIO12 → Physical pin 32
}

def main():
    """Main test program"""
    print("🚀 Ultrasonic Sensor Distance Measurement Test")
    print("This script will test both ultrasonic sensors separately")
    
    try:
        setup_gpio()
        
        while True:
            print(f"\n{'='*60}")
            print("Select test mode:")
            print("1 - Test Sensor 1 (Top - US1) only")
            print("2 - Test Sensor 2 (Side - US2) only") 
            print("3 - Test both sensors sequentially")
            print("4 - Continuous monitoring (both sensors)")
            print("5 - Wiring check")
            print("0 - Exit")
            print(f"{'='*60}")
            
            choice = input("Enter choice (0-5): ").strip()
            
            if choice == '1':
                test_single_sensor(
                    SENSOR_CONFIG['us1_trigger'],
                    SENSOR_CONFIG['us1_echo'],
                    "Ultrasonic Sensor 1 (Top - US1)",
                    10
                )
                
            elif choice == '2':
                test_single_sensor(
                    SENSOR_CONFIG['us2_trigger'],
                    SENSOR_CONFIG['us2_echo'],
                    "Ultrasonic Sensor 2 (Side - US2)", 
                    10
                )
                
            elif choice == '3':
                print("\n🧪 Testing both sensors sequentially...")
                success1 = test_single_sensor(
                    SENSOR_CONFIG['us1_trigger'],
                    SENSOR_CONFIG['us1_echo'],
                    "Ultrasonic Sensor 1 (Top - US1)",
                    5
                )
                success2 = test_single_sensor(
                    SENSOR_CONFIG['us2_trigger'],
                    SENSOR_CONFIG['us2_echo'],
                    "Ultrasonic Sensor 2 (Side - US2)",
                    5
                )
                
                print(f"\n📋 Overall Results:")
                print(f"   Sensor 1: {success1}/5 successful readings")
                print(f"   Sensor 2: {success2}/5 successful readings")
                
            elif choice == '4':
                continuous_monitoring()
                
            elif choice == '5':
                wiring_check()
                
            elif choice == '0':
                print("👋 Exiting test program")
                break
                
            else:
                print("❌ Invalid choice. Please enter 0-5")
                
            input("\nPress Enter to continue...")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Program interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        GPIO.cleanup()
        print("🧹 GPIO cleanup complete")

if __name__ == "__main__":
    main()