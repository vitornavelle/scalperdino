#!/usr/bin/env python3
import time
import json
import logging
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
    load_dotenv()
    # --- configurações ---
    with open('config/config.json') as f:
        cfg = json.load(f)
    tick_size        = cfg.get('tickSize', 1)
    symbol           = cfg['symbol']
    product_type     = cfg.get('productType', 'USDT-FUTURES')
    order_size       = cfg['orderSize']
    sl_pct           = cfg['slPct']
    tp_price_pcts    = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    tp_vol_portions  = cfg['tpPortions']
    be_offset1       = cfg['beOffsetPct1']
    be_offset2       = cfg['beOffsetPct2']
    interval         = cfg.get('pollIntervalSec', 1)
    signal_poll      = cfg.get('signalPollSec', 1)

    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    # set_position_mode UMA vez
    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    while True:
        state = load_state()
        if state.get('paused', False):
            logger.info("Bot pausado via dashboard.")
            time.sleep(interval)
            continue

        # sincroniza com corretora, limpa state se necessário
        sync_state_with_bitget(state)

        # ABERTURA
        if not state.get('position_open', False):
            logger.info("Aguardando sinal para abertura de posição...")
            while True:
                result = generate_signal()
                sig = result.get('signal')
                if sig in ('BUY', 'SELL'):
                    logger.info(
                        f"Sinal recebido: {sig} | "
                        f"EMA short={result.get('emaShort'):.2f} "
                        f"long={result.get('emaLong'):.2f} "
                        f"RSI={result.get('rsi'):.2f}"
                    )
                    break
                time.sleep(signal_poll)

            side = 'buy' if sig=='BUY' else 'sell'
            hold = 'long' if side=='buy' else 'short'

            try:
                resp_order = place_order(
                    side=side, trade_side='open',
                    size=order_size, hold_side=hold
                )
            except RuntimeError as e:
                logger.error(f"Erro ao abrir posição: {e}")
                time.sleep(interval)
                continue

            # entry e SL
            filled = resp_order.get('filledPrice') or resp_order.get('entry_price')
            if filled is None:
                filled = get_last_price(symbol)
                logger.warning(f"fallback entry_price: {filled}")
            entry_price = float(filled)
            sl_price = entry_price*(1-sl_pct) if side=='buy' else entry_price*(1+sl_pct)
            sl_price = round(sl_price,1)

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

            # TPs
            entry_order_id = resp_order.get('orderId')
            for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                raw = entry_price*(1+pct) if side=='buy' else entry_price*(1-pct)
                tp = round(raw/tick_size)*tick_size
                oid = str(int(time.time()*1000))
                payload = {
                    'symbol': symbol,
                    'productType': product_type,
                    'marginCoin': cfg.get('marginCoin','USDT'),
                    'planType': 'profit_plan',
                    'triggerType': 'mark_price',
                    'orderId': entry_order_id,
                    'size': str(order_size*vol),
                    'triggerPrice': str(tp),
                    'executePrice': str(tp),
                    'side': side,
                    'holdSide': hold,
                    'reduceOnly': True,
                    'clientOid': oid
                }
                try:
                    hdrs, body, _ = headers(
                        'POST','/api/v2/mix/order/place-tpsl-order',
                        body_dict=payload
                    )
                    r = requests.post(
                        BASE_URL+'/api/v2/mix/order/place-tpsl-order',
                        headers=hdrs,data=body
                    ).json()
                    if r.get('code')!='00000':
                        raise RuntimeError(r.get('msg'))
                    tp_id = r['data']['orderId']
                    state['tp_order_ids'].append(tp_id)
                    logger.info(f"TP criado: {tp_id} @ {tp}")
                except Exception as e:
                    logger.error(f"Erro ao criar TP @ {tp}: {e}")

            update_state(state)
            logger.info(
                f"Posição aberta: {side} @ {entry_price} | "
                f"SL=@{sl_price} | TPs={state['tp_order_ids']}"
            )

        # MONITORAMENTO
        else:
            price      = get_last_price(symbol)
            entry      = state['entry_price']
            current_sl = state.get('current_sl')

            logger.info(f"DEBUG SL Check → side={state['side']} | price={price} | SL={current_sl}")

            # SL manual
            if state['side']=='buy' and current_sl and price<=current_sl:
                for tp in state.get('tp_order_ids',[]): cancel_plan(tp)
                try:
                    place_order(side='sell',trade_side='close',
                                size=order_size,hold_side='long')
                except RuntimeError as e:
                    if 'No position to close' in str(e):
                        logger.warning("Tentativa de fechar SL, mas não havia posição.")
                    else:
                        logger.error(f"Erro ao fechar posição: {e}")
                finally:
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
                for tp in state.get('tp_order_ids',[]): cancel_plan(tp)
                try:
                    place_order(side='buy',trade_side='close',
                                size=order_size,hold_side='short')
                except RuntimeError as e:
                    if 'No position to close' in str(e):
                        logger.warning("Tentativa de fechar SL, mas não havia posição.")
                    else:
                        logger.error(f"Erro ao fechar posição: {e}")
                finally:
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

            # BE automático TP1
            if not state['be1']:
                t1 = (entry*(1+tp_price_pcts[0])
                      if state['side']=='buy'
                      else entry*(1-tp_price_pcts[0]))
                if (state['side']=='buy' and price>=t1) or \
                   (state['side']=='sell' and price<=t1):
                    sln = (entry*(1+be_offset1)
                           if state['side']=='buy'
                           else entry*(1-be_offset1))
                    sln = round(sln,1)
                    state['current_sl']=sln
                    state['be1']=True
                    update_state(state)
                    logger.info(f"TP1 reached; SL moved to {sln}")

            # BE automático TP2
            if state['be1'] and not state['be2']:
                t2 = (entry*(1+tp_price_pcts[1])
                      if state['side']=='buy'
                      else entry*(1-tp_price_pcts[1]))
                if (state['side']=='buy' and price>=t2) or \
                   (state['side']=='sell' and price<=t2):
                    sln = (entry*(1+be_offset2)
                           if state['side']=='buy'
                           else entry*(1-be_offset2))
                    sln = round(sln,1)
                    state['current_sl']=sln
                    state['be2']=True
                    update_state(state)
                    logger.info(f"TP2 reached; SL moved to {sln}")

        time.sleep(interval)

if __name__=='__main__':
    main()
