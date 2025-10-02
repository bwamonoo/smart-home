#!/usr/bin/env python3
"""
LightChatbot (Rhasspy + Snips-friendly)

Delegates NLU to Rhasspy when available; falls back to a lightweight local
parser. Integrates with the project's RoomLightsController.

Place this file at chatbot/light_chatbot.py (overwrite).
"""

import os
import sys
import json
import difflib
import traceback
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

# Add project root to path (so imports work when run as module)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except Exception:
    requests = None

# Try to import the hardware controller if available
try:
    from hardware.room_lights import RoomLightsController
    HARDWARE_AVAILABLE = True
except Exception:
    HARDWARE_AVAILABLE = False

# Try to read RHASSPY_URL from config.settings or environment
RHASSPY_URL = None
try:
    from config import settings as project_settings
    RHASSPY_URL = getattr(project_settings, 'RHASSPY_URL', None)
except Exception:
    project_settings = None

# Environment variable override
RHASSPY_URL = os.environ.get('RHASSPY_URL', RHASSPY_URL)

# Default Rhasspy endpoint path for text-to-intent
RHASSPY_TEXT2INTENT_PATH = '/api/text-to-intent'

# Default room synonyms (used for fuzzy mapping only)
DEFAULT_ROOM_MAPPINGS = {
    'hall': ['hall', 'living room', 'living', 'lounge', 'sitting room', 'main room'],
    'bedroom': ['bedroom', 'bed room', 'master bedroom', 'sleeping room', 'room'],
    'kitchen': ['kitchen', 'cook', 'cooking area', 'cooking'],
    'bathroom': ['bathroom', 'bath room', 'restroom', 'toilet', 'washroom', 'wc'],
}


class LightChatbot:
    """Light chatbot that delegates NLU to Rhasspy (Snips) when available."""

    def __init__(self, lights_controller: Optional[Any] = None, rhasspy_url: Optional[str] = None):
        # Use provided lights controller, or create simple simulator
        self.lights = lights_controller or self._create_simulator()

        # Conversation history (keeps last 200 entries)
        self.conversation_history: List[Dict[str, Any]] = []

        # Room mapping (canonical -> synonyms). If lights controller exposes
        # available rooms, use that to narrow candidates.
        self.room_mappings = DEFAULT_ROOM_MAPPINGS.copy()
        self._refresh_rooms_from_controller()

        # Rhasspy URL resolution
        self.rhasspy_url = rhasspy_url or RHASSPY_URL
        if self.rhasspy_url and self.rhasspy_url.endswith('/'):
            self.rhasspy_url = self.rhasspy_url[:-1]

        # Decide whether we have requests available
        self._have_requests = requests is not None

        # Initialization message
        mode = "Hardware" if HARDWARE_AVAILABLE else "Simulation"
        nlu_mode = f"Rhasspy @ {self.rhasspy_url}" if self.rhasspy_url else "Local fallback (no NLU)"
        print(f"🤖 LightChatbot initialized ({mode} mode). NLU: {nlu_mode}")

    def _refresh_rooms_from_controller(self):
        """If controller exposes leds or states, derive canonical room names."""
        try:
            if hasattr(self.lights, 'leds') and isinstance(self.lights.leds, dict):
                controller_rooms = list(self.lights.leds.keys())
            elif hasattr(self.lights, 'states') and isinstance(self.lights.states, dict):
                controller_rooms = list(self.lights.states.keys())
            elif hasattr(self.lights, 'get_all_states'):
                controller_rooms = list(self.lights.get_all_states().keys())
            else:
                controller_rooms = []

            for room in controller_rooms:
                room = room.lower()
                if room not in self.room_mappings:
                    self.room_mappings[room] = [room]
        except Exception:
            pass

    def _create_simulator(self):
        class LightSimulator:
            def __init__(self):
                self.states = {r: False for r in ['hall', 'bedroom', 'kitchen', 'bathroom']}

            def set_light(self, room, state, source='system'):
                if room == 'all':
                    for k in self.states:
                        self.states[k] = state
                    return True
                if room in self.states:
                    self.states[room] = state
                    return True
                return False

            def toggle_light(self, room, source='system'):
                if room in self.states:
                    self.states[room] = not self.states[room]
                    return self.states[room]
                return False

            def get_light_state(self, room):
                return self.states.get(room, False)

            def get_all_states(self):
                return self.states.copy()

            def cleanup(self):
                pass

        return LightSimulator()

    # ---------------- Public API ----------------
    def process_message(self, message: str) -> str:
        """Main entrypoint: takes plain text and returns a user-facing response."""
        if not message or not message.strip():
            return "Please type a command, for example: 'turn on kitchen light'."

        user_text = message.strip()
        self._append_history(user_text, None)

        # ------------------ HOTFIX: handle "all" commands locally ------------------
        # Prevent 'all' -> 'hall' confusion by short-circuiting 'all' requests.
        lower = user_text.lower()
        if re.search(r'\b(all|every|entire|whole|everything)\b', lower):
            exc_room = None
            m = re.search(r'except (the )?([a-zA-Z ]+)', lower)
            if m:
                exc_room_text = m.group(2).strip()
                exc_room = self._map_room(exc_room_text)

            # detect state word (on/off/toggle) from text (typo tolerant)
            state = self._extract_state_from_text(lower)
            if not state:
                # If Rhasspy is configured, let it resolve ambiguous all-commands.
                if not (self.rhasspy_url and self._have_requests):
                    return "Please tell me 'on' or 'off' for controlling all lights."
            else:
                state_bool = state == 'on'
                if exc_room:
                    success = True
                    # set all except the exception
                    for r in self._get_room_keys():
                        if r == exc_room:
                            continue
                        ok = self._set_room_state(r, state_bool)
                        success = success and bool(ok)
                    resp = f"Turned {'on' if state_bool else 'off'} all lights except the {exc_room}." if success else "Failed to control some lights."
                    self._update_last_history_response(resp)
                    return resp
                else:
                    ok = self._set_all_lights(state_bool)
                    resp = self._format_all_response(ok, state_bool)
                    self._update_last_history_response(resp)
                    return resp
        # ---------------- end HOTFIX ------------------------------------------------

        # Try NLU if configured
        if self.rhasspy_url and self._have_requests:
            try:
                intent_json = self._text_to_intent_rhasspy(user_text)
                if intent_json:
                    response = self._handle_intent_json(intent_json)
                    self._update_last_history_response(response)
                    return response
            except Exception:
                traceback.print_exc()

        # Fallback local parsing
        try:
            response = self._local_fallback_parse(user_text)
            self._update_last_history_response(response)
            return response
        except Exception:
            traceback.print_exc()
            response = "Sorry — I couldn't understand that. Try: 'turn on kitchen light'"
            self._update_last_history_response(response)
            return response

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        return list(self.conversation_history)

    def cleanup(self):
        try:
            if hasattr(self.lights, 'cleanup'):
                self.lights.cleanup()
        except Exception:
            pass

    # ---------------- Helpers: history ----------------
    def _append_history(self, user_text: str, response: Optional[str]):
        self.conversation_history.append({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'user': user_text,
            'response': response,
        })
        self.conversation_history = self.conversation_history[-200:]

    def _update_last_history_response(self, response: str):
        if self.conversation_history:
            self.conversation_history[-1]['response'] = response

    # ---------------- Helpers: Rhasspy integration ----------------
    def _text_to_intent_rhasspy(self, text: str) -> Optional[Dict[str, Any]]:
        """Post text to Rhasspy and return the parsed intent JSON (or None)."""
        url = f"{self.rhasspy_url}{RHASSPY_TEXT2INTENT_PATH}"
        resp = requests.post(url, json={"text": text}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # DEBUG: print Rhasspy response so we can inspect slots/format
        try:
            print("RHASSPY JSON ->", json.dumps(data, ensure_ascii=False))
        except Exception:
            print("RHASSPY JSON ->", data)
        if not data:
            return None
        return data

    def _handle_intent_json(self, intent_json: Dict[str, Any]) -> str:
        """Normalize various intent JSON shapes and perform the action."""
        # DEBUG: quick dump for troubleshooting
        try:
            dbg_intent = intent_json.get('intent') or intent_json.get('intent_name') or intent_json.get('name')
            dbg_text = intent_json.get('text') or intent_json.get('raw_text') or intent_json.get('rawText') or ''
            print("DBG _handle_intent_json: intent:", dbg_intent, "text:", dbg_text)
        except Exception:
            pass

        # normalize intent name and slots
        intent_name = None
        slots = {}

        if 'intent' in intent_json:
            intent = intent_json.get('intent')
            if isinstance(intent, dict):
                intent_name = intent.get('name') or intent.get('intentName')
            else:
                intent_name = str(intent)
            raw_slots = intent_json.get('slots') or []
            slots = self._normalize_slots_list(raw_slots)

        elif 'intent_name' in intent_json or 'intentName' in intent_json:
            intent_name = intent_json.get('intent_name') or intent_json.get('intentName')
            raw_slots = intent_json.get('slots') or []
            slots = self._normalize_slots_list(raw_slots)

        else:
            intent_name = intent_json.get('intent') or intent_json.get('name') or intent_json.get('intentName')
            raw_slots = intent_json.get('slots') or {}
            if isinstance(raw_slots, dict):
                slots = raw_slots
            else:
                slots = self._normalize_slots_list(raw_slots)

        intent_name = (intent_name or '').lower()

        # robust raw_text extraction
        raw_text = ''
        if isinstance(intent_json.get('text'), str):
            raw_text = intent_json.get('text')
        elif isinstance(intent_json.get('raw_text'), str):
            raw_text = intent_json.get('raw_text')
        else:
            raw_text = str(intent_json.get('text') or intent_json.get('raw_text') or '')
        raw_text = raw_text.lower().strip()

        # determine state from slots OR from raw_text
        state_candidate = self._pick_slot_value(slots, ['state', 'switch', 'power', 'action'])
        if not state_candidate:
            state_candidate = self._extract_state_from_text(raw_text)

        # room candidate from slots if present
        room_candidate = self._pick_slot_value(slots, ['room', 'location', 'area', 'place'])
        if room_candidate:
            room_candidate = str(room_candidate).strip().lower()

        # prefer 'all' if raw_text contains it as a whole word (avoid 'hall')
        if not room_candidate:
            if re.search(r'\b(all|every|entire|everything|whole)\b', raw_text):
                room_candidate = 'all'

        # fallback: find a known room inside raw_text (whole words)
        if not room_candidate:
            for canonical, synonyms in self.room_mappings.items():
                if re.search(r'\b' + re.escape(canonical) + r'\b', raw_text):
                    room_candidate = canonical
                    break
                for syn in synonyms:
                    if re.search(r'\b' + re.escape(syn) + r'\b', raw_text):
                        room_candidate = canonical
                        break
                if room_candidate:
                    break

        canonical_room = self._map_room(room_candidate)

        # detect "except <room>"
        except_room = None
        if 'except' in raw_text:
            try:
                after = raw_text.split('except', 1)[1]
                for canonical, syns in self.room_mappings.items():
                    if re.search(r'\b' + re.escape(canonical) + r'\b', after):
                        except_room = canonical
                        break
                    for s in syns:
                        if re.search(r'\b' + re.escape(s) + r'\b', after):
                            except_room = canonical
                            break
                    if except_room:
                        break
            except Exception:
                except_room = None

        # HANDLE "all" (with optional except)
        if (canonical_room == 'all') or (room_candidate and str(room_candidate).lower() in ['all', 'every', 'entire', 'everything', 'whole']):
            if except_room:
                if state_candidate in ['on', 'off']:
                    state_bool = state_candidate == 'on'
                    success = True
                    for r in self._get_room_keys():
                        if r == except_room:
                            continue
                        ok = self._set_room_state(r, state_bool)
                        success = success and bool(ok)
                    return f"Turned {'on' if state_bool else 'off'} all lights except the {except_room}." if success else "Failed to control some lights."
                else:
                    return "Please tell me 'on' or 'off' when using 'except'."

            if state_candidate in ['on', 'off']:
                state_bool = state_candidate == 'on'
                success = self._set_all_lights(state_bool)
                return self._format_all_response(success, state_bool)
            else:
                return "Please tell me 'on' or 'off' when controlling all lights."

        # If intent is a status/query without any room, return overall status
        if (not canonical_room) and any(k in intent_name for k in ['status', 'check', 'query', 'which', 'what', 'are', 'is']):
            return self._get_overall_status()

        if not canonical_room:
            available = ', '.join(sorted(self.room_mappings.keys()))
            return f"I didn't recognize the room '{room_candidate or ''}'. Available rooms: {available}."

        # Now perform the requested action for a specific room
        if state_candidate in ['on', 'off']:
            state_bool = state_candidate == 'on'
            ok = self._set_room_state(canonical_room, state_bool)
            if ok:
                return f"{'Turned on' if state_bool else 'Turned off'} the {canonical_room} light."
            else:
                return f"Couldn't set the {canonical_room} light."

        if state_candidate == 'toggle' or 'toggle' in intent_name:
            new_state = self._toggle_room(canonical_room)
            if isinstance(new_state, bool):
                return f"Toggled the {canonical_room} light {'on' if new_state else 'off'}."
            else:
                return f"Couldn't toggle the {canonical_room} light."

        if any(w in intent_name for w in ['status', 'check', 'is', 'are']):
            return self._room_status_text(canonical_room)

        return "Sorry — I understood the intent but I'm not sure what action to take."

    def _normalize_slots_list(self, raw_slots) -> Dict[str, Any]:
        """Convert various slot list shapes into a simple dict: {slot_name: value}."""
        slots = {}
        try:
            if isinstance(raw_slots, dict):
                return raw_slots
            for s in raw_slots:
                if isinstance(s, dict):
                    name = s.get('slot_name') or s.get('name') or s.get('entity')
                    val = None
                    if 'value' in s:
                        v = s.get('value')
                        if isinstance(v, dict):
                            val = v.get('value') or v.get('raw') or v.get('kind')
                        else:
                            val = v
                    else:
                        val = s.get('rawValue') or s.get('raw') or s.get('text')
                    if name and val is not None:
                        slots[name] = str(val)
        except Exception:
            traceback.print_exc()
        return slots

    def _extract_state_from_text(self, raw_text: str) -> Optional[str]:
        """Detect on/off/toggle from free text (tiny autocorrect for short typos)."""
        if not raw_text:
            return None
        tokens = re.findall(r"[a-zA-Z]+", raw_text.lower())
        candidates = ['on', 'off', 'toggle']
        for t in tokens:
            if t in candidates:
                return t
        for t in tokens:
            m = difflib.get_close_matches(t, candidates, n=1, cutoff=0.6)
            if m:
                return m[0]
        return None

    def _pick_slot_value(self, slots: Dict[str, Any], candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in slots and slots[c]:
                return str(slots[c])
        for k, v in slots.items():
            if k.lower() in candidates and v:
                return str(v)
        return None

    # ---------------- Room mapping / fuzzy ----------------
    def _map_room(self, raw_room: Optional[str]) -> Optional[str]:
        """Return canonical room name if a close match is found, or 'all', or None."""
        if not raw_room:
            return None
        r = raw_room.strip().lower()
        if r in ['all', 'every', 'entire', 'everything', 'house']:
            return 'all'
        for canonical, synonyms in self.room_mappings.items():
            if r == canonical or r in synonyms:
                return canonical
        for canonical, synonyms in self.room_mappings.items():
            if any(syn in r for syn in synonyms):
                return canonical
        candidates = []
        for canonical, synonyms in self.room_mappings.items():
            candidates.append(canonical)
            candidates.extend(synonyms)
        match = difflib.get_close_matches(r, candidates, n=1, cutoff=0.6)
        if match:
            m = match[0]
            for canonical, synonyms in self.room_mappings.items():
                if m == canonical or m in synonyms:
                    return canonical
        return None

    # ---------------- Controller actions ----------------
    def _get_room_keys(self) -> List[str]:
        """Return the authoritative list of actual room keys to iterate."""
        if hasattr(self.lights, 'leds') and isinstance(self.lights.leds, dict):
            return list(self.lights.leds.keys())
        if hasattr(self.lights, 'get_all_states'):
            try:
                return list(self.lights.get_all_states().keys())
            except Exception:
                pass
        if hasattr(self.lights, 'states') and isinstance(self.lights.states, dict):
            return list(self.lights.states.keys())
        # fallback to mapping keys
        return list(self.room_mappings.keys())

    def _set_room_state(self, room: str, state: bool) -> bool:
        """Set one room; returns True on success."""
        try:
            # try preferred signature
            if hasattr(self.lights, 'set_light'):
                # Defensive: don't pass 'all' to controllers that don't expect it
                if room == 'all':
                    # call the all-lights handler instead
                    return self._set_all_lights(state)
                # ensure room is valid for controller if possible
                if hasattr(self.lights, 'leds') and room not in self.lights.leds:
                    # if controller doesn't know this room, fail gracefully
                    # (but still try to map via get_all_states)
                    if hasattr(self.lights, 'get_all_states'):
                        if room not in self.lights.get_all_states().keys():
                            return False
                # call set_light
                self.lights.set_light(room, state, source='chatbot')
                return True
            # fallback: toggle or set via simulator
            if hasattr(self.lights, 'toggle_light') and hasattr(self.lights, 'get_light_state'):
                current = self.lights.get_light_state(room)
                if current == state:
                    return True
                # if controller has direct set_light, we would have used it; attempt toggle
                if hasattr(self.lights, 'set_light'):
                    self.lights.set_light(room, state, source='chatbot')
                    return True
                else:
                    self.lights.toggle_light(room, source='chatbot')
                    return True
        except KeyError:
            return False
        except Exception:
            traceback.print_exc()
            return False

    def _toggle_room(self, room: str):
        try:
            if hasattr(self.lights, 'toggle_light'):
                return self.lights.toggle_light(room, source='chatbot')
            current = self.lights.get_light_state(room)
            ok = self._set_room_state(room, not current)
            if ok:
                return not current
            return None
        except Exception:
            traceback.print_exc()
            return None

    def _set_all_lights(self, state: bool) -> bool:
        """Try to set all lights using controller's efficient method if available."""
        try:
            # If controller has explicit all-lights helpers, use them
            if state:
                if hasattr(self.lights, 'all_lights_on'):
                    try:
                        self.lights.all_lights_on(source='chatbot')
                        return True
                    except TypeError:
                        # some implementations may not accept source kw
                        try:
                            self.lights.all_lights_on()
                            return True
                        except Exception:
                            pass
            else:
                if hasattr(self.lights, 'all_lights_off'):
                    try:
                        self.lights.all_lights_off(source='chatbot')
                        return True
                    except TypeError:
                        try:
                            self.lights.all_lights_off()
                            return True
                        except Exception:
                            pass

            # If no explicit helpers, iterate authoritative room keys
            room_keys = self._get_room_keys()
            success = True
            for r in room_keys:
                ok = self._set_room_state(r, state)
                success = success and bool(ok)
            return success
        except Exception:
            traceback.print_exc()
            return False

    # ---------------- Status helpers ----------------
    def _room_status_text(self, room: str) -> str:
        try:
            state = self.lights.get_light_state(room)
            return f"The {room} light is {'on' if state else 'off'}."
        except Exception:
            return f"I couldn't determine the state of {room}."

    def _get_overall_status(self) -> str:
        try:
            if hasattr(self.lights, 'get_all_states'):
                states = self.lights.get_all_states()
            else:
                states = {r: self.lights.get_light_state(r) for r in self.room_mappings.keys()}
            on_rooms = [r for r, s in states.items() if s]
            if not on_rooms:
                return "No lights are currently on."
            return f"Lights currently on: {', '.join(on_rooms)}."
        except Exception:
            traceback.print_exc()
            return "Couldn't determine overall status."

    def _format_all_response(self, success: bool, state_bool: bool) -> str:
        if success:
            return f"Turned {'on' if state_bool else 'off'} all lights."
        return "Failed to control all lights."

    # ---------------- Local fallback parser ----------------
    def _local_fallback_parse(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ['turn on', 'switch on', 'enable', 'on']):
            verb = 'on'
        elif any(w in t for w in ['turn off', 'switch off', 'disable', 'off']):
            verb = 'off'
        elif 'toggle' in t:
            verb = 'toggle'
        elif any(w in t for w in ['status', 'is', 'are', 'state']):
            verb = 'status'
        else:
            verb = None

        room_candidate = None
        for canonical, synonyms in self.room_mappings.items():
            if canonical in t or any(syn in t for syn in synonyms):
                room_candidate = canonical
                break

        if not room_candidate and 'all' in t:
            room_candidate = 'all'

        if not verb:
            return "I couldn't understand the command. Examples: 'turn on kitchen light'"

        if room_candidate == 'all':
            if verb in ['on', 'off']:
                ok = self._set_all_lights(verb == 'on')
                return self._format_all_response(ok, verb == 'on')
            return "Try 'turn on all lights' or 'turn off all lights'."

        if not room_candidate:
            available = ', '.join(sorted(self.room_mappings.keys()))
            return f"Couldn't find a room in your message. Available rooms: {available}."

        if verb == 'on':
            ok = self._set_room_state(room_candidate, True)
            return f"Turned on the {room_candidate} light." if ok else f"Couldn't turn on {room_candidate}."
        if verb == 'off':
            ok = self._set_room_state(room_candidate, False)
            return f"Turned off the {room_candidate} light." if ok else f"Couldn't turn off {room_candidate}."
        if verb == 'toggle':
            state = self._toggle_room(room_candidate)
            if isinstance(state, bool):
                return f"Toggled the {room_candidate} light {'on' if state else 'off'}."
            return f"Couldn't toggle {room_candidate}."

        if verb == 'status':
            return self._room_status_text(room_candidate)

        return "I couldn't understand the request."


# When run directly, act as a simple CLI using the controller if present
if __name__ == '__main__':
    print('Starting LightChatbot CLI...')
    lights = None
    try:
        if HARDWARE_AVAILABLE:
            lights = RoomLightsController()
    except Exception:
        pass

    bot = LightChatbot(lights)
    try:
        while True:
            msg = input('You: ').strip()
            if not msg:
                continue
            if msg.lower() in ['quit', 'exit', 'bye']:
                print('Bye!')
                break
            resp = bot.process_message(msg)
            print('Bot:', resp)
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        bot.cleanup()
