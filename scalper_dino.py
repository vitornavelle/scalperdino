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

    # Parâmetro de reversão
    reversal_required = cfg.get('reversalSignalsRequired', 0)

    # Configura logger
    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # Carrega estado e sincroniza com Bitget
    state = load_state()
    state.setdefault('reversal_count', 0)
    state.setdefault('side', None)
    state.setdefault('current_sl', None)
    sync_state_with_bitget(state)

    # Define modo de posição
    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    # Parâmetros principais
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
        # Aguardando sinal e abertura de posição
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

            # Abre posição de mercado
            resp_order = place_order(
                side=side,
                trade_side='open',
                size=order_size,
                hold_side=hold
            )
            entry_price = float(resp_order.get('filledPrice', resp_order.get('entry_price')))
            # Atualiza estado inicial da posição
            sl_price = entry_price * (1 - sl_pct) if side == 'buy' else entry_price * (1 + sl_pct)
            state.update({
                'entry_price': entry_price,
                'position_open': True,
                'side': side,
                'reversal_count': 0,
                'current_sl': sl_price
            })

            # Cria TPs iniciais
            state['tp_order_ids'] = []
            for price_pct, vol_portion in zip(tp_price_pcts, tp_vol_portions):
                tp_price = entry_price * (1 + price_pct) if side == 'buy' else entry_price * (1 - price_pct)
                tp = place_tpsl_order('takeProfit', tp_price, order_size * vol_portion)
                state['tp_order_ids'].append(tp['orderId'])

            # Flags de break-even
            state['be1'] = False
            state['be2'] = False
            update_state(state)
            logger.info(f"Opened {side} at {entry_price} | SL manual at {sl_price} | TPs {state['tp_order_ids']}")

        # Monitoramento de posição aberta
        if state.get('position_open', False):
            price = get_last_price(cfg['symbol'])
            entry = state['entry_price']

            # Checagem manual de Stop Loss
            current_sl = state.get('current_sl')
            if state['side'] == 'buy' and current_sl is not None and price <= current_sl:
                logger.info(f"SL manual atingido em {price} (threshold {current_sl})")
                # Cancela TPs
                for tp_id in state.get('tp_order_ids', []):
                    cancel_plan(tp_id)
                # Fecha posição a mercado
                resp_close = place_order(
                    side='sell',
                    trade_side='close',
                    size=order_size,
                    hold_side='long'
                )
                logger.info(f"Posição BUY fechada a mercado em {resp_close.get('filledPrice')}")
                state.update({
                    'position_open': False,
                    'tp_order_ids': [],
                    'current_sl': None,
                    'reversal_count': 0,
                    'side': None
                })
                update_state(state)
                continue

            if state['side'] == 'sell' and current_sl is not None and price >= current_sl:
                logger.info(f"SL manual atingido em {price} (threshold {current_sl})")
                for tp_id in state.get('tp_order_ids', []):
                    cancel_plan(tp_id)
                resp_close = place_order(
                    side='buy',
                    trade_side='close',
                    size=order_size,
                    hold_side='short'
                )
                logger.info(f"Posição SELL fechada a mercado em {resp_close.get('filledPrice')}")
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
            sig = generate_signal()
            if sig in ('BUY', 'SELL'):
                if (sig == 'BUY' and state['side'] == 'sell') or (sig == 'SELL' and state['side'] == 'buy'):
                    state['reversal_count'] += 1
                    logger.info(f"Reversal signal {sig} detected (count {state['reversal_count']}/{reversal_required})")
                else:
                    state['reversal_count'] = 0
                update_state(state)

            if reversal_required > 0 and state['reversal_count'] >= reversal_required:
                logger.info(f"Reversal threshold reached ({reversal_required}); executing reversal.")
                # Cancela TPs
                for tp_id in state.get('tp_order_ids', []):
                    cancel_plan(tp_id)
                # Fecha posição atual a mercado
                close_side = 'sell' if state['side'] == 'buy' else 'buy'
                hold_side = state['side']
                close_resp = place_order(
                    side=close_side,
                    trade_side='close',
                    size=order_size,
                    hold_side=hold_side
                )
                close_price = float(close_resp.get('filledPrice', close_resp.get('entry_price')))
                logger.info(f"Closed position {state['side']} at {close_price} for reversal")
                # Abre nova posição invertida
                new_side = close_side
                new_hold = 'long' if new_side == 'buy' else 'short'
                open_resp = place_order(
                    side=new_side,
                    trade_side='open',
                    size=order_size,
                    hold_side=new_hold
                )
                new_entry = float(open_resp.get('filledPrice', open_resp.get('entry_price')))
                # Atualiza estado com nova posição e SL manual
                new_sl = new_entry * (1 - sl_pct) if new_side == 'buy' else new_entry * (1 + sl_pct)
                state.update({
                    'entry_price': new_entry,
                    'side': new_side,
                    'reversal_count': 0,
                    'current_sl': new_sl
                })
                # Cria novos TPs
                state['tp_order_ids'] = []
                for price_pct, vol_portion in zip(tp_price_pcts, tp_vol_portions):
                    tp_price = new_entry * (1 + price_pct) if new_side == 'buy' else new_entry * (1 - price_pct)
                    tp = place_tpsl_order('takeProfit', tp_price, order_size * vol_portion)
                    state['tp_order_ids'].append(tp['orderId'])
                state['be1'] = False
                state['be2'] = False
                update_state(state)
                logger.info(f"Reversal executed: new SL manual {new_sl} and TPs {state['tp_order_ids']}")
                time.sleep(interval)
                continue

            # Ajustes de BE manuais
            if not state['be1'] and price >= entry * (1 + tp_price_pcts[0]):  # TP1 alcançado
                new_sl = entry * (1 + be_offset1)
                state['current_sl'] = new_sl
                state['be1'] = True
                update_state(state)
                logger.info(f"TP1 reached; SL manual moved to {new_sl}")

            if state['be1'] and not state['be2'] and price >= entry * (1 + tp_price_pcts[1]):  # TP2 alcançado
                new_sl = entry * (1 + be_offset2)
                state['current_sl'] = new_sl
                state['be2'] = True
                update_state(state)
                logger.info(f"TP2 reached; SL manual moved to {new_sl}")

            # Sincroniza estado final com Bitget (sem planos de SL ativos)
            sync_state_with_bitget(state)
            if not state.get('position_open', False):
                logger.info("Position closed; retornando à espera de sinal.")

        time.sleep(interval)

    logger.info("Bot execution finalizado.")

if __name__ == '__main__':
    main()
