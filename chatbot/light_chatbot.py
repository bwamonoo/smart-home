#!/usr/bin/env python3
"""
Enhanced Smart Home Chatbot for Light Control
Natural language processing with advanced features
"""

import re
import sys
import os
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple, Optional

# Add parent folder to sys.path so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from hardware.room_lights import RoomLightsController
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print("⚠️  Hardware controller not available - running in simulation mode")


class LightState(Enum):
    ON = "on"
    OFF = "off"
    TOGGLE = "toggle"


class LightChatbot:
    def __init__(self, lights_controller=None):
        self.lights = lights_controller or self._create_simulator()
        self.conversation_history = []
        
        # Enhanced room mappings with synonyms
        self.room_mappings = {
            'hall': ['hall', 'living room', 'living', 'lounge', 'livingroom', 'sitting room'],
            'bedroom': ['bedroom', 'bed room', 'master bedroom', 'sleeping room', 'room'],
            'kitchen': ['kitchen', 'cooking area', 'cook room', 'cooking'],
            'bathroom': ['bathroom', 'bath room', 'restroom', 'toilet', 'washroom', 'wc']
        }
        
        # All rooms identifier
        self.all_rooms = ['all', 'every', 'every room', 'entire house', 'whole house', 'everything']
        
        # Enhanced command patterns with better regex
        self.patterns = [
            # Turn on patterns
            (r'(turn on|switch on|enable|light up|activate|start|open) (?:the )?(.+?) (?:light|lights|bulb|lamp|illumination)', self.turn_on_light),
            (r'(make|set) (?:the )?(.+?) (?:light|lights) (on|active)', self.set_light_state),
            (r'(illuminate|brighten) (?:the )?(.+)', self.turn_on_light),
            
            # Turn off patterns
            (r'(turn off|switch off|disable|deactivate|stop|close|shut off) (?:the )?(.+?) (?:light|lights|bulb|lamp|illumination)', self.turn_off_light),
            (r'(make|set) (?:the )?(.+?) (?:light|lights) (off|inactive)', self.set_light_state),
            (r'(darken) (?:the )?(.+)', self.turn_off_light),
            
            # Toggle patterns
            (r'(toggle|flip|change) (?:the )?(.+?) (?:light|lights|bulb|lamp)', self.toggle_light),
            
            # Status check patterns
            (r'(status|state|condition) (?:of|for) (?:the )?(.+) (?:light|lights|bulb|lamp)', self.check_light_status),
            (r'(is|are) (?:the )?(.+) (?:light|lights|bulb|lamp) (on|off|working|functioning)', self.check_light_state),
            (r'(which|what) (?:lights|lighting) (?:is|are) (on|off|active|inactive)', self.get_all_lights_status),
            (r'(how many|how much) (?:lights|lighting) (?:is|are) (on|off)', self.get_light_count),
            
            # All lights control
            (r'(all|every|entire|whole) (?:light|lights|bulb|lamps|illumination) (on|off)', self.control_all_lights),
            (r'(turn|switch) (on|off) (?:all|every|entire|whole) (?:light|lights|bulb|lamps)', self.control_all_lights_direct),
            (r'(lights?|lighting|illumination) (on|off|all)', self.control_all_lights_short),
            
            # Special commands
            (r'(good night|goodnight|sleep time|bed time)', self.good_night_mode),
            (r'(welcome home|i\'m home|i am home|arrived home)', self.welcome_home_mode),
            (r'(movie time|cinema mode|watch movie|film mode)', self.movie_mode),
            (r'(party mode|celebration|festive lights)', self.party_mode),
            
            # Help and system commands
            (r'(help|commands|what can you do|options|menu)', self.show_help),
            (r'(list rooms|available rooms|which rooms|rooms list)', self.list_rooms),
            (r'(thank you|thanks|ty|appreciate it)', self.thank_you),
            (r'(hello|hi|hey|greetings|good morning|good afternoon|good evening)', self.greeting),
            (r'(bye|goodbye|exit|quit|see you|farewell)', self.goodbye),
        ]

        self.setup_complete = False
        self.initialize_chatbot()
    
    def _create_simulator(self):
        """Create a simulator if hardware is not available"""
        class LightSimulator:
            def __init__(self):
                self.states = {
                    'hall': False,
                    'bedroom': False, 
                    'kitchen': False,
                    'bathroom': False
                }
            
            def set_light(self, room, state):
                if room == 'all':
                    for r in self.states:
                        self.states[r] = state
                elif room in self.states:
                    self.states[room] = state
                return True
            
            def get_light_state(self, room):
                return self.states.get(room, False)
            
            def toggle_light(self, room):
                if room in self.states:
                    self.states[room] = not self.states[room]
                    return self.states[room]
                return False
            
            def get_all_states(self):
                return self.states.copy()
            
            def cleanup(self):
                pass
        
        return LightSimulator()

    def initialize_chatbot(self):
        """Initialize the chatbot with welcome message"""
        self.setup_complete = True
        mode = "Hardware" if HARDWARE_AVAILABLE else "Simulation"
        print(f"🏠 Smart Home Chatbot Initialized ({mode} Mode)")
        print("Type 'help' for available commands or 'quit' to exit\n")

    def process_message(self, message: str) -> str:
        """Process user message and return response"""
        if not message or not message.strip():
            return "Please type a command. Type 'help' to see what I can do."
        
        message = message.lower().strip()
        
        # Add to conversation history
        self.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'user': message,
            'response': None
        })
        
        # Keep only last 50 messages
        self.conversation_history = self.conversation_history[-50:]
        
        # Try pattern matching first
        response = self._pattern_match(message)
        if response:
            # Store the response in history
            if self.conversation_history:
                self.conversation_history[-1]['response'] = response
            return response
        
        # Fallback to fuzzy matching and context understanding
        response = self._contextual_fallback(message)
        
        # Store the response in history
        if self.conversation_history:
            self.conversation_history[-1]['response'] = response
            
        return response

    def _pattern_match(self, message: str) -> Optional[str]:
        """Match message against command patterns"""
        for pattern, handler in self.patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return handler(match.groups())
        return None

    def _contextual_fallback(self, message: str) -> str:
        """Handle messages that don't match patterns using contextual understanding"""
        words = message.lower().split()
        
        # Check for light-related words
        light_words = ['light', 'lights', 'bulb', 'lamp', 'bright', 'dark']
        room_words = list(self.room_mappings.keys()) + [word for sublist in self.room_mappings.values() for word in sublist]
        
        has_light_word = any(word in light_words for word in words)
        has_room_word = any(word in room_words for word in words)
        
        if has_light_word and has_room_word:
            # Try to extract room and action
            for room in self.room_mappings:
                if any(word in self.room_mappings[room] for word in words):
                    if any(word in ['on', 'enable', 'activate'] for word in words):
                        return self.turn_on_light(('turn on', room, 'light'))
                    elif any(word in ['off', 'disable', 'deactivate'] for word in words):
                        return self.turn_off_light(('turn off', room, 'light'))
                    else:
                        return self.check_light_status(('status', room, 'light'))
        
        # Greeting detection
        if any(word in ['hello', 'hi', 'hey'] for word in words):
            return self.greeting(())
        
        # Help detection
        if any(word in ['help', 'what', 'how'] for word in words):
            return self.show_help(())
        
        return "I'm not quite sure what you want to do with the lights. Try something like 'turn on kitchen light' or 'are the bedroom lights on?'"

    def turn_on_light(self, groups: Tuple) -> str:
        """Turn on a specific light"""
        action, room_text, _ = groups
        room = self._identify_room(room_text)
        
        if room == 'all':
            return self.control_all_lights(('all', 'on'))
        elif room:
            success = self.lights.set_light(room, True)
            if success:
                return f"💡 {self._random_affirmation()} Turned on the {room} light!"
            else:
                return f"❌ Sorry, I couldn't turn on the {room} light. There might be a hardware issue."
        else:
            return f"❌ I don't recognize the room '{room_text}'. Available rooms: {', '.join(self.room_mappings.keys())}"

    def turn_off_light(self, groups: Tuple) -> str:
        """Turn off a specific light"""
        action, room_text, _ = groups
        room = self._identify_room(room_text)
        
        if room == 'all':
            return self.control_all_lights(('all', 'off'))
        elif room:
            success = self.lights.set_light(room, False)
            if success:
                return f"💡 {self._random_affirmation()} Turned off the {room} light!"
            else:
                return f"❌ Sorry, I couldn't turn off the {room} light. There might be a hardware issue."
        else:
            return f"❌ I don't recognize the room '{room_text}'. Available rooms: {', '.join(self.room_mappings.keys())}"

    def set_light_state(self, groups: Tuple) -> str:
        """Set light to specific state"""
        action, room_text, state = groups
        room = self._identify_room(room_text)
        
        if room:
            state_bool = state == 'on'
            success = self.lights.set_light(room, state_bool)
            if success:
                return f"💡 Set the {room} light {state}!"
            else:
                return f"❌ Sorry, I couldn't set the {room} light {state}."
        else:
            return f"❌ Room '{room_text}' not recognized."

    def toggle_light(self, groups: Tuple) -> str:
        """Toggle light state"""
        action, room_text = groups
        room = self._identify_room(room_text)
        
        if room:
            new_state = self.lights.toggle_light(room)
            state_text = "on" if new_state else "off"
            return f"💡 Toggled the {room} light {state_text}!"
        else:
            return f"❌ Room '{room_text}' not recognized."

    def check_light_status(self, groups: Tuple) -> str:
        """Check status of a specific light"""
        action, room_text, _ = groups
        room = self._identify_room(room_text)
        
        if room:
            state = self.lights.get_light_state(room)
            status = "on" if state else "off"
            return f"🔍 The {room} light is currently {status}."
        else:
            return f"❌ Room '{room_text}' not recognized."

    def check_light_state(self, groups: Tuple) -> str:
        """Check if light is on/off"""
        is_word, room_text, state = groups
        room = self._identify_room(room_text)
        
        if room:
            actual_state = self.lights.get_light_state(room)
            expected_state = state in ['on', 'working', 'functioning']
            
            if actual_state == expected_state:
                return f"✅ Yes, the {room} light is {state}."
            else:
                return f"❌ No, the {room} light is {'on' if actual_state else 'off'}."
        else:
            return f"❌ Room '{room_text}' not recognized."

    def get_all_lights_status(self, groups: Tuple) -> str:
        """Get status of all lights"""
        which, state = groups
        state_bool = state in ['on', 'active']
        
        all_states = self.lights.get_all_states() if hasattr(self.lights, 'get_all_states') else {}
        if not all_states:
            # Fallback: check each room individually
            all_states = {room: self.lights.get_light_state(room) for room in self.room_mappings.keys()}
        
        matching_rooms = [room for room, is_on in all_states.items() if is_on == state_bool]
        
        if matching_rooms:
            room_list = ', '.join(matching_rooms)
            return f"🔍 The following lights are {state}: {room_list}"
        else:
            return f"🔍 No lights are currently {state}."

    def get_light_count(self, groups: Tuple) -> str:
        """Count how many lights are on/off"""
        how_many, state = groups
        state_bool = state == 'on'
        
        all_states = self.lights.get_all_states() if hasattr(self.lights, 'get_all_states') else {}
        if not all_states:
            all_states = {room: self.lights.get_light_state(room) for room in self.room_mappings.keys()}
        
        count = sum(1 for is_on in all_states.values() if is_on == state_bool)
        total = len(all_states)
        
        return f"📊 {count} out of {total} lights are {state}."

    def control_all_lights(self, groups: Tuple) -> str:
        """Control all lights at once"""
        scope, state = groups
        state_bool = state == 'on'
        
        success = self.lights.set_light('all', state_bool)
        if success:
            action = "on" if state_bool else "off"
            return f"🏠 {self._random_affirmation()} Turned {action} all lights in the house!"
        else:
            return "❌ Sorry, I couldn't control all lights. There might be a hardware issue."

    def control_all_lights_direct(self, groups: Tuple) -> str:
        """Control all lights with direct command"""
        action, state, scope = groups
        state_bool = state == 'on'
        
        success = self.lights.set_light('all', state_bool)
        if success:
            action_text = "on" if state_bool else "off"
            return f"🏠 Turned {action_text} all lights!"
        else:
            return "❌ Sorry, I couldn't control all lights."

    def control_all_lights_short(self, groups: Tuple) -> str:
        """Short command for all lights"""
        lights, state = groups
        state_bool = state == 'on'
        
        success = self.lights.set_light('all', state_bool)
        if success:
            action_text = "on" if state_bool else "off"
            return f"🏠 Lights {action_text}!"
        else:
            return "❌ Couldn't control lights."

    def good_night_mode(self, groups: Tuple) -> str:
        """Turn off all lights for bedtime"""
        success = self.lights.set_light('all', False)
        if success:
            return "🌙 Good night! All lights are turned off. Sleep well! 💤"
        else:
            return "❌ Couldn't set good night mode."

    def welcome_home_mode(self, groups: Tuple) -> str:
        """Turn on hall and kitchen lights when arriving home"""
        self.lights.set_light('hall', True)
        self.lights.set_light('kitchen', True)
        return "👋 Welcome home! I've turned on the hall and kitchen lights for you. 🏠"

    def movie_mode(self, groups: Tuple) -> str:
        """Dim lights for movie watching"""
        self.lights.set_light('hall', True)  # Keep hall light on for safety
        self.lights.set_light('bedroom', False)
        self.lights.set_light('kitchen', False)
        self.lights.set_light('bathroom', False)
        return "🎬 Movie mode activated! Dimmed the lights for optimal viewing. Enjoy your film! 🍿"

    def party_mode(self, groups: Tuple) -> str:
        """Special lighting for parties"""
        # This would be enhanced with RGB lights in a real implementation
        self.lights.set_light('all', True)
        return "🎉 Party mode activated! All lights are on. Let's celebrate! 🥳"

    def show_help(self, groups: Tuple) -> str:
        """Show help message"""
        return """
🤖 **Smart Home Light Control Commands:**

**Basic Control:**
• "turn on [room] light" / "turn off [room] light"
• "switch on kitchen light" / "switch off hall light"
• "toggle bedroom light"
• "set bathroom light on/off"

**All Lights:**
• "all lights on/off"
• "turn on all lights" 
• "lights on/off"
• "everything on/off"

**Status & Info:**
• "is bedroom light on?"
• "status of kitchen light"
• "which lights are on?"
• "how many lights are off?"
• "list rooms"

**Special Modes:**
• "good night" - Turns off all lights
• "welcome home" - Turns on entry lights
• "movie time" - Dims lights for movies
• "party mode" - All lights on

**Available Rooms:** hall, bedroom, kitchen, bathroom

💡 **Tip:** I understand natural language - try speaking normally!
"""

    def list_rooms(self, groups: Tuple) -> str:
        """List available rooms"""
        rooms = ", ".join(self.room_mappings.keys())
        return f"🏠 Available rooms: {rooms}"

    def thank_you(self, groups: Tuple) -> str:
        """Respond to thanks"""
        return "😊 You're welcome! Happy to help with your smart home."

    def greeting(self, groups: Tuple) -> str:
        """Respond to greetings"""
        return "👋 Hello! I'm your smart home assistant. I can control your lights and more. How can I help you today?"

    def goodbye(self, groups: Tuple) -> str:
        """Respond to goodbye"""
        return "👋 Goodbye! Have a great day! 😊"

    def _identify_room(self, room_text: str) -> Optional[str]:
        """Identify room from text with fuzzy matching"""
        room_text = room_text.strip().lower()
        
        # Check for "all" first
        if any(word in room_text for word in self.all_rooms):
            return 'all'
        
        # Check exact matches and synonyms
        for room, keywords in self.room_mappings.items():
            if room_text == room or any(keyword == room_text for keyword in keywords):
                return room
            # Check if any keyword is contained in the room_text
            if any(keyword in room_text for keyword in keywords):
                return room
        
        return None

    def _random_affirmation(self) -> str:
        """Return random affirmation to make responses more natural"""
        affirmations = [
            "Done!", "Okay!", "Sure!", "Got it!", "No problem!", 
            "Absolutely!", "Certainly!", "You got it!", "Alright!"
        ]
        import random
        return random.choice(affirmations)

    def get_conversation_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.conversation_history.copy()

    def cleanup(self):
        """Cleanup resources"""
        if hasattr(self.lights, 'cleanup'):
            self.lights.cleanup()


def main():
    print("=== 🤖 Enhanced Smart Home Chatbot ===")
    print("Initializing...")
    
    # Create lights controller
    lights = RoomLightsController() if HARDWARE_AVAILABLE else None
    
    chatbot = LightChatbot(lights)
    
    try:
        while True:
            try:
                user_input = input("\n🎤 You: ").strip()
                if not user_input:
                    continue
                    
                if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                    print("🤖 Chatbot: Goodbye! 👋")
                    break
                
                response = chatbot.process_message(user_input)
                print(f"🤖 Chatbot: {response}")
                
            except KeyboardInterrupt:
                print("\n\n🤖 Chatbot: Goodbye! 👋")
                break
            except Exception as e:
                print(f"🤖 Chatbot: Sorry, I encountered an error: {str(e)}")
                
    except KeyboardInterrupt:
        print("\n\n🤖 Chatbot: Goodbye! 👋")
    finally:
        chatbot.cleanup()


if __name__ == "__main__":
    main()