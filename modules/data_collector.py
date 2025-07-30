import requests
from dotenv import load_dotenv
import os

load_dotenv()
BASE_URL = os.getenv('HOST', 'https://api.bitget.com')
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')
PRODUCT = os.getenv('PRODUCT', 'USDT-FUTURES')

def get_last_price(symbol=None):
    """
    Retorna o último preço de mercado para o símbolo.
    """
    sym = symbol or SYMBOL
    path = "/api/v2/mix/market/ticker"
    params = {
        "symbol": sym,
        "marginCoin": "USDT",
        "productType": PRODUCT
    }

    try:
        resp = requests.get(BASE_URL + path, params=params, timeout=5)
        data = resp.json()
        price = data.get('data', [{}])[0].get('lastPr') or data.get('data', [{}])[0].get('last')
        return float(price)
    except Exception as e:
        print(f"[ERRO] get_last_price falhou: {e}")
        return None
