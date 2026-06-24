"""
VISI v2 — Telegram Bot Command Handler
Commands:
  /start       — welcome + help
  /help        — all commands
  /status      — bot health + config check
  /signal      — scan NIFTY (default)
  /signal BANKNIFTY — scan specific instrument
  /backtest NIFTY 30  — backtest last 30 days
  /backtest NIFTY 2026-01-01 2026-03-31
  /trades      — today's virtual trades
  /summary     — today's P&L summary
  /data        — show data inventory
  /params      — show all current parameters
  /setparam EMA_FAST 5 — change a parameter
"""

import asyncio, re
from datetime import datetime, date, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import config
from db.database import get_conn

HELP_TEXT = """
🤖 <b>VISI Bot Commands</b>
━━━━━━━━━━━━━━━━━━
/status — system health
/signal — scan NIFTY
/signal BANKNIFTY — scan specific instrument
/backtest NIFTY 30 — last 30 days
/backtest NIFTY 2026-01-01 2026-06-01 — date range
/trades — today's virtual trades
/summary — today's P&L
/data — data inventory per instrument
/params — current parameters
/setparam NAME VALUE — change a parameter
  Example: /setparam EMA_FAST 5
/help — this message
"""

def _missing_warn():
    missing = config.validate()
    if missing:
        return f"⚠️ Missing: {', '.join(missing)}\n\n"
    return ""

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 <b>VISI Bot v2 Active</b>\n"
        f"All F&O instruments | Virtual trading\n"
        f"{_missing_warn()}"
        f"Type /help for all commands.",
        parse_mode="HTML")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from core.data_manager import get_data_inventory
    missing = config.validate()
    cfg_lines = []
    for name, val in config.REQUIRED_CREDENTIALS:
        icon = "✅" if val else "❌"
        cfg_lines.append(f"  {icon} {name}")

    inventory = get_data_inventory()
    inv_lines = []
    for inst, info in inventory.items():
        inv_lines.append(f"  {inst}: 5min={info['5min']} 1min={info['1min']}"
                         + (f" ({info['5min_from']}→{info['5min_to']})" if info['5min'] else ""))

    msg = (
        f"🤖 <b>VISI Status</b>\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Credentials:</b>\n" + "\n".join(cfg_lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Data inventory:</b>\n" + "\n".join(inv_lines)
    )
    if missing:
        msg += f"\n\n⚠️ Missing: {', '.join(missing)}"
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    instrument = args[0].upper() if args else config.DEFAULT_INSTRUMENT

    if instrument not in config.FO_INSTRUMENTS:
        await update.message.reply_text(
            f"❓ Unknown instrument: {instrument}\n"
            f"Available: {', '.join(config.FO_INSTRUMENTS.keys())}")
        return

    await update.message.reply_text(f"🔍 Scanning {instrument}...")

    try:
        from core.data_manager import get_live_candles
        from core.engine import run_scan
        import pandas as pd

        df5_list = get_live_candles(instrument, 'FIVE_MINUTE', 50)
        df1_list = get_live_candles(instrument, 'ONE_MINUTE',  30)

        if not df5_list or not df1_list:
            await update.message.reply_text(
                f"❌ No live data for {instrument}.\n"
                f"Is market open? Check AngelOne session.")
            return

        df5 = pd.DataFrame(df5_list)
        df1 = pd.DataFrame(df1_list)
        result = run_scan(instrument, df5, df1)

        from alerts.telegram_alerts import send_signal
        send_signal(instrument, result)

        # Also open virtual trade if signal YES
        if result['decision'] == "YES":
            from core.virtual_trader import open_trade
            open_trade(instrument, result)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def cmd_backtest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /backtest NIFTY 30
    /backtest BANKNIFTY 2026-01-01 2026-06-01
    """
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage:\n/backtest NIFTY 30\n/backtest NIFTY 2026-01-01 2026-06-01")
        return

    instrument = args[0].upper() if args else config.DEFAULT_INSTRUMENT
    if instrument not in config.FO_INSTRUMENTS:
        await update.message.reply_text(f"Unknown instrument: {instrument}")
        return

    today = date.today()
    try:
        if len(args) == 2 and args[1].isdigit():
            days = int(args[1])
            to_dt   = today - timedelta(days=1)
            from_dt = to_dt - timedelta(days=days)
        elif len(args) == 3:
            from_dt = date.fromisoformat(args[1])
            to_dt   = date.fromisoformat(args[2])
        else:
            to_dt   = today - timedelta(days=1)
            from_dt = to_dt - timedelta(days=30)
    except:
        await update.message.reply_text("Invalid date format. Use YYYY-MM-DD")
        return

    await update.message.reply_text(
        f"⏳ Running backtest: {instrument} | {from_dt} → {to_dt}\n"
        f"Downloading data if needed...")

    try:
        from core.backtest import run_backtest
        from alerts.telegram_alerts import send_backtest_result
        summary, trades, run_id = run_backtest(instrument, from_dt, to_dt, verbose=False)
        if summary:
            send_backtest_result(instrument, summary, run_id)
        else:
            await update.message.reply_text(f"❌ Backtest failed — no data for {instrument}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    today = date.today().isoformat()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM virtual_trades WHERE date=? ORDER BY entry_time", (today,)
    ).fetchall()]
    conn.close()

    if not rows:
        await update.message.reply_text(f"No virtual trades today ({today})")
        return

    lines = [f"📋 <b>Virtual Trades — {today}</b>"]
    for t in rows:
        icon = "✅" if (t.get('pnl_points') or 0) > 0 else "❌" if t['status']=="CLOSED" else "🔄"
        pnl  = f"{t['pnl_points']:+.1f} pts" if t.get('pnl_points') is not None else "OPEN"
        lines.append(f"{icon} {t['instrument']} {t['direction']} | "
                     f"E={t['entry_price']} SL={t['sl_price']} T={t['target_price']} | "
                     f"{pnl} | {t['status']}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from core.virtual_trader import get_today_summary
    lines = [f"📅 <b>Today's Summary — {date.today()}</b>", "━━━━━━━━━━━━━━━━━━"]
    for inst in config.FO_INSTRUMENTS:
        s = get_today_summary(inst)
        if s['trades'] == 0: continue
        icon = "✅" if s['pnl_pts'] > 0 else "❌"
        lines.append(f"{icon} {inst}: {s['trades']} trades | "
                     f"{s['wins']}W/{s['losses']}L | "
                     f"{s['pnl_pts']:+.1f} pts | ₹{s['pnl_rs']:+,.0f}")
    if len(lines) == 2:
        lines.append("No closed trades today.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from core.data_manager import get_data_inventory
    inv = get_data_inventory()
    lines = ["📦 <b>Data Inventory</b>", "━━━━━━━━━━━━━━━━━━"]
    for inst, info in inv.items():
        if info['5min'] > 0:
            lines.append(f"✅ {inst}: 5min={info['5min']} ({info['5min_from']}→{info['5min_to']}) | 1min={info['1min']}")
        else:
            lines.append(f"❌ {inst}: no data")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_params(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    params = {
        "EMA_FAST": config.EMA_FAST, "EMA_SLOW": config.EMA_SLOW,
        "PCR_BULLISH": config.PCR_BULLISH, "PCR_BEARISH": config.PCR_BEARISH,
        "RVOL_MIN_SIGNAL": config.RVOL_MIN_SIGNAL,
        "MAX_SL_POINTS": config.MAX_SL_POINTS,
        "MIN_RR_RATIO": config.MIN_RR_RATIO,
        "MAX_TRADES_PER_DAY": config.MAX_TRADES_PER_DAY,
        "MAX_CONSECUTIVE_LOSS": config.MAX_CONSECUTIVE_LOSS,
        "VSA_HIGH_MULT": config.VSA_HIGH_MULT,
        "VSA_LOW_MULT": config.VSA_LOW_MULT,
        "CONSOLIDATION_MIN_CANDLES": config.CONSOLIDATION_MIN_CANDLES,
        "TRIGGER_BODY_RATIO": config.TRIGGER_BODY_RATIO,
    }
    lines = ["⚙️ <b>Current Parameters</b>", "━━━━━━━━━━━━━━━━━━"]
    for k,v in params.items():
        lines.append(f"  {k} = {v}")
    lines.append("\nUse /setparam NAME VALUE to change.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_setparam(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setparam EMA_FAST 5")
        return
    name  = args[0].upper()
    value = args[1]
    if not hasattr(config, name):
        await update.message.reply_text(f"❌ Unknown parameter: {name}\nUse /params to see valid names.")
        return
    try:
        current = getattr(config, name)
        if isinstance(current, int):   value = int(value)
        elif isinstance(current, float): value = float(value)
        setattr(config, name, value)
        await update.message.reply_text(f"✅ {name} = {value}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def run_bot():
    missing = config.validate()
    if "TELEGRAM_BOT_TOKEN" in missing:
        print("[Bot] TELEGRAM_BOT_TOKEN missing — Telegram bot disabled")
        return
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("signal",   cmd_signal))
    app.add_handler(CommandHandler("backtest", cmd_backtest))
    app.add_handler(CommandHandler("trades",   cmd_trades))
    app.add_handler(CommandHandler("summary",  cmd_summary))
    app.add_handler(CommandHandler("data",     cmd_data))
    app.add_handler(CommandHandler("params",   cmd_params))
    app.add_handler(CommandHandler("setparam", cmd_setparam))
    print("[Bot] Telegram bot started — polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
