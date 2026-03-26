from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    binance_fee_rate: float = float(os.getenv('BINANCE_FEE_RATE', '0.00055'))
    bybit_fee_rate: float = float(os.getenv('BYBIT_FEE_RATE', '0.00055'))
    paper_initial_balance: float = float(os.getenv('PAPER_INITIAL_BALANCE', '10000'))
    paper_slippage_bps: float = float(os.getenv('PAPER_SLIPPAGE_BPS', '4'))
    entry_threshold_pct: float = float(os.getenv('ENTRY_THRESHOLD_PCT', '0.13'))
    exit_threshold_pct: float = float(os.getenv('EXIT_THRESHOLD_PCT', '0.03'))
    notional_usd: float = float(os.getenv('NOTIONAL_USD', '750'))
    feed_mode: str = os.getenv('FEED_MODE', 'live').strip().lower()
    symbols: list[str] = [item.strip().upper() for item in os.getenv('SYMBOLS', 'BRUSDT,LYNUSDT,JCTUSDT').split(',') if item.strip()]


settings = Settings()
