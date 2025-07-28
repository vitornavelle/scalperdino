#!/usr/bin/env python3
import time
import json
import logging
import math
import requests
from dotenv import load_dotenv
from modules.data_collector import get_last_price
from modules.order_executor import (
    set_position_mode,
    place_order,
    cancel_plan,
    headers,
    BASE_URL
)
from modules.recovery_manager import load_state, update_state, sync_state_with_bitget
from modules.signal_generator import generate_signal


def main():
    # Carrega variáveis de ambiente
    load_dotenv()

    # Carrega configuração
    with open('config/config.json') as f:
        cfg = json.load(f)
    reversal_required = cfg.get('reversalSignalsRequired', 0)
    tick_size = cfg.get('tickSize', 1)
    margin_coin = cfg.get('marginCoin', 'USDT')
    symbol = cfg['symbol']
    product_type = cfg.get('productType', 'USDT-FUTURES')

    # Configura logger
    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # Define modo de posição UMA ÚNICA VEZ
    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    # Parâmetros principais
    order_size      = cfg['orderSize']
    sl_pct          = cfg['slPct']
    tp_price_pcts   = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    tp_vol_portions = cfg['tpPortions']
    be_offset1      = cfg['beOffsetPct1']
    be_offset2      = cfg['beOffsetPct2']
    interval        = cfg.get('pollIntervalSec', 1)
    signal_poll     = cfg.get('signalPollSec', 1)

    # Loop principal
    while True:
        # Recarrega estado
        state = load_state()
        if state.get('paused', False):
            logger.info("Bot pausado via dashboard.")
            time.sleep(interval)
            continue
        sync_state_with_bitget(state)

        # Abertura de posição
        if not state.get('position_open', False):
            logger.info("Aguardando sinal para abertura de posição...")
            while True:
                result = generate_signal()
                sig = result.get('signal')
                if sig in ('BUY', 'SELL'):
                    logger.info(
                        f"Sinal recebido: {sig} | EMA short={result.get('emaShort'):.2f} "
                        f"long={result.get('emaLong'):.2f} RSI={result.get('rsi'):.2f}"
                    )
                    break
                time.sleep(signal_poll)

            side = 'buy' if sig == 'BUY' else 'sell'
            hold = 'long' if side == 'buy' else 'short'

            # Executa market order
            try:
                resp_order = place_order(
                    side=side,
                    trade_side='open',
                    size=order_size,
                    hold_side=hold
                )
            except RuntimeError as e:
                logger.error(f"Erro ao abrir posição: {e}")
                time.sleep(interval)
                continue

            # Determina entry_price
            filled = resp_order.get('filledPrice') or resp_order.get('entry_price')
            if filled is None:
                filled = get_last_price(symbol)
                logger.warning(f"fallback entry_price: {filled}")
            entry_price = float(filled)
            sl_price = entry_price * (1 - sl_pct) if side == 'buy' else entry_price * (1 + sl_pct)

            # Persiste estado antes de criar TPs
            state.update({
                'entry_price': entry_price,
                'position_open': True,
                'side': side,
                'reversal_count': 0,
                'current_sl': sl_price,
                'tp_order_ids': [],
                'be1': False,
                'be2': False
            })
            update_state(state)

            # Cria planos de take-profit via API direta
            entry_order_id = resp_order.get('orderId')
            for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                raw_price = entry_price * (1 + pct) if side == 'buy' else entry_price * (1 - pct)
                tp_price = round(raw_price / tick_size) * tick_size
                client_oid = str(int(time.time() * 1000))
                payload = {
                    'symbol': symbol,
                    'productType': product_type,
                    'marginCoin': margin_coin,
                    'planType': 'profit_plan',
                    'triggerType': 'mark_price',
                    'orderId': entry_order_id,
                    'size': str(order_size * vol),
                    'triggerPrice': str(tp_price),
                    'executePrice': str(tp_price),
                    'side': side,
                    'holdSide': hold,
                    'reduceOnly': True,
                    'clientOid': client_oid
                }
                try:
                    hdrs, body, _ = headers('POST', '/api/v2/mix/order/place-tpsl-order', body_dict=payload)
                    resp_tp = requests.post(BASE_URL + '/api/v2/mix/order/place-tpsl-order', headers=hdrs, data=body).json()
                    if resp_tp.get('code') != '00000':
                        raise RuntimeError(resp_tp.get('msg'))
                    tp_id = resp_tp['data']['orderId']
                    state['tp_order_ids'].append(tp_id)
                    logger.info(f"TP criado: {tp_id} @ {tp_price}")
                except Exception as e:
                    logger.error(f"Erro ao criar TP @ {tp_price}: {e}")

            # Persiste TPs no estado
            update_state(state)
            logger.info(f"Posição aberta: {side} @ {entry_price} | SL=@{sl_price} | TPs={state['tp_order_ids']}")

        # Monitoramento de posição aberta
        else:
            price = get_last_price(symbol)
            entry = state['entry_price']
            current_sl = state.get('current_sl')

            # Verifica SL manual
            if state['side']=='buy' and current_sl and price<=current_sl:
                for tp_id in state.get('tp_order_ids',[]): cancel_plan(tp_id)
                place_order(side='sell', trade_side='close', size=order_size, hold_side='long')
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
                logger.info(f"SL manual atingido: {price}")
                continue
            if state['side']=='sell' and current_sl and price>=current_sl:
                for tp_id in state.get('tp_order_ids',[]): cancel_plan(tp_id)
                place_order(side='buy', trade_side='close', size=order_size, hold_side='short')
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
                logger.info(f"SL manual atingido: {price}")
                continue

            # Break-even automático
            # TP1
            if not state['be1']:
                target1 = entry * (1 + tp_price_pcts[0]) if state['side']=='buy' else entry * (1 - tp_price_pcts[0])
                if (state['side']=='buy' and price>=target1) or (state['side']=='sell' and price<=target1):
                    sl_new = entry * (1 + be_offset1) if state['side']=='buy' else entry * (1 - be_offset1)
                    state['current_sl'] = sl_new
                    state['be1'] = True
                    update_state(state)
                    logger.info(f"TP1 reached; SL manual moved to {state['current_sl']}")
            # TP2
            if state['be1'] and not state['be2']:
                target2 = entry * (1 + tp_price_pcts[1]) if state['side']=='buy' else entry * (1 - tp_price_pcts[1])
                if (state['side']=='buy' and price>=target2) or (state['side']=='sell' and price<=target2):
                    sl_new = entry * (1 + be_offset2) if state['side']=='buy' else entry * (1 - be_offset2)
                    state['current_sl'] = sl_new
                    state['be2'] = True
                    update_state(state)
                    logger.info(f"TP2 reached; SL manual moved to {state['current_sl']}")

        time.sleep(interval)

if __name__=='__main__':
    main()
