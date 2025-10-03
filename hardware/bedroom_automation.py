#!/usr/bin/env python3
"""
Bedroom Automation with Dual Ultrasonic Sensors and RC LDR (no ADC)
Optimized for 42cm doorway measurements.

LDR implemented via RC timing on a GPIO pin:
 - Drive pin LOW briefly to discharge cap
 - Switch pin to INPUT and time until reads HIGH
 - Longer time -> darker
"""

import time
from threading import Thread, Lock
from enum import Enum
import sys
import os

# If you keep a config/settings module, it should provide:
# BEDROOM_SENSORS = {'us1_trigger':..., 'us1_echo':..., 'us2_trigger':..., 'us2_echo':..., 'ldr_gpio': <BCM pin>}
# US1_DISTANCE_THRESHOLD, US2_DISTANCE_THRESHOLD, US1_NORMAL_DISTANCE, US2_NORMAL_DISTANCE, EXIT_DELAY
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config.settings import BEDROOM_SENSORS, LIGHT_THRESHOLD, US1_DISTANCE_THRESHOLD, US2_DISTANCE_THRESHOLD, US1_NORMAL_DISTANCE, US2_NORMAL_DISTANCE, EXIT_DELAY
except Exception:
    # sensible defaults if config is not present
    BEDROOM_SENSORS = {
        'us1_trigger': 23,
        'us1_echo': 24,
        'us2_trigger': 25,
        'us2_echo': 12,
        'ldr_gpio': 4,   # BCM 4 (physical pin 7) default for RC LDR node
    }
    # thresholds for ultrasonic (cm)
    US1_DISTANCE_THRESHOLD = 100.0
    US2_DISTANCE_THRESHOLD = 100.0
    US1_NORMAL_DISTANCE = 22.0
    US2_NORMAL_DISTANCE = 17.0
    EXIT_DELAY = 8

# LDR timing defaults (seconds)
DEFAULT_LDR_THRESHOLD_SECONDS = 0.12   # initial guess; calibrate with the helper below
LDR_SAMPLE_COUNT = 7
LDR_SAMPLE_DELAY = 0.05   # seconds between samples
RC_DISCHARGE_MS = 10      # milliseconds to hold pin LOW to discharge capacitor
RC_TIMEOUT = 2.0          # maximum wait for cap to charge

# Try to import RPi.GPIO; enable simulation mode if unavailable
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("RPi.GPIO not available - running in SIMULATION MODE")
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

        # stats
        self.us1_readings = []
        self.us2_readings = []
        self.last_debug_output = 0.0

        # LDR threshold seconds: use config LIGHT_THRESHOLD if it looks like a seconds value (0.001..10)
        try:
            if 'LIGHT_THRESHOLD' in globals() and isinstance(LIGHT_THRESHOLD, (int, float)) and 0.001 < LIGHT_THRESHOLD <= 10:
                self.ldr_threshold = float(LIGHT_THRESHOLD)
            else:
                self.ldr_threshold = DEFAULT_LDR_THRESHOLD_SECONDS
        except Exception:
            self.ldr_threshold = DEFAULT_LDR_THRESHOLD_SECONDS

        if not self.simulation_mode:
            self.setup_sensors()

        print("🤖 Bedroom Automation Initialized (RC LDR + Dual Ultrasonics)")
        if self.simulation_mode:
            print("  Running in SIMULATION MODE (no GPIO)")
        print(f"  LDR threshold (seconds): {self.ldr_threshold:.3f}")
        print(f"  Top Sensor (US1) trigger < {US1_DISTANCE_THRESHOLD} cm (normal {US1_NORMAL_DISTANCE} cm)")
        print(f"  Side Sensor (US2) trigger < {US2_DISTANCE_THRESHOLD} cm (normal {US2_NORMAL_DISTANCE} cm)")
        print(f"  Exit delay: {EXIT_DELAY}s")
        print("  ENTRY pattern: US2 -> US1 (within 1s); EXIT: US1 -> US2 (within 1s)")

    def setup_sensors(self):
        """Initialize GPIO pins for ultrasonic and prepare LDR node usage (no steady input setup)."""
        GPIO.setmode(GPIO.BCM)
        # Ultrasonic sensor pins
        GPIO.setup(BEDROOM_SENSORS['us1_trigger'], GPIO.OUT)
        GPIO.setup(BEDROOM_SENSORS['us1_echo'], GPIO.IN)
        GPIO.setup(BEDROOM_SENSORS['us2_trigger'], GPIO.OUT)
        GPIO.setup(BEDROOM_SENSORS['us2_echo'], GPIO.IN)
        GPIO.output(BEDROOM_SENSORS['us1_trigger'], False)
        GPIO.output(BEDROOM_SENSORS['us2_trigger'], False)
        time.sleep(0.2)

        # Note: LDR node pin will be switched between OUT (to discharge) and IN (to measure)
        print("✅ GPIO (ultrasonics) initialized - LDR uses RC timing on pin", BEDROOM_SENSORS.get('ldr_gpio'))

    # --- Ultrasonic reading (unchanged) ---
    def read_ultrasonic_distance(self, trigger_pin, echo_pin):
        """Return distance (cm) or 500 as timeout sentinel or None on error."""
        if self.simulation_mode:
            # simulate around the normal 42cm, occasionally produce a close reading
            now = time.time()
            if trigger_pin == BEDROOM_SENSORS['us1_trigger']:
                base = US1_NORMAL_DISTANCE
                if int(now) % 15 in (2,3,4):
                    return 30.0  # simulated person
                return base + (now % 3)
            else:
                base = US2_NORMAL_DISTANCE
                if int(now) % 12 in (5,6):
                    return 32.0
                return base + (now % 2)
        try:
            GPIO.output(trigger_pin, True)
            time.sleep(0.00001)
            GPIO.output(trigger_pin, False)

            start_time = time.time()
            stop_time = time.time()

            timeout = time.time() + 0.1
            while GPIO.input(echo_pin) == 0:
                start_time = time.time()
                if time.time() > timeout:
                    return 500
            timeout = time.time() + 0.1
            while GPIO.input(echo_pin) == 1:
                stop_time = time.time()
                if time.time() > timeout:
                    return 500
            elapsed = stop_time - start_time
            distance = (elapsed * 34300) / 2.0
            return distance
        except Exception as e:
            print("Ultrasonic read error:", e)
            return 500

    def read_us1_sensor(self):
        d = self.read_ultrasonic_distance(BEDROOM_SENSORS['us1_trigger'], BEDROOM_SENSORS['us1_echo'])
        return (d is not None) and (d < US1_DISTANCE_THRESHOLD), d

    def read_us2_sensor(self):
        d = self.read_ultrasonic_distance(BEDROOM_SENSORS['us2_trigger'], BEDROOM_SENSORS['us2_echo'])
        return (d is not None) and (d < US2_DISTANCE_THRESHOLD), d

    # --- RC LDR timing functions ---
    def _discharge_cap(self):
        """Drive LDR node low to discharge the capacitor."""
        if self.simulation_mode:
            return
        gpio = BEDROOM_SENSORS.get('ldr_gpio', 4)
        GPIO.setup(gpio, GPIO.OUT)
        GPIO.output(gpio, GPIO.LOW)
        time.sleep(RC_DISCHARGE_MS / 1000.0)

    def measure_ldr_charge_time(self, timeout=RC_TIMEOUT):
        """
        Return the time in seconds it takes the node to read HIGH after discharge.
        Returns None on timeout/error.
        """
        if self.simulation_mode:
            now = time.time()
            # simulate short times for bright, long times for dark
            return 0.04 if (int(now) % 10) < 5 else 0.6

        try:
            gpio = BEDROOM_SENSORS.get('ldr_gpio', 4)
            self._discharge_cap()
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

    def measure_ldr_median(self, samples=LDR_SAMPLE_COUNT, delay=LDR_SAMPLE_DELAY):
        vals = []
        for _ in range(samples):
            v = self.measure_ldr_charge_time()
            if v is not None:
                vals.append(v)
            time.sleep(delay)
        if not vals:
            return None
        return statistics.median(vals)

    def is_room_dark(self, threshold_seconds=None):
        """
        Return (is_dark_bool, measured_time_seconds_or_None)
        is_dark_bool True means room is dark.
        """
        if threshold_seconds is None:
            threshold_seconds = self.ldr_threshold
        med = self.measure_ldr_median()
        if med is None:
            # treat measurement failure as dark (safe default), but could be changed
            return True, None
        return (med > threshold_seconds), med

    # --- Main automation lifecycle ---
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = Thread(target=self._automation_loop, daemon=True)
        self.thread.start()
        print("✅ Bedroom automation started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("🛑 Bedroom automation stopped")

    def _automation_loop(self):
        while self.running:
            try:
                self._check_occupancy()
                time.sleep(0.1)
            except Exception as e:
                print("Error in automation loop:", e)
                time.sleep(1)

    def _check_occupancy(self):
        us2_detected, us2_distance = self.read_us2_sensor()
        us1_detected, us1_distance = self.read_us1_sensor()

        current_time = time.time()
        event = {
            'time': current_time,
            'us2': us2_detected,
            'us1': us1_detected,
            'us2_distance': us2_distance,
            'us1_distance': us1_distance
        }

        self.last_sensor_events.append(event)
        self.last_sensor_events = [e for e in self.last_sensor_events if current_time - e['time'] < 1.5]

        # statistics
        self.us1_readings.append(us1_distance)
        self.us2_readings.append(us2_distance)
        if len(self.us1_readings) > 100:
            self.us1_readings.pop(0)
            self.us2_readings.pop(0)

        # debug output every ~3 seconds
        now = time.time()
        if now - self.last_debug_output > 3.0:
            is_dark, ldr_time = self.is_room_dark(self.ldr_threshold) if self.simulation_mode == False else self.is_room_dark(self.ldr_threshold)
            us1_avg = sum([x for x in self.us1_readings if x is not None]) / len(self.us1_readings) if self.us1_readings else 0
            us2_avg = sum([x for x in self.us2_readings if x is not None]) / len(self.us2_readings) if self.us2_readings else 0
            ldr_disp = f"{(ldr_time if ldr_time is not None else 'ERR'):>6}"
            ldr_state = "DARK" if is_dark else "BRIGHT"
            print(f"📊 US1: {us1_distance:5.1f}cm (avg:{us1_avg:5.1f}) | US2: {us2_distance:5.1f}cm (avg:{us2_avg:5.1f}) | LDR_time: {ldr_disp}s ({ldr_state}) | State: {self.state.name}")
            us1_status = "🔴 TRIGGERED" if us1_detected else "🟢 NORMAL"
            us2_status = "🔴 TRIGGERED" if us2_detected else "🟢 NORMAL"
            print(f"   US1: {us1_status} | US2: {us2_status}")
            self.last_debug_output = now

        # state machine
        with self.lock:
            if self.state == RoomState.EMPTY:
                self._handle_empty_state(us2_detected, us1_detected)
            elif self.state == RoomState.OCCUPIED:
                self._handle_occupied_state(us2_detected, us1_detected)
            elif self.state == RoomState.EXITING:
                self._handle_exiting_state(us2_detected, us1_detected)

    def _handle_empty_state(self, us2_detected, us1_detected):
        if self._detect_entrance_sequence():
            is_dark, ldr_time = self.is_room_dark(self.ldr_threshold)
            print(f"🚶 ENTRANCE DETECTED - LDR_time: {ldr_time if ldr_time is not None else 'ERR'}s => {'DARK' if is_dark else 'BRIGHT'}")
            if is_dark:
                self._turn_on_bedroom_light()
                print("💡 Room is dark - turning on bedroom light")
            else:
                print("☀️ Room bright - no light action")
            self.state = RoomState.OCCUPIED
            print("✅ Room now OCCUPIED")

    def _handle_occupied_state(self, us2_detected, us1_detected):
        if self._detect_exit_sequence():
            self.state = RoomState.EXITING
            self._start_exit_timer()
            print("🚶 EXIT SEQUENCE DETECTED - Starting exit delay")

    def _handle_exiting_state(self, us2_detected, us1_detected):
        if us1_detected:
            self._cancel_exit_timer()
            self.state = RoomState.OCCUPIED
            print("🔄 Movement during exit delay - cancel exit")

    def _detect_entrance_sequence(self):
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        for i in range(len(events) - 1):
            if events[i]['us2'] and events[i+1]['us1'] and (events[i+1]['time'] - events[i]['time'] < 1.0):
                print(f"🎯 ENTRY SEQ: US2({events[i]['us2_distance']:.1f}cm) -> US1({events[i+1]['us1_distance']:.1f}cm) in {(events[i+1]['time'] - events[i]['time'])*1000:.0f}ms")
                return True
        return False

    def _detect_exit_sequence(self):
        events = self.last_sensor_events
        if len(events) < 2:
            return False
        for i in range(len(events) - 1):
            if events[i]['us1'] and events[i+1]['us2'] and (events[i+1]['time'] - events[i]['time'] < 1.0):
                print(f"🎯 EXIT SEQ: US1({events[i]['us1_distance']:.1f}cm) -> US2({events[i+1]['us2_distance']:.1f}cm) in {(events[i+1]['time'] - events[i]['time'])*1000:.0f}ms")
                return True
        return False

    def _start_exit_timer(self):
        if self.exit_timer and self.exit_timer.is_alive():
            return
        self.exit_timer = Thread(target=self._exit_delay_countdown, daemon=True)
        self.exit_timer.start()

    def _exit_delay_countdown(self):
        print(f"⏰ Exit delay started: {EXIT_DELAY} seconds")
        for i in range(EXIT_DELAY):
            time.sleep(1)
            if not self.running or self.state != RoomState.EXITING:
                return
        with self.lock:
            if self.state == RoomState.EXITING:
                self._turn_off_bedroom_light()
                self.state = RoomState.EMPTY
                print("💡 Exit delay completed - lights OFF, room EMPTY")

    def _cancel_exit_timer(self):
        self.exit_timer = None

    def _turn_on_bedroom_light(self):
        if self.lights:
            self.lights.set_light('bedroom', True, source='automation')
        print("🤖 Automation: Bedroom light -> ON")

    def _turn_off_bedroom_light(self):
        if self.lights:
            self.lights.set_light('bedroom', False, source='automation')
        print("🤖 Automation: Bedroom light -> OFF")

    def set_lights_controller(self, lights_controller):
        self.lights = lights_controller

# --- standalone test harness ---
def main():
    print("=== Bedroom Automation (RC LDR + Dual Ultrasonic) Standalone ===")
    class MinimalLights:
        def set_light(self, room, state, source='system'):
            print(f"💡 Would turn {room} {'ON' if state else 'OFF'} (source={source})")

    lights = MinimalLights()
    automation = BedroomAutomation(lights)
    try:
        automation.start()
        print("Automation running. Press Ctrl+C to stop.")
        while automation.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping automation...")
    finally:
        automation.stop()
        if GPIO_AVAILABLE:
            GPIO.cleanup()

if __name__ == "__main__":
    main()
