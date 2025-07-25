#!/usr/bin/env python3
import time
import logging
import json

# Importa módulos internos
from modules.data_collector import fetch_candles
from modules.signal_generator import generate_signal
from modules.order_executor import (
    set_position_mode,
    place_order,
    place_tpsl_order,
    cancel_plan,
    get_single_position
)
from modules.recovery_manager import load_state, update_state, sync_state_with_bitget  # <--- ATUALIZAÇÃO

# Carrega configurações
with open("config/config.json") as f:
    cfg = json.load(f)

# Configura logger
logging.basicConfig(
    filename="logs/bot.log",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def main():
    # 0) Sincroniza state.json com a posição real na Bitget ao iniciar
    sync_state_with_bitget()
    logging.info("Sincronização inicial do state.json com a posição real da Bitget concluída.")

    # 1) Garante hedge_mode
    resp = set_position_mode()
    logging.info(f"Mode response: {resp}")

    while True:
        try:
            # (Opcional) Sincronize a cada ciclo - DESCOMENTE SE DESEJAR PERIODICAMENTE
            # sync_state_with_bitget()

            # Recarrega o estado a cada ciclo
            state = load_state()

            # Se estiver pausado, apenas loga e espera
            if state.get("paused", False):
                logging.info("Robô PAUSADO; aguardando retomada...")
                time.sleep(cfg["pollIntervalSec"])
                continue

            # 2) Coleta dados e gera sinal
            candles = fetch_candles()
            sig = generate_signal()
            logging.info(f"Signal: {sig}")

            # --- LÓGICA DE TRADING ---
            position = state.get("position")        # None, "long" ou "short"
            sig_type = sig.get("signal")            # "BUY", "SELL" ou None

            # 3.1) Abrir posição somente se houver sinal e mudar de posição
            if sig_type == "BUY" and position != "long":
                resp_order = place_order(
                    side="buy",
                    trade_side="open",
                    size=cfg["orderSize"],
                    hold_side="long"
                )
                entry = resp_order.get("entry_price", 0)
                logging.info(f"Abrir BUY: {resp_order} | entry_price={entry}")

                # SL e TPs
                place_tpsl_order("stopLoss", entry * (1 - cfg["slPct"]), cfg["orderSize"], "long")
                place_tpsl_order("takeProfit", entry * (1 + cfg["tp1Pct"]), cfg["orderSize"] * cfg["tpPortions"][0], "long")
                place_tpsl_order("takeProfit", entry * (1 + cfg["tp2Pct"]), cfg["orderSize"] * cfg["tpPortions"][1], "long")
                place_tpsl_order("takeProfit", entry * (1 + cfg["tp3Pct"]), cfg["orderSize"] * cfg["tpPortions"][2], "long")

                state = update_state(
                    position="long",
                    last_signal="BUY",
                    reversal_count=0
                )

            elif sig_type == "SELL" and position != "short":
                resp_order = place_order(
                    side="sell",
                    trade_side="open",
                    size=cfg["orderSize"],
                    hold_side="short"
                )
                entry = resp_order.get("entry_price", 0)
                logging.info(f"Abrir SELL: {resp_order} | entry_price={entry}")

                # SL e TPs invertidos para short
                place_tpsl_order("stopLoss", entry * (1 + cfg["slPct"]), cfg["orderSize"], "short")
                place_tpsl_order("takeProfit", entry * (1 - cfg["tp1Pct"]), cfg["orderSize"] * cfg["tpPortions"][0], "short")
                place_tpsl_order("takeProfit", entry * (1 - cfg["tp2Pct"]), cfg["orderSize"] * cfg["tpPortions"][1], "short")
                place_tpsl_order("takeProfit", entry * (1 - cfg["tp3Pct"]), cfg["orderSize"] * cfg["tpPortions"][2], "short")

                state = update_state(
                    position="short",
                    last_signal="SELL",
                    reversal_count=0
                )

            # 3.2) Reversão após sinais contrários
            elif position == "long" and sig_type == "SELL":
                count = state.get("reversal_count", 0) + 1
                logging.info(f"Sinal contrário detectado ({count}/{cfg['reversalSignalsRequired']})")
                if count >= cfg["reversalSignalsRequired"]:
                    resp_close = place_order("sell", "close", cfg["orderSize"], "long")
                    logging.info(f"Fechar posição long: {resp_close}")

                    cancel_plan(state.get("sl_order_id", ""), "stopLoss")
                    for oid in state.get("tp_order_ids", []):
                        cancel_plan(oid, "takeProfit")

                    state = update_state(position=None, last_signal="SELL", reversal_count=0)

            elif position == "short" and sig_type == "BUY":
                count = state.get("reversal_count", 0) + 1
                logging.info(f"Sinal contrário detectado ({count}/{cfg['reversalSignalsRequired']})")
                if count >= cfg["reversalSignalsRequired"]:
                    resp_close = place_order("buy", "close", cfg["orderSize"], "short")
                    logging.info(f"Fechar posição short: {resp_close}")

                    cancel_plan(state.get("sl_order_id", ""), "stopLoss")
                    for oid in state.get("tp_order_ids", []):
                        cancel_plan(oid, "takeProfit")

                    state = update_state(position=None, last_signal="BUY", reversal_count=0)

            else:
                # Nenhuma ação, apenas atualiza ultimo sinal e contagem
                state = update_state(last_signal=sig_type)

        except Exception as e:
            logging.error(f"Erro no loop principal: {e}")

        time.sleep(cfg["pollIntervalSec"])

if __name__ == "__main__":
    main()
