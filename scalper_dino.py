#!/usr/bin/env python3
import time
import json
import logging
import math
import requests
from dotenv import load_dotenv
from urllib.parse import urlencode
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
    margin_coin = 'USDT'

    # Configura logger
    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # Ajusta modo de posição
    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    # Parâmetros
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
        state = load_state()
        # Pausa via dashboard
        if state.get('paused', False):
            logger.info("Bot pausado via dashboard.")
            time.sleep(interval)
            continue
        sync_state_with_bitget(state)

        # Se não há posição aberta, tenta abrir
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

            # Abre posição de mercado
            try:
                resp_order = place_order(
                    side=side,
                    trade_side='open',
                    size=order_size,
                    hold_side=hold
                )
            except RuntimeError as e:
                msg = str(e)
                if "exceeds the balance" in msg:
                    logger.warning("Saldo insuficiente; ajuste orderSize no config ou aguarde.")
                    time.sleep(60)
                else:
                    logger.error(f"Falha ao abrir posição ({sig}): {e}")
                    time.sleep(interval)
                continue

            # Determina price e SL
            filled = resp_order.get('filledPrice') or resp_order.get('entry_price')
            if filled is None:
                filled = get_last_price(cfg['symbol'])
                logger.warning(f"filledPrice não retornado; usando preço de mercado {filled}")
            entry_price = float(filled)
            sl_price = entry_price * (1 - sl_pct) if side == 'buy' else entry_price * (1 + sl_pct)

            # Registra estado inicial e persiste antes de criar TPs
            state.update({
                'entry_price': entry_price,
                'position_open': True,
                'side': side,
                'reversal_count': 0,
                'current_sl': sl_price
            })
            update_state(state)

            # Cria TPs usando método similar ao teste
            entry_oid = resp_order.get('orderId')
            state['tp_order_ids'] = []
            for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                raw_price = entry_price * (1 + pct) if side == 'buy' else entry_price * (1 - pct)
                tp_price = round(raw_price / tick_size) * tick_size
                payload = {
                    'symbol': cfg['symbol'],
                    'productType': cfg['productType'],
                    'marginCoin': margin_coin,
                    'planType': 'profit_plan',
                    'triggerType': 'mark_price',
                    'orderId': entry_oid,
                    'size': str(order_size * vol),
                    'triggerPrice': str(tp_price),
                    'executePrice': str(tp_price),
                    'side': side,
                    'holdSide': hold,
                    'reduceOnly': True,
                    'clientOid': str(int(time.time() * 1000))
                }
                try:
                    hdrs, body, request_path = headers('POST', '/api/v2/mix/order/place-tpsl-order', body_dict=payload)
                    resp_tp = requests.post(BASE_URL + '/api/v2/mix/order/place-tpsl-order', headers=hdrs, data=body).json()
                    if resp_tp.get('code') != '00000':
                        raise RuntimeError(resp_tp.get('msg'))
                    tp_id = resp_tp.get('data', {}).get('orderId')
                    state['tp_order_ids'].append(tp_id)
                except Exception as e:
                    logger.error(f"Erro ao criar TP em {tp_price}: {e}")
            # Finaliza estado
            update_state(state)
            logger.info(f"Posição aberta: {side} em {entry_price} | SL={sl_price} | TPs {state['tp_order_ids']}")

        # Se há posição aberta, monitora
        else:
            price = get_last_price(cfg['symbol'])
            entry = state['entry_price']
            current_sl = state.get('current_sl')

            # Checa SL manual
            if state['side'] == 'buy' and current_sl and price <= current_sl:
                for tp_id in state.get('tp_order_ids', []): cancel_plan(tp_id)
                place_order(side='sell', trade_side='close', size=order_size, hold_side='long')
                state.update({
                    'position_open': False,
                    'tp_order_ids': [],
                    'current_sl': None,
                    'reversal_count': 0,
                    'side': None
                })
                update_state(state)
                logger.info(f"SL manual atingido; posição fechada em {price}")
                continue
            if state['side'] == 'sell' and current_sl and price >= current_sl:
                for tp_id in state.get('tp_order_ids', []): cancel_plan(tp_id)
                place_order(side='buy', trade_side='close', size=order_size, hold_side='short')
                state.update({
                    'position_open': False,
                    'tp_order_ids': [],
                    'current_sl': None,
                    'reversal_count': 0,
                    'side': None
                })
                update_state(state)
                logger.info(f"SL manual atingido; posição fechada em {price}")
                continue

            # Reversão e BE omitidos para brevidade (mantêm lógica anterior)
            # ...

        time.sleep(interval)

if __name__ == '__main__':
    main()
