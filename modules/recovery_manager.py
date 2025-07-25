# File: modules/recovery_manager.py
import os
import json

# Aponta para data/state.json
STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'state.json')

def load_state():
    """
    Carrega o estado do robô do arquivo JSON, garantindo chaves padrão
    para todos os parâmetros, incluindo reversão, lado atual e SL manual.
    """
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            raw = json.load(f)
    else:
        raw = {}

    return {
        'position_open':  raw.get('position_open', False),
        'entry_price':    raw.get('entry_price'),
        'current_sl':     raw.get('current_sl'),
        'tp_order_ids':   raw.get('tp_order_ids', []),
        'be1':            raw.get('be1', False),
        'be2':            raw.get('be2', False),
        'paused':         raw.get('paused', False),
        'reversal_count': raw.get('reversal_count', 0),
        'side':           raw.get('side')  # 'buy' ou 'sell'
    }

def update_state(state):
    """
    Persiste o estado completo (incluindo reversão, side e SL manual) no arquivo JSON.
    """
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def sync_state_with_bitget(state):
    """
    Se não houver ordens de TP nem SL manual ativo, marca posição como fechada
    e zera contador de reversão, side e SL.
    """
    if not state.get('tp_order_ids') and not state.get('current_sl'):
        state['position_open'] = False
        state['reversal_count'] = 0
        state['side'] = None
        state['current_sl'] = None
        update_state(state)
    return state
