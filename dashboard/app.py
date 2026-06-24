"""VISI v2 — Dashboard Flask App. Run: python dashboard/app.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request
from datetime import datetime, date, timedelta
import config
from db.database import get_conn, init_db

app = Flask(__name__, template_folder="templates")

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/status")
def api_status():
    from core.data_manager import get_data_inventory
    from datetime import time as dtime
    now = datetime.now(); t = now.time()
    if now.weekday()>=5: window="WEEKEND"
    elif dtime(9,15)<=t<dtime(9,30): window="PRE-BIAS"
    elif dtime(9,30)<=t<dtime(9,45): window="BIAS WINDOW"
    elif dtime(9,45)<=t<=dtime(14,30): window="ACTIVE TRADING"
    elif dtime(14,30)<t<=dtime(15,30): window="POST-TRADE"
    else: window="MARKET CLOSED"
    missing = config.validate()
    cfg = {name: bool(val) for name,val in config.REQUIRED_CREDENTIALS}
    return jsonify({"time":now.strftime("%Y-%m-%d %H:%M:%S"),"day":now.strftime("%A"),
                    "window":window,"config":cfg,"missing":missing,
                    "inventory":get_data_inventory()})

@app.route("/api/trades")
def api_trades():
    target = request.args.get("date", date.today().isoformat())
    instrument = request.args.get("instrument", "")
    conn = get_conn()
    q = "SELECT * FROM virtual_trades WHERE date=?"
    args = [target]
    if instrument: q += " AND instrument=?"; args.append(instrument)
    q += " ORDER BY entry_time"
    rows = [dict(r) for r in conn.execute(q, args).fetchall()]
    conn.close()
    closed = [r for r in rows if r['status']=='CLOSED']
    return jsonify({"trades":rows,"summary":{
        "total":len(rows),"closed":len(closed),
        "wins":sum(1 for r in closed if (r.get('pnl_points') or 0)>0),
        "pnl_pts":round(sum(r.get('pnl_points') or 0 for r in closed),2),
        "pnl_rs": round(sum(r.get('pnl_rupees')  or 0 for r in closed),2),
    }})

@app.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit",50))
    instrument = request.args.get("instrument","")
    conn = get_conn()
    q = "SELECT * FROM signals"
    args = []
    if instrument: q += " WHERE instrument=?"; args.append(instrument)
    q += f" ORDER BY id DESC LIMIT {limit}"
    rows = [dict(r) for r in conn.execute(q, args).fetchall()]
    conn.close()
    return jsonify({"signals":rows})

@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    p = request.json or {}
    instrument = p.get("instrument", config.DEFAULT_INSTRUMENT).upper()
    from_date  = p.get("from_date", (date.today()-timedelta(days=30)).isoformat())
    to_date    = p.get("to_date",   (date.today()-timedelta(days=1)).isoformat())
    lots       = int(p.get("lots",1))

    # Apply param overrides
    overrides = {}
    param_keys = ["EMA_FAST","EMA_SLOW","PCR_BULLISH","PCR_BEARISH",
                  "RVOL_MIN_SIGNAL","MAX_SL_POINTS","MAX_TRADES_PER_DAY",
                  "MIN_RR_RATIO","MAX_CONSECUTIVE_LOSS"]
    for k in param_keys:
        if k in p: overrides[k] = p[k]

    if instrument not in config.FO_INSTRUMENTS:
        return jsonify({"ok":False,"error":f"Unknown instrument: {instrument}. Valid: {list(config.FO_INSTRUMENTS.keys())}"})

    try:
        from core.backtest import run_backtest
        from_dt = datetime.strptime(from_date,"%Y-%m-%d").date()
        to_dt   = datetime.strptime(to_date,  "%Y-%m-%d").date()
        summary, trades, run_id = run_backtest(instrument, from_dt, to_dt,
                                                lots=lots, params_override=overrides,
                                                verbose=False)
        if not summary:
            return jsonify({"ok":False,"error":"No data — download data first or check credentials"})

        cum=0; curve=[]
        for t in trades: cum+=t['pnl_points']; curve.append(round(cum,2))
        return jsonify({"ok":True,"instrument":instrument,"summary":summary,
                        "trades":trades[-50:],"curve":curve,"run_id":run_id})
    except Exception as e:
        import traceback
        return jsonify({"ok":False,"error":str(e),"trace":traceback.format_exc()})

@app.route("/api/backtest/history")
def api_backtest_history():
    instrument = request.args.get("instrument","")
    conn = get_conn()
    q = "SELECT * FROM backtest_runs"
    args = []
    if instrument: q += " WHERE instrument=?"; args.append(instrument)
    q += " ORDER BY id DESC LIMIT 30"
    rows = [dict(r) for r in conn.execute(q, args).fetchall()]
    conn.close()
    return jsonify({"runs":rows})

@app.route("/api/data/download", methods=["POST"])
def api_data_download():
    p = request.json or {}
    instrument = p.get("instrument", config.DEFAULT_INSTRUMENT).upper()
    from_date  = p.get("from_date", (date.today()-timedelta(days=30)).isoformat())
    to_date    = p.get("to_date",   (date.today()-timedelta(days=1)).isoformat())
    force      = p.get("force", False)
    try:
        from core.data_manager import fetch_historical
        from_dt = datetime.strptime(from_date,"%Y-%m-%d").date()
        to_dt   = datetime.strptime(to_date,  "%Y-%m-%d").date()
        df5, df1 = fetch_historical(instrument, from_dt, to_dt, force=force)
        if df5.empty or df1.empty:
            return jsonify({"ok":False,"error":"No data returned"})
        return jsonify({"ok":True,"instrument":instrument,
                        "5min":len(df5),"1min":len(df1)})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)})

@app.route("/api/params")
def api_params():
    return jsonify({"params":{
        "EMA_FAST":config.EMA_FAST,"EMA_SLOW":config.EMA_SLOW,
        "PCR_BULLISH":config.PCR_BULLISH,"PCR_BEARISH":config.PCR_BEARISH,
        "RVOL_MIN_SIGNAL":config.RVOL_MIN_SIGNAL,
        "MAX_SL_POINTS":config.MAX_SL_POINTS,
        "MAX_TRADES_PER_DAY":config.MAX_TRADES_PER_DAY,
        "MIN_RR_RATIO":config.MIN_RR_RATIO,
        "MAX_CONSECUTIVE_LOSS":config.MAX_CONSECUTIVE_LOSS,
        "VSA_HIGH_MULT":config.VSA_HIGH_MULT,
        "VSA_LOW_MULT":config.VSA_LOW_MULT,
        "TRIGGER_BODY_RATIO":config.TRIGGER_BODY_RATIO,
        "VIRTUAL_CAPITAL":config.VIRTUAL_CAPITAL,
    },"instruments":list(config.FO_INSTRUMENTS.keys())})

if __name__ == "__main__":
    init_db()
    print("\n"+"="*46)
    print("  VISI v2 Dashboard")
    print("  http://localhost:5001/")
    print("="*46+"\n")
    app.run(host="0.0.0.0", port=5001, debug=False)
