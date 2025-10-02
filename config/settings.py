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

# Bedroom automation sensors - DUAL ULTRASONIC SYSTEM
BEDROOM_SENSORS = {
    # Ultrasonic Sensor 1 (Top - inside room detection)
    'us1_trigger': 23,
    'us1_echo': 24,
    
    # Ultrasonic Sensor 2 (Side - doorway crossing detection)  
    'us2_trigger': 25,
    'us2_echo': 12,
    
    'ldr': 0  # ADC channel for LDR
}

# Automation settings
LIGHT_THRESHOLD = 0.3           # LDR threshold for darkness
US1_DISTANCE_THRESHOLD = 100    # cm - top sensor threshold (inside room)
US2_DISTANCE_THRESHOLD = 50     # cm - side sensor threshold (doorway)
EXIT_DELAY = 10                 # seconds delay before turning off light

# Web server settings
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False
SECRET_KEY = 'your_secret_key_here'
# Rhasspy URL used by chatbot
RHASSPY_URL = "http://localhost:12101"