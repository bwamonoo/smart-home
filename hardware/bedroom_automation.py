#!/usr/bin/env python3
"""
Bedroom Automation with Dual Ultrasonic Sensors and ADS1115 LDR
"""

import time
from threading import Thread, Lock
from enum import Enum
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import BEDROOM_SENSORS, LIGHT_THRESHOLD, US1_DISTANCE_THRESHOLD, US2_DISTANCE_THRESHOLD, EXIT_DELAY

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("RPi.GPIO not available - running in simulation mode")
    GPIO_AVAILABLE = False

try:
    import Adafruit_ADS1x15
    ADS1115_AVAILABLE = True
except ImportError:
    print("Adafruit_ADS1x15 not available - LDR will run in simulation mode")
    ADS1115_AVAILABLE = False

class RoomState(Enum):
    EMPTY = 0
    OCCUPIED = 1
    EXITING = 2

class BedroomAutomation:
    def __init__(self, lights_controller=None):
        self.lights = lights_controller
        self.simulation_mode = not GPIO_AVAILABLE
        self.ads1115 = None
        
        self.state = RoomState.EMPTY
        self.last_sensor_events = []
        self.exit_timer = None
        self.lock = Lock()
        self.running = False
        self.thread = None
        
        if not self.simulation_mode:
            self.setup_sensors()
        
        print("🤖 Bedroom Automation Initialized (Dual Ultrasonic + ADS1115)")
        if self.simulation_mode:
            print("  Running in SIMULATION MODE")
        print(f"  Light threshold: {LIGHT_THRESHOLD} (ADS1115 value)")
        print(f"  Top Sensor (US1) threshold: {US1_DISTANCE_THRESHOLD}cm")
        print(f"  Side Sensor (US2) threshold: {US2_DISTANCE_THRESHOLD}cm")
        print(f"  Exit delay: {EXIT_DELAY}s")
    
    def setup_sensors(self):
        """Initialize dual ultrasonic sensor GPIO pins and ADS1115"""
        GPIO.setmode(GPIO.BCM)
        
        # Ultrasonic Sensor 1 (Top - inside room detection)
        GPIO.setup(BEDROOM_SENSORS['us1_trigger'], GPIO.OUT)
        GPIO.setup(BEDROOM_SENSORS['us1_echo'], GPIO.IN)
        
        # Ultrasonic Sensor 2 (Side - doorway crossing detection)
        GPIO.setup(BEDROOM_SENSORS['us2_trigger'], GPIO.OUT)
        GPIO.setup(BEDROOM_SENSORS['us2_echo'], GPIO.IN)
        
        # Initialize triggers to low
        GPIO.output(BEDROOM_SENSORS['us1_trigger'], False)
        GPIO.output(BEDROOM_SENSORS['us2_trigger'], False)
        time.sleep(0.5)
        
        # Initialize ADS1115 for LDR
        if ADS1115_AVAILABLE:
            try:
                self.ads1115 = Adafruit_ADS1x15.ADS1115(address=BEDROOM_SENSORS['ads1115_address'])
                print("✅ ADS1115 initialized successfully")
            except Exception as e:
                print(f"❌ Error initializing ADS1115: {e}")
                self.ads1115 = None
        else:
            print("⚠️  ADS1115 not available - LDR in simulation mode")
        
        print("✅ Dual ultrasonic sensors and ADS1115 initialized")
    
    def read_ultrasonic_distance(self, trigger_pin, echo_pin):
        """Generic function to read distance from any ultrasonic sensor"""
        if self.simulation_mode:
            # Simulate realistic distance readings
            if trigger_pin == BEDROOM_SENSORS['us1_trigger']:  # Top sensor
                return 150 + (time.time() % 5) * 30  # Vary between 150-300cm
            else:  # Side sensor
                return 200 + (time.time() % 8) * 25  # Vary between 200-400cm
        
        try:
            # Send trigger pulse
            GPIO.output(trigger_pin, True)
            time.sleep(0.00001)
            GPIO.output(trigger_pin, False)
            
            # Wait for echo response
            start_time = time.time()
            stop_time = time.time()
            
            # Wait for echo to go high (with timeout)
            timeout = time.time() + 0.1
            while GPIO.input(echo_pin) == 0:
                start_time = time.time()
                if time.time() > timeout:
                    return 500  # Timeout
            
            # Wait for echo to go low (with timeout)
            timeout = time.time() + 0.1
            while GPIO.input(echo_pin) == 1:
                stop_time = time.time()
                if time.time() > timeout:
                    return 500  # Timeout
            
            # Calculate distance in cm
            time_elapsed = stop_time - start_time
            distance = (time_elapsed * 34300) / 2
            
            return distance
            
        except Exception as e:
            print(f"❌ Error reading ultrasonic sensor: {e}")
            return 500
    
    def read_us1_sensor(self):
        """Read top ultrasonic sensor (inside room detection)"""
        distance = self.read_ultrasonic_distance(
            BEDROOM_SENSORS['us1_trigger'], 
            BEDROOM_SENSORS['us1_echo']
        )
        return distance < US1_DISTANCE_THRESHOLD, distance
    
    def read_us2_sensor(self):
        """Read side ultrasonic sensor (doorway crossing detection)"""
        distance = self.read_ultrasonic_distance(
            BEDROOM_SENSORS['us2_trigger'], 
            BEDROOM_SENSORS['us2_echo']
        )
        return distance < US2_DISTANCE_THRESHOLD, distance
    
    def read_light_level(self):
        """Read light level using ADS1115"""
        if self.simulation_mode or not self.ads1115:
            # Simulate day/night cycle - more realistic
            current_hour = (time.time() / 3600) % 24
            if 7 <= current_hour <= 19:  # Daytime
                return 5000 + (time.time() % 10) * 500  # Vary between 5000-10000 (bright)
            else:  # Nighttime
                return 20000 + (time.time() % 5) * 1000  # Vary between 20000-25000 (dark)
        
        try:
            # Read from ADS1115 channel 0 (A0)
            # Gain = 1 means ±4.096V, which is perfect for 3.3V systems
            light_value = self.ads1115.read_adc(BEDROOM_SENSORS['ldr_channel'], gain=1)
            return light_value
        except Exception as e:
            print(f"❌ Error reading ADS1115: {e}")
            return 20000  # Default to dark if sensor fails
    
    def start(self):
        """Start the automation system"""
        if self.running:
            return
        
        self.running = True
        self.thread = Thread(target=self._automation_loop)
        self.thread.daemon = True
        self.thread.start()
        print("✅ Bedroom automation started")
    
    def stop(self):
        """Stop the automation system"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("🛑 Bedroom automation stopped")
    
    def _automation_loop(self):
        """Main automation logic loop"""
        while self.running:
            try:
                self._check_occupancy()
                time.sleep(0.1)  # 100ms loop interval
            except Exception as e:
                print(f"❌ Error in automation loop: {e}")
                time.sleep(1)
    
    def _check_occupancy(self):
        """Check sensors and determine room occupancy using dual ultrasonic system"""
        us2_detected, us2_distance = self.read_us2_sensor()  # Side sensor (doorway)
        us1_detected, us1_distance = self.read_us1_sensor()  # Top sensor (inside)
        
        # Record sensor event with timestamp and distances
        current_time = time.time()
        event = {
            'time': current_time,
            'us2': us2_detected,    # Side sensor
            'us1': us1_detected,    # Top sensor
            'us2_distance': us2_distance,
            'us1_distance': us1_distance
        }
        
        self.last_sensor_events.append(event)
        # Keep only recent events (1.5 second window for smoother detection)
        self.last_sensor_events = [e for e in self.last_sensor_events 
                                 if current_time - e['time'] < 1.5]
        
        # Print sensor status for debugging (less frequent to avoid spam)
        if int(time.time()) % 5 == 0:  # Every 5 seconds
            light_level = self.read_light_level()
            print(f"📊 Sensors - US1: {us1_distance:.1f}cm, US2: {us2_distance:.1f}cm, LDR: {light_level}")
        
        # State machine logic
        with self.lock:
            if self.state == RoomState.EMPTY:
                self._handle_empty_state(us2_detected, us1_detected)
            elif self.state == RoomState.OCCUPIED:
                self._handle_occupied_state(us2_detected, us1_detected)
            elif self.state == RoomState.EXITING:
                self._handle_exiting_state(us2_detected, us1_detected)
    
    def _handle_empty_state(self, us2_detected, us1_detected):
        """Handle logic when room is empty"""
        if self._detect_entrance_sequence():
            light_level = self.read_light_level()
            print(f"🚶 Entrance detected - Light level: {light_level}")
            if light_level > LIGHT_THRESHOLD:  # Higher value = darker
                self._turn_on_bedroom_light()
                print("💡 Room is dark - turning on bedroom light")
            else:
                print("☀️  Room has enough light - no action needed")
            self.state = RoomState.OCCUPIED
            print("✅ Room now OCCUPIED")
    
    def _handle_occupied_state(self, us2_detected, us1_detected):
        """Handle logic when room is occupied"""
        if self._detect_exit_sequence():
            self.state = RoomState.EXITING
            self._start_exit_timer()
            print("🚶 Exit sequence detected - Starting exit delay")
    
    def _handle_exiting_state(self, us2_detected, us1_detected):
        """Handle exiting state with safety delay"""
        # If top sensor detects movement during exit delay, cancel exit
        if us1_detected:
            self._cancel_exit_timer()
            self.state = RoomState.OCCUPIED
            print("🔄 Movement detected during exit delay - Canceling exit")
    
    def _detect_entrance_sequence(self):
        """Detect entrance: US2 (side/doorway) → US1 (top/inside)"""
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        
        # Look for pattern: Side sensor → Top sensor within 1 second
        for i in range(len(events) - 1):
            if (events[i]['us2'] and      # Side sensor triggered first (doorway)
                events[i+1]['us1'] and    # Then top sensor (inside)
                events[i+1]['time'] - events[i]['time'] < 1.0):  # Within 1 second
                return True
        return False
    
    def _detect_exit_sequence(self):
        """Detect exit: US1 (top/inside) → US2 (side/doorway)"""
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        
        # Look for pattern: Top sensor → Side sensor within 1 second
        for i in range(len(events) - 1):
            if (events[i]['us1'] and      # Top sensor triggered first (inside)
                events[i+1]['us2'] and    # Then side sensor (doorway)
                events[i+1]['time'] - events[i]['time'] < 1.0):  # Within 1 second
                return True
        return False
    
    def _start_exit_timer(self):
        """Start timer for exit delay"""
        if self.exit_timer and self.exit_timer.is_alive():
            return
        
        self.exit_timer = Thread(target=self._exit_delay_countdown)
        self.exit_timer.daemon = True
        self.exit_timer.start()
    
    def _exit_delay_countdown(self):
        """Countdown for exit delay"""
        time.sleep(EXIT_DELAY)
        
        with self.lock:
            if self.state == RoomState.EXITING:
                self._turn_off_bedroom_light()
                self.state = RoomState.EMPTY
                print("💡 Exit delay completed - Light turned off, room EMPTY")
    
    def _cancel_exit_timer(self):
        """Cancel the exit timer"""
        self.exit_timer = None
    
    def _turn_on_bedroom_light(self):
        """Turn on bedroom light"""
        if self.lights:
            self.lights.set_light('bedroom', True, source='automation')
        print("🤖 Automation: Bedroom light turned ON")
    
    def _turn_off_bedroom_light(self):
        """Turn off bedroom light"""
        if self.lights:
            self.lights.set_light('bedroom', False, source='automation')
        print("🤖 Automation: Bedroom light turned OFF")
    
    def set_lights_controller(self, lights_controller):
        """Set the lights controller for automation"""
        self.lights = lights_controller

def main():
    """Standalone bedroom automation testing"""
    print("=== 🤖 Bedroom Automation (Dual Ultrasonic + ADS1115) Standalone Mode ===")
    print("This will control the bedroom light automatically")
    print("based on occupancy using two ultrasonic sensors and LDR.")
    
    # Create a minimal lights controller for standalone use
    class MinimalLights:
        def set_light(self, room, state, source='system'):
            action = "ON" if state else "OFF"
            print(f"💡 Would turn {room} light {action} (standalone mode)")
    
    lights = MinimalLights()
    automation = BedroomAutomation(lights)
    
    try:
        automation.start()
        print("\nAutomation running. Press Ctrl+C to stop.")
        print("Sensor readings will be displayed every 5 seconds...")
        
        # Keep the main thread alive
        while automation.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping bedroom automation...")
    finally:
        automation.stop()
        if not automation.simulation_mode:
            GPIO.cleanup()

if __name__ == "__main__":
    main()