#!/usr/bin/env python3
"""
Standalone bedroom automation controller
Can run independently without web interface
"""

import time
from threading import Thread, Lock
from enum import Enum
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import BEDROOM_SENSORS, LIGHT_THRESHOLD, DISTANCE_THRESHOLD, EXIT_DELAY

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("RPi.GPIO not available - running in simulation mode")
    GPIO_AVAILABLE = False

class RoomState(Enum):
    EMPTY = 0
    OCCUPIED = 1
    EXITING = 2

class BedroomAutomation:
    def __init__(self, lights_controller=None):
        self.lights = lights_controller
        self.simulation_mode = not GPIO_AVAILABLE
        
        self.state = RoomState.EMPTY
        self.last_sensor_events = []
        self.exit_timer = None
        self.lock = Lock()
        self.running = False
        self.thread = None
        
        if not self.simulation_mode:
            self.setup_sensors()
        
        print("Bedroom automation initialized")
        if self.simulation_mode:
            print("  Running in SIMULATION MODE")
        print(f"  Light threshold: {LIGHT_THRESHOLD}")
        print(f"  Distance threshold: {DISTANCE_THRESHOLD}cm")
        print(f"  Exit delay: {EXIT_DELAY}s")
    
    def setup_sensors(self):
        """Initialize sensor GPIO pins"""
        GPIO.setmode(GPIO.BCM)
        
        # Laser sensor (input with pull-up)
        GPIO.setup(BEDROOM_SENSORS['laser_beam'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Ultrasonic sensor
        GPIO.setup(BEDROOM_SENSORS['ultrasonic_trigger'], GPIO.OUT)
        GPIO.setup(BEDROOM_SENSORS['ultrasonic_echo'], GPIO.IN)
        
        # Initialize trigger to low
        GPIO.output(BEDROOM_SENSORS['ultrasonic_trigger'], False)
        time.sleep(0.5)
    
    def read_laser_sensor(self):
        """Read laser beam status"""
        if self.simulation_mode:
            # Simulate laser sensor - you would replace this with actual input
            return False
        return not GPIO.input(BEDROOM_SENSORS['laser_beam'])
    
    def read_ultrasonic_distance(self):
        """Measure distance using ultrasonic sensor"""
        if self.simulation_mode:
            # Simulate distance reading
            return 200  # cm (far away)
        
        # Send trigger pulse
        GPIO.output(BEDROOM_SENSORS['ultrasonic_trigger'], True)
        time.sleep(0.00001)
        GPIO.output(BEDROOM_SENSORS['ultrasonic_trigger'], False)
        
        # Wait for echo
        start_time = time.time()
        stop_time = time.time()
        
        timeout = time.time() + 0.1  # 100ms timeout
        while GPIO.input(BEDROOM_SENSORS['ultrasonic_echo']) == 0:
            start_time = time.time()
            if time.time() > timeout:
                return 500  # Timeout value
        
        timeout = time.time() + 0.1
        while GPIO.input(BEDROOM_SENSORS['ultrasonic_echo']) == 1:
            stop_time = time.time()
            if time.time() > timeout:
                return 500
        
        # Calculate distance in cm
        time_elapsed = stop_time - start_time
        distance = (time_elapsed * 34300) / 2
        
        return distance
    
    def read_light_level(self):
        """Read light level (simulated for now)"""
        if self.simulation_mode:
            # Simulate light level - replace with actual ADC reading
            return 0.1  # Dark
        # For real implementation, you'd read from ADC here
        return 0.1
    
    def start(self):
        """Start the automation system"""
        if self.running:
            return
        
        self.running = True
        self.thread = Thread(target=self._automation_loop)
        self.thread.daemon = True
        self.thread.start()
        print("Bedroom automation started")
    
    def stop(self):
        """Stop the automation system"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("Bedroom automation stopped")
    
    def _automation_loop(self):
        """Main automation logic loop"""
        while self.running:
            self._check_occupancy()
            time.sleep(0.1)  # 100ms loop interval
    
    def _check_occupancy(self):
        """Check sensors and determine room occupancy"""
        laser_broken = self.read_laser_sensor()
        distance = self.read_ultrasonic_distance()
        object_detected = distance < DISTANCE_THRESHOLD
        
        # Record sensor event
        current_time = time.time()
        event = {
            'time': current_time,
            'laser': laser_broken,
            'ultrasonic': object_detected
        }
        
        self.last_sensor_events.append(event)
        # Keep only recent events (1 second window)
        self.last_sensor_events = [e for e in self.last_sensor_events 
                                 if current_time - e['time'] < 1.0]
        
        # State machine
        with self.lock:
            if self.state == RoomState.EMPTY:
                self._handle_empty_state(laser_broken, object_detected)
            elif self.state == RoomState.OCCUPIED:
                self._handle_occupied_state(laser_broken, object_detected)
            elif self.state == RoomState.EXITING:
                self._handle_exiting_state(laser_broken, object_detected)
    
    def _handle_empty_state(self, laser_broken, object_detected):
        """Handle logic when room is empty"""
        if self._detect_entrance_sequence():
            light_level = self.read_light_level()
            if light_level < LIGHT_THRESHOLD:
                self._turn_on_bedroom_light()
            self.state = RoomState.OCCUPIED
    
    def _handle_occupied_state(self, laser_broken, object_detected):
        """Handle logic when room is occupied"""
        if self._detect_exit_sequence():
            self.state = RoomState.EXITING
            self._start_exit_timer()
    
    def _handle_exiting_state(self, laser_broken, object_detected):
        """Handle exiting state with safety delay"""
        # If movement detected during exit delay, cancel exit
        if object_detected:
            self._cancel_exit_timer()
            self.state = RoomState.OCCUPIED
    
    def _detect_entrance_sequence(self):
        """Detect entrance: Laser → Ultrasonic"""
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        
        for i in range(len(events) - 1):
            if (events[i]['laser'] and 
                events[i+1]['ultrasonic'] and
                events[i+1]['time'] - events[i]['time'] < 0.5):
                return True
        return False
    
    def _detect_exit_sequence(self):
        """Detect exit: Ultrasonic → Laser"""
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        
        for i in range(len(events) - 1):
            if (events[i]['ultrasonic'] and 
                events[i+1]['laser'] and
                events[i+1]['time'] - events[i]['time'] < 0.5):
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
    
    def _cancel_exit_timer(self):
        """Cancel the exit timer"""
        self.exit_timer = None
    
    def _turn_on_bedroom_light(self):
        """Turn on bedroom light"""
        if self.lights:
            self.lights.set_light('bedroom', True)
        print("🤖 Automation: Bedroom light turned ON")
    
    def _turn_off_bedroom_light(self):
        """Turn off bedroom light"""
        if self.lights:
            self.lights.set_light('bedroom', False)
        print("🤖 Automation: Bedroom light turned OFF")
    
    def set_lights_controller(self, lights_controller):
        """Set the lights controller for automation"""
        self.lights = lights_controller

def main():
    """Standalone bedroom automation"""
    print("=== Bedroom Automation Standalone Mode ===")
    print("This will control the bedroom light automatically")
    print("based on occupancy and light level.")
    
    # Create a minimal lights controller for standalone use
    class MinimalLights:
        def set_light(self, room, state):
            action = "ON" if state else "OFF"
            print(f"💡 Would turn {room} light {action} (standalone mode)")
    
    lights = MinimalLights()
    automation = BedroomAutomation(lights)
    
    try:
        automation.start()
        print("\nAutomation running. Press Ctrl+C to stop.")
        
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