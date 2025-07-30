#!/usr/bin/env python3
import time
import json
import logging
from dotenv import load_dotenv
from modules.data_collector import get_last_price
from modules.order_executor import (
    set_position_mode,
    place_order,
    place_tpsl_order,
    cancel_plan,
    has_open_position
)
from modules.recovery_manager import load_state, save_state, sync_state_with_bitget
from modules.signal_generator import generate_signal

def wait_for_signal(signal_poll, timeout=3600):
    start = time.time()
    while time.time() - start < timeout:
        result = generate_signal()
        sig = result.get("signal")
        if sig in ("BUY", "SELL"):
            return sig, result
        time.sleep(signal_poll)
    return None, None

def open_position(cfg, sig, result, logger):
    side = 'buy' if sig == 'BUY' else 'sell'
    hold = 'long' if side == 'buy' else 'short'

    try:
        order = place_order(side=side, trade_side='open', size=cfg['orderSize'], hold_side=hold)
    except RuntimeError as e:
        logger.error(f"Erro ao abrir posição: {e}")
        return None, None

    filled = order.get('filledPrice') or get_last_price(cfg['symbol'])
    entry_price = float(filled)
    sl_raw = entry_price * (1 - cfg['slPct']) if side == 'buy' else entry_price * (1 + cfg['slPct'])
    sl_price = round(sl_raw / cfg.get('tickSize', 1)) * cfg.get('tickSize', 1)

    logger.info(
        f"Posição aberta: {side} @ {entry_price:.2f} | "
        f"SL: {sl_price:.2f} | EMA: {result['emaShort']:.2f}/{result['emaLong']:.2f} | RSI: {result['rsi']:.2f}"
    )
    return {
        "side": side,
        "hold": hold,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "order_id": order.get("orderId"),
    }, order

def handle_stop_loss(price, state, cfg, logger):
    close_side = 'sell' if state['side'] == 'buy' else 'buy'
    hold = 'long' if state['side'] == 'buy' else 'short'
    for tp in state.get('tp_order_ids', []):
        cancel_plan(tp)
    try:
        place_order(close_side, 'close', cfg['orderSize'], hold)
    except RuntimeError as e:
        logger.warning(f"Erro ao fechar posição no SL: {e}")
    state.update({
        'position_open': False,
        'entry_price': None,
        'current_sl': None,
        'tp_order_ids': [],
        'be1': False,
        'be2': False,
        'reversal_count': 0,
        'side': None
    })
    save_state(state)
    logger.info(f"Stop Loss atingido em {price:.2f}")

def monitor_position(cfg, state, logger):
    symbol = cfg['symbol']
    tp_price_pcts = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    be_offset1 = cfg['beOffsetPct1']
    be_offset2 = cfg['beOffsetPct2']
    tick_size = cfg.get('tickSize', 1)

    if not has_open_position(symbol, cfg['productType']):
        logger.warning("⚠️ Estado indica posição aberta, mas corretora NÃO. Resetando state.")
        state.update({
            'position_open': False,
            'entry_price': None,
            'current_sl': None,
            'tp_order_ids': [],
            'be1': False,
            'be2': False,
            'reversal_count': 0,
            'side': None
        })
        update_state(state)
        return

    while state.get('position_open') and not state.get('paused'):
        price = get_last_price(symbol)
        entry = state['entry_price']
        sl = state['current_sl']
        logger.info(f"[MONITOR] price={price} | SL={sl}")

        if state['side'] == 'buy' and price <= sl:
            handle_stop_loss(price, state, cfg, logger)
            break
        if state['side'] == 'sell' and price >= sl:
            handle_stop_loss(price, state, cfg, logger)
            break

        if not state['be1']:
            t1 = entry * (1 + tp_price_pcts[0]) if state['side'] == 'buy' else entry * (1 - tp_price_pcts[0])
            if (state['side'] == 'buy' and price >= t1) or (state['side'] == 'sell' and price <= t1):
                new_sl = entry * (1 + be_offset1) if state['side'] == 'buy' else entry * (1 - be_offset1)
                new_sl = round(new_sl / tick_size) * tick_size
                state['current_sl'] = new_sl
                state['be1'] = True
                update_state(state)
                logger.info(f"TP1 atingido → SL movido para {new_sl}")

        if state['be1'] and not state['be2']:
            t2 = entry * (1 + tp_price_pcts[1]) if state['side'] == 'buy' else entry * (1 - tp_price_pcts[1])
            if (state['side'] == 'buy' and price >= t2) or (state['side'] == 'sell' and price <= t2):
                new_sl = entry * (1 + be_offset2) if state['side'] == 'buy' else entry * (1 - be_offset2)
                new_sl = round(new_sl / tick_size) * tick_size
                state['current_sl'] = new_sl
                state['be2'] = True
                update_state(state)
                logger.info(f"TP2 atingido → SL movido para {new_sl}")

        time.sleep(cfg.get('pollIntervalSec', 1))

def main():
    load_dotenv()
    with open('config/config.json') as f:
        cfg = json.load(f)

    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    set_position_mode()

    while True:
        state = load_state()
        if state.get('paused'):
            logger.info("Robô pausado.")
            time.sleep(cfg.get('pollIntervalSec', 1))
            continue

        sync_state_with_bitget(state)

        if has_open_position(cfg['symbol'], cfg['productType']):
            if not state.get('position_open'):
                state['position_open'] = True
                update_state(state)
            time.sleep(cfg.get('pollIntervalSec', 1))
            continue

        logger.info("Esperando sinal...")
        sig, result = wait_for_signal(cfg.get('signalPollSec', 1))
        if not sig:
            logger.warning("Timeout: nenhum sinal válido encontrado.")
            continue

        pos_info, order = open_position(cfg, sig, result, logger)
        if not pos_info:
            continue

        state.update({
            'position_open': True,
            'entry_price': pos_info['entry_price'],
            'side': pos_info['side'],
            'current_sl': pos_info['sl_price'],
            'tp_order_ids': [],
            'be1': False,
            'be2': False,
            'reversal_count': 0
        })

        try:
            tp1 = pos_info['entry_price'] * (1 - cfg['tp1Pct']) if pos_info['side'] == 'sell' else pos_info['entry_price'] * (1 + cfg['tp1Pct'])
            tp2 = pos_info['entry_price'] * (1 - cfg['tp2Pct']) if pos_info['side'] == 'sell' else pos_info['entry_price'] * (1 + cfg['tp2Pct'])
            tp3 = pos_info['entry_price'] * (1 - cfg['tp3Pct']) if pos_info['side'] == 'sell' else pos_info['entry_price'] * (1 + cfg['tp3Pct'])

            tp_orders = []
            for tp_price in [tp1, tp2, tp3]:
                order_id = place_tpsl_order(
                    trigger_price=round(tp_price, 2),
                    trigger_type="market_price",
                    side='buy' if pos_info['side'] == 'sell' else 'sell',
                    size=cfg['orderSize'],
                    hold_side=pos_info['hold']
                )
                tp_orders.append(order_id)

            state['tp_order_ids'] = tp_orders
        except Exception as e:
            logger.warning(f"Erro ao enviar TPs: {e}")

        save_state(state)
        monitor_position(cfg, state, logger)

if __name__ == '__main__':
    main()
