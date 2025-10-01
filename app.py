#!/usr/bin/env python3
"""
Main integrated smart home application
Combines room lights, bedroom automation, chatbot, and web interface
"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import eventlet
eventlet.monkey_patch()

# Import our modules
from hardware.room_lights import RoomLightsController
from hardware.bedroom_automation import BedroomAutomation
from chatbot.light_chatbot import LightChatbot
from config.settings import HOST, PORT, DEBUG, SECRET_KEY

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global components
lights_controller = None
bedroom_automation = None
chatbot = None

def initialize_components():
    """Initialize all system components"""
    global lights_controller, bedroom_automation, chatbot
    
    print("Initializing Smart Home System...")
    
    # 1. Initialize room lights with PiGPIOFactory and SocketIO
    lights_controller = RoomLightsController(
        double_click_time=0.4, 
        hold_time=1.0, 
        socketio=socketio  # Pass socketio instance for real-time updates
    )
    print("✓ Room lights controller ready (pigpio backend)")
    
    # 2. Initialize bedroom automation
    bedroom_automation = BedroomAutomation(lights_controller)
    bedroom_automation.start()
    print("✓ Bedroom automation ready")
    
    # 3. Initialize chatbot
    chatbot = LightChatbot(lights_controller)
    print("✓ Chatbot ready")
    
    print("🎉 All systems ready!")

# Web Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/light/<room>/<state>', methods=['POST'])
def control_light(room, state):
    """API endpoint to control lights"""
    if room not in lights_controller.leds:
        return jsonify({'error': 'Room not found'}), 404
    
    new_state = state.lower() == 'on'
    lights_controller.set_light(room, new_state, source='web')
    
    return jsonify({'room': room, 'state': new_state})

@app.route('/api/lights/status', methods=['GET'])
def get_all_light_status():
    """Get status of all lights"""
    status = {}
    for room in lights_controller.leds:
        status[room] = lights_controller.get_light_state(room)
    return jsonify(status)

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """API endpoint for chatbot"""
    message = request.json.get('message', '')
    response = chatbot.process_message(message)
    return jsonify({'response': response})

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # Send current light states to newly connected client
    for room in lights_controller.leds:
        state = lights_controller.get_light_state(room)
        socketio.emit('light_changed', {
            'room': room, 
            'state': state,
            'source': 'system'
        })

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

def cleanup_system():
    """Clean up all system components"""
    print("\nShutting down smart home system...")
    
    if bedroom_automation:
        bedroom_automation.stop()
    
    if lights_controller:
        lights_controller.cleanup()
    
    print("System shutdown complete")

if __name__ == '__main__':
    try:
        # Initialize all components
        initialize_components()
        
        # Start the web server
        print(f"Starting web server on http://{HOST}:{PORT}")
        socketio.run(app, host=HOST, port=PORT, debug=DEBUG)
        
    except KeyboardInterrupt:
        print("\nReceived interrupt signal...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cleanup_system()