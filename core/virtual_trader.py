"""VISI v2 — Virtual Trader. Logs all trades as paper trades. No real money."""
from datetime import datetime, date
from db.database import get_conn
import config

def open_trade(instrument, scan_result):
    """Record a virtual trade open from scan result."""
    entry = scan_result.get("entry")
    signal = scan_result.get("signal")
    if not entry: return None

    cfg = config.FO_INSTRUMENTS.get(instrument.upper(), {})
    lot_size = cfg.get("lot_size", 25)
    lots = 1

    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO virtual_trades
        (instrument,date,entry_time,direction,entry_price,sl_price,target_price,
         sl_points,lots,lot_size,vsa_signal,rvol,layers_passed,status,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,7,'OPEN',?)""",
        (instrument, date.today().isoformat(),
         datetime.now().strftime("%H:%M"),
         entry['direction'], entry['price'], entry['sl'], entry['target'],
         entry['sl_points'], lots, lot_size,
         signal['name'] if signal else '', signal['rvol'] if signal else 0,
         f"VWAP={entry.get('vwap',0)}"))
    trade_id = c.lastrowid
    conn.commit(); conn.close()
    print(f"[VT] Trade #{trade_id} OPENED: {instrument} {entry['direction']} @ {entry['price']}")
    return trade_id

def close_trade(trade_id, exit_price, exit_reason):
    """Close a virtual trade and calculate P&L."""
    conn = get_conn()
    trade = dict(conn.execute(
        "SELECT * FROM virtual_trades WHERE id=?", (trade_id,)
    ).fetchone() or {})

    if not trade:
        conn.close(); return None

    direction   = trade['direction']
    entry_price = trade['entry_price']
    lot_size    = trade['lot_size'] or 25
    lots        = trade['lots'] or 1

    if direction == "CE":
        pnl_pts = round(exit_price - entry_price, 2)
    else:
        pnl_pts = round(entry_price - exit_price, 2)

    pnl_rs = round(pnl_pts * lot_size * lots, 2)

    conn.execute("""UPDATE virtual_trades SET
        exit_time=?, exit_price=?, pnl_points=?, pnl_rupees=?,
        exit_reason=?, status='CLOSED'
        WHERE id=?""",
        (datetime.now().strftime("%H:%M"), exit_price, pnl_pts, pnl_rs,
         exit_reason, trade_id))
    conn.commit(); conn.close()
    icon = "✅" if pnl_pts > 0 else "❌"
    print(f"[VT] {icon} Trade #{trade_id} CLOSED: {exit_reason} PnL={pnl_pts:+.1f} pts ₹{pnl_rs:+,.0f}")
    return {"pnl_points": pnl_pts, "pnl_rupees": pnl_rs, "exit_reason": exit_reason}

def monitor_open_trades(live_price_fn):
    """Check all open trades against live prices. Close if SL/Target hit."""
    conn = get_conn()
    open_trades = [dict(r) for r in conn.execute(
        "SELECT * FROM virtual_trades WHERE status='OPEN'"
    ).fetchall()]
    conn.close()

    for trade in open_trades:
        try:
            price = live_price_fn(trade['instrument'])
            if price is None: continue

            if trade['direction'] == "CE":
                if price <= trade['sl_price']:
                    close_trade(trade['id'], trade['sl_price'], "SL")
                elif price >= trade['target_price']:
                    close_trade(trade['id'], trade['target_price'], "Target")
            else:
                if price >= trade['sl_price']:
                    close_trade(trade['id'], trade['sl_price'], "SL")
                elif price <= trade['target_price']:
                    close_trade(trade['id'], trade['target_price'], "Target")
        except Exception as e:
            print(f"[VT] Monitor error trade #{trade['id']}: {e}")

def get_today_summary(instrument=None):
    today = date.today().isoformat()
    conn  = get_conn()
    query = "SELECT * FROM virtual_trades WHERE date=? AND status='CLOSED'"
    args  = [today]
    if instrument:
        query += " AND instrument=?"; args.append(instrument)
    trades = [dict(r) for r in conn.execute(query, args).fetchall()]
    conn.close()
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "pnl_pts": 0, "pnl_rs": 0}
    wins = sum(1 for t in trades if (t.get('pnl_points') or 0) > 0)
    return {
        "trades": len(trades), "wins": wins, "losses": len(trades)-wins,
        "pnl_pts": round(sum(t.get('pnl_points') or 0 for t in trades), 2),
        "pnl_rs":  round(sum(t.get('pnl_rupees')  or 0 for t in trades), 2),
    }
