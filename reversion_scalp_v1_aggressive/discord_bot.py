import csv
from datetime import datetime, timezone

import requests
from reversion_scalp_v1_aggressive.config import DISCORD_WEBHOOK_URL, NOTIFICATIONS_LOG_PATH, NOTIFICATIONS_CSV_PATH


def _append_notification_log(message: str):
    try:
        NOTIFICATIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NOTIFICATIONS_LOG_PATH.open('a', encoding='utf-8') as f:
            ts = datetime.now(timezone.utc).isoformat()
            f.write(f'[{ts}]\n{message}\n\n')
    except Exception:
        pass


def _append_notification_csv(row: dict):
    try:
        NOTIFICATIONS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_exists = NOTIFICATIONS_CSV_PATH.exists()
        fieldnames = [
            'timestamp', 'event', 'symbol', 'direction', 'entry', 'sl', 'tp',
            'size', 'score', 'exit_reason', 'pnl', 'balance'
        ]
        with NOTIFICATIONS_CSV_PATH.open('a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, '') for k in fieldnames})
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
    _append_notification_csv({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': 'OPEN',
        'symbol': trade.get('symbol'),
        'direction': trade.get('direction'),
        'entry': trade.get('entry'),
        'sl': trade.get('sl'),
        'tp': trade.get('tp'),
        'size': trade.get('size'),
        'score': trade.get('score'),
    })
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
    _append_notification_csv({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': 'CLOSE',
        'symbol': trade.get('symbol'),
        'direction': trade.get('direction'),
        'entry': trade.get('entry'),
        'sl': trade.get('sl'),
        'tp': trade.get('tp'),
        'size': trade.get('size'),
        'score': trade.get('score'),
        'exit_reason': exit_reason,
        'pnl': pnl,
        'balance': balance,
    })
    send_discord(msg)

def notify_risk_blocked(reason: str):
    send_discord(f"⚠️ **RISK BLOCKED:** {reason}")