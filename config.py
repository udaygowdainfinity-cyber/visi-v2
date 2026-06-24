"""VISI v2 — Configuration. Credentials via .env only."""
import os
from dotenv import load_dotenv
load_dotenv()

ANGELONE_API_KEY     = os.environ.get("ANGELONE_API_KEY", "")
ANGELONE_CLIENT_ID   = os.environ.get("ANGELONE_CLIENT_ID", "")
ANGELONE_MPIN        = os.environ.get("ANGELONE_MPIN", "")
ANGELONE_TOTP_SECRET = os.environ.get("ANGELONE_TOTP_SECRET", "")
TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL           = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS      = 150
DB_PATH              = os.environ.get("DB_PATH", "visi_v2.db")

FO_INSTRUMENTS = {
    "NIFTY":      {"token": "99926000", "exchange": "NSE", "lot_size": 25,  "index": True},
    "BANKNIFTY":  {"token": "99926009", "exchange": "NSE", "lot_size": 15,  "index": True},
    "FINNIFTY":   {"token": "99926037", "exchange": "NSE", "lot_size": 40,  "index": True},
    "MIDCPNIFTY": {"token": "99926074", "exchange": "NSE", "lot_size": 75,  "index": True},
    "SENSEX":     {"token": "99919000", "exchange": "BSE", "lot_size": 10,  "index": True},
    "BANKEX":     {"token": "99919001", "exchange": "BSE", "lot_size": 15,  "index": True},
}
DEFAULT_INSTRUMENT   = "NIFTY"

MARKET_OPEN   = "09:15"
ACTIVE_START  = "09:45"
ACTIVE_END    = "14:30"
MARKET_CLOSE  = "15:30"

AD_BULLISH_THRESHOLD = 32
AD_BEARISH_THRESHOLD = 32
NIFTY50_SYMBOLS = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK",
    "BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV","BPCL","BHARTIARTL",
    "BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY",
    "EICHERMOT","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE",
    "HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","ITC",
    "INDUSINDBK","INFY","JSWSTEEL","KOTAKBANK","LT",
    "LTIM","M&M","MARUTI","NESTLEIND","NTPC",
    "ONGC","POWERGRID","RELIANCE","SBILIFE","SHRIRAMFIN",
    "SBIN","SUNPHARMA","TCS","TATACONSUM","TATAMOTORS",
    "TATASTEEL","TECHM","TITAN","ULTRACEMCO","WIPRO"
]

EMA_FAST             = 9
EMA_SLOW             = 21
PCR_BULLISH          = 1.2
PCR_BEARISH          = 0.8
VSA_VOLUME_LOOKBACK  = 20
VSA_ULTRA_HIGH_MULT  = 2.5
VSA_HIGH_MULT        = 1.5
VSA_LOW_MULT         = 0.7
VSA_BODY_RATIO_CAB   = 0.4
RVOL_MIN_SIGNAL      = 1.5
RVOL_STRONG_BREAKOUT = 2.0
RVOL_CLIMACTIC       = 3.0
CONSOLIDATION_MIN_CANDLES = 3
CONSOLIDATION_MAX_CANDLES = 6
TRIGGER_BODY_RATIO        = 0.60
ENTRY_CHASE_LIMIT         = 5
MAX_TRADES_PER_DAY        = 3
MAX_SL_POINTS             = 12
MIN_RR_RATIO              = 2.0
MAX_CONSECUTIVE_LOSS      = 2
VIRTUAL_CAPITAL           = 100000
SCAN_INTERVAL_SECONDS     = 60

REQUIRED_CREDENTIALS = [
    ("ANGELONE_API_KEY",     ANGELONE_API_KEY),
    ("ANGELONE_CLIENT_ID",   ANGELONE_CLIENT_ID),
    ("ANGELONE_MPIN",    ANGELONE_MPIN),
    ("ANGELONE_TOTP_SECRET", ANGELONE_TOTP_SECRET),
    ("TELEGRAM_BOT_TOKEN",   TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_CHAT_ID",     TELEGRAM_CHAT_ID),
    ("GROQ_API_KEY",         GROQ_API_KEY),
]

def validate():
    return [name for name, val in REQUIRED_CREDENTIALS if not val]

def validate_or_warn():
    missing = validate()
    if missing:
        print(f"[Config] ⚠️  Missing: {', '.join(missing)} — add to .env")
    return missing
