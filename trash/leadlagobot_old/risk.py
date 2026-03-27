from pathlib import Path
import json
from leadlagobot.config.settings import settings


class RiskEngine:
    def __init__(self, state_path: str = 'data/risk_state.json'):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_realized_pnl = 0.0
        self.cancelled = 0
        self.total_signals = 0

    def load(self):
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding='utf8'))
            self.daily_realized_pnl = data.get('daily_realized_pnl', 0.0)
            self.cancelled = data.get('cancelled', 0)
            self.total_signals = data.get('total_signals', 0)
        except Exception:
            pass

    def flush(self):
        self.state_path.write_text(json.dumps({
            'daily_realized_pnl': self.daily_realized_pnl,
            'cancelled': self.cancelled,
            'total_signals': self.total_signals,
        }, indent=2), encoding='utf8')

    def kill_switch_active(self) -> bool:
        return Path(settings.kill_switch_file).exists()

    def register_signal(self):
        self.total_signals += 1

    def register_cancel(self):
        self.cancelled += 1

    def register_trade(self, net_pnl: float):
        self.daily_realized_pnl += net_pnl

    def cancel_rate(self) -> float:
        if self.total_signals <= 0:
            return 0.0
        return self.cancelled / self.total_signals

    def validate_entry(self, open_positions: int, current_exposure_usd: float, expected_worst_loss_usd: float):
        if not settings.risk_enabled:
            return True, 'risk_disabled'
        if self.kill_switch_active():
            return False, 'kill_switch_active'
        if self.daily_realized_pnl <= -abs(settings.max_daily_loss_usd):
            return False, 'max_daily_loss_reached'
        if open_positions >= settings.max_open_positions:
            return False, 'max_open_positions_reached'
        if current_exposure_usd + settings.notional_usd > settings.max_exposure_usd:
            return False, 'max_exposure_reached'
        if expected_worst_loss_usd > settings.max_loss_per_trade_usd:
            return False, 'max_loss_per_trade_exceeded'
        if self.cancel_rate() > settings.max_cancel_rate:
            return False, 'cancel_rate_too_high'
        return True, 'ok'
