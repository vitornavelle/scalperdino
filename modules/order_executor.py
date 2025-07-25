import time
import requests
import json
import hmac
import hashlib
<<<<<<< HEAD
import base64
=======
>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
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

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
def sign(ts, method, path, body=""):
    mac = hmac.new(API_SECRET.encode(), (ts + method.upper() + path + body).encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
def headers(method, path, params=None, body_dict=None):
    ts = str(int(time.time() * 1000))
    body, sign_path = "", path
    if method == 'GET' and params:
        qs = urlencode(sorted(params.items()))
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

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
def set_position_mode():
    path = '/api/v2/mix/account/set-position-mode'
    payload = {'productType': PRODUCT, 'posMode': 'hedge_mode'}
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body).json()
    return resp

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
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

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
def place_tpsl_order(plan_type, trigger_price, size):
    path = '/api/v2/mix/order/place-tpsl-order'
    payload = {
        'symbol': SYMBOL,
        'productType': PRODUCT,
        'marginCoin': 'USDT',
        'planType': 'profit_plan' if plan_type == 'takeProfit' else 'loss_plan',
        'triggerType': 'mark_price',
<<<<<<< HEAD
        'orderId': None,
=======
        'orderId': None,  # preenchido pela execução anterior
>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
        'size': str(size),
        'triggerPrice': str(trigger_price),
        'executePrice': str(trigger_price),
        'side': 'buy' if plan_type == 'takeProfit' else 'sell',
        'holdSide': 'long' if plan_type == 'takeProfit' else 'short',
        'reduceOnly': True,
        'clientOid': str(int(time.time() * 1000))
    }
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body).json()
    if resp.get('code') != '00000':
        raise RuntimeError(resp.get('msg'))
    return resp.get('data', {})

<<<<<<< HEAD
=======

>>>>>>> 8d572722e9e800ad9697f1f8f779d8d48fa2fd49
def cancel_plan(order_id):
    path = '/api/v2/mix/order/cancel-plan-order'
    payload = {
        'symbol': SYMBOL,
        'productType': PRODUCT,
        'marginCoin': 'USDT',
        'orderId': order_id
    }
    hdrs, body, _ = headers('POST', path, body_dict=payload)
    requests.post(BASE_URL + path, headers=hdrs, data=body)
