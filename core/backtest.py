"""VISI v2 — Backtest Runner"""
import json, math, pandas as pd
from datetime import date
from db.database import get_conn
from core.engine import backtest_day
from core.data_manager import fetch_historical
import config

def compute_summary(trades):
    if not trades:
        return {"total_trades":0,"wins":0,"losses":0,"win_rate":0,"total_pnl":0,
                "avg_win":0,"avg_loss":0,"max_drawdown":0,"profit_factor":0,
                "sharpe_ratio":0,"calmar_ratio":0}
    pnls   = [t['pnl_points'] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    cum=0; peak=0; max_dd=0
    for p in pnls:
        cum+=p; peak=max(peak,cum); max_dd=max(max_dd,peak-cum)
    gp = sum(wins); gl = abs(sum(losses))
    mean = sum(pnls)/len(pnls) if pnls else 0
    std  = math.sqrt(sum((p-mean)**2 for p in pnls)/(len(pnls)-1)) if len(pnls)>1 else 0
    sharpe = round((mean/std)*math.sqrt(252),2) if std>0 else 0
    calmar = round(sum(pnls)/max_dd,2) if max_dd>0 else float('inf')
    return {
        "total_trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins)/len(trades)*100,1),
        "total_pnl": round(sum(pnls),2),
        "avg_win":  round(gp/len(wins),2) if wins else 0,
        "avg_loss": round(sum(losses)/len(losses),2) if losses else 0,
        "max_drawdown": round(max_dd,2),
        "profit_factor": round(gp/gl,2) if gl>0 else float('inf'),
        "sharpe_ratio": sharpe, "calmar_ratio": calmar,
    }

def run_backtest(instrument, from_date, to_date, lots=1, params_override=None, verbose=True):
    """
    Full backtest for any F&O instrument.
    Downloads data if not cached. Returns (summary, trades, run_id).
    """
    if params_override:
        for k,v in params_override.items():
            if hasattr(config, k): setattr(config, k, v)

    if verbose: print(f"\n[BT] {instrument} | {from_date} → {to_date} | Lots: {lots}")

    df5, df1 = fetch_historical(instrument, from_date, to_date, verbose=verbose)
    if df5.empty or df1.empty:
        print(f"[BT] ❌ No data for {instrument}. Check credentials and date range.")
        return None, [], None

    df5['dt'] = pd.to_datetime(df5['timestamp'])
    df1['dt'] = pd.to_datetime(df1['timestamp'])
    df5['date_str'] = df5['dt'].dt.date.astype(str)
    df1['date_str'] = df1['dt'].dt.date.astype(str)

    trade_days = sorted(df5['date_str'].unique())
    if verbose: print(f"[BT] Trading days: {len(trade_days)}")

    all_trades = []
    for day in trade_days:
        day_trades = backtest_day(
            day,
            df5[df5['date_str']==day].reset_index(drop=True),
            df1[df1['date_str']==day].reset_index(drop=True),
            pcr=1.0, lots=lots
        )
        all_trades.extend(day_trades)
        if verbose and day_trades:
            pnl = sum(t['pnl_points'] for t in day_trades)
            print(f"  {day}: {len(day_trades)} trades | PnL={pnl:+.1f} pts")

    summary  = compute_summary(all_trades)
    run_id   = _save_run(instrument, from_date, to_date, summary, all_trades, lots, params_override)

    if verbose:
        print(f"\n{'='*50}")
        print(f"  {instrument} BACKTEST RESULTS")
        print(f"{'='*50}")
        print(f"  Trades:        {summary['total_trades']}")
        print(f"  Win Rate:      {summary['win_rate']}%  ({summary['wins']}W / {summary['losses']}L)")
        print(f"  Total PnL:     {summary['total_pnl']:+.1f} pts")
        print(f"  Avg Win:       {summary['avg_win']:+.1f} pts")
        print(f"  Avg Loss:      {summary['avg_loss']:+.1f} pts")
        print(f"  Max Drawdown:  {summary['max_drawdown']:.1f} pts")
        print(f"  Profit Factor: {summary['profit_factor']:.2f}")
        print(f"  Sharpe:        {summary['sharpe_ratio']:.2f}")
        print(f"{'='*50}\n")

    return summary, all_trades, run_id

def _save_run(instrument, from_date, to_date, summary, trades, lots, params):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO backtest_runs
        (instrument,run_date,from_date,to_date,total_trades,wins,losses,
         win_rate,total_pnl,avg_win,avg_loss,max_drawdown,profit_factor,
         sharpe_ratio,calmar_ratio,params_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (instrument, date.today().isoformat(), str(from_date), str(to_date),
         summary['total_trades'], summary['wins'], summary['losses'],
         summary['win_rate'], summary['total_pnl'], summary['avg_win'],
         summary['avg_loss'], summary['max_drawdown'], summary['profit_factor'],
         summary['sharpe_ratio'], summary['calmar_ratio'],
         json.dumps(params or {})))
    run_id = c.lastrowid
    for t in trades:
        c.execute("""INSERT INTO backtest_trades
            (run_id,instrument,date,entry_time,exit_time,direction,
             entry_price,sl_price,target_price,exit_price,pnl_points,
             exit_reason,vsa_signal,rvol)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, instrument, t['date'], t['entry_time'], t['exit_time'],
             t['direction'], t['entry_price'], t['sl_price'], t['target_price'],
             t['exit_price'], t['pnl_points'], t['exit_reason'],
             t['vsa_signal'], t['rvol']))
    conn.commit(); conn.close()
    print(f"[BT] Saved run_id={run_id}")
    return run_id
