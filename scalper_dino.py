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
    load_dotenv()
    with open('config/config.json') as f:
        cfg = json.load(f)
    reversal_required = cfg.get('reversalSignalsRequired', 0)

    logging.basicConfig(
        filename='logs/bot.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger()

    state = load_state()
    state.setdefault('reversal_count', 0)
    state.setdefault('side', None)
    state.setdefault('current_sl', None)
    sync_state_with_bitget(state)

    resp = set_position_mode()
    logger.info(f"Position mode set: {resp}")

    order_size     = cfg['orderSize']
    sl_pct         = cfg['slPct']
    tp_price_pcts  = [cfg['tp1Pct'], cfg['tp2Pct'], cfg['tp3Pct']]
    tp_vol_portions= cfg['tpPortions']
    be_offset1     = cfg['beOffsetPct1']
    be_offset2     = cfg['beOffsetPct2']
    interval       = cfg.get('pollIntervalSec', 1)
    signal_poll    = cfg.get('signalPollSec', 1)

    while not state.get('paused', False):
        # abertura de posição
        if not state.get('position_open', False):
            logger.info("Aguardando sinal para abertura de posição...")
            while True:
                signal = generate_signal()
                if signal in ('BUY','SELL'):
                    break
                time.sleep(signal_poll)
            side = 'buy' if signal=='BUY' else 'sell'
            hold = 'long' if side=='buy' else 'short'
            resp_order = place_order(side=side, trade_side='open',
                                     size=order_size, hold_side=hold)
            entry_price = float(resp_order.get('filledPrice',
                                               resp_order.get('entry_price')))
            # SL manual
            sl_price = entry_price*(1-sl_pct) if side=='buy' else entry_price*(1+sl_pct)
            state.update({
                'entry_price': entry_price,
                'position_open': True,
                'side': side,
                'reversal_count': 0,
                'current_sl': sl_price
            })
            # TPs via API
            state['tp_order_ids']=[]
            for pct, vol in zip(tp_price_pcts, tp_vol_portions):
                tp_price = entry_price*(1+ pct) if side=='buy' else entry_price*(1- pct)
                tp = place_tpsl_order('takeProfit', tp_price, order_size*vol)
                state['tp_order_ids'].append(tp['orderId'])
            state['be1']=False; state['be2']=False
            update_state(state)
            logger.info(f"Abrindo {side} em {entry_price} | SL manual em {sl_price} | TPs {state['tp_order_ids']}")

        # monitoramento
        if state.get('position_open', False):
            price = get_last_price(cfg['symbol'])
            # stop loss manual
            current_sl = state.get('current_sl')
            if state['side']=='buy' and current_sl and price<=current_sl:
                logger.info(f"SL manual atingido em {price}")
                for tp in state['tp_order_ids']:
                    cancel_plan(tp)
                close = place_order(side='sell', trade_side='close',
                                    size=order_size, hold_side='long')
                state.update({'position_open':False,'tp_order_ids':[],
                              'current_sl':None,'reversal_count':0,'side':None})
                update_state(state); continue
            if state['side']=='sell' and current_sl and price>=current_sl:
                logger.info(f"SL manual atingido em {price}")
                for tp in state['tp_order_ids']:
                    cancel_plan(tp)
                close = place_order(side='buy', trade_side='close',
                                    size=order_size, hold_side='short')
                state.update({'position_open':False,'tp_order_ids':[],
                              'current_sl':None,'reversal_count':0,'side':None})
                update_state(state); continue

            # reversão
            sig = generate_signal()
            if sig in ('BUY','SELL'):
                if (sig=='BUY' and state['side']=='sell') or \
                   (sig=='SELL' and state['side']=='buy'):
                    state['reversal_count']+=1
                else:
                    state['reversal_count']=0
                update_state(state)
            if reversal_required>0 and state['reversal_count']>=reversal_required:
                # cancelar TPs
                for tp in state['tp_order_ids']: cancel_plan(tp)
                close_side = 'sell' if state['side']=='buy' else 'buy'
                close = place_order(side=close_side, trade_side='close',
                                    size=order_size, hold_side=state['side'])
                new_entry = float(place_order(side=close_side, trade_side='open',
                                     size=order_size,
                                     hold_side=('long' if close_side=='buy' else 'short')
                                   ).get('filledPrice'))
                # novo SL manual
                new_sl = new_entry*(1-sl_pct) if close_side=='buy' else new_entry*(1+sl_pct)
                state.update({'entry_price':new_entry,'side':close_side,
                              'reversal_count':0,'current_sl':new_sl})
                # refaz TPs
                state['tp_order_ids']=[]
                for pct, vol in zip(tp_price_pcts,tp_vol_portions):
                    tp_price = new_entry*(1+ pct) if close_side=='buy' \
                               else new_entry*(1- pct)
                    tp = place_tpsl_order('takeProfit', tp_price, order_size*vol)
                    state['tp_order_ids'].append(tp['orderId'])
                state['be1']=False; state['be2']=False
                update_state(state); continue

            # break-even manual
            entry = state['entry_price']
            if not state['be1'] and price>=entry*(1+tp_price_pcts[0]):
                state['current_sl'] = entry*(1+be_offset1)
                state['be1']=True; update_state(state)
            if state['be1'] and not state['be2'] and price>=entry*(1+tp_price_pcts[1]):
                state['current_sl'] = entry*(1+be_offset2)
                state['be2']=True; update_state(state)

            sync_state_with_bitget(state)
        time.sleep(interval)

    logger.info("Bot execution finalizado.")

if __name__=='__main__':
    main()
