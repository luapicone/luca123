import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from tick_vampire_v3.calendar import news_blackout_active
from tick_vampire_v3.config import INITIAL_BALANCE, SYMBOL, SESSIONS
from tick_vampire_v3.db import init_db, insert_trade
from tick_vampire_v3.execution import execute_trade
from tick_vampire_v3.report import format_session_report
from tick_vampire_v3.risk import risk_checks
from tick_vampire_v3.state import BotState

LOG_PATH = Path('tick_vampire_v3/tick_vampire.log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', default=True)
    args = parser.parse_args()

    init_db()
    state = BotState(balance=INITIAL_BALANCE, session_open_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    ok, reason = risk_checks(state)
    logging.info('Tick Vampire v3 paper-first scaffold ready | dry_run=%s | risk_ok=%s | reason=%s | symbol=%s', args.dry_run, ok, reason, SYMBOL)
    if news_blackout_active():
        logging.info('News blackout active.')
    report = format_session_report({
        'datetime': datetime.now(timezone.utc).isoformat(),
        'session': 'N/A',
        'trades': 0,
        'wins': 0,
        'losses': 0,
        'wr': 0.0,
        'pnl': 0.0,
        'pnl_pct': 0.0,
        'start': state.session_open_balance,
        'end': state.balance,
        'best': 0.0,
        'worst': 0.0,
        'skipped': 0,
        'halt': reason or 'no',
    })
    print(report)

if __name__ == '__main__':
    main()
