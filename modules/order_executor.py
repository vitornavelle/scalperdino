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

def has_open_position(symbol):
    path = '/api/mix/v1/position/singlePosition'
    try:
        hdrs, _, _ = headers('GET', path, query_dict={"symbol": symbol})
        resp = requests.get(BASE_URL + path + f"?symbol={symbol}", headers=hdrs, timeout=5)
        if resp.status_code != 200:
            print(f"[ERRO] HTTP {resp.status_code} em has_open_position")
            return False
        data = resp.json()
        if data.get("code") != "00000":
            print(f"[ERRO] API Bitget: {data.get('msg')}")
            return False
        size = float(data.get('data', {}).get('size', 0))
        return size > 0
    except Exception as e:
        print(f"[ERRO] Falha em has_open_position: {e}")
        return False

def place_tpsl_order(entry_price, side, cfg, symbol):
    tick_size = cfg.get('tickSize', 1)
    portions = cfg['tpPortions']
    percents = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    order_size = cfg['orderSize']
    product_type = cfg.get('productType', 'USDT-FUTURES')
    margin_coin = cfg.get('marginCoin', 'USDT')
    hold = 'long' if side == 'buy' else 'short'
    ids = []

    for pct, vol in zip(percents, portions):
        raw = entry_price * (1 + pct) if side == 'buy' else entry_price * (1 - pct)
        tp = round(raw / tick_size) * tick_size
        oid = str(int(time.time() * 1000))
        payload = {
            'symbol': symbol,
            'productType': product_type,
            'marginCoin': margin_coin,
            'planType': 'profit_plan',
            'triggerType': 'mark_price',
            'orderId': '',  # não obrigatório
            'size': str(order_size * vol),
            'triggerPrice': str(tp),
            'executePrice': str(tp),
            'side': side,
            'holdSide': hold,
            'reduceOnly': True,
            'clientOid': oid
        }

        try:
            hdrs, body, _ = headers('POST', '/api/v2/mix/order/place-tpsl-order', body_dict=payload)
            resp = requests.post(BASE_URL + '/api/v2/mix/order/place-tpsl-order', headers=hdrs, data=body).json()
            if resp.get('code') != '00000':
                raise RuntimeError(resp.get('msg'))
            ids.append(resp['data']['orderId'])
        except Exception as e:
            print(f"[ERRO ao criar TP @ {tp}] {e}")

    return ids
