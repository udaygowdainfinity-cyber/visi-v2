"""
VISI v2 — Main Entry Point (Railway 24/7)
Runs: market scanner + virtual trader + Telegram bot simultaneously
"""

import sys, time, threading, asyncio
from datetime import datetime, date, timedelta
import config
from db.database import init_db

def _in_market_hours():
    from datetime import time as dtime
    now = datetime.now()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)

def _in_active_window():
    from datetime import time as dtime
    t = datetime.now().time()
    return dtime(9, 45) <= t <= dtime(14, 30)

def scanner_loop():
    """Continuously scan all instruments during market hours."""
    from core.data_manager import get_live_candles
    from core.engine import run_scan
    from core.virtual_trader import open_trade, monitor_open_trades, get_today_summary
    from alerts.telegram_alerts import send_signal, send_daily_summary
    import pandas as pd

    print("[Main] Scanner loop started")
    last_summary_date = None
    instruments = list(config.FO_INSTRUMENTS.keys())

    while True:
        try:
            now = datetime.now()
            today = date.today()

            if _in_active_window():
                for instrument in instruments:
                    try:
                        df5_list = get_live_candles(instrument, 'FIVE_MINUTE', 50)
                        df1_list = get_live_candles(instrument, 'ONE_MINUTE',  30)
                        if not df5_list or not df1_list:
                            continue
                        df5 = pd.DataFrame(df5_list)
                        df1 = pd.DataFrame(df1_list)
                        result = run_scan(instrument, df5, df1)
                        if result['decision'] == "YES":
                            send_signal(instrument, result)
                            open_trade(instrument, result)
                        time.sleep(2)
                    except Exception as e:
                        print(f"[Main] Scan error {instrument}: {e}")

                # Monitor open virtual trades
                try:
                    from core.data_manager import get_live_candles as glc
                    def get_price(inst):
                        candles = glc(inst, 'ONE_MINUTE', 2)
                        return candles[-1]['close'] if candles else None
                    monitor_open_trades(get_price)
                except Exception as e:
                    print(f"[Main] Monitor error: {e}")

            # End of day summary
            if now.hour == 15 and now.minute >= 35 and last_summary_date != today:
                try:
                    summary = {inst: get_today_summary(inst) for inst in instruments}
                    if any(s['trades'] > 0 for s in summary.values()):
                        send_daily_summary(summary)
                    last_summary_date = today
                except Exception as e:
                    print(f"[Main] Summary error: {e}")

            time.sleep(config.SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("[Main] Scanner stopped.")
            break
        except Exception as e:
            print(f"[Main] Loop error: {e}")
            time.sleep(30)

def main():
    print("\n" + "="*50)
    print("  VISI Bot v2 Starting...")
    print("="*50)

    # Validate config
    missing = config.validate_or_warn()
    if missing:
        from alerts.telegram_alerts import send_missing_params
        try: send_missing_params(missing)
        except: pass

    # Init DB
    init_db()

    # Start Telegram bot in background thread
    tg_thread = threading.Thread(target=_run_telegram, daemon=True)
    tg_thread.start()

    print("[Main] VISI v2 running. Press Ctrl+C to stop.")

    # Run scanner in main thread
    scanner_loop()

def _run_telegram():
    try:
        from telegram_bot import run_bot
        run_bot()
    except Exception as e:
        print(f"[TG] Bot error: {e}")

if __name__ == "__main__":
    main()
