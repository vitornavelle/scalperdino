import json
import os

STATE_FILE = 'state.json'


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    # Estado inicial padrão
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
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)


def sync_state_with_bitget(state):
    # Exemplo: checa se ordens SL/TP foram executadas e atualiza state['position_open']
    # Esse método deve ser customizado conforme a API retornos
    # Placeholder: assume que, se não há tp_order_ids e sl_order_id, posição fechada
    if not state.get('tp_order_ids') and not state.get('sl_order_id'):
        state['position_open'] = False
        update_state(state)

    return state
