from datetime import datetime, timezone

import requests
from reversion_scalp_v1_aggressive.config import DISCORD_WEBHOOK_URL, NOTIFICATIONS_LOG_PATH


def _append_notification_log(message: str):
    try:
        NOTIFICATIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NOTIFICATIONS_LOG_PATH.open('a', encoding='utf-8') as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(f'[{ts}]\n{message}\n\n')
    except Exception:
        pass


def send_discord(message: str):
    _append_notification_log(message)
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception:
        pass  # nunca romper el bot por un fallo de Discord

def notify_open(trade: dict):
    emoji = "🟢" if trade['direction'] == 'LONG' else "🔴"
    msg = (
        f"{emoji} **OPEN {trade['direction']} — {trade['symbol']}**\n"
        f"📍 Entrada: `${trade['entry']:.4f}`\n"
        f"🛑 SL: `${trade['sl']:.4f}`\n"
        f"🎯 TP: `${trade['tp']:.4f}`\n"
        f"📦 Size: `{trade['size']}`\n"
        f"⚡ Score: `{trade.get('score', 0):.3f}`"
    )
    send_discord(msg)

def notify_close(trade: dict, pnl: float, exit_reason: str, balance: float):
    emoji = "✅" if pnl > 0 else "❌"
    pnl_str = f"+${pnl:.4f}" if pnl > 0 else f"-${abs(pnl):.4f}"
    msg = (
        f"{emoji} **CLOSE {trade['direction']} — {trade['symbol']}**\n"
        f"📤 Salida: `{exit_reason}`\n"
        f"💰 P&L: `{pnl_str}`\n"
        f"🏦 Balance: `${balance:.4f}`"
    )
    send_discord(msg)

def notify_risk_blocked(reason: str):
    send_discord(f"⚠️ **RISK BLOCKED:** {reason}")