#!/usr/bin/env python3
"""
room_lights_controller.py (pigpio backend via gpiozero PiGPIOFactory)
Room lights controller with:
 - single press: toggle corresponding light
 - double press (any button): turn ALL lights ON
 - hold (any button): turn ALL lights OFF
"""

from gpiozero import LED, Button
from gpiozero.pins.pigpio import PiGPIOFactory
from signal import pause
from threading import Timer
import sys
import os
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import LED_PINS, BUTTON_PINS

class RoomLightsController:
    def __init__(self, double_click_time: float = 0.4, hold_time: float = 1.0, pigpio_host: str = None):
        """
        double_click_time: max interval (s) between two presses to count as double-press
        hold_time: seconds to register a hold (when_held)
        pigpio_host: if None -> local pigpiod; else pass host/IP for remote pigpiod
        """
        self.double_click_time = double_click_time
        self.hold_time = hold_time

        # create a PiGPIOFactory that gpiozero devices will use
        # If pigpio_host is None, it connects to localhost pigpiod
        self.factory = PiGPIOFactory(host=pigpio_host) if pigpio_host else PiGPIOFactory()

        self.leds = {}
        self.buttons = {}
        self.led_states = {}
        # pending timers for single-press resolution (room -> Timer)
        self._pending_single_timers = {}

        self.setup_lights()

    def setup_lights(self):
        """Initialize all LEDs and buttons using PiGPIOFactory"""
        print("Initializing room lights (using pigpio backend)...")

        # Create LED objects using the pigpio pin factory
        for room, pin in LED_PINS.items():
            self.leds[room] = LED(pin, pin_factory=self.factory)
            self.led_states[room] = False
            print(f"  {room.capitalize():8} - LED on pin {pin}")

        # Create button objects with pull-down resistors using PiGPIOFactory
        for room, pin in BUTTON_PINS.items():
            # gpiozero Button: pull_up=False -> internal pull-down; but pigpio supports pull-up/down via factory
            btn = Button(pin, pull_up=False, bounce_time=0.05, pin_factory=self.factory)
            btn.hold_time = self.hold_time
            # wire handlers (use default args to avoid late-binding)
            btn.when_pressed = lambda r=room: self._on_button_press(r)
            btn.when_held = lambda r=room: self._on_button_hold(r)
            self.buttons[room] = btn
            print(f"  {room.capitalize():8} - Button on pin {pin}")

        print("Room lights controller ready!")
        print("Press buttons to toggle lights. Double-press any button to turn ALL ON.")
        print(f"Hold any button for {self.hold_time} seconds to turn ALL OFF.")

    # ----- Button event handlers -----
    def _on_button_press(self, room: str):
        """
        Called immediately on a physical press. We start a short timer:
         - if a second press occurs before the timer expires -> treat as double-press
         - otherwise the timer fires and performs the single-press toggle
        """
        # If there's already a pending single-press timer for this room, it's the 2nd press
        timer = self._pending_single_timers.get(room)
        if timer and timer.is_alive():
            # second press within double-click interval -> double-press
            timer.cancel()
            del self._pending_single_timers[room]
            self._handle_double_press(room)
        else:
            # start a timer that will execute the single-press action after double_click_time
            t = Timer(self.double_click_time, lambda: self._single_press_action(room))
            self._pending_single_timers[room] = t
            t.start()

    def _single_press_action(self, room: str):
        """Execute the single-press behavior (toggle the room's light)."""
        # remove pending timer entry if present
        if room in self._pending_single_timers:
            del self._pending_single_timers[room]

        self.toggle_light(room)

    def _handle_double_press(self, room: str):
        """Double-press of any button -> turn ALL lights ON"""
        # Cancel any pending single-press timers for all rooms to avoid race conditions
        self._cancel_all_pending_timers()
        self.all_lights_on()
        print(f"Double-press detected on '{room}' -> ALL lights ON")

    def _on_button_hold(self, room: str):
        """Hold any button -> turn ALL lights OFF immediately"""
        # Cancel any pending single-press timers (so a hold doesn't later trigger a single-press)
        self._cancel_all_pending_timers()
        self.all_lights_off()
        print(f"Hold detected on '{room}' -> ALL lights OFF")

    def _cancel_all_pending_timers(self):
        """Cancel and clear all pending single-press timers."""
        for r, t in list(self._pending_single_timers.items()):
            try:
                t.cancel()
            except Exception:
                pass
        self._pending_single_timers.clear()

    # ----- Light control methods -----
    def toggle_light(self, room: str):
        """Toggle a specific room's light"""
        current_state = self.led_states.get(room, False)
        new_state = not current_state

        if new_state:
            self.leds[room].on()
        else:
            self.leds[room].off()

        self.led_states[room] = new_state
        print(f"{room.capitalize()} light turned {'ON' if new_state else 'OFF'}")

    def set_light(self, room: str, state: bool):
        """Set a specific room's light state"""
        if state:
            self.leds[room].on()
        else:
            self.leds[room].off()

        self.led_states[room] = state
        return state

    def get_light_state(self, room: str):
        """Get current light state"""
        return self.led_states.get(room, False)

    def all_lights_off(self):
        """Turn all lights off"""
        for room in self.leds:
            self.set_light(room, False)
        print("All lights turned OFF")

    def all_lights_on(self):
        """Turn all lights on"""
        for room in self.leds:
            self.set_light(room, True)
        print("All lights turned ON")

    # ----- Cleanup -----
    def cleanup(self):
        """Clean up GPIO resources and timers"""
        self._cancel_all_pending_timers()
        # turn off lights and close gpiozero devices
        self.all_lights_off()
        for led in self.leds.values():
            try:
                led.close()
            except Exception:
                pass
        for btn in self.buttons.values():
            try:
                btn.close()
            except Exception:
                pass

        # Attempt to close/cleanup the factory if available (no-op if not)
        try:
            if hasattr(self.factory, "close"):
                self.factory.close()
        except Exception:
            pass

        print("GPIO cleanup completed")

def main():
    controller = RoomLightsController(double_click_time=0.4, hold_time=1.0)

    try:
        print("\n=== Room Lights Controller Running ===")
        print("Single press: toggle room")
        print("Double press any button: turn ALL ON")
        print("Hold any button: turn ALL OFF")
        pause()

    except KeyboardInterrupt:
        print("\nShutting down room lights controller...")
    finally:
        controller.cleanup()

if __name__ == "__main__":
    main()
