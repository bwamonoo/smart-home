#!/usr/bin/env python3
"""
Project configuration and settings - UPDATED WITH EXACT DOORWAY MEASUREMENTS
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
    
    'ldr_channel': 0,  # ADS1115 channel for LDR (A0)
    'ads1115_address': 0x48  # Default I2C address for ADS1115
}

# Automation settings - OPTIMIZED FOR 42CM DOORWAY
LIGHT_THRESHOLD = 15000        # ADS1115 value for darkness (adjust based on testing)

# Top sensor: triggers when distance < 35cm (person is under sensor)
US1_DISTANCE_THRESHOLD = 35    # cm - top sensor threshold (was 100cm)

# Side sensor: triggers when distance < 35cm (person blocks doorway)  
US2_DISTANCE_THRESHOLD = 35    # cm - side sensor threshold (was 50cm)

# Normal distances when no one is present
US1_NORMAL_DISTANCE = 60       # cm - top sensor to ground
US2_NORMAL_DISTANCE = 42       # cm - side sensor across doorway

EXIT_DELAY = 10                # seconds delay before turning off light

# Web server settings
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False
SECRET_KEY = 'your_secret_key_here'
# Rhasspy URL used by chatbot
RHASSPY_URL = "http://localhost:12101"