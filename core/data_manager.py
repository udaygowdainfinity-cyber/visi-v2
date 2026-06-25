"""VISI v2 — Data Manager. Fetches + caches OHLCV for any F&O instrument."""
import time, pyotp, pandas as pd
from datetime import datetime, timedelta, date
from SmartApi import SmartConnect
import config
from db.database import get_conn

_session = None

def get_session():
    global _session
    if _session:
        return _session
    try:
        obj  = SmartConnect(api_key=config.ANGELONE_API_KEY)
        totp = pyotp.TOTP(config.ANGELONE_TOTP_SECRET).now()
        data = obj.generateSession(config.ANGELONE_CLIENT_ID, config.ANGELONE_MPIN, totp)
        if data['status']:
            _session = obj
            print(f"[Data] AngelOne session OK at {datetime.now().strftime('%H:%M:%S')}")
            return _session
        print(f"[Data] Session failed: {data['message']}")
    except Exception as e:
        print(f"[Data] Session error: {e}")
    return None

def reset_session():
    global _session
    _session = None

def _fetch_ohlcv(token, exchange, interval, from_str, to_str):
    obj = get_session()
    if not obj:
        return []
    try:
        resp = obj.getCandleData({"exchange": exchange, "symboltoken": token,
                                   "interval": interval, "fromdate": from_str, "todate": to_str})
        if resp['status'] and resp['data']:
            return [{"timestamp": c[0], "open": float(c[1]), "high": float(c[2]),
                     "low": float(c[3]), "close": float(c[4]), "volume": int(c[5])}
                    for c in resp['data']]
    except Exception as e:
        print(f"[Data] OHLCV error: {e}")
    return []

def _save(candles, table, instrument):
    if not candles:
        return 0
    conn = get_conn(); c = conn.cursor(); saved = 0
    for row in candles:
        try:
            ts = row['timestamp']
            dt_obj = datetime.fromisoformat(str(ts).replace('Z','').split('+')[0])
            date_str = dt_obj.strftime('%Y-%m-%d')
            ts_str   = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            c.execute(f"INSERT OR IGNORE INTO {table} "
                      f"(instrument,date,timestamp,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?,?)",
                      (instrument, date_str, ts_str,
                       row['open'], row['high'], row['low'], row['close'], row['volume']))
            saved += c.rowcount
        except: pass
    conn.commit(); conn.close()
    return saved

def _load(table, instrument, from_date, to_date):
    conn = get_conn()
    rows = conn.execute(f"SELECT * FROM {table} WHERE instrument=? AND date>=? AND date<=? ORDER BY timestamp",
                        (instrument, str(from_date), str(to_date))).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

def _days_coverage(table, instrument, from_date, to_date):
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT COUNT(DISTINCT date) as d FROM {table} "
                           f"WHERE instrument=? AND date>=? AND date<=?",
                           (instrument, str(from_date), str(to_date))).fetchone()
        conn.close()
        return row['d'] or 0
    except:
        conn.close(); return 0

def fetch_historical(instrument, from_date, to_date, force=False, verbose=True):
    """
    Download 5-min + 1-min candles for instrument between from_date and to_date.
    Uses DB cache. Re-downloads only if force=True or data missing.
    Returns (df5, df1).
    """
    cfg = config.FO_INSTRUMENTS.get(instrument.upper())
    if not cfg:
        print(f"[Data] Unknown instrument: {instrument}")
        return pd.DataFrame(), pd.DataFrame()

    token    = cfg['token']
    exchange = cfg['exchange']

    total_days = sum(1 for i in range((to_date - from_date).days + 1)
                     if (from_date + timedelta(days=i)).weekday() < 5)

    def _download(interval, table, chunk_days, label):
        coverage = _days_coverage(table, instrument, from_date, to_date)
        if not force and coverage >= max(1, total_days - 2):
            if verbose: print(f"[Data] {instrument} {label}: cached ({coverage} days)")
            return _load(table, instrument, from_date, to_date)

        if verbose: print(f"[Data] {instrument} {label}: downloading...")
        # chunk to avoid rate limits
        chunks = []
        cur = datetime.combine(from_date, datetime.min.time())
        end = datetime.combine(to_date,   datetime.min.time())
        while cur <= end:
            chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
            chunks.append((cur, chunk_end))
            cur = chunk_end + timedelta(days=1)

        for i, (cs, ce) in enumerate(chunks):
            from_str = cs.strftime('%Y-%m-%d') + ' 09:00'
            to_str   = ce.strftime('%Y-%m-%d') + ' 15:30'
            if verbose: print(f"  [{i+1}/{len(chunks)}] {from_str[:10]} → {to_str[:10]}", end=' ')
            candles = _fetch_ohlcv(token, exchange, interval, from_str, to_str)
            saved   = _save(candles, table, instrument)
            if verbose: print(f"→ {len(candles)} candles, {saved} new")
            time.sleep(0.6)

        return _load(table, instrument, from_date, to_date)

    df5 = _download('FIVE_MINUTE', 'candles_5min', 50, '5-min')
    df1 = _download('ONE_MINUTE',  'candles_1min', 10, '1-min')
    return df5, df1

def get_live_candles(instrument, interval='FIVE_MINUTE', n=50):
    """Fetch recent live candles for scanning."""
    cfg = config.FO_INSTRUMENTS.get(instrument.upper(), {})
    if not cfg: return []
    minutes_back = n * (5 if interval == 'FIVE_MINUTE' else 1) + 30
    from_dt = (datetime.now() - timedelta(minutes=minutes_back)).strftime('%Y-%m-%d %H:%M')
    to_dt   = datetime.now().strftime('%Y-%m-%d %H:%M')
    return _fetch_ohlcv(cfg['token'], cfg['exchange'], interval, from_dt, to_dt)

def get_data_inventory():
    """Return summary of what's in DB per instrument."""
    conn = get_conn(); result = {}
    for inst in config.FO_INSTRUMENTS:
        try:
            r5 = conn.execute("SELECT COUNT(*) as c, MIN(date) as mn, MAX(date) as mx "
                              "FROM candles_5min WHERE instrument=?", (inst,)).fetchone()
            r1 = conn.execute("SELECT COUNT(*) as c, MIN(date) as mn, MAX(date) as mx "
                              "FROM candles_1min WHERE instrument=?", (inst,)).fetchone()
            result[inst] = {
                "5min": r5['c'] or 0, "5min_from": r5['mn'], "5min_to": r5['mx'],
                "1min": r1['c'] or 0, "1min_from": r1['mn'], "1min_to": r1['mx'],
            }
        except: result[inst] = {"5min": 0, "1min": 0}
    conn.close()
    return result
