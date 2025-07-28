#!/usr/bin/env python3
import time
import json
import logging
import math
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
    reversal_required = cfg.get('reversalSignalsRequired', 0)
    tick_size = cfg.get('tickSize', 1)  # granularidade de preço para ajustar TP/SL

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
        # Recarrega estado para detectar pausa ou alterações externas
        state = load_state()
        if state.get('paused', False):
            logger.info("Bot pausado via dashboard.")
            time.sleep(interval)
            continue
        sync_state_with_bitget(state)

        # 1) Abertura de posição
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

            filled = resp_order.get('filledPrice') or resp_order.get('entry_price')
            if filled is None:
                filled = get_last_price(cfg['symbol'])
                logger.warning(f"filledPrice não retornado; usando preço de mercado {filled} como entry_price")

            entry_price = float(filled)
            sl_price = entry_price * (1 - sl_pct) if side == 'buy' else entry_price * (1 + sl_pct)

            # Atualiza estado inicial
            state.update({
                'entry_price': entry_price,
                'position_open': True,
                'side': side,
                'reversal_count': 0,
                'current_sl': sl_price
            })

            # 2) TPs iniciais com ajuste de tick_size
            state['tp_order_ids'] = []
            for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                raw_price = entry_price * (1 + pct) if side == 'buy' else entry_price * (1 - pct)
                tp_price = round(raw_price / tick_size) * tick_size
                tp = place_tpsl_order('takeProfit', tp_price, order_size * vol)
                state['tp_order_ids'].append(tp['orderId'])

            state['be1'] = False
            state['be2'] = False
            update_state(state)
            logger.info(f"Abrindo {side} em {entry_price} | SL em {sl_price} | TPs {state['tp_order_ids']}")

        # 2) Monitoramento de posição
        else:
            price = get_last_price(cfg['symbol'])
            entry = state['entry_price']
            current_sl = state.get('current_sl')

            # Checa SL manual
            if state['side'] == 'buy' and current_sl and price <= current_sl:
                logger.info(f"SL atingido em {price}")
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
                continue

            if state['side'] == 'sell' and current_sl and price >= current_sl:
                logger.info(f"SL atingido em {price}")
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
                continue

            # Lógica de reversão
            result = generate_signal()
            sig = result.get('signal')
            if sig in ('BUY', 'SELL'):
                if (sig == 'BUY' and state['side']=='sell') or (sig=='SELL' and state['side']=='buy'):
                    state['reversal_count'] += 1
                    logger.info(f"Reversal {sig} (count {state['reversal_count']}/{reversal_required})")
                else:
                    state['reversal_count'] = 0
                update_state(state)

            if reversal_required and state['reversal_count'] >= reversal_required:
                logger.info("Executando reversal")
                for tp_id in state.get('tp_order_ids', []): cancel_plan(tp_id)
                place_order(side=('sell' if state['side']=='buy' else 'buy'),
                            trade_side='close', size=order_size, hold_side=state['side'])
                try:
                    open_resp = place_order(
                        side=('sell' if state['side']=='buy' else 'buy'),
                        trade_side='open', size=order_size,
                        hold_side=('long' if state['side']=='sell' else 'short')
                    )
                except RuntimeError as e:
                    logger.error(f"Erro reversal: {e}")
                    time.sleep(interval)
                    continue
                new_filled = open_resp.get('filledPrice') or open_resp.get('entry_price') or get_last_price(cfg['symbol'])
                new_entry = float(new_filled)
                new_sl = new_entry * (1 - sl_pct) if state['side']=='sell' else new_entry * (1 + sl_pct)
                state.update({'entry_price': new_entry, 'side':('sell' if state['side']=='buy' else 'buy'),
                              'reversal_count':0, 'current_sl':new_sl})
                state['tp_order_ids'] = []
                for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                    raw_price = new_entry * (1 + pct) if state['side']=='buy' else new_entry * (1 - pct)
                    tp_price = round(raw_price / tick_size) * tick_size
                    tp = place_tpsl_order('takeProfit', tp_price, order_size * vol)
                    state['tp_order_ids'].append(tp['orderId'])
                state['be1'] = False
                state['be2'] = False
                update_state(state)
                logger.info(f"Reversal executado: SL {new_sl} TPs {state['tp_order_ids']}")
                time.sleep(interval)
                continue

            # Break-even Manual
            if not state['be1'] and price >= entry * (1 + tp_price_pcts[0]):
                state['current_sl'] = entry * (1 + be_offset1)
                state['be1'] = True
                update_state(state)
                logger.info(f"TP1: SL atualizado para {state['current_sl']}")
            if state['be1'] and not state['be2'] and price >= entry * (1 + tp_price_pcts[1]):
                state['current_sl'] = entry * (1 + be_offset2)
                state['be2'] = True
                update_state(state)
                logger.info(f"TP2: SL atualizado para {state['current_sl']}")

        time.sleep(interval)

if __name__ == '__main__':
    main()
