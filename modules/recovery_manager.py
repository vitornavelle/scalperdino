# File: modules/recovery_manager.py
import os
import json

# Aponta para data/state.json
STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'position_open': False,
        'entry_price': None,
        'sl_order_id': None,
        'tp_order_ids': [],
        'be1': False,
        'be2': False,
        'paused': False
    }

def update_state(state):
    # Garante que a pasta existe
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def sync_state_with_bitget(state):
    if not state.get('tp_order_ids') and not state.get('sl_order_id'):
        state['position_open'] = False
        update_state(state)
    return state
