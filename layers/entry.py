"""VISI v2 Layer 7 — Entry. Reused from original."""
import pandas as pd
import config

def calculate_rvol(candles):
    if len(candles) < 5: return 1.0, 0
    df=pd.DataFrame(candles)
    avg=df['volume'].iloc[:-1].mean()
    if avg==0: return 1.0,0
    return round(df['volume'].iloc[-1]/avg,2), avg

def detect_consolidation(candles_1min):
    df=pd.DataFrame(candles_1min)
    if len(df)<config.CONSOLIDATION_MIN_CANDLES+1: return False,0,0,0
    window=df.iloc[-(config.CONSOLIDATION_MAX_CANDLES+1):]
    ranges=(window['high']-window['low']).values; volumes=window['volume'].values
    n=len(window)
    for length in range(config.CONSOLIDATION_MAX_CANDLES,config.CONSOLIDATION_MIN_CANDLES-1,-1):
        start=n-length
        if start<0: continue
        sub_rng=ranges[start:]; sub_vol=volumes[start:]
        range_ok=all(sub_rng[i]<=sub_rng[i-1]*1.1 for i in range(1,len(sub_rng)))
        half=max(1,len(sub_vol)//2)
        vol_ok=sub_vol[half:].mean()<=sub_vol[:half].mean()*1.1 if half<len(sub_vol) else True
        if range_ok and vol_ok:
            zh=window['high'].iloc[start:].max(); zl=window['low'].iloc[start:].min()
            if zh-zl>0: return True,round(zh,2),round(zl,2),length
    return False,0,0,0

def detect_trigger_candle(candles_1min,zone_high,zone_low,direction):
    df=pd.DataFrame(candles_1min); last=df.iloc[-1]
    body=abs(last['close']-last['open']); rng=last['high']-last['low']
    if rng==0: return False,0,0
    body_ratio=body/rng
    rvol,_=calculate_rvol(candles_1min); rvol=rvol or 0
    if direction=="CE":
        dir_ok=last['close']>zone_high and last['close']>last['open']
    else:
        dir_ok=last['close']<zone_low and last['close']<last['open']
    valid=dir_ok and body_ratio>=config.TRIGGER_BODY_RATIO and rvol>=config.RVOL_MIN_SIGNAL
    return valid,round(last['close'],2),round(rvol,2)

def calculate_trade_levels(direction,entry_price,zone_high,zone_low,vwap):
    sl=zone_low if direction=="CE" else zone_high
    sl_pts=abs(entry_price-sl)
    if sl_pts>config.MAX_SL_POINTS: return None,None,0,sl_pts
    if direction=="CE":
        target=entry_price+(sl_pts*config.MIN_RR_RATIO)
    else:
        target=entry_price-(sl_pts*config.MIN_RR_RATIO)
    return round(sl,2),round(target,2),config.MIN_RR_RATIO,round(sl_pts,2)
