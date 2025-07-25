import os
import json
import logging
import requests
import time
import hmac
import hashlib
import base64
from dotenv import load_dotenv

# Caminho do arquivo de estado
STATE_FILE = "data/state.json"

# Configura logger para este módulo
logger = logging.getLogger("recovery_manager")
handler = logging.FileHandler("logs/bot.log")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def load_state():
    """
    Carrega e retorna o estado salvo em STATE_FILE.
    Se não existir, retorna dicionário vazio.
    """
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            logger.info("Estado carregado com sucesso.")
            return state
        except Exception as e:
            logger.error(f"Erro ao carregar estado: {e}")
            return {}
    else:
        logger.info("Nenhum estado anterior encontrado; iniciando estado vazio.")
        return {}

def save_state(state: dict):
    """
    Salva o dicionário `state` em STATE_FILE.
    """
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        logger.info("Estado salvo com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao salvar estado: {e}")

def update_state(**kwargs):
    """
    Atualiza chaves em STATE_FILE com os pares key=value passados.
    Exemplo: update_state(position=..., last_signal=...)
    """
    state = load_state()
    state.update(kwargs)
    save_state(state)
    return state

# -------------------- NOVO: Sincronização automática --------------------

def sync_state_with_bitget():
    """
    Sincroniza o campo 'position' do state.json com a posição real da Bitget.
    Se não houver posição na corretora, seta position=None.
    """
    load_dotenv()
    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")
    PASSPHRASE = os.getenv("PASSPHRASE")
    BASE_URL = os.getenv("HOST", "https://api.bitget.com")
    SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
    PRODUCT = os.getenv("PRODUCT", "USDT-FUTURES")

    def bitget_headers(method, path):
        ts = str(int(time.time() * 1000))
        sign_str = ts + method.upper() + path
        signature = base64.b64encode(hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).digest()).decode()
        return {
            'ACCESS-KEY': API_KEY,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': ts,
            'ACCESS-PASSPHRASE': PASSPHRASE,
            'Content-Type': 'application/json'
        }

    path = f"/api/v2/mix/position/single-position?symbol={SYMBOL}&marginCoin=USDT&productType={PRODUCT}"
    try:
        resp = requests.get(BASE_URL + path, headers=bitget_headers("GET", path), timeout=10).json()
        position = resp.get("data", [])
        state = load_state()
        # Se NÃO há posição real, zera o campo "position"
        if not position or float(position[0].get("total", 0)) == 0:
            if state.get("position") not in [None, "", "none"]:
                logger.info("[SYNC] Nenhuma posição real na Bitget, zerando position do state.json...")
                state["position"] = None
                save_state(state)
        else:
            # Se existe posição real, ajusta para o valor correto (long/short)
            real_side = position[0].get("holdSide")
            if state.get("position") != real_side:
                logger.info(f"[SYNC] Corrigindo state.json para posição real: {real_side}")
                state["position"] = real_side
                save_state(state)
    except Exception as e:
        logger.error(f"Erro ao sincronizar com Bitget: {e}")

# -------------------- FIM da Sincronização automática --------------------

if __name__ == "__main__":
    # Teste rápido do módulo
    st = load_state()
    print("Estado inicial:", st)
    st = update_state(testKey="OK", last_signal="BUY")
    print("Estado após update:", st)
    # Teste: sincroniza com Bitget ao rodar manualmente
    sync_state_with_bitget()
    st = load_state()
    print("Estado após sync com Bitget:", st)
