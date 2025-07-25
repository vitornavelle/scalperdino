import os
import json
import time
import requests
import hashlib
import hmac
import base64
from urllib.parse import urlencode
from dotenv import load_dotenv
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()
API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PASSPHRASE = os.getenv("PASSPHRASE")
BASE_URL   = os.getenv("HOST", "https://api.bitget.com")

# Carrega configurações de trading
with open("config/config.json") as f:
    config = json.load(f)

def sign(ts: str, method: str, path: str, body: str = "") -> str:
    payload = f"{ts}{method.upper()}{path}{body}".encode()
    mac = hmac.new(API_SECRET.encode(), payload, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()

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

def fetch_candles():
    """Busca as últimas candles e grava em data/candles.json"""
    path = "/api/v2/mix/market/candles"
    params = {
        "symbol":      config["symbol"],
        "marginCoin":  "USDT",
        "productType": config["productType"],
        "granularity": int(config["timeframe"].replace("m","")) * 60,
        "limit":       config["candles"]
    }
    hdrs, _, sp = headers("GET", path, params=params)
    resp = requests.get(BASE_URL + sp, headers=hdrs, timeout=10).json()
    candles = resp.get("data", [])
    # Salva temporariamente
    with open("data/candles.json", "w") as f:
        json.dump(candles, f)
    print(datetime.utcnow().strftime("[%H:%M:%S]"), f"Fetched {len(candles)} candles.")
    return candles

if __name__ == "__main__":
    fetch_candles()
