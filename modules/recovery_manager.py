import json
import os
import logging
from modules.order_executor import has_open_position

STATE_FILE = "state/state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "position_open": False,
            "entry_price": 0,
            "current_sl": 0,
            "tp_order_ids": [],
            "be1": False,
            "be2": False,
            "paused": False,
            "reversal_count": 0,
            "side": ""
        }
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def update_state(key, value):
    state = load_state()
    state[key] = value
    save_state(state)

def sync_state_with_bitget(state):
    try:
        # Corrigido: leitura via JSON
        with open("config/config.json") as f:
            cfg = json.load(f)
        symbol = cfg["symbol"]
        product_type = cfg["productType"]

        if state.get("position_open") and not has_open_position(symbol, product_type):
            logging.warning("⚠️ Estado local indica posição, mas corretora NÃO. Resetando state.")
            new_state = {
                "position_open": False,
                "entry_price": 0,
                "current_sl": 0,
                "tp_order_ids": [],
                "be1": False,
                "be2": False,
                "paused": False,
                "reversal_count": 0,
                "side": ""
            }
            save_state(new_state)
    except Exception as e:
        logging.error(f"[sync_state_with_bitget] Erro ao sincronizar estado: {e}")
