<<<<<<< HEAD
# File: modules/data_collector.py
=======
>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
import requests
from dotenv import load_dotenv
import os

<<<<<<< HEAD
# Carrega variáveis de ambiente para conexão
load_dotenv()
BASE_URL = os.getenv('HOST', 'https://api.bitget.com')
SYMBOL   = os.getenv('SYMBOL', 'BTCUSDT')
PRODUCT  = os.getenv('PRODUCT', 'USDT-FUTURES')

def get_last_price(symbol=None):
    """
    Busca o último preço de mercado do símbolo na Bitget.
    Retorna um float referente ao último preço disponível.
    """
    sym  = symbol or SYMBOL
    path = "/api/v2/mix/market/ticker"
    params = {"symbol": sym, "marginCoin": "USDT", "productType": PRODUCT}

    resp = requests.get(BASE_URL + path, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    # Trata tanto lista quanto dict em data['data']
    raw = data.get('data')
    if isinstance(raw, list) and raw:
        ticker = raw[0]
    else:
        ticker = raw or {}

    # Extrai o preço: tenta lastPr, depois last, depois close
    last_price = ticker.get('lastPr') or ticker.get('last') or ticker.get('close')
    if last_price is None:
        raise ValueError(f"Não foi possível extrair o preço do ticker: {data}")

    return float(last_price)
=======
load_dotenv()
BASE_URL = os.getenv('HOST', 'https://api.bitget.com')
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')
PRODUCT = os.getenv('PRODUCT', 'USDT-FUTURES')


def get_last_price(symbol=None):
    """Retorna o último preço de mercado do símbolo."""
    sym = symbol or SYMBOL
    path = "/api/v2/mix/market/ticker"
    params = {"symbol": sym, "marginCoin": "USDT", "productType": PRODUCT}
    resp = requests.get(BASE_URL + path, params=params, timeout=5)
    data = resp.json()
    # Extrai campo lastPr ou last
    last = data.get('data', [{}])[0].get('lastPr') or data.get('data', [{}])[0].get('last')
    return float(last)
>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
