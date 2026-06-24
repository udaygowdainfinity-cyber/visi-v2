"""VISI v2 Layer 5 — VSA. Reused from original."""
import pandas as pd
import config

def detect_vsa(df):
    lb = config.VSA_VOLUME_LOOKBACK
    if len(df) < lb + 2: return []
    df = df.copy().reset_index(drop=True)
    avg_vol = df['volume'].rolling(lb).mean()
    avg_rng = (df['high'] - df['low']).rolling(lb).mean()
    df['avg_vol']=avg_vol; df['avg_rng']=avg_rng
    df['body']=abs(df['close']-df['open']); df['rng']=df['high']-df['low']
    df['rvol']=df['volume']/avg_vol
    df['roll_high5']=df['high'].shift(1).rolling(5).max()
    df['roll_low5'] =df['low'].shift(1).rolling(5).min()
    signals=[]; row=df.iloc[-1]
    is_green=row['close']>row['open']; is_red=row['close']<row['open']
    vol=row['volume']; avg_v=row['avg_vol']; avg_r=row['avg_rng']
    rng=row['rng']; body=row['body']; rvol=row['rvol']
    if is_green and vol<avg_v*config.VSA_LOW_MULT and rng<avg_r:
        signals.append({'name':'No Demand','direction':'PE','strength':'MEDIUM','rvol':round(rvol,2)})
    if is_red and row['high']>row['roll_high5'] and vol>avg_v*config.VSA_HIGH_MULT:
        signals.append({'name':'Up Thrust','direction':'PE','strength':'HIGH','rvol':round(rvol,2)})
    if is_red and vol<avg_v*config.VSA_LOW_MULT and rng<avg_r:
        signals.append({'name':'No Supply','direction':'CE','strength':'MEDIUM','rvol':round(rvol,2)})
    if is_green and row['low']<row['roll_low5'] and vol>avg_v*config.VSA_HIGH_MULT:
        signals.append({'name':'Spring','direction':'CE','strength':'HIGH','rvol':round(rvol,2)})
    if vol>avg_v*config.VSA_ULTRA_HIGH_MULT and rng>0 and body<rng*config.VSA_BODY_RATIO_CAB:
        signals.append({'name':'CAB','direction':'REVERSAL','strength':'EXTREME','rvol':round(rvol,2)})
    return signals
