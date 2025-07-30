
import time
import requests
import json
import hmac
import hashlib
import base64
from urllib.parse import urlencode
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
PASSPHRASE = os.getenv('PASSPHRASE')
BASE_URL = os.getenv('HOST', 'https://api.bitget.com')
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')
PRODUCT = os.getenv('PRODUCT', 'USDT-FUTURES')

def sign(ts, method, path, body=""):
    mac = hmac.new(API_SECRET.encode(), (ts + method.upper() + path + body).encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()

def headers(method, path, query_dict=None, body_dict=None):
    ts = str(int(time.time() * 1000))
    body, sign_path = "", path

    if method == 'GET' and query_dict:
        qs = urlencode(sorted(query_dict.items()))
        sign_path = f"{path}?{qs}"
    if method == 'POST' and body_dict is not None:
        body = json.dumps(body_dict, separators=(',', ':'))

    return {
        'ACCESS-KEY': API_KEY,
        'ACCESS-SIGN': sign(ts, method, sign_path, body),
        'ACCESS-TIMESTAMP': ts,
        'ACCESS-PASSPHRASE': PASSPHRASE,
        'Content-Type': 'application/json'
    }, body, sign_path

def set_position_mode():
    path = '/api/v2/mix/account/set-position-mode'
    payload = {'productType': PRODUCT, 'posMode': 'hedge_mode'}
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body).json()
    return resp

def place_order(side, trade_side, size, hold_side):
    path = '/api/v2/mix/order/place-order'
    payload = {
        'symbol': SYMBOL,
        'productType': PRODUCT,
        'marginCoin': 'USDT',
        'marginMode': 'isolated',
        'orderType': 'market',
        'side': side,
        'tradeSide': trade_side,
        'holdSide': hold_side,
        'size': str(size),
        'clientOid': str(int(time.time() * 1000))
    }
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body).json()
    if resp.get('code') != '00000':
        raise RuntimeError(resp.get('msg'))
    return resp.get('data', {})

def cancel_plan(plan_id):
    path = '/api/v2/mix/order/cancel-plan-order'
    payload = {
        'symbol': SYMBOL,
        'marginCoin': 'USDT',
        'productType': PRODUCT,
        'orderId': plan_id
    }
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    return requests.post(BASE_URL + path, headers=hdrs, data=body).json()

def has_open_position(symbol, product_type):
    path = '/api/v2/mix/position/single-position'
    query = {
        'symbol': symbol,
        'marginCoin': 'USDT',
        'productType': product_type
    }
    try:
        hdrs, _, _ = headers('GET', path, query_dict=query)
        resp = requests.get(BASE_URL + path, headers=hdrs, params=query, timeout=5)
        data = resp.json()
        if data.get("code") != "00000":
            print(f"[ERRO] Bitget: {data.get('msg')}")
            return False
        position_data = data.get("data", {})
        size = float(position_data.get("total", 0))
        return size > 0
    except Exception as e:
        print(f"[ERRO] Consulta posição falhou: {e}")
        return False

def place_tpsl_order(trigger_price, trigger_type, side, size, hold_side):
    path = "/api/v2/mix/order/place-plan-order"
    payload = {
        "symbol": SYMBOL,
        "marginCoin": "USDT",
        "productType": PRODUCT,
        "planType": "profit_loss",
        "triggerPrice": str(trigger_price),
        "triggerType": trigger_type,  # "market_price"
        "side": side,  # "buy" ou "sell"
        "size": str(size),
        "marginMode": "isolated",
        "holdSide": hold_side,
        "orderType": "market",
        "clientOid": str(int(time.time() * 1000))
    }
    hdrs, body, _ = headers("POST", path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body).json()
    if resp.get("code") != "00000":
        raise RuntimeError(f"[place_tpsl_order] {resp.get('msg')}")
    return resp.get("data", {}).get("orderId")
