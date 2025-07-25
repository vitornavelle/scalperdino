# File: modules/data_collector.py
import requests
from dotenv import load_dotenv
import os

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

    # Requisição sem necessidade de autenticação para ticker público
    resp = requests.get(BASE_URL + path, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    # Extrai o campo 'data', que pode ser dict ou lista
    raw = data.get('data')
    if isinstance(raw, list) and raw:
        ticker = raw[0]
    else:
        ticker = raw or {}

    # Tenta extrair o preço: lastPr (por vezes presente), depois last, por fim close
    last_price = ticker.get('lastPr') or ticker.get('last') or ticker.get('close')
    if last_price is None:
        raise ValueError(f"Não foi possível extrair o preço do ticker: {data}")

    return float(last_price)
