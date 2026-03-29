import subprocess
import sys
import os
import time
import datetime
import socket
import requests
from keep_alive import keep_alive

keep_alive()

BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
ADMIN_ID  = os.environ.get('ADMIN_ID', '').strip()

# ── Non-recoverable config errors → stop watchdog immediately ──
_CONFIG_ERRORS = [
    "BOT_TOKEN is not set",
    "ADMIN_ID is not set",
    "invalid literal for int",
]

def tg_notify(text):
    if not BOT_TOKEN or not ADMIN_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"[WATCHDOG] Notify failed: {e}")

# ── Start local Stripe Hitter Node.js server (if not already running) ──
_hitter_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stripe_hitter")

def _hitter_already_up():
    try:
        s = socket.create_connection(("localhost", 3001), timeout=2)
        s.close()
        return True
    except Exception:
        return False

_hitter_proc = None
if _hitter_already_up():
    print("[HITTER] Stripe hitter already running on port 3001 — skipping auto-start")
else:
    try:
        _hitter_proc = subprocess.Popen(
            ["node", "proxy-server.js"],
            cwd=_hitter_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[HITTER] Stripe hitter started (PID {_hitter_proc.pid}) on port 3001")
        time.sleep(2)
    except Exception as _e:
        print(f"[HITTER] Failed to start stripe hitter: {_e}")

print("Starting the bot...")
restart_count        = 0
consecutive_fast     = 0       # crashes under 10s in a row
MAX_CONSECUTIVE_FAST = 5       # give up after 5 instant crashes

while True:
    t_start = time.time()
    try:
        result    = subprocess.run(
            [sys.executable, "file1.py"],
            capture_output=True, text=True
        )
        exit_code = result.returncode
        stderr    = (result.stderr or "").strip()
        stdout    = (result.stdout or "").strip()
        runtime   = time.time() - t_start

        # ── Detect non-recoverable config errors ──
        output_combined = stderr + stdout
        for cfg_err in _CONFIG_ERRORS:
            if cfg_err in output_combined:
                print(f"[WATCHDOG] Config error detected: {cfg_err}")
                print(f"[WATCHDOG] Fix your environment variables then restart. Stopping watchdog.")
                sys.exit(1)

        if exit_code == 0:
            consecutive_fast = 0
            print("[WATCHDOG] Bot stopped cleanly (exit 0). Restarting in 5s...")
        else:
            restart_count += 1
            _now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[WATCHDOG] Bot crashed (exit {exit_code}, runtime {runtime:.1f}s). Restart #{restart_count} in 5s...")

            if stderr:
                print(f"[WATCHDOG] stderr: {stderr[:300]}")

            # Fast-crash detection (config/import error loops)
            if runtime < 10:
                consecutive_fast += 1
                if consecutive_fast >= MAX_CONSECUTIVE_FAST:
                    print(f"[WATCHDOG] {consecutive_fast} consecutive fast crashes (<10s). Stopping to prevent spam.")
                    print(f"[WATCHDOG] Last error: {stderr[:400] or stdout[:400]}")
                    tg_notify(
                        f"<b>🛑 WATCHDOG STOPPED\n\n"
                        f"Bot crashed {consecutive_fast}x in a row in under 10s.\n"
                        f"Fix the error and restart manually.\n\n"
                        f"<code>{(stderr or stdout)[:300]}</code></b>"
                    )
                    sys.exit(1)
            else:
                consecutive_fast = 0

            tg_notify(
                f"<b>╔══════════════════════╗\n"
                f"║  🔴  BOT CRASHED!     ║\n"
                f"╚══════════════════════╝\n\n"
                f"⚠️ Bot exited unexpectedly!\n\n"
                f"💥 Exit Code   : <code>{exit_code}</code>\n"
                f"⏱ Runtime     : <code>{runtime:.1f}s</code>\n"
                f"🔄 Restart No  : <code>#{restart_count}</code>\n"
                f"⏰ Time        : <code>{_now}</code>\n"
                f"📋 Error       : <code>{stderr[:200] if stderr else 'none'}</code>\n\n"
                f"♻️ <b>Auto-restarting in 5 seconds...</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"[⌤] YADISTAN - 🍀</b>"
            )

    except Exception as e:
        restart_count += 1
        _now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[WATCHDOG] Error running bot: {e}. Restarting in 5s...")
        tg_notify(
            f"<b>╔══════════════════════╗\n"
            f"║  ⚠️  BOT ERROR!       ║\n"
            f"╚══════════════════════╝\n\n"
            f"🛑 Watchdog caught an error:\n"
            f"<code>{str(e)[:200]}</code>\n\n"
            f"🔄 Restart No : <code>#{restart_count}</code>\n"
            f"⏰ Time       : <code>{_now}</code>\n\n"
            f"♻️ <b>Auto-restarting in 5 seconds...</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"[⌤] YADISTAN - 🍀</b>"
        )

    time.sleep(5)
