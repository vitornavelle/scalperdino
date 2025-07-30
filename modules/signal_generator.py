import json
import numpy as np

def ema(values, period):
    """Calcula a média móvel exponencial (EMA)."""
    ema_vals = []
    k = 2 / (period + 1)
    for i, price in enumerate(values):
        if i == 0:
            ema_vals.append(price)
        else:
            ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return ema_vals

def rsi(values, period):
    """Calcula o RSI (Índice de Força Relativa)."""
    deltas = np.diff(values)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi_vals = [100 - 100 / (1 + rs)]

    for delta in deltas[period:]:
        gain = max(delta, 0)
        loss = max(-delta, 0)
        up = (up * (period - 1) + gain) / period
        down = (down * (period - 1) + loss) / period
        rs = up / down if down != 0 else 0
        rsi_vals.append(100 - 100 / (1 + rs))

    return [None] * period + rsi_vals

def load_candles(path="data/candles.json"):
    """Carrega candles e retorna lista de preços de fechamento."""
    with open(path) as f:
        data = json.load(f)
    closes = [float(c[4]) for c in data]
    return closes

def generate_signal():
    """Gera sinal com base em cruzamento de EMA e limite de RSI."""
    with open("config/config.json") as f:
        cfg = json.load(f)

    closes = load_candles()
    if len(closes) < max(cfg["emaShort"], cfg["emaLong"], cfg["rsiPeriod"]) + 2:
        return {"signal": None, "emaShort": None, "emaLong": None, "rsi": None}

    ema_short = ema(closes, cfg["emaShort"])
    ema_long  = ema(closes, cfg["emaLong"])
    rsi_vals  = rsi(closes, cfg["rsiPeriod"])

    last_ema_short = ema_short[-1]
    last_ema_long  = ema_long[-1]
    last_rsi       = rsi_vals[-1]

    signal = None
    if ema_short[-2] <= ema_long[-2] and last_ema_short > last_ema_long and last_rsi < cfg["rsiBuyThreshold"]:
        signal = "BUY"
    elif ema_short[-2] >= ema_long[-2] and last_ema_short < last_ema_long and last_rsi > cfg["rsiSellThreshold"]:
        signal = "SELL"

    return {
        "signal": signal,
        "emaShort": last_ema_short,
        "emaLong": last_ema_long,
        "rsi": last_rsi
    }

if __name__ == "__main__":
    sig = generate_signal()
    print(f"Signal: {sig['signal']}, EMA Short: {sig['emaShort']}, EMA Long: {sig['emaLong']}, RSI: {sig['rsi']}")
