import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = "https://api.bitget.com"
SYMBOL = "BTCUSDT"
PRODUCT = "USDT-FUTURES"

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PASSPHRASE = os.getenv("PASSPHRASE")

def headers(method, path):
    import time, hmac, hashlib, base64
    ts = str(int(time.time() * 1000))
    sign_str = ts + method + path
    signature = base64.b64encode(hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).digest()).decode()
    return {
        'ACCESS-KEY': API_KEY,
        'ACCESS-SIGN': signature,
        'ACCESS-TIMESTAMP': ts,
        'ACCESS-PASSPHRASE': PASSPHRASE,
        'Content-Type': 'application/json'
    }

def get_position():
    path = f"/api/v2/mix/position/single-position?symbol={SYMBOL}&marginCoin=USDT&productType={PRODUCT}"
    resp = requests.get(BASE_URL + path, headers=headers('GET', path)).json()
    print(resp)

if __name__ == "__main__":
    get_position()
