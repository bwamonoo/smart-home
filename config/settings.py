#!/usr/bin/env python3
"""
Project configuration and settings
"""

# GPIO Pin configuration (BCM numbering)
LED_PINS = {
    'hall': 17,
    'bedroom': 27, 
    'kitchen': 22,
    'bathroom': 5
}

BUTTON_PINS = {
    'hall': 6,
    'bedroom': 13,
    'kitchen': 19,
    'bathroom': 26
}

# Bedroom automation sensors
BEDROOM_SENSORS = {
    'laser_beam': 23,      # Laser receiver input
    'ultrasonic_trigger': 24,
    'ultrasonic_echo': 25,
    'ldr': 0               # ADC channel for LDR
}

# Automation settings
LIGHT_THRESHOLD = 0.3      # LDR threshold for darkness
DISTANCE_THRESHOLD = 100   # cm for object detection
EXIT_DELAY = 10            # seconds delay before turning off light

# Web server settings
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False
SECRET_KEY = 'your_secret_key_here'