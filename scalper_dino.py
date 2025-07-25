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
from modules.signal_generator import generate_signal


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

    order_size = cfg['orderSize']
    sl_pct = cfg['slPct']
    tp_price_pcts = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    tp_vol_portions = cfg['tpPortions']
    be_offset1 = cfg['beOffsetPct1']
    be_offset2 = cfg['beOffsetPct2']
    interval = cfg.get('pollIntervalSec', 1)
    signal_poll = cfg.get('signalPollSec', 1)

    # Loop principal
    while not state.get('paused', False):
        # Aguardando sinal se não há posição aberta
        if not state.get('position_open', False):
            logger.info("Aguardando sinal para abertura de posição...")
            while True:
                signal = generate_signal()
                if signal in ('BUY', 'SELL'):
                    logger.info(f"Sinal recebido: {signal}")
                    break
                time.sleep(signal_poll)

            side = 'buy' if signal == 'BUY' else 'sell'
            hold = 'long' if side == 'buy' else 'short'

            # 1) Abre posição de mercado
            resp_order = place_order(
                side=side,
                trade_side='open',
                size=order_size,
                hold_side=hold
            )
            entry_price = float(resp_order.get('filledPrice', resp_order.get('entry_price')))
            state.update({
                'entry_price': entry_price,
                'position_open': True
            })
            update_state(state)
            logger.info(f"Opened position {side} at {entry_price}")

            # 2) SL inicial
            sl_price = entry_price * (1 - sl_pct) if side == 'buy' else entry_price * (1 + sl_pct)
            sl = place_tpsl_order('stopLoss', sl_price, order_size)
            state['sl_order_id'] = sl['orderId']

            # 3) TPs iniciais (preço e volume)
            state['tp_order_ids'] = []
            for price_pct, vol_portion in zip(tp_price_pcts, tp_vol_portions):
                tp_price = entry_price * (1 + price_pct) if side == 'buy' else entry_price * (1 - price_pct)
                tp = place_tpsl_order('takeProfit', tp_price, order_size * vol_portion)
                state['tp_order_ids'].append(tp['orderId'])

            # Flags BE
            state['be1'] = False
            state['be2'] = False
            update_state(state)
            logger.info(f"Placed SL {state['sl_order_id']} and TPs {state['tp_order_ids']}")

        # Monitoramento e ajustes de SL
        if state.get('position_open', False):
            price = get_last_price(cfg['symbol'])
            entry = state['entry_price']

            # TP1 alcançado? Move SL ao primeiro offset
            if not state['be1'] and price >= entry * (1 + tp_price_pcts[0]):
                cancel_plan(state['sl_order_id'])
                new_sl = entry * (1 + be_offset1)
                sl = place_tpsl_order('stopLoss', new_sl, order_size)
                state['sl_order_id'] = sl['orderId']
                state['be1'] = True
                update_state(state)
                logger.info(f"TP1 reached; SL moved to entry+offset1 at {new_sl}")

            # TP2 alcançado? Move SL ao segundo offset
            if state['be1'] and not state['be2'] and price >= entry * (1 + tp_price_pcts[1]):
                cancel_plan(state['sl_order_id'])
                new_sl = entry * (1 + be_offset2)
                sl = place_tpsl_order('stopLoss', new_sl, order_size * (1 - tp_vol_portions[0]))
                state['sl_order_id'] = sl['orderId']
                state['be2'] = True
                update_state(state)
                logger.info(f"TP2 reached; SL moved to entry+offset2 at {new_sl}")

            # Sincroniza e verifica posição fechada
            sync_state_with_bitget(state)
            if not state.get('position_open', False):
                logger.info("Position closed; retornando à espera de sinal.")

        time.sleep(interval)

    logger.info("Bot execution finalizado.")


if __name__ == '__main__':
    main()
