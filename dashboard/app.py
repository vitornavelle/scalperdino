from flask import Flask, render_template, jsonify, request
import json
import os
import re
import requests
import time
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Inicializa Flask
app = Flask(
    __name__,
    static_folder='static',
    template_folder='templates'
)

# Caminhos dos arquivos
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
STATE_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data', 'state.json')
LOG_PATH    = os.path.join(os.path.dirname(__file__), '..', 'logs', 'bot.log')
PLOG_PATH   = os.path.join(os.path.dirname(__file__), '..', 'logs', 'positions.log')

# --- Bitget: Função para status REAL ---
load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
PASSPHRASE = os.getenv("PASSPHRASE")
BASE_URL = os.getenv("HOST", "https://api.bitget.com")
SYMBOL = "BTCUSDT"
PRODUCT = "USDT-FUTURES"

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

def get_real_position():
    path = f"/api/v2/mix/position/single-position?symbol={SYMBOL}&marginCoin=USDT&productType={PRODUCT}"
    resp = requests.get(BASE_URL + path, headers=bitget_headers("GET", path)).json()
    position = resp.get("data", [])
    if position and float(position[0].get("total", 0)) > 0:
        return f"Em posição: {position[0]['holdSide']}"
    else:
        return "Sem posição aberta"

# --- Rotas principais ---
@app.route('/')
def index():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    with open(STATE_PATH) as f:
        state = json.load(f)
    return render_template('index.html', config=cfg, state=state)

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        new_cfg = request.json
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_cfg, f, indent=2)
        return jsonify(success=True)
    else:
        with open(CONFIG_PATH) as f:
            return jsonify(json.load(f))

@app.route('/api/state')
def api_state():
    with open(STATE_PATH) as f:
        return jsonify(json.load(f))

@app.route('/api/logs')
def api_logs():
    with open(LOG_PATH) as f:
        lines = f.read().splitlines()[-100:]
    return jsonify(lines)

@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    with open(STATE_PATH) as f:
        state = json.load(f)
    paused = not state.get('paused', False)
    state['paused'] = paused
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)
    return jsonify(paused=paused)

@app.route('/api/metrics')
def api_metrics():
    now = datetime.utcnow()
    cuts = {
        "pnl_day": now - timedelta(days=1),
        "pnl_7d": now - timedelta(days=7),
        "pnl_15d": now - timedelta(days=15),
        "pnl_30d": now - timedelta(days=30),
    }
    sums = {k: 0.0 for k in cuts}
    pattern = re.compile(r"P&L[:=]\\s*([+-]?[0-9]*\\.?[0-9]+)")
    with open(PLOG_PATH) as f:
        for line in f:
            parts = line.split(" - ")
            try:
                ts = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S,%f")
            except:
                continue
            m = pattern.search(line)
            if not m:
                continue
            pnl = float(m.group(1))
            for key, cut in cuts.items():
                if ts >= cut:
                    sums[key] += pnl
    # arredonda para 8 casas
    return jsonify({k: round(v, 8) for k, v in sums.items()})

# --- ROTA PARA STATUS REAL NA BITGET ---
@app.route('/api/real_status')
def api_real_status():
    return jsonify({"status": get_real_position()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
