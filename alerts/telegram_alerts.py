"""VISI v2 — Telegram Alerts. Sends formatted messages."""
import requests, config
from datetime import datetime

def _send(text):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"[TG] (no token) {text[:80]}")
        return
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID,
                                  "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[TG] Send error: {e}")

def send_signal(instrument, scan_result):
    layers = scan_result.get("layers", {})
    entry  = scan_result.get("entry")
    signal = scan_result.get("signal")
    bias   = scan_result.get("bias", "?")
    decision = scan_result.get("decision", "NO")

    if decision == "YES" and entry:
        msg = (
            f"🚦 <b>VISI SIGNAL — {instrument}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Direction : <b>{entry['direction']}</b>\n"
            f"💰 Entry     : <b>{entry['price']}</b>\n"
            f"🛑 SL        : {entry['sl']}  ({entry['sl_points']} pts)\n"
            f"🎯 Target    : {entry['target']}\n"
            f"📊 VWAP      : {entry.get('vwap', '—')}\n"
            f"📈 VSA       : {signal['name'] if signal else '—'}  RVOL={signal['rvol'] if signal else '—'}x\n"
            f"⏰ Time      : {datetime.now().strftime('%H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Virtual trade opened automatically</i>"
        )
    else:
        issues = scan_result.get("issues", [])
        layer_summary = "\n".join(f"  {k}: {v}" for k,v in layers.items())
        msg = (
            f"🔍 <b>VISI SCAN — {instrument}</b>\n"
            f"Bias: {bias}  Decision: {decision}\n"
            f"{layer_summary}\n"
        )
        if issues:
            msg += f"\n⚠️ Issues:\n" + "\n".join(f"  • {i}" for i in issues)

    _send(msg)

def send_trade_closed(instrument, trade_id, pnl_pts, pnl_rs, reason):
    icon = "✅ WIN" if pnl_pts > 0 else "❌ LOSS"
    msg = (
        f"{icon} <b>{instrument} Virtual Trade #{trade_id}</b>\n"
        f"PnL: <b>{pnl_pts:+.1f} pts</b>  (₹{pnl_rs:+,.0f})\n"
        f"Reason: {reason} | {datetime.now().strftime('%H:%M')}"
    )
    _send(msg)

def send_daily_summary(summary_dict):
    lines = ["📅 <b>VISI Daily Summary</b>", "━━━━━━━━━━━━━━━━━━"]
    for inst, s in summary_dict.items():
        icon = "✅" if s['pnl_pts'] > 0 else "❌" if s['pnl_pts'] < 0 else "➖"
        lines.append(f"{icon} <b>{inst}</b>: {s['trades']} trades | "
                     f"{s['wins']}W/{s['losses']}L | "
                     f"{s['pnl_pts']:+.1f} pts | ₹{s['pnl_rs']:+,.0f}")
    _send("\n".join(lines))

def send_backtest_result(instrument, summary, run_id):
    pf = summary['profit_factor']
    pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
    msg = (
        f"📊 <b>Backtest Complete — {instrument}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Trades : {summary['total_trades']}\n"
        f"Win %  : {summary['win_rate']}%  ({summary['wins']}W / {summary['losses']}L)\n"
        f"PnL    : {summary['total_pnl']:+.1f} pts\n"
        f"Avg W  : {summary['avg_win']:+.1f}  Avg L: {summary['avg_loss']:+.1f}\n"
        f"Max DD : {summary['max_drawdown']:.1f} pts\n"
        f"PF     : {pf_str}  Sharpe: {summary['sharpe_ratio']:.2f}\n"
        f"Run ID : #{run_id}"
    )
    _send(msg)

def send_missing_params(missing):
    msg = (
        f"⚠️ <b>VISI — Missing Parameters</b>\n"
        f"The following are not configured:\n"
        + "\n".join(f"  • {m}" for m in missing)
        + "\n\nAdd them to your .env file and restart."
    )
    _send(msg)

def send_status(status_dict):
    lines = ["🤖 <b>VISI Bot Status</b>", "━━━━━━━━━━━━━━━━━━"]
    for k,v in status_dict.items():
        lines.append(f"  {k}: {v}")
    _send("\n".join(lines))
