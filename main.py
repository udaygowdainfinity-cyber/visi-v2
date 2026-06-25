import sys, os
print("Starting VISI v2...", flush=True)

try:
    import config
    print(f"[Config] Loaded", flush=True)
except Exception as e:
    print(f"[Config] ERROR: {e}", flush=True)
    sys.exit(1)

try:
    from db.database import init_db
    init_db()
except Exception as e:
    print(f"[DB] ERROR: {e}", flush=True)
    sys.exit(1)

try:
    from telegram_bot import run_bot
    print("[Bot] Starting Telegram...", flush=True)
    run_bot()
except Exception as e:
    print(f"[Bot] ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)