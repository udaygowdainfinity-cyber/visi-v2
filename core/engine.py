"""VISI v2 — 7-Layer Engine. Works for any F&O instrument."""
import math, pandas as pd
from datetime import datetime, timedelta
import config
from layers.vsa import detect_vsa
from layers.entry import detect_consolidation, detect_trigger_candle, calculate_trade_levels

def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def _vwap(df):
    df = df.copy()
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()
    return df['vwap']

# ── Individual layer evaluators ───────────────────────────────────────────────

def layer1_bias(advancing, declining):
    if advancing > config.AD_BULLISH_THRESHOLD: return "BULLISH"
    if declining > config.AD_BEARISH_THRESHOLD: return "BEARISH"
    return "CHOPPY"

def layer2_ema(df5):
    if len(df5) < config.EMA_SLOW: return "NEUTRAL"
    e9  = _ema(df5['close'], config.EMA_FAST).iloc[-1]
    e21 = _ema(df5['close'], config.EMA_SLOW).iloc[-1]
    cl  = df5['close'].iloc[-1]
    if e9 > e21 and cl > e9:  return "BULLISH"
    if e9 < e21 and cl < e9:  return "BEARISH"
    return "NEUTRAL"

def layer3_vwap(df1):
    if len(df1) < 2: return "NEUTRAL", 0
    vwap_series = _vwap(df1)
    last_close  = df1['close'].iloc[-1]
    last_vwap   = vwap_series.iloc[-1]
    side = "BULLISH" if last_close > last_vwap else "BEARISH"
    return side, round(last_vwap, 2)

def layer4_pcr(pcr):
    if pcr > config.PCR_BULLISH: return "BULLISH", "HIGH"
    if pcr < config.PCR_BEARISH: return "BEARISH", "HIGH"
    return "NEUTRAL", "MEDIUM"

def layer5_vsa(df5_window):
    return detect_vsa(df5_window)

def layer6_rvol(signal_rvol):
    return signal_rvol >= config.RVOL_MIN_SIGNAL

def layer7_entry(df1_slice, bias, vwap_val):
    for end_idx in range(config.CONSOLIDATION_MIN_CANDLES, len(df1_slice)):
        sub = df1_slice.iloc[:end_idx + 1]
        found, zh, zl, _ = detect_consolidation(sub.to_dict('records'))
        if not found: continue
        valid, entry_price, _ = detect_trigger_candle(sub.to_dict('records'), zh, zl, bias)
        if not valid: continue
        sl, target, rr, sl_pts = calculate_trade_levels(bias, entry_price, zh, zl, vwap_val)
        if sl is None: continue
        if sl_pts > config.MAX_SL_POINTS: continue
        return entry_price, sl, target, sl_pts, df1_slice.iloc[end_idx]['dt']
    return None

# ── Missing parameter checker ─────────────────────────────────────────────────

def check_params(instrument, df5, df1, pcr=None):
    """Returns list of missing/invalid parameters."""
    issues = []
    if df5 is None or df5.empty:
        issues.append(f"No 5-min candle data for {instrument} — run data download first")
    elif len(df5) < config.EMA_SLOW:
        issues.append(f"Need at least {config.EMA_SLOW} 5-min candles, got {len(df5)}")
    if df1 is None or df1.empty:
        issues.append(f"No 1-min candle data for {instrument}")
    if pcr is None:
        issues.append("PCR not available — Layer 4 will use neutral default")
    if not config.GROQ_API_KEY:
        issues.append("GROQ_API_KEY missing — AI analysis disabled")
    return issues

# ── Full scan (live) ──────────────────────────────────────────────────────────

def run_scan(instrument, df5, df1, advancing=None, declining=None, pcr=None):
    """
    Run all 7 layers on live data.
    Returns result dict with decision + full layer breakdown.
    """
    result = {
        "instrument": instrument, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "decision": "NO", "bias": None,
        "layers": {}, "signal": None, "entry": None,
        "issues": check_params(instrument, df5, df1, pcr)
    }

    if df5 is None or df5.empty or df1 is None or df1.empty:
        result["decision"] = "NO_DATA"
        return result

    df5 = df5.copy(); df1 = df1.copy()
    df5['dt'] = pd.to_datetime(df5['timestamp'])
    df1['dt'] = pd.to_datetime(df1['timestamp'])

    # L1 — bias from A/D (fallback to L2 EMA if A/D unavailable)
    if advancing is not None and declining is not None:
        bias = layer1_bias(advancing, declining)
        result["layers"]["L1"] = f"A/D {advancing}/{declining} → {bias}"
    else:
        bias_candles = df5[df5['dt'].dt.time <= pd.Timestamp("09:45").time()]
        bias = layer2_ema(bias_candles) if len(bias_candles) >= config.EMA_SLOW else "NEUTRAL"
        result["layers"]["L1"] = f"EMA fallback → {bias}"

    if bias == "CHOPPY" or bias == "NEUTRAL":
        result["layers"]["L1"] += " ⛔ CHOPPY — no trade"
        return result

    result["bias"] = bias

    # L2
    l2 = layer2_ema(df5)
    result["layers"]["L2"] = f"EMA {config.EMA_FAST}/{config.EMA_SLOW} → {l2}"
    if l2 == "NEUTRAL" or l2 != bias:
        result["layers"]["L2"] += " ⛔ conflicts with bias"
        return result

    # L3
    l3_side, vwap_val = layer3_vwap(df1)
    result["layers"]["L3"] = f"VWAP={vwap_val} → price {'above' if l3_side=='BULLISH' else 'below'} → {l3_side}"
    if l3_side != bias:
        result["layers"]["L3"] += " ⛔ conflicts"
        return result

    # L4
    pcr_val = pcr if pcr is not None else 1.0
    l4_sig, l4_conf = layer4_pcr(pcr_val)
    result["layers"]["L4"] = f"PCR={pcr_val:.2f} → {l4_sig} ({l4_conf})"

    # L5 — VSA
    lb = config.VSA_VOLUME_LOOKBACK
    window5 = df5.tail(lb + 5)
    vsa_signals = layer5_vsa(window5)
    bias_signals = [s for s in vsa_signals if s['direction'] == bias]
    cab_signals  = [s for s in vsa_signals if s['name'] == 'CAB']
    result["layers"]["L5"] = f"VSA → {[s['name'] for s in vsa_signals] or 'None'}"

    if cab_signals:
        result["layers"]["L5"] += " ⚠️ CAB reversal warning"
    if not bias_signals:
        result["layers"]["L5"] += " ⛔ no matching signal"
        return result

    best = bias_signals[0]
    result["signal"] = best

    # L6 — RVOL
    rvol_ok = layer6_rvol(best['rvol'])
    result["layers"]["L6"] = f"RVOL={best['rvol']:.2f} min={config.RVOL_MIN_SIGNAL} → {'✅' if rvol_ok else '⛔'}"
    if not rvol_ok:
        return result

    # L7 — Entry
    signal_time = df5['dt'].iloc[-1]
    next_1min = df1[
        (df1['dt'] > signal_time) &
        (df1['dt'] <= signal_time + timedelta(minutes=15))
    ].reset_index(drop=True)

    entry_result = layer7_entry(next_1min, bias, vwap_val) if len(next_1min) >= config.CONSOLIDATION_MIN_CANDLES + 1 else None
    result["layers"]["L7"] = f"1-min candles available: {len(next_1min)}"

    if not entry_result:
        result["layers"]["L7"] += " — watching for consolidation+trigger"
        return result

    entry_price, sl, target, sl_pts, trigger_time = entry_result
    result["layers"]["L7"] += f" ✅ Entry={entry_price} SL={sl} TGT={target} SL_pts={sl_pts}"
    result["entry"] = {
        "price": entry_price, "sl": sl, "target": target,
        "sl_points": sl_pts, "trigger_time": str(trigger_time),
        "direction": bias, "vwap": vwap_val
    }
    result["decision"] = "YES"
    return result

# ── Backtest day ──────────────────────────────────────────────────────────────

def backtest_day(day, df5, df1, pcr=1.0, lots=1):
    trades = []
    df5 = df5.copy(); df1 = df1.copy()
    df5['dt'] = pd.to_datetime(df5['timestamp'])
    df1['dt'] = pd.to_datetime(df1['timestamp'])

    # L1+L2 combined bias (A/D not available historically — use EMA)
    bias_candles = df5[df5['dt'].dt.time <= pd.Timestamp("09:45").time()]
    if len(bias_candles) < config.EMA_SLOW:
        return []
    bias = layer2_ema(bias_candles)
    if bias == "NEUTRAL":
        return []

    trades_today = 0; consec_loss = 0

    active = df5[
        (df5['dt'].dt.time >= pd.Timestamp("09:45").time()) &
        (df5['dt'].dt.time <= pd.Timestamp("14:30").time())
    ].reset_index(drop=True)

    i = config.VSA_VOLUME_LOOKBACK
    while i < len(active):
        if trades_today >= config.MAX_TRADES_PER_DAY: break
        if consec_loss  >= config.MAX_CONSECUTIVE_LOSS: break

        row = active.iloc[i]

        # L3
        prefix_1min = df1[df1['dt'] <= row['dt']].reset_index(drop=True)
        if len(prefix_1min) < 5: i += 1; continue
        l3_side, vwap_val = layer3_vwap(prefix_1min)
        if l3_side != bias: i += 1; continue

        # L5
        window5 = active.iloc[max(0, i - config.VSA_VOLUME_LOOKBACK): i + 1]
        vsa_sigs = layer5_vsa(window5)
        bias_sigs = [s for s in vsa_sigs if s['direction'] == bias]
        if not bias_sigs: i += 1; continue
        best = bias_sigs[0]
        if best['name'] == 'CAB': i += 1; continue

        # L6
        if not layer6_rvol(best['rvol']): i += 1; continue

        # L7
        signal_time = row['dt']
        next_1min = df1[
            (df1['dt'] > signal_time) &
            (df1['dt'] <= signal_time + timedelta(minutes=15))
        ].reset_index(drop=True)
        if len(next_1min) < config.CONSOLIDATION_MIN_CANDLES + 1: i += 1; continue

        entry_result = layer7_entry(next_1min, bias, vwap_val)
        if not entry_result: i += 1; continue

        entry_price, sl, target, sl_pts, trigger_time = entry_result

        # Simulate outcome
        future = df1[df1['dt'] > trigger_time].reset_index(drop=True)
        exit_price, exit_reason, exit_time = _simulate_trade(bias, entry_price, sl, target, future)

        pnl_pts = (exit_price - entry_price) if bias == "CE" else (entry_price - exit_price)

        trades.append({
            "date": day, "entry_time": trigger_time.strftime("%H:%M"),
            "exit_time": exit_time, "direction": bias,
            "entry_price": entry_price, "sl_price": sl, "target_price": target,
            "exit_price": exit_price, "pnl_points": round(pnl_pts, 2),
            "exit_reason": exit_reason, "vsa_signal": best['name'],
            "rvol": best['rvol'], "layers_passed": 7
        })
        trades_today += 1
        consec_loss = consec_loss + 1 if pnl_pts < 0 else 0

        trade_end = pd.Timestamp(exit_time) if isinstance(exit_time, str) else exit_time
        i = next((j for j in range(i, len(active)) if active.iloc[j]['dt'] >= trade_end), len(active))

    return trades

def _simulate_trade(direction, entry, sl, target, future_1min):
    for _, row in future_1min.iterrows():
        if direction == "CE":
            if row['low']  <= sl:     return sl,     "SL",     row['dt'].strftime("%H:%M")
            if row['high'] >= target: return target, "Target", row['dt'].strftime("%H:%M")
        else:
            if row['high'] >= sl:     return sl,     "SL",     row['dt'].strftime("%H:%M")
            if row['low']  <= target: return target, "Target", row['dt'].strftime("%H:%M")
        if row['dt'].hour == 14 and row['dt'].minute >= 30:
            return row['close'], "TimeStop", row['dt'].strftime("%H:%M")
    if len(future_1min):
        last = future_1min.iloc[-1]
        return last['close'], "EOD", last['dt'].strftime("%H:%M")
    return entry, "NoExit", ""
