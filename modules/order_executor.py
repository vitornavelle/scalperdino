import os
import json
import time
import requests
import hashlib
import hmac
import base64
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlencode
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PASSPHRASE = os.getenv("PASSPHRASE")
BASE_URL   = os.getenv("HOST", "https://api.bitget.com")

# Configura logger de P&L
plogger = logging.getLogger("positions")
plogger.setLevel(logging.INFO)
ph = RotatingFileHandler("logs/positions.log", maxBytes=5_000_000, backupCount=5)
ph.setFormatter(logging.Formatter("%(asctime)s - P&L: %(message)s"))
plogger.addHandler(ph)

# Carrega configurações de trading
with open("config/config.json") as f:
    cfg = json.load(f)

# Assina a requisição
def sign(ts: str, method: str, path: str, body: str = "") -> str:
    payload = f"{ts}{method.upper()}{path}{body}".encode()
    mac = hmac.new(API_SECRET.encode(), payload, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()

# Monta headers
def headers(method: str, path: str, params: dict = None, body_dict: dict = None):
    ts = str(int(time.time() * 1000))
    body, sign_path = "", path
    if method == "GET" and params:
        qs = urlencode(sorted(params.items()))
        sign_path = f"{path}?{qs}"
    if method == "POST" and body_dict:
        body = json.dumps(body_dict, separators=(",", ":"))
    hdrs = {
        "ACCESS-KEY":        API_KEY,
        "ACCESS-SIGN":       sign(ts, method, sign_path, body),
        "ACCESS-TIMESTAMP":  ts,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type":      "application/json"
    }
    return hdrs, body, sign_path

# Define hedge mode
def set_position_mode():
    path = "/api/v2/mix/account/set-position-mode"
    payload = {"productType": cfg["productType"], "posMode": "hedge_mode"}
    hdrs, body, _ = headers("POST", path, body_dict=payload)
    return requests.post(BASE_URL + path, headers=hdrs, data=body, timeout=10).json()

# Detalhes de uma ordem
def get_order_details(order_id: str):
    path = "/api/v2/mix/order/detail"
    params = {"symbol": cfg["symbol"], "orderId": order_id}
    hdrs, _, sp = headers("GET", path, params=params)
    return requests.get(BASE_URL + sp, headers=hdrs, timeout=10).json()

# Pega posição única
def get_single_position():
    path = "/api/v2/mix/position/single-position"
    params = {"symbol": cfg["symbol"], "marginCoin": "USDT", "productType": cfg["productType"]}
    hdrs, _, sp = headers("GET", path, params=params)
    ret = requests.get(BASE_URL + sp, headers=hdrs, timeout=10).json()
    data = ret.get("data")
    if isinstance(data, list) and data:
        return {"data": data[0]}
    return ret

# Coloca ordem de mercado, com fecho de oposta
def place_order(side: str, trade_side: str, size: float, hold_side: str):
    pos_ret = get_single_position()
    pos = pos_ret.get("data", {})
    opp_side = "short" if hold_side == "long" else "long"
    if trade_side == "open" and pos.get("holdSide") == opp_side:
        close_position_and_log(opp_side, size)

    path = "/api/v2/mix/order/place-order"
    action = f"{trade_side.lower()}_{hold_side}"
    payload = {
        "symbol":       cfg["symbol"],
        "productType":  cfg["productType"],
        "marginCoin":   "USDT",
        "marginMode":   "isolated",
        "orderType":    "market",
        "side":         action,
        "size":         str(size),
        "clientOid":    str(int(time.time() * 1000))
    }
    hdrs, body, _ = headers("POST", path, body_dict=payload)
    resp = requests.post(BASE_URL + path, headers=hdrs, data=body, timeout=10).json()

    data = resp.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    entry_price = float(data.get("avgPrice", data.get("openPriceAvg", 0)))
    resp["entry_price"] = entry_price
    return resp

# Fecha posição e loga PnL
def close_position_and_log(position: str, size: float):
    side_close = "sell" if position == "long" else "buy"
    resp = place_order(side_close, "close", size, position)
    data = resp.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    pnl = float(data.get("realizedPnl", data.get("achievedProfits", 0)))
    plogger.info(f"{pnl}")
    return resp

def place_tpsl_order(plan_type: str, trigger_price: float, size: float, side: str):
    path = "/api/v2/mix/order/place-tpsl-order"
    payload = {
        "symbol":      cfg["symbol"],
        "marginCoin":  "USDT",
        "productType": cfg["productType"],
        "planType":    plan_type,
        "triggerPrice": str(trigger_price),
        "size":         str(size),
        "side":         side.lower()
    }
    hdrs, body, _ = headers("POST", path, body_dict=payload)
    return requests.post(BASE_URL + path, headers=hdrs, data=body, timeout=10).json()

def cancel_plan(order_id: str, plan_type: str):
    path = "/api/v2/mix/order/cancel-plan-order"
    payload = {
        "symbol":      cfg["symbol"],
        "marginCoin":  "USDT",
        "productType": cfg["productType"],
        "orderId":     order_id,
        "planType":    plan_type
    }
    hdrs, body, _ = headers("POST", path, body_dict=payload)
    return requests.post(BASE_URL + path, headers=hdrs, data=body, timeout=10).json()

# Teste rápido (opcional, pode remover em produção)
if __name__ == "__main__":
    print("Mode:", set_position_mode())
    ord_r = place_order("buy", "open", float(cfg["orderSize"]), "long")
    print("Order Open:", ord_r)
    print("Entry price:", ord_r.get("entry_price"))
    print("Close & Log:", close_position_and_log("long", float(cfg["orderSize"])))
