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
    cancel_plan
)
from modules.recovery_manager import load_state, update_state, sync_state_with_bitget


def main():
    # Carrega variáveis de ambiente
    load_dotenv()

    # Carrega configuração
    with open('config/config.json') as f:
        cfg = json.load(f)

    # Configura logger
    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # Carrega estado e sincroniza com Bitget
    state = load_state()
    sync_state_with_bitget(state)

    # Define modo de posição
    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    # Se não houver posição aberta, abre e cria ordens iniciais
    if not state.get('position_open', False):
        side = 'buy' if cfg['direction'] == 'long' else 'sell'
        hold = 'long' if side == 'buy' else 'short'

        # 1) Abre posição de mercado
        resp_order = place_order(
            side=side,
            trade_side='open',
            size=cfg['orderSize'],
            hold_side=hold
        )
        entry_price = float(resp_order.get('filledPrice', resp_order.get('entry_price')))
        state['entry_price'] = entry_price
        state['position_open'] = True
        update_state(state)
        logger.info(f"Opened position {side} at {entry_price}")

        # 2) Cria SL inicial e TPs
        sl_price = entry_price * (1 - cfg['slPct']) if side == 'buy' else entry_price * (1 + cfg['slPct'])
        sl = place_tpsl_order('stopLoss', sl_price, cfg['orderSize'])
        state['sl_order_id'] = sl['orderId']

        state['tp_order_ids'] = []
        for pct in cfg['tpPct']:
            tp_price = entry_price * (1 + pct) if side == 'buy' else entry_price * (1 - pct)
            tp = place_tpsl_order('takeProfit', tp_price, cfg['orderSize'] * pct)
            state['tp_order_ids'].append(tp['orderId'])

        # Flags de break-even
        state['be1'] = False
        state['be2'] = False
        update_state(state)
        logger.info(f"Placed SL {sl['orderId']} and TPs {state['tp_order_ids']}")

    # 3) Loop de monitoramento ativo
    interval = cfg.get('pollIntervalSec', 0.5)
    while state.get('position_open', False) and not state.get('paused', False):
        price = get_last_price(cfg['symbol'])
        entry = state['entry_price']

        # Verifica TP1 e move SL para BE
        tp1_price = entry * (1 + cfg['tpPct'][0])
        if not state['be1'] and price >= tp1_price:
            cancel_plan(state['sl_order_id'])
            new_sl = entry  # break-even
            sl = place_tpsl_order('stopLoss', new_sl, cfg['orderSize'])
            state['sl_order_id'] = sl['orderId']
            state['be1'] = True
            update_state(state)
            logger.info(f"TP1 reached; SL moved to BE1 at {new_sl}")

        # Verifica TP2 e move SL para nível de TP1
        tp2_price = entry * (1 + cfg['tpPct'][1])
        if state['be1'] and not state['be2'] and price >= tp2_price:
            cancel_plan(state['sl_order_id'])
            new_sl = entry * (1 + cfg['tpPct'][0])
            sl = place_tpsl_order('stopLoss', new_sl, cfg['orderSize'] * (1 - cfg['tpPct'][0]))
            state['sl_order_id'] = sl['orderId']
            state['be2'] = True
            update_state(state)
            logger.info(f"TP2 reached; SL moved to TP1 price {new_sl}")

        # Sincroniza estado (fecha posição se SL/TP executados)
        sync_state_with_bitget(state)
        if not state.get('position_open', False):
            logger.info("Position closed; exiting loop.")
            break

        time.sleep(interval)

    logger.info("Bot execution finished.")


if __name__ == '__main__':
    main()
