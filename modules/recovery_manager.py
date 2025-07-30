import os
import json
import logging
from modules.order_executor import has_open_position

STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'state.json')

def load_state():
    """Carrega o estado do robô do arquivo JSON, com valores padrão."""
    try:
        with open(STATE_FILE) as f:
            raw = json.load(f)
    except Exception:
        raw = {}

    return {
        'position_open':     raw.get('position_open', False),
        'entry_price':       raw.get('entry_price'),
        'current_sl':        raw.get('current_sl'),
        'tp_order_ids':      raw.get('tp_order_ids', []),
        'be1':               raw.get('be1', False),
        'be2':               raw.get('be2', False),
        'paused':            raw.get('paused', False),
        'reversal_count':    raw.get('reversal_count', 0),
        'side':              raw.get('side')  # 'buy' ou 'sell'
    }

def update_state(state):
    """Salva o estado atual no arquivo JSON."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)


def sync_state_with_bitget(state):
    """
    Sincroniza o estado local com a corretora: se não houver posição real, limpa o state.
    """
    try:
        symbol = os.getenv("SYMBOL") or state.get("symbol") or "BTCUSDT"
        if not has_open_position(symbol):
            logging.warning("⚠️ Estado local indica posição, mas corretora NÃO. Resetando state.")
            state.update({
                'position_open': False,
                'entry_price': None,
                'current_sl': None,
                'tp_order_ids': [],
                'be1': False,
                'be2': False,
                'reversal_count': 0,
                'side': None
            })
            update_state(state)
    except Exception as e:
        logging.error(f"[sync_state_with_bitget] Erro ao sincronizar estado: {e}")
    if not state.get('tp_order_ids') and not state.get('current_sl'):
        state.update({
            'position_open': False,
            'reversal_count': 0,
            'side': None,
            'current_sl': None
        })
        update_state(state)
    return state
